#!/bin/bash
# Enregistrement micro pour la campagne rue (lot D0 outillage, chantier
# "conversation en déambulation" -- dadou_robot_ros/docs/
# etude-declenchement-conversation.md §5.5/§7, "D0 -- Mesures & calibration" :
# enregistrements en conditions rue, rejoués ensuite dans le VAD de prod).
#
# QUOI : capture le micro EXACTEMENT au format du pipeline chat (16 kHz mono
#        16 bits, cf. vision.nodes.chat_node.MIC_SAMPLE_RATE) -- ces wav sont
#        ensuite rejoués TELS QUELS par `python -m vision.audio.vad_replay`,
#        qui REFUSE tout resampling (règle du projet : mesurer le MÊME code
#        que la prod, pas une approximation) -- un mauvais format ici rendrait
#        toute la campagne inexploitable.
# POURQUOI --max-file-time/--use-strftime plutôt qu'une boucle bash : ce sont
#        des options natives d'arecord (alsa-utils) qui gèrent le découpage
#        en segments horodatés SANS perte d'échantillon à la jointure -- une
#        boucle bash relançant arecord perdrait quelques ms à chaque
#        redémarrage de processus.
#
# Usage : ./enregistre-rue.sh [dossier_de_sortie] [duree_totale_s]
#   dossier_de_sortie  défaut ~/enregistrements-rue
#   duree_totale_s     défaut : illimité (Ctrl-C pour arrêter)
#   DEVICE             variable d'env, défaut "casque_mic" (alias ALSA du
#                      micro U20 câblé au casque, cf. mémoire de session
#                      "Audio Pi 5 -> mixette" -- alias par nom de carte, pas
#                      par numéro, qui peut changer d'un boot à l'autre)

set -u

OUT_DIR="${1:-$HOME/enregistrements-rue}"
DURATION="${2:-}"
DEVICE="${DEVICE:-casque_mic}"
# 60 s : taille de segment décidée dans la spec du lot D0 (fichiers assez
# courts pour être rejoués/écoutés un par un, sans perdre de continuité utile
# pour mesurer un taux de déclenchement par minute).
SEGMENT_S=60

mkdir -p "$OUT_DIR"

echo "=================================================================="
echo " RAPPEL (dispositif type tournage obligatoire, cf. etude-"
echo " declenchement-conversation.md §5.7) : l'affichage 'spectacle"
echo " enregistré' doit être visible aux abords AVANT de lancer cet"
echo " enregistrement -- pas de captation rue sans lui."
echo "=================================================================="
echo "Enregistrement -> $OUT_DIR (segments de ${SEGMENT_S}s, device=$DEVICE, 16 kHz mono 16 bits)"

# --use-strftime : chaque nouveau segment (toutes les SEGMENT_S secondes,
# cf. --max-file-time) applique strftime au nom de fichier au moment de
# l'ouverture -- exactement le nommage rue_YYYYmmdd_HHMMSS.wav demandé, sans
# compteur numérique séparé à gérer.
CMD=(arecord -D "$DEVICE" -f S16_LE -r 16000 -c 1 \
     --max-file-time "$SEGMENT_S" --use-strftime \
     "$OUT_DIR/rue_%Y%m%d_%H%M%S.wav")

if [ -n "$DURATION" ]; then
  echo "Durée totale bornée à ${DURATION}s."
  timeout "$DURATION" "${CMD[@]}"
else
  echo "Durée illimitée -- Ctrl-C pour arrêter proprement."
  "${CMD[@]}"
fi
