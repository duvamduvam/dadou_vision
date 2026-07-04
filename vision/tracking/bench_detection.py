#!/usr/bin/env python3
"""Bench de détection de personne — choix du backend pour le lot V1 (person_tracker).

QUOI : mesure FPS / latence / (CPU et RAM en externe, cf. commentaires) / qualité
       des boîtes pour plusieurs backends CPU candidats, sur la webcam USB réelle
       du Pi 5 "vision".
POURQUOI : ARCHITECTURE.md fixe le critère V1 = /vision/person à 10-15 Hz avec
       marge CPU (le person_tracker_node tournera en continu pendant tout un
       spectacle, pas juste une démo de 30 s) ; il faut un chiffre mesuré sur le
       matériel réel, pas une estimation de datasheet.

Ce fichier est l'embryon du futur vision/tracking/detector.py de V1 : chaque
backend implémente la même interface minimale (Detector.detect(frame) ->
liste de Detection), pour rester interchangeable une fois le gagnant choisi.

NE PUBLIE RIEN SUR ROS, NE TOUCHE AUCUN MOTEUR : ce script fait de l'inférence
pure sur des frames OpenCV. Aucun import rclpy ici, volontairement.

Usage (dans le conteneur dadou-vision-container, PAS dans le venv d'export
YOLO du PC) :

    python3 bench_detection.py --backend mediapipe \
        --model /root/bench-v1/models/efficientdet_lite0.tflite \
        --camera /dev/video0 --out-dir /root/bench-v1/out

    python3 bench_detection.py --backend onnx-yolo \
        --model /root/bench-v1/models/yolo11n_640.onnx --input-size 640 \
        --camera /dev/video0 --out-dir /root/bench-v1/out

    python3 bench_detection.py --backend opencv-ssd \
        --model /root/bench-v1/models/ssd/mobilenet_iter_73000.caffemodel \
        --prototxt /root/bench-v1/models/ssd/deploy.prototxt \
        --camera /dev/video0 --out-dir /root/bench-v1/out

CPU% : mesurée EN DEHORS de ce script (docker stats --no-stream échantillonné
pendant l'exécution) car ajouter psutil juste pour le bench serait une
dépendance de plus à installer/retirer ; le script s'en tient à cv2 + numpy +
la lib du backend testé, comme le fera detector.py en prod.
RAM : le script lit lui-même /proc/self/status (VmHWM = pic de RSS) : aucune
dépendance requise, l'info est native Linux.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import statistics
import sys
import time
from pathlib import Path


# --------------------------------------------------------------------------
# Interface commune (préfigure detector.py de V1)
# --------------------------------------------------------------------------

@dataclasses.dataclass
class Detection:
    """Une boîte détectée, coordonnées en pixels dans l'image d'origine."""

    x1: float
    y1: float
    x2: float
    y2: float
    score: float
    label: str


class Detector:
    """Interface commune à tous les backends du bench.

    Volontairement minimaliste : un backend ne fait QUE de la détection sur une
    frame BGR (format natif OpenCV) et retourne des Detection déjà filtrées sur
    la catégorie "person" — le filtrage catégorie est laissé à chaque backend
    car le vocabulaire de classes diffère (COCO 80 classes pour YOLO/MediaPipe,
    VOC 21 classes pour MobileNet-SSD).
    """

    name: str = "base"

    def warmup(self, frame) -> None:
        """Appelé sur les frames de chauffe : certains runtimes (TFLite,
        onnxruntime) allouent leurs graphes/threads à la première inférence,
        ce qui fausserait la mesure de latence si on ne les exclut pas."""
        self.detect(frame)

    def detect(self, frame) -> list[Detection]:
        raise NotImplementedError


# --------------------------------------------------------------------------
# Backend 1 : MediaPipe ObjectDetector (EfficientDet-Lite0)
# --------------------------------------------------------------------------

class MediaPipeDetector(Detector):
    """ObjectDetector MediaPipe, filtré sur la catégorie COCO "person".

    PIÈGE (découvert en bench, 2026-07-04) : `pip3 install mediapipe` DOWNGRADE
    numpy de 2.x vers 1.26.4 et installe opencv-contrib-python 4.11 EN PLUS de
    opencv-python-headless déjà présent (conflit de dépendance signalé par pip :
    "opencv-python-headless 5.0.0.93 requires numpy>=2 ... but you have numpy
    1.26.4"). Sans conséquence tant que l'install reste éphémère (perdue au
    restart du conteneur), mais si mediapipe devient une dépendance PERMANENTE
    de conf/requirements.txt, il faudra vérifier que rien d'autre dans le
    conteneur (vision_status, ai/interactions.py, etc.) ne dépend de numpy>=2.
    """

    name = "mediapipe"

    def __init__(self, model_path: str, score_threshold: float = 0.4):
        # Import différé : ne doit pas être requis pour tester les autres backends.
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
            # IMAGE (pas VIDEO/LIVE_STREAM) : on appelle detect() de façon
            # synchrone frame par frame, comme les autres backends du bench —
            # comparaison à mode égal. En prod V1, passer en LIVE_STREAM avec
            # callback pourrait gagner un peu de latence (à réévaluer alors).
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


class MediaPipePoseDetector(Detector):
    """Bonus demandé par la mission : PoseLandmarker lite, mesuré séparément.

    Utile plus tard pour "où regarde la personne" (V1/V3), mais ce n'est PAS
    un détecteur de personnes au sens bbox — ici on encadre juste les
    landmarks visibles pour produire une bbox comparable au reste du bench.
    """

    name = "mediapipe-pose"

    def __init__(self, model_path: str):
        import mediapipe as mp
        from mediapipe.tasks.python import vision as mp_vision

        self._mp = mp
        base_options = mp.tasks.BaseOptions(model_asset_path=model_path)
        options = mp_vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=mp_vision.RunningMode.IMAGE,
            num_poses=1,
        )
        self._detector = mp_vision.PoseLandmarker.create_from_options(options)

    def detect(self, frame) -> list[Detection]:
        import cv2

        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._detector.detect(mp_image)
        out = []
        for pose in result.pose_landmarks:
            xs = [lm.x * w for lm in pose]
            ys = [lm.y * h for lm in pose]
            if not xs:
                continue
            out.append(Detection(
                x1=min(xs), y1=min(ys), x2=max(xs), y2=max(ys),
                score=1.0, label="pose",
            ))
        return out


# --------------------------------------------------------------------------
# Backend 2 : YOLO11n exporté en ONNX, inférence PURE onnxruntime (pas
# d'ultralytics sur le Pi). L'export se fait SUR LE PC, dans un venv jetable
# (ultralytics tire torch, ~2 Go, à ne jamais installer sur le Pi) :
#   pip install ultralytics && yolo export model=yolo11n.pt format=onnx imgsz=640
# puis scp du .onnx vers le Pi.
# --------------------------------------------------------------------------

class OnnxYoloDetector(Detector):
    """YOLO11n ONNX, pré/post-traitement fait main (letterbox + NMS).

    Pas d'ultralytics ici par contrainte de la mission (le Pi ne doit pas
    installer torch) : tout le pré/post-traitement qu'ultralytics fait
    d'habitude en interne est réécrit ici.
    """

    name = "onnx-yolo"
    COCO_PERSON_CLASS = 0  # classe 0 = "person" dans l'ordre COCO d'ultralytics

    def __init__(self, model_path: str, input_size: int = 640,
                 conf_threshold: float = 0.35, iou_threshold: float = 0.45):
        import onnxruntime as ort

        self.input_size = input_size
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        # CPUExecutionProvider explicite : sur un Pi sans GPU/NPU exposé à
        # onnxruntime, c'est le seul provider disponible, mais autant ne pas
        # laisser onnxruntime deviner et logguer un warning à chaque run.
        self._session = ort.InferenceSession(
            model_path, providers=["CPUExecutionProvider"],
        )
        self._input_name = self._session.get_inputs()[0].name

    def _letterbox(self, frame):
        """Redimensionne en conservant le ratio + padding gris, comme
        ultralytics le fait à l'entraînement — un simple resize déformerait
        les personnes et dégraderait la détection (bien documenté dans les
        issues ultralytics)."""
        import cv2
        import numpy as np

        h, w = frame.shape[:2]
        scale = self.input_size / max(h, w)
        nh, nw = int(round(h * scale)), int(round(w * scale))
        resized = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
        canvas = np.full((self.input_size, self.input_size, 3), 114, dtype=np.uint8)
        top = (self.input_size - nh) // 2
        left = (self.input_size - nw) // 2
        canvas[top:top + nh, left:left + nw] = resized
        return canvas, scale, left, top

    def detect(self, frame) -> list[Detection]:
        import cv2
        import numpy as np

        canvas, scale, pad_left, pad_top = self._letterbox(frame)
        blob = canvas[:, :, ::-1].astype(np.float32) / 255.0  # BGR->RGB, normalise
        blob = blob.transpose(2, 0, 1)[None, ...]  # HWC->CHW + batch

        raw = self._session.run(None, {self._input_name: blob})[0]
        # Sortie YOLO11 ultralytics : [1, 4+num_classes, num_anchors] (84, 8400
        # en imgsz=640 COCO). On transpose pour itérer par anchor.
        preds = raw[0].transpose(1, 0)  # [num_anchors, 84]

        boxes, scores = [], []
        for row in preds:
            cx, cy, w, h = row[:4]
            class_scores = row[4:]
            cls_id = int(np.argmax(class_scores))
            if cls_id != self.COCO_PERSON_CLASS:
                continue
            score = float(class_scores[cls_id])
            if score < self.conf_threshold:
                continue
            x1 = cx - w / 2
            y1 = cy - h / 2
            boxes.append([x1, y1, w, h])
            scores.append(score)

        out: list[Detection] = []
        if boxes:
            idxs = cv2.dnn.NMSBoxes(boxes, scores, self.conf_threshold, self.iou_threshold)
            for i in np.array(idxs).flatten() if len(idxs) else []:
                x1, y1, w, h = boxes[i]
                # Retire le padding puis remet à l'échelle image d'origine.
                x1 = (x1 - pad_left) / scale
                y1 = (y1 - pad_top) / scale
                x2 = x1 + w / scale
                y2 = y1 + h / scale
                out.append(Detection(x1=x1, y1=y1, x2=x2, y2=y2,
                                      score=scores[i], label="person"))
        return out


# --------------------------------------------------------------------------
# Backend 3 : baseline OpenCV DNN MobileNet-SSD (Caffe, chuanqi305) — zéro
# dépendance nouvelle, sert de plancher de comparaison.
# --------------------------------------------------------------------------

class OpenCVSSDDetector(Detector):
    """MobileNet-SSD (VOC 20 classes + background), classe "person" = index 15."""

    name = "opencv-ssd"
    VOC_PERSON_CLASS = 15

    def __init__(self, prototxt_path: str, model_path: str,
                 conf_threshold: float = 0.4):
        import cv2

        self.conf_threshold = conf_threshold
        self._net = cv2.dnn.readNetFromCaffe(prototxt_path, model_path)

    def detect(self, frame) -> list[Detection]:
        import cv2

        h, w = frame.shape[:2]
        # Réseau entraîné en 300x300, normalisation (127.5,127.5,127.5)/0.007843
        # spécifique à ce modèle (valeurs du repo chuanqi305, pas génériques).
        blob = cv2.dnn.blobFromImage(frame, 0.007843, (300, 300), (127.5, 127.5, 127.5))
        self._net.setInput(blob)
        detections = self._net.forward()

        out = []
        for i in range(detections.shape[2]):
            conf = float(detections[0, 0, i, 2])
            if conf < self.conf_threshold:
                continue
            cls_id = int(detections[0, 0, i, 1])
            if cls_id != self.VOC_PERSON_CLASS:
                continue
            x1 = detections[0, 0, i, 3] * w
            y1 = detections[0, 0, i, 4] * h
            x2 = detections[0, 0, i, 5] * w
            y2 = detections[0, 0, i, 6] * h
            out.append(Detection(x1=x1, y1=y1, x2=x2, y2=y2, score=conf, label="person"))
        return out


# --------------------------------------------------------------------------
# Boucle de mesure : identique pour tous les backends (protocole de la mission)
# --------------------------------------------------------------------------

def open_camera(device: str, width: int = 640, height: int = 480, fps: int = 30):
    """Ouvre la webcam en forçant MJPG.

    PIÈGE (confirmé sur cette webcam Jieli) : sans forcer explicitement le
    FOURCC, OpenCV/V4L2 peut négocier YUYV, qui plafonne le débit USB à
    ~5-25 fps selon la résolution (vu au v4l2-ctl --list-formats-ext : YUYV
    640x480 = 25 fps max annoncé, mais en pratique bien pire une fois le CPU
    sollicité par l'inférence, car YUYV non compressé sature l'USB2). MJPG
    est le mode natif de cette caméra à 640x480/30fps.
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


