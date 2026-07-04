# Architecture cible — dadou_vision_ros (refonte 2026-07)

Cerveau perceptif de Didier, sur **Raspberry Pi 5 (8 Go, hostname `vision`, Pi OS Lite
trixie)**. Remplace la « suite d'essais » 2023-2025 (état des lieux du 2026-07-04 :
3 briques réutilisables, le reste refait).

## Principes (non négociables, hérités du parc)

1. **Mêmes standards que dadou_robot_ros** : ROS 2 Jazzy en Docker, provisioning
   Ansible d'utils, CI GitHub Actions minimale, tests unitaires purs (sans matériel),
   `ROS_DOMAIN_ID` 42 (prod) / 43 (sim).
2. **Interfaces ROS standard** — pas de nouveau format maison. La vision *publie des
   perceptions*, le robot *décide des mouvements* : aucune commande moteur ne part
   d'ici, tout passe par le twist_mux/deadman du robot (sécurité déjà validée).
3. **Jamais de secret dans le code ni le dépôt** (GitHub public) : tout vient de
   `conf/secret` (gitignoré), chargé par un unique module config. `conf/secret.example`
   documente les clés attendues.
4. Chaque lot laisse un système **démontrable** (règle : Didier jouable à chaque étape).

## Structure cible

```
dadou_vision_ros/
├── ARCHITECTURE.md / CLAUDE.md      # ce document + passation sessions
├── conf/
│   ├── requirements.txt             # MINIMAL (openai, opencv-headless, sounddevice, sqlobject…)
│   ├── packages-docker.txt          # apt du conteneur (filtré par sed, cf. leçons Dockerfiles)
│   ├── secret.example               # modèle sans valeurs (chatgpt_key=, google_cloud=…)
│   ├── docker/arm/                  # FROM ros:jazzy-ros-base — calqué sur le robot,
│   │                                #  AVEC les leçons: sed s/#.*// packages, PAS de pip
│   │                                #  upgrade, PIP_BREAK_SYSTEM_PACKAGES=1, entrypoint
│   │                                #  sentinelle vision/CHANGE
│   └── ros2/                        # package ament "vision" (PAS "robot") : setup.py propre
├── vision/
│   ├── nodes/                       # fins : I/O ROS seulement, zéro logique
│   │   ├── person_tracker_node.py   # V1 — caméra → /vision/person
│   │   └── chat_node.py             # V2 — micro → GPT → TTS + topics face/audio
│   ├── tracking/                    # V1 — logique PURE testable :
│   │   ├── detector.py              #   backend de détection interchangeable
│   │   └── target_picker.py         #   choix cible + lissage + bbox→angle
│   ├── ai/                          # V2 — briques recyclées et durcies :
│   │   ├── interactions.py          #   GPT (parsing JSON structuré, plus d'ast.literal_eval)
│   │   ├── tts.py                   #   TTS OpenAI streaming + effet robot (gardé tel quel)
│   │   └── stt.py                   #   à retrancher : faster-whisper local vs API (bench V2)
│   ├── db/chat_db.py                # gardé (SQLite conversations)
│   └── tests/unit/                  # purs, lancés par la CI
└── json/, medias/                   # épurés (les configs lumières copiées du robot : supprimées)
```

Supprimé à la refonte : MQTT (essais), torch/whisper/blinka/pysftp (jamais utilisés),
tests lumières/neopixel (copiés du robot), `conf/ros2_dependencies/` dupliqué (le vrai
`robot_interfaces` arrive par le rsync ansible comme sur les autres machines),
`robot` symlink (dépendance à retirer du code), venv commité sur disque.

## Interfaces ROS (le contrat avec le robot)

| Topic | Type | Sens | Contenu |
|---|---|---|---|
| `/vision/person` | `geometry_msgs/msg/PointStamped` | vision → robot | x = azimut normalisé [-1..1] (0 = face caméra), y = élévation, z = confiance [0..1]. 10-15 Hz. Silence = personne perdue (le consommateur gère son timeout, comme cmd_vel). |
| `/face`, `/audio` | `robot_interfaces/StringTime` | vision → robot | V2 : émotions et parole via les topics EXISTANTS du robot (lights_node/audio_node) — zéro modif côté robot. |

Côté **robot** (chantier séparé, dadou_robot_ros) : un node `gaze_follower`
/vision/person → `/neck/position` (**suivre du regard d'abord** — théâtral, sans
risque, les servos sim/réels existent déjà) ; la conduite (cmd_vel prio basse via le
mux) ne viendra qu'après validation scénique du regard.

## Lots

- **V0 — socle sain** : structure ci-dessus, Dockerfile Jazzy, package `vision`,
  requirements minimal, briques recyclées déplacées + durcies, tests unitaires purs,
  CI, provisioning Ansible du Pi 5 (install-pios-full, groupe `vision`/hôte `ai`).
  Démo de fin de lot : conteneur qui tourne sur le Pi 5, `ros2 topic list` propre.
- **V1 — suivi de personne** : bench de détection SUR LE PI 5 réel (candidats :
  YOLO11n via ncnn, MediaPipe pose, moondream-tiny ; critère : ≥10 Hz en 640×480,
  CPU < 60 %) → `person_tracker_node`. Démo : `/vision/person` suit quelqu'un qui
  passe devant la webcam (validable par mon protocole caméra).
  Si le CPU ne suffit pas : Hailo AI HAT (~70 €) en plan B.
- **V2 — parole & émotions** : chat_node (STT → GPT-4o → TTS + émotion → /face),
  micro USB à acheter avant. Démo : conversation avec Didier qui « ressent ».

## Matériel

- Webcam USB Jieli 1080p (validée le 2026-07-04, MJPEG 30 fps) — V1 travaillera en 640×480.
- Micro : MANQUANT — requis pour V2 (USB omnidirectionnel simple).
- Caméra CSI : possible plus tard (nappe 22 broches spécifique Pi 5).
