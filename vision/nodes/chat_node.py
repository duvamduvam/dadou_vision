#!/usr/bin/env python3
"""Node 'chat' : micro -> écoute -> LLM streamé -> voix + expressions (V2).

QUOI : node FIN (I/O + câblage ROS seulement) — construit les vraies briques
       V1-V6 (mic/vad/stt/brain/tts/player/bips) et les injecte dans
       vision.ai.conversation.ConversationEngine, qui porte TOUTE la logique
       d'un tour de conversation (déjà testée sans ROS, cf.
       vision/tests/unit/test_conversation.py). Même pattern que
       vision/nodes/person_tracker_node.py : classe d'erreur de démarrage
       dédiée (ChatStartupError -> SystemExit(1) sans crash-loop), paramètres
       ROS déclarés avec défauts (ici lus depuis vision_config.config via
       vision.nodes._chat_wiring.default_chat_parameters, pas dupliqués en
       dur), piège logger rclpy documenté ci-dessous.
POURQUOI ConversationEngine.run_forever tourne dans un THREAD dédié plutôt
       que d'être appelé depuis un timer rclpy : run_once() est bloquant de
       bout en bout (lecture micro frame par frame, transcription STT,
       streaming LLM) — l'exécuter depuis un callback timer gèlerait le
       spinner rclpy (plus aucun autre callback/topic traité pendant tout un
       tour de parole). Le thread est démon (cf. AudioPlayer, même pattern
       déjà en place dans vision.audio.playback) : il ne doit jamais empêcher
       l'arrêt du process si stop_event n'était pas honoré à temps, mais
       destroy_node() reste la voie normale d'arrêt propre (stop_event.set()
       + mic.stop() pour débloquer un read_frame() en cours + join borné).
POURQUOI publish() ne connaît QUE le topic/payload/durée (RosMessage, cf.
       vision.ai.performance) et jamais la logique métier : ce node réutilise
       les topics FACE/ANIMATION EXISTANTS du robot (zéro nouveau topic, cf.
       ARCHITECTURE.md "V2 : émotions et parole via les topics EXISTANTS du
       robot — zéro modif côté robot") — un publisher StringTime par topic,
       choisi par message.topic au moment de publier.
POURQUOI le gate `vision.ai.arbitration` (ajouté 2026-07-12, étude
       d'arbitrage des actionneurs côté robot,
       dadou_robot_ros/docs/etude-arbitrage-actionneurs.md §3/§5/§6) : sans
       lui, le chat écrase le visage d'une séquence de spectacle en cours au
       moindre bruit de salle (S1), et peut la TUER via son stop d'animation
       — speaking_stop() publie animation=False, qui déclenche un arrêt
       GLOBAL côté animations_node, pas seulement l'arrêt de "parle" (S2).
       Le node s'abonne donc en plus à ANIMATION_STATE (StringTime latché,
       publié par animations_node : nom de la séquence en cours, "" au
       repos) et retient le dernier état vu ; _publish() consulte
       arbitration.allow_message() avant chaque publication et retient un
       message si une séquence de spectacle a la main.
POURQUOI CHAT_STATE_TOPIC est un nouveau topic (seule exception au "zéro
       nouveau topic" ci-dessus, lot D0 outillage du chantier "conversation en
       déambulation", dadou_robot_ros/docs/etude-declenchement-conversation.md
       §6.1/§6.2/§7) : c'est de l'ÉTAT (ce que le chat observe de lui-même),
       pas une commande d'actionneur -- rien à quoi le vocabulaire
       FACE/ANIMATION du robot puisse correspondre. Publié en QoS TRANSIENT_
       LOCAL (même piège documenté qu'ANIMATION_STATE plus bas) et SANS passer
       par l'arbitrage (_publish_state, à la différence de _publish) : un état
       n'entre jamais en conflit avec une séquence de spectacle.
"""
import json
import logging
import os
import threading
import time

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from robot_interfaces.msg import StringTime

