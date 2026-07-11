# Didier — vision (dadou_vision_ros)

Cerveau perceptif du robot de théâtre Didier, sur Pi 5 « vision » (alias ssh `v` et
`ai`, clé didier). **Lire ARCHITECTURE.md d'abord** : refonte complète décidée le
2026-07-04 (l'historique 2023-2025 = essais, instantané commité avant refonte).

## Règles

- **Dépôt GitHub PUBLIC** : jamais de secret dans le code, les tests, les commits.
  Tout secret vit dans `conf/secret` (gitignoré) ; `conf/secret.example` fait foi.
- La vision **publie des perceptions** (topics standard), ne commande JAMAIS les
  moteurs directement — la sécurité mouvement vit dans dadou_robot_ros (twist_mux,
  deadman, e-stop, validés physiquement).
- Mêmes standards que dadou_robot_ros : Jazzy/Docker, tests purs + CI, Ansible
  d'utils (groupe `vision`, hôte `ai`), commenter chaque action (quoi + pourquoi),
  commit avant refactoring, validation caméra pour tout comportement physique.
- Leçons Dockerfile du parc (2026-07-04, déjà payées 3 fois) : filtrer les paquets
  apt avec `sed 's/#.*$//' | xargs -r`, PAS de `pip install --upgrade pip`,
  `ENV PIP_BREAK_SYSTEM_PACKAGES=1`, sentinelle de build dans un dossier bind-mounté.

## État (2026-07-04 soir — V0 et V1 FAITS)

- **V0 déployé** : Pi 5 provisionné (install-pios-lite, service systemd `vision`
  autostart), image Jazzy buildée sur le Pi, heartbeat /vision/status.
- **V1 déployé et validé personne réelle** : person_tracker → /vision/person
  (~16 Hz, silence=perdu), MediaPipe EfficientDet-Lite0 (bench a22ca8b :
  16,7 Hz à 24 % CPU ; la webcam plafonne à 16,7 fps). Robuste en basse lumière.
  Consommateur côté robot : gaze_follower (dadou_robot_ros 55676b6, validé sim,
  reste le protocole caméra : direction_sign/amplitude/StringTime réel).
- Pièges consignés dans les commits/le code : logger rclpy ≠ logging stdlib
  (f-strings), purger build/ après changement numpy, mediapipe impose numpy<2
  + opencv-contrib (un seul opencv, libgl1 requis).
- **Photo de contrôle par la webcam** : `conf/scripts/photo-camera.sh` (à lancer
  sur le Pi ; validé 2026-07-11). La caméra étant tenue en exclusif par
  person_tracker (aucun topic image publié), le script arrête le tracker, capture
  via OpenCV (15 trames de chauffe — auto-exposition lente), puis `docker restart`
  restaure le pipeline nominal. Depuis le PC :
  `ssh v 'bash /home/pi/ros2_ws/src/vision/conf/scripts/photo-camera.sh' && scp v:photo-camera.jpg .`
- Prochains lots : V2 parole/émotions (micro à ACHETER d'abord ; briques
  ai/interactions+tts+chat_db prêtes) → V3 personnage autonome (ARCHITECTURE.md).
