#!/bin/bash
# Mesure CPU/RAM en conversation complète (lot D0 outillage, cf.
# dadou_robot_ros/docs/etude-declenchement-conversation.md §5.6/§7 : "D0
# mesure le CPU réel en conversation complète (détection + whisper + piper),
# puis on ajoute E2 (visage) et on re-mesure -- accélérateur (Hailo/Coral)
# SEULEMENT si la mesure le condamne").
#
# QUOI : échantillonne 1x/s les processus pertinents (détection vision, chat,
#        arecord, piper) pendant N secondes, une ligne CSV par PROCESSUS par
#        seconde, + température Pi + charge globale sur la même ligne.
# POURQUOI un motif grep large (python3|arecord|piper|...) plutôt qu'un PID
#        fixé au démarrage : les nodes ROS sont tous des process python3, et
#        whisper/piper peuvent être relancés en cours de mesure (redémarrage
#        d'un node) -- suivre par NOM plutôt que par PID capte ces relances.
# POURQUOI best-effort (pas de set -e, vcgencmd optionnel) : ce script doit
#        tourner IDENTIQUEMENT sur le host Pi (vcgencmd présent) et dans le
#        conteneur (vcgencmd absent) -- même philosophie que
#        dadou_robot_ros/conf/scripts/collect-incident.sh : une section
#        indisponible reste vide, jamais bloquante.
#
# Usage : ./mesure-cpu-conversation.sh [duree_s] [dossier_de_sortie]
#   duree_s            défaut 120
#   dossier_de_sortie  défaut ~/mesures-d0

set -u

DURATION="${1:-120}"
OUT_DIR="${2:-$HOME/mesures-d0}"
mkdir -p "$OUT_DIR"

STAMP="$(date +%Y%m%d_%H%M%S)"
CSV="$OUT_DIR/cpu-conversation-$STAMP.csv"

# Motif des processus pertinents à la conversation complète (cf. docstring
# ci-dessus) : python3 couvre tous les nodes ROS (détection MediaPipe, chat,
# person_tracker...), arecord/piper sont les sous-process audio.
PATTERN='python3|arecord|piper|chat|person_tracker|vision'

echo "t_s;pid;pcpu;pmem;comm;args;temp_c;loadavg_1min" > "$CSV"
echo "Mesure CPU/RAM -> $CSV (${DURATION}s, motif: $PATTERN)"

t=0
while [ "$t" -lt "$DURATION" ]; do
  # Température Pi : absente en conteneur ou sur un PC de dev -- champ vide,
  # PAS d'échec du script (2>/dev/null + fallback vide).
  temp="$(vcgencmd measure_temp 2>/dev/null | grep -oE '[0-9.]+' || true)"
  load="$(awk '{print $1}' /proc/loadavg 2>/dev/null || true)"

  # ps -eo ... filtré par le motif : une ligne par PROCESSUS correspondant,
  # "grep -v grep" retire la commande grep elle-même du résultat (piège
  # classique de ce genre de filtrage).
  ps -eo pid,pcpu,pmem,comm,args --no-headers | grep -E "$PATTERN" | grep -v grep |
    while IFS= read -r line; do
      pid="$(awk '{print $1}' <<<"$line")"
      pcpu="$(awk '{print $2}' <<<"$line")"
      pmem="$(awk '{print $3}' <<<"$line")"
      comm="$(awk '{print $4}' <<<"$line")"
      # args = reste de la ligne (peut contenir des espaces) ; ';' interdit
      # dans un champ CSV -- remplacé par ',' plutôt qu'échappé (le format
      # de sortie reste simple à parser en awk/pandas ensuite).
      args="$(cut -d' ' -f5- <<<"$line" | tr ';' ',')"
      echo "$t;$pid;$pcpu;$pmem;$comm;$args;$temp;$load" >> "$CSV"
    done

  sleep 1
  t=$((t + 1))
done

echo "Mesure terminée -> $CSV"

# Résumé : moyenne/max de %CPU par NOM de processus (pas par PID -- un
# process relancé en cours de mesure change de PID mais garde son nom, cf.
# POURQUOI ci-dessus).
echo "--- Résumé (moyenne/max %CPU par processus, sur ${DURATION}s) ---"
awk -F';' 'NR>1 {sum[$5]+=$3; if ($3>max[$5]) max[$5]=$3; n[$5]++}
           END {for (c in sum) printf "%-20s moyenne=%.1f%% max=%.1f%% (n=%d echantillons)\n", c, sum[c]/n[c], max[c], n[c]}' \
  "$CSV" | sort