from dadou_utils_ros.utils_static import ANIMATION, ANIMATION_STATE, FACE

from vision.ai import arbitration
from vision.ai.ai_static import realtime_instructions
from vision.ai.conversation import ConversationEngine
from vision.ai.llm_stream import StreamingBrain
from vision.ai.performance import RosMessage
from vision.ai.stt import FasterWhisperStt
from vision.ai.tts_piper import PiperTts
from vision.audio.beeps import build_thinking_beeps
from vision.audio.mic import MicCapture
from vision.audio.playback import AudioPlayer
from vision.audio.vad import EnergyVad
from vision.nodes._chat_wiring import default_chat_parameters, ros_message_to_string_time_kwargs
from vision.vision_config import config, get_secret

# Durée d'une trame micro (ms) : DOIT être identique côté MicCapture (qui
# découpe le flux arecord en trames de cette taille) et côté EnergyVad (qui
# compte le temps écoulé en additionnant frame_ms à chaque feed()) — un écart
# entre les deux désynchroniserait toute la temporisation du VAD
# (calibration_ms, end_silence_ms...) sans qu'aucune erreur ne soit levée
# (juste un VAD qui déclenche trop tôt/tard). 30 ms = valeur du proto validé
# le 10/07 (cf. CLAUDE.md), reprise telle quelle (pas de paramètre ROS dédié :
# aucune raison scénique d'y toucher, contrairement à refresh_ms/beep_seconds).
MIC_FRAME_MS = 30

# Fréquence d'échantillonnage du flux micro (Hz) : idem, valeur du proto
# validé, pas exposée en paramètre ROS (faster-whisper/l'EnergyVad n'ont pas
# de contrainte particulière à ce sujet, 16 kHz suffit largement pour de la
# voix humaine).
MIC_SAMPLE_RATE = 16000

# Fréquence d'échantillonnage des bips de réflexion (vision.audio.beeps) :
# DOIT être la même valeur passée à build_thinking_beeps() ET à
# ConversationEngine(beeps_rate=...) — c'est ce taux qui permet à
# AudioPlayer.play_async_raw() de jouer le wav écrit par
# write_wav_tempfile(beeps_pcm, beeps_rate) sans le déformer.
BEEPS_SAMPLE_RATE = 22050

# Nom de la clé de secret OpenRouter (vision.vision_config.get_secret) :
# vérifié explicitement AU DÉMARRAGE (cf. __init__) même si StreamingBrain ne
# le lit que paresseusement au premier appel réel — mieux vaut un échec de
# démarrage clair (conf/secret manquant) qu'un plantage silencieux du premier
# tour de conversation en pleine scène.
LLM_API_KEY_NAME = "openrouter_key"

# Délai (s) laissé au thread de conversation pour honorer stop_event avant de
# continuer l'arrêt du node : run_once() peut être bloqué en plein STT/TTS au
# moment du SIGINT — ce n'est qu'une borne de politesse (le thread est démon,
# cf. docstring de module), pas une garantie d'arrêt immédiat.
SHUTDOWN_JOIN_TIMEOUT_S = 5.0

# Topic d'activation du mode interactif ("on"/"off") — même contrat que le
# topic `gaze` de gaze_follower côté robot (dadou_robot_ros) : StringTime,
# valeur json ou brute tolérée. Permet à la régie de couper/relancer la
# conversation EN COURS DE SPECTACLE sans tuer le node (le modèle whisper et
# la voix Piper restent chargés — la reprise est instantanée).
CHAT_CMD_TOPIC = "chat"

# Topic d'état du chat (lot D0 outillage, cf. dadou_robot_ros/docs/
# etude-declenchement-conversation.md §6.1/§6.2) — expose listening/thinking/
# speaking/off pour la régie, le télédiagnostic et le futur engagement_node
# (qui doit savoir si le chat écoute encore pour tenir IN_CONVERSATION).
# Locale ici, PAS dans dadou_utils_ros : même choix que CHAT_CMD_TOPIC
# ci-dessus (ce topic n'a de sens que côté chat, aucune raison de le
# mutualiser dans la lib partagée).
CHAT_STATE_TOPIC = "chat_state"


