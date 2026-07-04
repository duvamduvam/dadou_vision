"""Détection de personnes — interface commune + backend de PRODUCTION.

QUOI : extrait de vision/tracking/bench_detection.py les deux éléments dont
       person_tracker_node (V1) a besoin :
         - l'interface commune Detection / Detector (le bench la définissait
           déjà pour comparer ses 4 backends à interface égale) ;
         - MediaPipeDetector, le backend GAGNANT du bench sur le Pi 5 réel
           (commit a22ca8b : EfficientDet-Lite0 int8, 16,7 Hz à ~24 % CPU,
           RunningMode.IMAGE — la webcam Jieli plafonne de toute façon à
           16,7 fps, donc RunningMode.LIVE_STREAM n'apporterait rien ici) ;
         - open_camera, l'ouverture MJPG de la webcam, identique en bench et
           en prod (même piège YUYV/USB2, cf. docstring ci-dessous).
POURQUOI un module séparé plutôt que de laisser bench_detection.py tout
       porter : le bench doit rester exécutable tel quel (backends YOLO/SSD/
       pose gardés pour comparaison future) SANS dupliquer le code que
       person_tracker_node exécute réellement en spectacle — une seule
       source de vérité pour l'interface et le backend retenu. bench_detection
       importe maintenant Detection/Detector/MediaPipeDetector/open_camera
       d'ici au lieu de les redéfinir.

Import mediapipe/cv2 volontairement DIFFÉRÉ (dans les méthodes, pas en tête de
module) : ce module doit rester importable (dataclasses/logging seulement au
niveau module) même sur une machine SANS mediapipe/opencv installés — c'est
ce qui permet à vision/tracking/target_picker.py et à ses tests unitaires de
ne rien tirer de lourd, et à ce module lui-même d'être importé sans planter
par du code qui n'a besoin que de la dataclass Detection (aucun cas actuel,
mais gardé en tête pour la prochaine session).
"""
from __future__ import annotations

import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class Detection:
    """Une boîte détectée, coordonnées en PIXELS dans l'image d'origine (pas
    normalisées : c'est target_picker.py qui fait la conversion en azimut/
    élévation normalisés, cf. contrat ARCHITECTURE.md)."""

    x1: float
    y1: float
    x2: float
    y2: float
    score: float
    label: str


class Detector:
    """Interface commune à tous les backends (bench ET prod).

    Volontairement minimaliste : un backend ne fait QUE de la détection sur
    une frame BGR (format natif OpenCV) et retourne des Detection déjà
    filtrées sur la catégorie "person" — le filtrage catégorie est laissé à
    chaque backend car le vocabulaire de classes diffère (COCO 80 classes
    pour YOLO/MediaPipe, VOC 21 classes pour MobileNet-SSD).
    """

    name: str = "base"

    def warmup(self, frame) -> None:
        """Appelé sur les frames de chauffe : certains runtimes (TFLite,
        onnxruntime) allouent leurs graphes/threads à la première inférence,
        ce qui fausserait la mesure de latence si on ne les exclut pas.
        En prod (person_tracker_node), sert aussi à absorber ce coût de
        démarrage AVANT le premier tour de boucle publié."""
        self.detect(frame)

    def detect(self, frame) -> list[Detection]:
        raise NotImplementedError


class MediaPipeDetector(Detector):
    """ObjectDetector MediaPipe, filtré sur la catégorie COCO "person".

    Backend retenu pour la PRODUCTION (person_tracker_node) après bench sur
    le Pi 5 réel le 2026-07-04 : 16,7 Hz à ~24 % CPU, dans le budget V1
    (10-15 Hz visé, webcam plafonnée à 16,7 fps de toute façon).

    PIÈGE mediapipe (découvert en bench, désormais PERMANENT puisque
    mediapipe est une dépendance officielle de conf/requirements.txt) :
    `pip3 install mediapipe` DOWNGRADE numpy de 2.x vers 1.26.4 et installe
    opencv-contrib-python (non-headless, a besoin de libgl1) qui entre en
    CONFLIT DE FICHIERS avec opencv-python-headless si les deux sont
    installés. Résolution retenue (cf. conf/requirements.txt) : on retire
    opencv-python-headless du requirements et on épingle numpy<2 — un seul
    opencv dans le conteneur (celui apporté transitivement par mediapipe),
    et libgl1 ajouté à conf/packages-docker.txt pour cet opencv non-headless.
    """

    name = "mediapipe"

    def __init__(self, model_path: str, score_threshold: float = 0.4):
        # Import différé : ne doit pas être requis pour tester les autres
        # backends du bench, ni pour importer ce module sans mediapipe installé.
        import mediapipe as mp
        from mediapipe.tasks.python import vision as mp_vision

        self._mp = mp
        # PIÈGE : BaseOptions vit sous mp.tasks.BaseOptions (pas
        # mediapipe.tasks.python.core.BaseOptions, qui n'existe pas — le
        # sous-module s'appelle "base_options", pas la classe elle-même).
        base_options = mp.tasks.BaseOptions(model_asset_path=model_path)
        options = mp_vision.ObjectDetectorOptions(
            base_options=base_options,
            score_threshold=score_threshold,
            # IMAGE (pas VIDEO/LIVE_STREAM) : appel synchrone frame par frame.
            # Choix conservé du bench (comparaison à mode égal entre backends)
            # ET valable en prod : la webcam plafonne à 16,7 fps, LIVE_STREAM
            # ne ferait gagner de la latence que si la capture était le goulot
            # d'étranglement plus lent que l'inférence, ce qui n'est pas le cas
            # ici (mesuré : c'est l'inférence qui domine le budget de frame).
            running_mode=mp_vision.RunningMode.IMAGE,
        )
        self._detector = mp_vision.ObjectDetector.create_from_options(options)

    def detect(self, frame) -> list[Detection]:
        import cv2

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._detector.detect(mp_image)
        out = []
        for det in result.detections:
            cat = det.categories[0]
            if cat.category_name != "person":
                continue
            bb = det.bounding_box
            out.append(Detection(
                x1=bb.origin_x, y1=bb.origin_y,
                x2=bb.origin_x + bb.width, y2=bb.origin_y + bb.height,
                score=cat.score, label="person",
            ))
        return out


def open_camera(device: str, width: int = 640, height: int = 480, fps: int = 30):
    """Ouvre la webcam en forçant MJPG.

    PIÈGE (confirmé sur la webcam Jieli du Pi 5, bench 2026-07-04) : sans
    forcer explicitement le FOURCC, OpenCV/V4L2 peut négocier YUYV, qui
    plafonne le débit USB à ~5-25 fps selon la résolution (v4l2-ctl
    --list-formats-ext : YUYV 640x480 = 25 fps max annoncé, mais en pratique
    bien pire une fois le CPU sollicité par l'inférence, car YUYV non
    compressé sature l'USB2). MJPG est le mode natif de cette caméra à
    640x480/30fps — c'est ce mode que person_tracker_node utilise en prod,
    identique au bench qui l'a validé.
    """
    import cv2

    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    if not cap.isOpened():
        raise RuntimeError(f"Impossible d'ouvrir la caméra {device}")
    return cap
