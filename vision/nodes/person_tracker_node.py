#!/usr/bin/env python3
"""Node 'person_tracker' : webcam -> détection -> /vision/person (V1).

QUOI : node FIN (I/O seulement) — ouvre la caméra (open_camera de detector.py,
       PAS de duplication), lit une frame par tour de timer, détecte les
       personnes (MediaPipeDetector), choisit/lisse la cible (TargetPicker),
       publie geometry_msgs/PointStamped sur /vision/person si une cible est
       retenue. Toute la LOGIQUE vit ailleurs et est testée sans ROS :
       vision/tracking/detector.py (backend) et vision/tracking/target_picker.py
       (choix de cible + lissage, testé par vision/tests/unit/test_target_picker.py).
POURQUOI la cadence n'est pas fixée par le timer : la webcam Jieli plafonne à
       16,7 fps et l'inférence MediaPipe domine le budget de frame (mesuré au
       bench : ~24% CPU pour 16,7 Hz) — un timer à période courte (voir
       TIMER_PERIOD_SECONDS) ne fait que déclencher le tour suivant dès que le
       précédent est fini ; la cadence RÉELLE est bornée par cap.read()+detect(),
       pas par le timer. C'est le même principe que la boucle de mesure du bench
       (bench_detection.run_bench), volontairement gardé identique.
CONTRAT (ARCHITECTURE.md, ne pas dévier) : silence = personne perdue — on ne
       publie RIEN quand TargetPicker.update() renvoie None (pas de message
       "vide"), le consommateur (gaze_follower côté robot) gère son timeout,
       comme cmd_vel/twist_deadman.
"""
import os
import time

import cv2
import rclpy
from geometry_msgs.msg import PointStamped
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage

from vision.tracking.detector import MediaPipeDetector, open_camera
from vision.tracking.target_picker import TargetPicker

# Modèle téléchargé DANS L'IMAGE Docker (Dockerfile-arm, curl au build) : pas
# de dépendance réseau au démarrage du node. Chemin par défaut du paramètre
# ROS model_path — modifiable pour du dev PC hors conteneur.
DEFAULT_MODEL_PATH = "/home/ros2_ws/models/efficientdet_lite0.tflite"

# Bornée par la caméra/l'inférence (cf. docstring module) : ce n'est PAS la
# cadence réelle de publication, juste un plafond haut pour ne pas monopoliser
# le thread ROS en cas de lecture caméra anormalement rapide.
TIMER_PERIOD_SECONDS = 1.0 / 30.0

# Résolution de capture : identique au bench qui a validé le couple
# webcam/MJPG/CPU (640x480/30fps demandés, 16,7 fps réels côté Jieli).
CAPTURE_WIDTH = 640
CAPTURE_HEIGHT = 480
CAPTURE_FPS = 30

# frame_id du contrat ARCHITECTURE.md (topic /vision/person).
CAMERA_FRAME_ID = "camera"

# Retour vidéo (console de régie, cf. dadou_robot_ros docs/etude-interface-web.md
# W2 « MJPEG embarqué ») : la webcam étant tenue en EXCLUSIF par ce node, il est
# la seule source d'images possible — il republie donc ses trames en JPEG
# compressé (sensor_msgs/CompressedImage), throttlées et à qualité modérée :
# ~25 Ko/trame à 5 i/s ≈ 125 Ko/s sur le réseau, compatible WiFi/4G, là où du
# sensor_msgs/Image brut (640x480 BGR) ferait 4,6 Mo/s au même débit. Le
# web_bridge (Pi robot) sert ces octets TELS QUELS en MJPEG (camera_compressed).
VIDEO_TOPIC = "camera/image_raw/compressed"
VIDEO_FPS_DEFAULT = 5.0        # 0 = publication désactivée
VIDEO_JPEG_QUALITY = 70        # même qualité que _encode_jpeg côté web_bridge


class PersonTrackerStartupError(RuntimeError):
    """Levée quand le node ne peut pas démarrer proprement (modèle ou caméra
    manquants/invalides). Différencie un échec de démarrage EXPLICITE (déjà
    loggé via self.get_logger().error(...) avant d'être levée) d'un crash
    Python générique — main() l'attrape spécifiquement pour sortir proprement
    plutôt que de laisser une trace de crash-loop silencieuse."""