class ChatStartupError(RuntimeError):
    """Levée quand le node ne peut pas démarrer proprement (secret, voix
    Piper, modèle STT... manquants ou invalides). Différencie un échec de
    démarrage EXPLICITE (déjà loggé via self.get_logger().error(...) avant
    d'être levée) d'un crash Python générique — main() l'attrape
    spécifiquement pour sortir proprement plutôt que de laisser une trace de
    crash-loop silencieuse (même pattern que
    person_tracker_node.PersonTrackerStartupError)."""


class ChatNode(Node):
    def __init__(self):
        super().__init__("chat")

        # Paramètres ROS déclarés avec défauts (issus de vision_config.config
        # via _chat_wiring.default_chat_parameters — jamais dupliqués en
        # dur ici) : modifiables par YAML/CLI sans toucher au code, ex.
        # `ros2 run vision chat --ros-args -p whisper_model:=tiny`.
        defaults = default_chat_parameters()
        self.declare_parameter("llm_model", defaults["llm_model"])
        self.declare_parameter("llm_base_url", defaults["llm_base_url"])
        self.declare_parameter("whisper_model", defaults["whisper_model"])
        self.declare_parameter("piper_voice", defaults["piper_voice"])
        self.declare_parameter("mic_device", defaults["mic_device"])
        self.declare_parameter("out_device", defaults["out_device"])
        self.declare_parameter("refresh_ms", defaults["refresh_ms"])
        self.declare_parameter("beep_seconds", defaults["beep_seconds"])

        llm_model = self.get_parameter("llm_model").value
        llm_base_url = self.get_parameter("llm_base_url").value
        whisper_model = self.get_parameter("whisper_model").value
        piper_voice = self.get_parameter("piper_voice").value
        mic_device = self.get_parameter("mic_device").value
        out_device = self.get_parameter("out_device").value
        refresh_ms = int(self.get_parameter("refresh_ms").value)
        beep_seconds = float(self.get_parameter("beep_seconds").value)

        # --- Secret LLM : vérifié ICI, pas laissé au premier appel paresseux
        # de StreamingBrain (cf. constante LLM_API_KEY_NAME) ------------------
        try:
            get_secret(LLM_API_KEY_NAME)
        except (KeyError, FileNotFoundError) as exc:
            # PIÈGE (rclpy) : RcutilsLogger n'est PAS le module logging
            # stdlib — .error()/.info() ne prennent qu'UNE chaîne déjà
            # formatée, pas de style printf %s/args variadiques (ça lève un
            # TypeError). On formate donc systématiquement avec des
            # f-strings, jamais de virgule d'argument séparé.
            self.get_logger().error(
                f"Secret LLM manquant ({LLM_API_KEY_NAME}) : {exc} — copiez "
                "conf/secret.example vers conf/secret et renseignez la clé "
                "OpenRouter avant de démarrer le node chat."
            )
            raise ChatStartupError("secret LLM manquant") from exc

        # --- Micro + VAD -------------------------------------------------
        # Construction pure (aucun subprocess lancé avant mic.start(), aucune
        # I/O bloquante ici) : peu de raisons d'échouer, mais on protège quand
        # même par cohérence avec le reste du constructeur (une régression
        # future dans MicCapture.__init__ resterait un échec de DÉMARRAGE
        # propre, pas un crash Python nu).
        try:
            mic = MicCapture(mic_device, sample_rate=MIC_SAMPLE_RATE, frame_ms=MIC_FRAME_MS)
            vad = EnergyVad(config["chat_vad"], frame_ms=MIC_FRAME_MS)
        except Exception as exc:  # noqa: BLE001 - log explicite avant de propager
            self.get_logger().error(f"Échec d'initialisation micro/VAD : {exc}")
            raise ChatStartupError("échec init micro/VAD") from exc

        # --- STT (faster-whisper local) -----------------------------------
        try:
            stt = FasterWhisperStt(model_name=whisper_model)
        except Exception as exc:  # noqa: BLE001
            self.get_logger().error(
                f"STT indisponible (modèle faster-whisper={whisper_model!r}) : "
                f"{exc} — vérifiez que faster-whisper est installé (conf/"
                "requirements.txt) et que le modèle a été préchargé dans "
                "l'image (Dockerfile-arm, pour un fonctionnement hors ligne)."
            )
            raise ChatStartupError("échec init STT") from exc

        # --- Cerveau LLM streamé (OpenRouter) -----------------------------
        try:
            brain = StreamingBrain(
                model=llm_model, base_url=llm_base_url,
                api_key_name=LLM_API_KEY_NAME, system_prompt=realtime_instructions(),
            )
        except Exception as exc:  # noqa: BLE001
            self.get_logger().error(
                f"Échec d'initialisation du cerveau LLM (modèle={llm_model!r}, "
                f"base_url={llm_base_url!r}) : {exc}"
            )
            raise ChatStartupError("échec init StreamingBrain") from exc

        # --- TTS Piper (voix locale de Didier) ----------------------------
        # Piper attend DEUX fichiers : le modèle .onnx et son config .json à
        # côté (PiperVoice.load, config_path par défaut = f"{model_path}.json")
        # — on vérifie les deux explicitement pour un message d'erreur qui
        # pointe la VRAIE cause (l'un des deux manquant) plutôt qu'une
        # exception onnxruntime opaque plus loin.
        if not os.path.isfile(piper_voice) or not os.path.isfile(f"{piper_voice}.json"):
            self.get_logger().error(
                f"Voix Piper absente : {piper_voice} (+ .json) — téléchargez "
                "la voix fr_FR-siwis-medium (.onnx + .json) vers ce chemin, "
                "cf. Dockerfile-arm (censé le faire au build) et le paramètre "
                "ROS piper_voice."
            )
            raise ChatStartupError(f"voix Piper introuvable : {piper_voice}")

        try:
            tts = PiperTts(piper_voice)
        except Exception as exc:  # noqa: BLE001
            self.get_logger().error(f"Échec de chargement de la voix Piper ({piper_voice}) : {exc}")
            raise ChatStartupError("échec init PiperTts") from exc

        # --- Lecture audio + bips de réflexion ----------------------------
        try:
            player = AudioPlayer(out_device)
        except Exception as exc:  # noqa: BLE001
            self.get_logger().error(f"Échec d'initialisation du lecteur audio ({out_device}) : {exc}")
            raise ChatStartupError("échec init AudioPlayer") from exc

        beeps_pcm = build_thinking_beeps(beep_seconds, sample_rate=BEEPS_SAMPLE_RATE)

        # --- Publishers StringTime : un par topic réutilisé côté robot ----
        # PIÈGE (vécu, 2026-07-11) : ne JAMAIS nommer cet attribut
        # `self._publishers` — rclpy.node.Node tient déjà une liste interne
        # de ce nom, et l'écraser par un dict fait planter
        # super().destroy_node() (`self._publishers[0]` -> KeyError: 0),
        # interrompant le nettoyage à l'arrêt.
        self._string_time_pubs = {
            FACE: self.create_publisher(StringTime, FACE, 10),
            ANIMATION: self.create_publisher(StringTime, ANIMATION, 10),
        }

        # --- Publisher d'état du chat (lot D0 outillage) -------------------
        # QoS TRANSIENT_LOCAL : MÊME motif que l'abonnement à ANIMATION_STATE
        # plus bas -- piège déjà vécu sur ce topic-là : sans durability
        # partagée des DEUX côtés, un abonné qui démarre APRÈS le premier
        # changement d'état (régie/télédiagnostic lancés après coup, ou
        # futur engagement_node) ne recevrait jamais l'état courant avant la
        # PROCHAINE transition -- potentiellement jamais. depth=1 : seul
        # l'état COURANT compte, pas un historique.
        self._chat_state_pub = self.create_publisher(
            StringTime, CHAT_STATE_TOPIC,
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))

        # --- Orchestrateur (logique déjà testée hors ROS) ------------------
        self._engine = ConversationEngine(
            mic=mic, vad=vad, stt=stt, brain=brain, tts=tts, player=player,
            publish=self._publish, beeps_pcm=beeps_pcm, beeps_rate=BEEPS_SAMPLE_RATE,
            refresh_ms=refresh_ms, on_state=self._publish_state,
            # État initial émis par le MOTEUR à la construction (publisher
            # chat_state créé juste au-dessus) : un abonné tardif trouve une
            # valeur latchée même avant le premier tour. "listening" en dur :
            # le mode interactif démarre TOUJOURS activé (cf. self._enabled
            # ci-dessous, lancer le node = vouloir la conversation).
            initial_state="listening",
        )
        self._mic = mic
        self._player = player

        # --- Mode interactif : ON au démarrage (lancer le node = vouloir la
        # conversation), basculable à chaud via le topic CHAT_CMD_TOPIC -----
        self._enabled = threading.Event()
        self._enabled.set()
        self.create_subscription(StringTime, CHAT_CMD_TOPIC, self._on_chat_cmd, 10)

        # --- Arbitrage amont (2026-07-12, cf. docstring de module POURQUOI) :
        # None = jamais reçu (topic ANIMATION_STATE absent ou robot pas encore
        # démarré) -- distinct de "" (repos), cf. vision.ai.arbitration : ces
        # deux valeurs déclenchent des règles différentes dans allow_message.
        # ÉCRITE par _on_animation_state, qui tourne dans le thread rclpy.spin
        # (callback ROS) ; LUE par _publish, appelé par le thread DÉDIÉ de
        # ConversationEngine.run_forever (cf. docstring de module, POURQUOI du
        # thread) -- donc bien deux threads différents. Aucun verrou n'est
        # nécessaire malgré tout : l'affectation d'une référence str/None est
        # une opération atomique sous le GIL CPython, et _publish ne fait
        # qu'une LECTURE simple (jamais de lecture-puis-modification) -- la
        # pire chose qui puisse arriver est de lire l'état juste avant ou
        # juste après une transition, jamais une valeur corrompue.
        self._animation_state = None
        # Échéance de PÉREMPTION de l'état actif (garde-fou façon deadman,
        # cf. arbitration.state_expiry) : si animations_node meurt en pleine
        # séquence, le "" de fin n'arrive jamais — sans échéance le chat
        # resterait muet pour toujours. Deux attributs écrits séparément par
        # le callback : une lecture « déchirée » (état neuf + échéance
        # ancienne ou l'inverse) reste bénigne — au pire un message retenu ou
        # laissé passer À l'instant d'une transition, jamais un état corrompu.
        self._animation_expiry = 0.0
        # QoS TRANSIENT_LOCAL : DOIT correspondre à celle du publisher côté
        # animations_node (dadou_robot_ros, depth=1 + durability
        # TRANSIENT_LOCAL) -- sans ça, un chat_node démarré EN COURS de
        # spectacle n'obtiendrait l'état courant qu'à la PROCHAINE transition
        # (donc potentiellement jamais avant la fin de la séquence en cours).
        self.create_subscription(
            StringTime, ANIMATION_STATE, self._on_animation_state,
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))

        # --- Thread de conversation (cf. docstring de module POURQUOI) ----
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._engine.run_forever,
            args=(self._stop_event, self._enabled), daemon=True,
        )
        self._thread.start()

        self.get_logger().info(
            f"chat démarré (llm_model={llm_model}, whisper_model={whisper_model}, "
            f"mic_device={mic_device}, out_device={out_device}) -> topics "
            f"{FACE}/{ANIMATION}, toggle sur '{CHAT_CMD_TOPIC}' (on/off), "
            f"état publié sur '{CHAT_STATE_TOPIC}' (latché)"
        )

    def _on_chat_cmd(self, ros_msg):
        """Active/désactive le mode interactif — même contrat que le topic
        `gaze` de gaze_follower (dadou_robot_ros) : "on"/"off", json ou brut."""
        raw = ros_msg.msg
        try:
            value = json.loads(raw)
        except (ValueError, TypeError):
            value = raw
        if value in ("on", True, 1, "1"):
            self._enabled.set()
            self.get_logger().info("chat ON : mode interactif activé")
        elif value in ("off", False, 0, "0"):
            self._enabled.clear()
            # Interrompt une ÉCOUTE en cours : read_frame() bloquant retourne
            # None dès que le subprocess arecord meurt, la boucle run_forever
            # voit alors enabled baissé et se met en attente. Une RÉPLIQUE en
            # cours n'est PAS coupée (choix scénique : Didier finit sa
            # phrase, cf. ConversationEngine.run_forever) — le micro qu'on
            # stoppe ici est de toute façon déjà coupé pendant qu'il parle
            # (anti-larsen).
            self._mic.stop()
            self.get_logger().info("chat OFF : mode interactif désactivé (micro coupé)")
        else:
            self.get_logger().warning(f"commande chat inconnue : {raw!r}")

    def _on_animation_state(self, ros_msg):
        """Callback du topic ANIMATION_STATE (latché, publié par
        animations_node côté robot) : mémorise le nom de la séquence en
        cours ("" au repos) via vision.ai.arbitration.parse_animation_state
        (logique de décodage testée hors ROS). Affectation d'un str sur
        self._animation_state : pas de verrou nécessaire (cf. commentaire
        du constructeur) -- ce callback tourne dans le thread rclpy.spin,
        _publish() (appelé par le thread de conversation) ne fait qu'une
        LECTURE de la référence courante, jamais de lecture-modification."""
        state = arbitration.parse_animation_state(ros_msg.msg)
        if state:
            # ros_msg.time = remaining_ms au (re)démarrage (contrat
            # animations_node, republié à chaque relance de séquence même à
            # nom identique) : arme la péremption façon deadman. Échéance
            # écrite AVANT l'état (une lecture croisée reste bénigne, cf.
            # commentaire du constructeur).
            self._animation_expiry = arbitration.state_expiry(
                int(ros_msg.time), time.monotonic())
        self._animation_state = state

    def _publish(self, message: RosMessage) -> None:
        """Callback injecté dans ConversationEngine : traduit un RosMessage en
        StringTime (cf. vision.nodes._chat_wiring.ros_message_to_string_time_kwargs,
        la seule partie testable sans ROS de cette méthode) et publie sur le
        publisher correspondant à message.topic -- SAUF si l'arbitrage amont
        retient le message (une séquence de spectacle a la main, cf.
        vision.ai.arbitration et docstring de module)."""
        # Péremption appliquée à la LECTURE (cf. arbitration.effective_state) :
        # un état actif dont l'échéance est dépassée est traité comme le repos
        # (animations_node probablement mort en pleine séquence).
        state = arbitration.effective_state(
            self._animation_state, self._animation_expiry, time.monotonic())
        if not arbitration.allow_message(message.topic, message.payload, state):
            # PIÈGE rclpy documenté en tête de fichier : f-strings uniquement,
            # jamais de %s variadique (RcutilsLogger n'est pas le logging stdlib).
            self.get_logger().info(
                f"message {message.topic} retenu : la séquence "
                f"'{state}' a la main (arbitrage amont)"
            )
            return

        publisher = self._string_time_pubs.get(message.topic)
        if publisher is None:
            # Ne devrait jamais arriver (vision.ai.performance ne produit que
            # des RosMessage sur FACE/ANIMATION) : on log plutôt que de
            # planter le thread de conversation pour une seule publication
            # ratée — le spectacle continue (même philosophie défensive que
            # ConversationEngine._speak_reply).
            self.get_logger().warning(f"Topic inconnu, message ignoré : {message.topic}")
            return
        publisher.publish(StringTime(**ros_message_to_string_time_kwargs(message)))

    def _publish_state(self, state: str) -> None:
        """Callback `on_state` injecté dans ConversationEngine : publie l'état
        (listening/thinking/speaking/off) tel quel sur CHAT_STATE_TOPIC.
        PAS d'arbitrage ici (contrairement à _publish ci-dessus) : c'est un
        topic d'ÉTAT (ce que le chat OBSERVE de lui-même), pas un actionneur
        qui pourrait entrer en conflit avec une séquence de spectacle -- rien
        à retenir. msg=state BRUT (pas de json.dumps, contrairement à
        FACE/ANIMATION) : ce topic n'a pas le même contrat que ceux
        d'animations_node, une chaîne simple suffit à un abonné qui lit
        `msg` directement."""
        self._chat_state_pub.publish(StringTime(msg=state, time=0, anim=False))

    def destroy_node(self):
        # Arrêt propre : stop_event débloque la boucle run_forever DÈS que le
        # tour en cours se termine ; mic.stop() coupe le subprocess arecord
        # tout de suite, ce qui fait échouer le read_frame() bloquant en
        # cours (retourne None) si le node est arrêté EN PLEIN tour d'écoute
        # — sans ça, le thread pourrait rester bloqué indéfiniment sur un
        # micro qui n'a plus de raison de parler.
        stop_event = getattr(self, "_stop_event", None)
        if stop_event is not None:
            stop_event.set()

        mic = getattr(self, "_mic", None)
        if mic is not None:
            mic.stop()

        player = getattr(self, "_player", None)
        if player is not None:
            player.stop()

        thread = getattr(self, "_thread", None)
        if thread is not None:
            thread.join(timeout=SHUTDOWN_JOIN_TIMEOUT_S)

        super().destroy_node()


