#!/bin/bash
# Calibration hauteur de silhouette (/vision/person_box, champ y) -> mètres
# réels (lot D0 outillage, cf. dadou_robot_ros/docs/
# etude-declenchement-conversation.md §5.2/§8/§7 : "calibration hauteur de
# silhouette -> mètres (1,2 / 2,4 / 3,6 m, adulte ET enfant)").
#
# QUOI : échantillonne 5 s le topic /vision/person_box (PointStamped : point.y
#        = hauteur de silhouette, proxy monoculaire EMA, cf. §3 du plan),
#        calcule moyenne et écart-type, ajoute une ligne au CSV cumulatif de
#        campagne. À LANCER DANS LE CONTENEUR vision (ros2 topic echo exige
#        l'environnement ROS sourcé -- ce script fait le sourcing lui-même,
#        MÊME motif que conf/scripts/launch-ros-in-docker.sh) :
#          docker exec -it dadou-vision-container \
#            ./conf/scripts/calibre-distance.sh 1.2
#
# POURQUOI adulte ET enfant (rappel du protocole ci-dessous) : le proxy
#        hauteur de silhouette est BIAISÉ pour les enfants (une même
#        distance réelle donne une hauteur mesurée plus petite qu'un adulte)
#        -- cf. plan §5.2/§8 : sans ce rappel, une calibration faite
#        uniquement sur adultes fausserait la distance estimée pour tous les
#        enfants rencontrés en rue (cas fréquent, cf. §4.3/§4.7 du plan).
#
# Usage : calibre-distance.sh <distance_en_m> [dossier_de_sortie]
#   distance_en_m      OBLIGATOIRE -- distance RÉELLE mesurée au sol entre le
#                      sujet et la caméra pendant l'échantillonnage
#   dossier_de_sortie  défaut ~/mesures-d0 (fichier calibration-distance.csv)
#
# PROTOCOLE : mesurer à 1,2 / 2,4 / 3,6 m (zones de Hall, cf. §4.1 du plan),
# ET pour un ADULTE ET pour un ENFANT si possible -- relancer ce script une
# fois par (distance, gabarit) ; les lignes s'accumulent dans le même CSV.

set -u

if [ -z "${1:-}" ]; then
  echo "Usage : $0 <distance_en_m> [dossier_de_sortie]" >&2
  echo "Protocole : mesurer à 1,2 / 2,4 / 3,6 m, ADULTE ET ENFANT si" \
       "possible (proxy hauteur de silhouette biaisé pour les enfants," \
       "cf. etude-declenchement-conversation.md §5.2/§8)." >&2
  exit 2
fi

DISTANCE_M="$1"
OUT_DIR="${2:-$HOME/mesures-d0}"
mkdir -p "$OUT_DIR"
CSV="$OUT_DIR/calibration-distance.csv"

# Sourcing de l'environnement ROS -- MÊME motif que
# conf/scripts/launch-ros-in-docker.sh (ROS_DISTRO fourni par l'image, pas
# codé en dur) ; best-effort sur le setup.bash de l'espace d'install (peut
# être absent selon l'état du build, cf. sentinelle CHANGE du même script).
source /opt/ros/"${ROS_DISTRO}"/setup.sh
[ -f /home/ros2_ws/install/setup.bash ] && source /home/ros2_ws/install/setup.bash

echo "Échantillonnage 5 s de /vision/person_box à ${DISTANCE_M} m..."
RAW="$(timeout 5 ros2 topic echo /vision/person_box --csv 2>/dev/null)"

if [ -z "$RAW" ]; then
  echo "Aucun échantillon reçu sur /vision/person_box -- person_tracker_node" \
       "est-il lancé et une personne bien visible par la caméra ?" >&2
  exit 1
fi

# Colonnes CSV de geometry_msgs/msg/PointStamped (ros2 topic echo --csv
# aplatit les champs dans l'ordre du message) : sec,nanosec,frame_id,x,y,z --
# le champ y (5e colonne) est la hauteur de silhouette [0..1], cf. §3 du plan
# ("hauteur de silhouette (proxy monoculaire, EMA)").
STATS="$(echo "$RAW" | awk -F',' '
  { y = $5; sum += y; sumsq += y * y; n++ }
  END {
    if (n == 0) { print "0;0;0"; exit }
    mean = sum / n
    var = (sumsq / n) - (mean * mean)
    if (var < 0) var = 0  # garde-fou arrondi flottant : jamais négatif en théorie
    printf "%.4f;%.4f;%d", mean, sqrt(var), n
  }')"

if [ ! -f "$CSV" ]; then
  echo "date;distance_m;y_moyen;y_ecart_type;n_echantillons" > "$CSV"
fi

DATE="$(date -Iseconds)"
LINE="$DATE;$DISTANCE_M;$STATS"
echo "$LINE" >> "$CSV"
echo "Ajouté -> $CSV"
echo "  $LINE"