class PersonTrackerNode(Node):
    def __init__(self):
        super().__init__("person_tracker")

        # Paramètres ROS déclarés avec défauts (mission V1) : modifiables par
        # YAML/CLI sans toucher au code, ex. `ros2 run vision person_tracker
        # --ros-args -p camera_device:=/dev/video2`.
        self.declare_parameter("camera_device", "/dev/video0")
        self.declare_parameter("model_path", DEFAULT_MODEL_PATH)
        self.declare_parameter("score_threshold", 0.4)
        self.declare_parameter("ema_alpha", 0.4)
        self.declare_parameter("video_fps", VIDEO_FPS_DEFAULT)

        camera_device = self.get_parameter("camera_device").value
        model_path = self.get_parameter("model_path").value
        score_threshold = float(self.get_parameter("score_threshold").value)
        ema_alpha = float(self.get_parameter("ema_alpha").value)
        self._video_fps = float(self.get_parameter("video_fps").value)

        # Échec explicite et propre si le modèle est absent : mieux vaut un
        # message clair au démarrage ("chemin X introuvable, vérifier le
        # montage/le build Docker") qu'une exception mediapipe opaque plus
        # loin, ou pire, une crash-loop silencieuse du conteneur.
        if not os.path.isfile(model_path):
            # PIÈGE (trouvé au déploiement Pi 5, 2026-07-04) : RcutilsLogger
            # (rclpy) n'est PAS le module `logging` stdlib — .error()/.info()
            # ne prennent qu'UNE chaîne déjà formatée, pas de style printf
            # %s/args variadiques (ça lève un TypeError "takes 2 positional
            # arguments but N were given"). On formate donc avec des f-strings.
            self.get_logger().error(
                f"Modèle MediaPipe introuvable : {model_path} — le "
                "Dockerfile-arm est censé le télécharger au build (curl vers "
                "ce chemin). Vérifiez le paramètre model_path et l'image Docker."
            )
            raise PersonTrackerStartupError(f"modèle introuvable : {model_path}")

        try:
            self._detector = MediaPipeDetector(model_path, score_threshold=score_threshold)
        except Exception as exc:  # noqa: BLE001 - on veut un log explicite avant de propager
            self.get_logger().error(
                f"Échec d'initialisation MediaPipe (modèle={model_path}) : {exc}"
            )
            raise PersonTrackerStartupError("échec init MediaPipe") from exc

        try:
            self._cap = open_camera(
                camera_device, width=CAPTURE_WIDTH, height=CAPTURE_HEIGHT, fps=CAPTURE_FPS,
            )
        except RuntimeError as exc:
            self.get_logger().error(
                f"Caméra indisponible ({camera_device}) : {exc} — vérifiez que "
                "le périphérique existe (v4l2-ctl --list-devices) et que /dev "
                "est bien monté dans le conteneur."
            )
            raise PersonTrackerStartupError("caméra indisponible") from exc

        self._picker = TargetPicker(ema_alpha=ema_alpha)
        self._publisher = self.create_publisher(PointStamped, "/vision/person", 10)

        # Retour vidéo (cf. constantes VIDEO_*) : publisher créé SEULEMENT si
        # video_fps > 0 — même garantie structurelle que drive_enabled côté
        # web_bridge (aucune ligne de code ne PEUT publier d'image sinon).
        self._video_pub = None
        self._last_video_s = 0.0
        if self._video_fps > 0:
            self._video_pub = self.create_publisher(CompressedImage, VIDEO_TOPIC, 10)

        self._timer = self.create_timer(TIMER_PERIOD_SECONDS, self._on_timer)

        self.get_logger().info(
            f"person_tracker démarré (camera={camera_device}, model={model_path}, "
            f"score_threshold={score_threshold:.2f}, ema_alpha={ema_alpha:.2f}, "
            f"video_fps={self._video_fps:g}) -> /vision/person"
            + (f" + {VIDEO_TOPIC}" if self._video_pub is not None else "")
        )

    def _publish_video(self, frame) -> None:
        """Republie la trame courante en JPEG compressé, throttlée à video_fps.
        Publiée QUE quelqu'un regarde ou non (DDS ne transmet rien sans
        abonné : le coût réseau est nul sans console ouverte ; le coût CPU de
        l'encodage — ~2-3 ms à 5 i/s sur Pi 5 — est assumé en continu plutôt
        que de complexifier avec une détection d'abonnés)."""
        now = time.monotonic()
        if now - self._last_video_s < 1.0 / self._video_fps:
            return  # trame excédentaire : jetée AVANT tout encodage
        ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, VIDEO_JPEG_QUALITY])
        if not ok:
            return  # échec d'encodage ponctuel : on retentera à la prochaine trame
        self._last_video_s = now
        msg = CompressedImage()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = CAMERA_FRAME_ID
        msg.format = "jpeg"
        msg.data = jpeg.tobytes()
        self._video_pub.publish(msg)

    def _on_timer(self) -> None:
        ok, frame = self._cap.read()
        if not ok:
            # Échec de lecture PONCTUEL (pas au démarrage) : on log et on
            # attend le prochain tour plutôt que de crasher le node — une
            # webcam USB peut avoir un hoquet transitoire sans être hors service.
            self.get_logger().warning("Échec de lecture caméra (frame ignorée)")
            return

        # Retour vidéo AVANT la détection : la vidéo vit même si MediaPipe
        # échoue ou ne voit personne (deux services indépendants).
        if self._video_pub is not None:
            self._publish_video(frame)

        height, width = frame.shape[:2]
        detections = self._detector.detect(frame)
        result = self._picker.update(detections, width, height)

        if result is None:
            # Silence = personne perdue (contrat ARCHITECTURE.md) : ne rien publier.
            return

        azimuth, elevation, confidence = result
        msg = PointStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = CAMERA_FRAME_ID
        msg.point.x = azimuth
        msg.point.y = elevation
        msg.point.z = confidence
        self._publisher.publish(msg)

    def destroy_node(self):
        # Libère la caméra même si le node est détruit après une erreur avant
        # que self._cap n'existe (cas modèle manquant : on sort avant cap).
        cap = getattr(self, "_cap", None)
        if cap is not None:
            cap.release()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    try:
        node = PersonTrackerNode()
    except PersonTrackerStartupError:
        # Déjà loggé en détail dans __init__ (get_logger().error avant la
        # levée) : ici on se contente de sortir proprement, contexte ROS
        # fermé, code de retour non nul pour que systemd/docker sachent que
        # ça n'a pas tourné (mais SANS boucle de crash bruyante : un seul
        # message clair, pas une pile d'exception).
        rclpy.try_shutdown()
        raise SystemExit(1)

    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        # SIGINT ou arrêt du contexte par rclpy : chemin d'arrêt NORMAL (fin
        # de spectacle, docker stop), pas une erreur à tracer.
        pass
    finally:
        node.destroy_node()
        # try_shutdown (PAS shutdown) : le handler SIGINT de rclpy (Jazzy) a
        # souvent DÉJÀ fermé le contexte — shutdown() lèverait
        # « rcl_shutdown already called » (cf. chat_node.main, 2026-07-11).
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