def percentile(values: list[float], pct: float) -> float:
    """p50/p95 sans dépendance numpy pour rester lisible (liste déjà petite, 100 val)."""
    if not values:
        return float("nan")
    s = sorted(values)
    k = (len(s) - 1) * (pct / 100.0)
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def peak_rss_mb() -> float:
    """Pic de RSS du process courant, lu dans /proc/self/status (VmHWM, en kB).

    Natif Linux, aucune dépendance — évite d'installer psutil juste pour le
    bench (voir note d'en-tête sur les dépendances volontairement minimales)."""
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmHWM:"):
                    return int(line.split()[1]) / 1024.0
    except OSError:
        pass
    return float("nan")


def run_bench(detector: Detector, cap, warmup_frames: int, measure_frames: int) -> dict:
    # Chauffe : exclue de la mesure. Premier appel = allocation de graphes
    # d'exécution (TFLite/onnxruntime), sinon la 1ère frame mesurée serait
    # un outlier énorme qui fausserait p95.
    for _ in range(warmup_frames):
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError("Échec lecture caméra pendant la chauffe")
        detector.warmup(frame)

    capture_times, total_times = [], []
    n_detections = []
    t_start = time.perf_counter()
    for _ in range(measure_frames):
        t0 = time.perf_counter()
        ok, frame = cap.read()
        t1 = time.perf_counter()
        if not ok:
            raise RuntimeError("Échec lecture caméra pendant la mesure")
        dets = detector.detect(frame)
        t2 = time.perf_counter()

        capture_times.append(t1 - t0)
        total_times.append(t2 - t0)
        n_detections.append(len(dets))
    elapsed = time.perf_counter() - t_start

    return {
        "backend": detector.name,
        "n_frames": measure_frames,
        "fps_mean": measure_frames / elapsed,
        "capture_ms_p50": percentile(capture_times, 50) * 1000,
        "capture_ms_p95": percentile(capture_times, 95) * 1000,
        "total_ms_p50": percentile(total_times, 50) * 1000,
        "total_ms_p95": percentile(total_times, 95) * 1000,
        "mean_detections_per_frame": statistics.mean(n_detections),
        "peak_rss_mb": peak_rss_mb(),
    }


