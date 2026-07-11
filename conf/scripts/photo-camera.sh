#!/bin/bash
# photo-camera.sh — prend une photo avec la webcam du robot (à lancer SUR le Pi vision, hôte).
#
# QUOI : libère la caméra (arrêt de person_tracker dans le conteneur), capture une
# image via OpenCV — le MÊME outil que person_tracker, pas de dépendance ffmpeg
# (absente de l'hôte comme du conteneur) — la copie sur l'hôte, puis redémarre le
# conteneur pour restaurer le pipeline nominal.
#
# POURQUOI tuer person_tracker : la webcam UVC est ouverte en EXCLUSIF par le
#   tracker (aucune capture parallèle possible), et il ne publie aucun topic image
#   (choix assumé : pas de bande passante gâchée pour un flux que personne ne lit).
# POURQUOI docker restart plutôt que relancer le node à la main : l'entrypoint
#   (launch-ros-in-docker.sh) restaure l'état nominal complet — zéro risque de
#   dérive entre « pipeline relancé à la main » et « pipeline au boot ».
# POURQUOI 15 trames de chauffe : l'auto-exposition de cette webcam converge
#   lentement (piège déjà payé lors de la calibration LED côté robot) — les
#   premières trames sont sous-exposées, on ne garde que la dernière.
#
# Usage sur le Pi :  bash photo-camera.sh [fichier_sortie.jpg]
# Depuis le PC    :  ssh v 'bash /home/pi/ros2_ws/src/vision/conf/scripts/photo-camera.sh' \
#                    && scp v:photo-camera.jpg .
set -euo pipefail

CONTAINER=dadou-vision-container
# Nom fixe par défaut (écrasé à chaque prise) : c'est un outil de contrôle visuel
# ponctuel, pas une archive — un nom stable simplifie le scp depuis le PC.
OUT="${1:-/home/pi/photo-camera.jpg}"

# Le conteneur doit tourner : c'est lui qui a OpenCV, et c'est son entrypoint
# qui restaurera le pipeline à la fin.
if ! sudo docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null | grep -q true; then
    echo "ERREUR : conteneur $CONTAINER absent ou arrêté." >&2
    exit 1
fi

# Quoi qu'il arrive (capture ratée comprise), restaurer le pipeline en sortant :
# person_tracker est un service de perception permanent (consommé par gaze_follower
# côté robot), il ne doit JAMAIS rester coupé par oubli.
trap 'echo "Restauration du pipeline (docker restart)…"; sudo docker restart "$CONTAINER" >/dev/null' EXIT

echo "Libération de la caméra (arrêt de person_tracker)…"
sudo docker exec "$CONTAINER" bash -c 'pkill -f "[p]erson_tracker" || true'

# Attendre la libération réelle de /dev/video0 : pkill est asynchrone, et ouvrir
# la caméra encore tenue ferait échouer cap.read() de façon peu lisible.
for _ in $(seq 1 10); do
    sudo docker exec "$CONTAINER" bash -c 'fuser /dev/video0' >/dev/null 2>&1 || break
    sleep 0.5
done
if sudo docker exec "$CONTAINER" bash -c 'fuser /dev/video0' >/dev/null 2>&1; then
    echo "ERREUR : /dev/video0 toujours occupé après 5 s." >&2
    exit 1
fi

echo "Capture (15 trames de chauffe pour l'auto-exposition)…"
# docker exec -i : le script Python arrive par stdin (heredoc) — évite d'embarquer
# un .py dans l'image ou de jongler avec les quotes d'un python3 -c.
sudo docker exec -i "$CONTAINER" python3 - <<'EOF'
import sys
import cv2

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
ok, frame = False, None
for _ in range(15):
    ok, frame = cap.read()
cap.release()
if not ok or frame is None:
    sys.exit("ERREUR : lecture caméra impossible (cap.read() a échoué).")
cv2.imwrite("/tmp/photo-camera.jpg", frame)
print(f"Trame capturée : {frame.shape[1]}x{frame.shape[0]}")
EOF

sudo docker cp "$CONTAINER:/tmp/photo-camera.jpg" "$OUT"
echo "Photo : $OUT"
