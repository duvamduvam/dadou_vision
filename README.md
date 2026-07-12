Dadou Vision

## Outillage D0 conversation

Outils du lot D0 (mesures & calibration) du chantier "conversation en
déambulation" (cf. `../dadou_robot_ros/docs/etude-declenchement-conversation.md`) :

- **Topic d'état du chat** `chat_state` (StringTime latché, `listening` /
  `thinking` / `speaking` / `off`) publié par `chat_node` — abonnez-vous-y
  pour observer l'état interne de la conversation (régie, télédiagnostic,
  futur `engagement_node`) : `ros2 topic echo /chat_state`.
- **Rejeu VAD sur enregistrement** (mesure le taux de déclenchement du VAD de
  prod sur du son capté en rue, sans resampling) :
  `python -m vision.audio.vad_replay fichier.wav [autres.wav...]`.
- **Enregistrement micro rue** (16 kHz mono 16 bits, segments de 60 s) :
  `conf/scripts/enregistre-rue.sh [dossier_de_sortie] [duree_totale_s]`.
- **Mesure CPU/RAM en conversation** (échantillonnage 1 Hz vers un CSV,
  host ou conteneur) : `conf/scripts/mesure-cpu-conversation.sh [duree_s] [dossier_de_sortie]`.
- **Calibration distance** (hauteur de silhouette `/vision/person_box` ->
  mètres, à lancer dans le conteneur vision) :
  `conf/scripts/calibre-distance.sh <distance_en_m> [dossier_de_sortie]`.
