"""Launch V1/V2 : heartbeat (vision_status) + suivi de personne
(person_tracker) + conversation temps réel (chat, V2 — OFF par défaut).

    ros2 launch vision vision.launch.py
    ros2 launch vision vision.launch.py score_threshold:=0.5 ema_alpha:=0.3
    ros2 launch vision vision.launch.py chat_enabled:=true

POURQUOI un launch file plutôt que deux `ros2 run ... &` dans
conf/scripts/launch-ros-in-docker.sh (option envisagée par la mission V1) :
un seul process `ros2 launch` supervise proprement l'arrêt de tous les nodes
(un SIGINT sur le conteneur arrête les deux proprement, pas de wait manuel à
bash à maintenir), et les paramètres de person_tracker (camera_device,
model_path, score_threshold, ema_alpha) sont déclarés ici avec leurs défauts
plutôt qu'éparpillés en arguments CLI dans le script bash. Pattern déjà en
place côté robot pour la chaîne roues (conf/ros2_dependencies/robot_drive/
launch/drive.launch.py) : même choix pour rester cohérent dans le parc.

Défauts alignés sur person_tracker_node.py (DEFAULT_MODEL_PATH etc.) — s'ils
divergent un jour, ce fichier prime au runtime (les défauts du node ne
servent que pour un lancement direct hors launch, ex. tests manuels).

POURQUOI chat_enabled=false PAR DÉFAUT (contrairement à person_tracker,
toujours lancé) : person_tracker est le SERVICE PRINCIPAL de ce dépôt
(perception, toujours utile) ; le node chat consomme un micro/haut-parleur
physiques et un budget LLM (API payante via OpenRouter) — il ne doit
s'activer qu'explicitement pour une séquence de spectacle qui en a besoin,
jamais par défaut au démarrage du conteneur.

POURQUOI aucun paramètre chat_* (llm_model, whisper_model...) n'est exposé
ICI contrairement à camera_device/model_path pour person_tracker : ces
valeurs viennent TOUTES de vision_config.config, lu directement par
ChatNode.__init__ via vision.nodes._chat_wiring.default_chat_parameters —
les redéclarer ici en DeclareLaunchArgument imposerait soit de dupliquer les
défauts en dur (interdit par vision_config.py : "aucun autre fichier ne doit
coder une valeur par défaut en dur"), soit de les laisser vides par défaut
("") ce qui CASSERAIT le node au démarrage pour les paramètres non-string
(refresh_ms/beep_seconds : ROS2 rejette un override de type incompatible
avec le type déclaré côté node, ex. chaîne vide face à un entier). Pour un
réglage ponctuel, le pattern déjà établi dans ce dépôt (cf. docstring de
person_tracker_node.py) est `ros2 run vision chat --ros-args -p
whisper_model:=tiny` — un lancement direct hors launch, pas un argument de
ce fichier.
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    camera_device = LaunchConfiguration("camera_device")
    model_path = LaunchConfiguration("model_path")
    score_threshold = LaunchConfiguration("score_threshold")
    ema_alpha = LaunchConfiguration("ema_alpha")
    video_fps = LaunchConfiguration("video_fps")
    chat_enabled = LaunchConfiguration("chat_enabled")

    return LaunchDescription([
        DeclareLaunchArgument(
            "camera_device", default_value="/dev/video0",
            description="Périphérique V4L2 de la webcam USB (Jieli validée le 2026-07-04)",
        ),
        DeclareLaunchArgument(
            "model_path",
            default_value="/home/ros2_ws/models/efficientdet_lite0.tflite",
            description="Modèle MediaPipe EfficientDet-Lite0 int8 (téléchargé DANS l'image Docker, cf. Dockerfile-arm)",
        ),
        DeclareLaunchArgument(
            "score_threshold", default_value="0.4",
            description="Seuil de confiance MediaPipe pour retenir une détection 'person'",
        ),
        DeclareLaunchArgument(
            "ema_alpha", default_value="0.4",
            description="Coefficient de lissage exponentiel azimut/élévation (vision/tracking/target_picker.py)",
        ),
        DeclareLaunchArgument(
            "video_fps", default_value="5.0",
            description="Cadence (i/s) du retour vidéo JPEG camera/image_raw/compressed"
                        " pour la console de régie (web_bridge) — 0 = désactivé",
        ),
        DeclareLaunchArgument(
            "chat_enabled", default_value="false",
            description="Active le node de conversation temps réel (micro -> LLM -> voix) — OFF par défaut, cf. docstring de module",
        ),

        # V0 : heartbeat, preuve de vie ROS bout-en-bout (déjà validé sur le
        # Pi 5, gardé tel quel — /vision/status ne doit jamais disparaître,
        # même si person_tracker échoue à démarrer faute de caméra/modèle).
        Node(package="vision", executable="vision_status", name="vision_status"),

        # V1 : suivi de personne -> /vision/person (silence = personne perdue,
        # cf. ARCHITECTURE.md et person_tracker_node.py).
        Node(
            package="vision",
            executable="person_tracker",
            name="person_tracker",
            parameters=[{
                "camera_device": camera_device,
                "model_path": model_path,
                "score_threshold": score_threshold,
                "ema_alpha": ema_alpha,
                "video_fps": video_fps,
            }],
        ),

        # V2 : conversation temps réel -> topics face/animation existants du
        # robot (cf. ARCHITECTURE.md, chat_node.py). Lancé UNIQUEMENT si
        # chat_enabled:=true — sinon ce Node n'apparaît même pas dans la
        # description résolue (IfCondition), pas de tentative de démarrage
        # avortée qui polluerait les logs. Aucun paramètre transmis : le node
        # construit ses propres défauts depuis vision_config.config (cf.
        # POURQUOI en tête de fichier) — un réglage ponctuel passe par
        # `ros2 run vision chat --ros-args -p <param>:=<valeur>`.
        Node(
            package="vision",
            executable="chat",
            name="chat",
            condition=IfCondition(chat_enabled),
        ),
    ])