def main(args=None):
    # ConversationEngine (brique pure, sans dépendance rclpy) journalise via
    # le logging STDLIB — sans handler configuré, ces logs sont INVISIBLES
    # (niveau WARNING par défaut, aucun handler) : le premier test micro réel
    # (2026-07-11) s'est déroulé à l'aveugle à cause de ça. Racine à WARNING
    # pour ne pas hériter du bruit INFO des libs HTTP (httpx/openai), INFO
    # ciblé sur vision.* uniquement (tours de conversation : STT, répliques,
    # abandons).
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )
    logging.getLogger("vision").setLevel(logging.INFO)

    rclpy.init(args=args)
    try:
        node = ChatNode()
    except ChatStartupError:
        # Déjà loggé en détail dans __init__ (get_logger().error avant la
        # levée) : ici on se contente de sortir proprement, contexte ROS
        # fermé, code de retour non nul pour que systemd/docker sachent que
        # ça n'a pas tourné (mais SANS boucle de crash bruyante : un seul
        # message clair, pas une pile d'exception) — même pattern que
        # person_tracker_node.main().
        rclpy.try_shutdown()
        raise SystemExit(1)

    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        # SIGINT (Ctrl-C, pkill -INT) ou arrêt du contexte par rclpy : c'est
        # le chemin d'arrêt NORMAL, pas une erreur — sans ce except, la pile
        # d'exception polluerait le log à chaque arrêt de spectacle.
        pass
    finally:
        node.destroy_node()
        # try_shutdown (PAS shutdown) : en Jazzy, le handler SIGINT de rclpy
        # a souvent DÉJÀ fermé le contexte quand on arrive ici — shutdown()
        # lèverait « rcl_shutdown already called » (constaté au premier test
        # du toggle, 2026-07-11).
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