def annotate_reference_image(detector: Detector, image_path: str, out_path: str) -> int:
    """Détecte sur l'image de référence (bus.jpg) et sauvegarde les boîtes
    dessinées, pour vérification humaine — pas d'IoU chiffré (mission)."""
    import cv2

    frame = cv2.imread(image_path)
    if frame is None:
        raise RuntimeError(f"Impossible de lire {image_path}")
    dets = detector.detect(frame)
    for d in dets:
        cv2.rectangle(frame, (int(d.x1), int(d.y1)), (int(d.x2), int(d.y2)),
                       (0, 255, 0), 2)
        cv2.putText(frame, f"{d.label} {d.score:.2f}", (int(d.x1), max(0, int(d.y1) - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    cv2.imwrite(out_path, frame)
    return len(dets)


def build_detector(args) -> Detector:
    if args.backend == "mediapipe":
        return MediaPipeDetector(args.model)
    if args.backend == "mediapipe-pose":
        return MediaPipePoseDetector(args.model)
    if args.backend == "onnx-yolo":
        return OnnxYoloDetector(args.model, input_size=args.input_size)
    if args.backend == "opencv-ssd":
        return OpenCVSSDDetector(args.prototxt, args.model)
    raise ValueError(f"Backend inconnu : {args.backend}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", required=True,
                         choices=["mediapipe", "mediapipe-pose", "onnx-yolo", "opencv-ssd"])
    parser.add_argument("--model", required=True, help="chemin du modèle (.tflite/.task/.onnx/.caffemodel)")
    parser.add_argument("--prototxt", help="requis pour opencv-ssd")
    parser.add_argument("--input-size", type=int, default=640, help="requis pour onnx-yolo")
    parser.add_argument("--camera", default="/dev/video0")
    parser.add_argument("--warmup-frames", type=int, default=20)
    parser.add_argument("--measure-frames", type=int, default=100)
    parser.add_argument("--ref-image", default=None, help="bus.jpg pour le contrôle qualité")
    parser.add_argument("--out-dir", default=".")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[bench] backend={args.backend} construction du détecteur...", file=sys.stderr)
    detector = build_detector(args)

    result = {"backend": args.backend, "input_size": args.input_size}

    if args.ref_image:
        print("[bench] contrôle qualité sur l'image de référence...", file=sys.stderr)
        out_img = str(out_dir / f"quality_{args.backend}.jpg")
        n = annotate_reference_image(detector, args.ref_image, out_img)
        result["quality_check_image"] = out_img
        result["quality_check_n_detections"] = n
        print(f"[bench] {n} détection(s) -> {out_img}", file=sys.stderr)

    print(f"[bench] ouverture caméra {args.camera}...", file=sys.stderr)
    cap = open_camera(args.camera)
    try:
        print(f"[bench] chauffe ({args.warmup_frames} frames)...", file=sys.stderr)
        # warmup fait dans run_bench
        print(f"[bench] mesure ({args.measure_frames} frames)...", file=sys.stderr)
        result.update(run_bench(detector, cap, args.warmup_frames, args.measure_frames))
    finally:
        cap.release()

    out_json = out_dir / f"result_{args.backend}_{args.input_size}.json"
    out_json.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    print(f"[bench] résultat -> {out_json}", file=sys.stderr)


if __name__ == "__main__":
    main()
