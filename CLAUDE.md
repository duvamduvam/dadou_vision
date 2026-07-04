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

## État (2026-07-04)

- Pi 5 provisionnable, webcam USB validée, pas de micro.
- Briques à recycler : `vision/ai/ai_interactions.py` (GPT-4o), `ai_audio.py` (TTS),
  `vision/db/chat_db.py`. Le reste : voir verdicts dans ARCHITECTURE.md.
- Lots : V0 socle sain → V1 suivi de personne (/vision/person) → V2 parole/émotions.
