"""Orchestrateur d'un tour de conversation (V7) — colle les briques V1-V6
ensemble : micro -> VAD -> STT -> LLM streamé -> parseur de jeu -> TTS ->
lecture, avec publication des messages ROS (face/animation) au bon moment.

QUOI : ConversationEngine ne fait AUCUN I/O lui-même — tout (mic/vad/stt/
       brain/tts/player/publish) est injecté au constructeur. Ce module reste
       donc testable avec des fakes purs (cf. test_conversation.py), même si
       ce n'est pas un module "pur" au sens strict des lots V1-V5 (il
       ORCHESTRE des effets de bord, il ne les produit pas lui-même).
POURQUOI aucun thread supplémentaire créé ici : AudioPlayer a déjà le sien
       (lecture séquentielle en tâche de fond, cf. vision.audio.playback) ;
       run_once() est de toute façon bloquant sur la boucle d'écoute micro
       (read_frame) — ajouter un thread ici n'apporterait rien, juste de la
       complexité de synchronisation en plus.

DÉCISION (le déroulé du proto laissait un choix implicite à trancher) :
       thinking() est publié JUSTE APRÈS speech_end, AVANT même de savoir si
       le STT renverra du texte exploitable — donc thinking() part MÊME SI
       le tour est ensuite abandonné (STT vide/trop court). Choix VOLONTAIRE
       (pas un oubli) : le visage "reflechit" est une réaction honnête au
       fait que le STT est réellement en train de tourner (calcul bloquant
       en cours), pas une promesse qu'une réponse va suivre — le spectateur
       voit le robot "y penser", ce qui reste cohérent même si l'énoncé
       capté était en fait trop court pour être exploité. cf.
       test_conversation.py::test_stt_vide_publie_thinking_puis_rien_dautre
       pour le test qui fige ce choix. Limite connue acceptée : le visage
       reste sur "reflechit" après un abandon (pas de idle() de rattrapage)
       — non demandé par la spec V7, à revisiter si ça se voit mal sur scène.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from vision.ai import performance
from vision.ai.stream_parser import Didascalie, Emotion, Sentence, StreamPerformanceParser


class ConversationEngine:
    """Un tour de conversation = un cycle écoute -> pensée -> parole complet.
    Toutes les dépendances (I/O réelles ou fakes de test) sont injectées."""

    def __init__(self, *, mic, vad, stt, brain, tts, player,
                 publish: Callable[[object], None],
                 perf=None,
                 beeps_pcm: bytes = b"", beeps_rate: int = 22050,
                 refresh_ms: int = 15000):
        self._mic = mic
        self._vad = vad
        self._stt = stt
        self._brain = brain
        self._tts = tts
        self._player = player
        self._publish = publish
        # perf par défaut = le MODULE vision.ai.performance lui-même (ses
        # fonctions thinking/speaking_start/... sont utilisées comme
        # namespace) — un fake de test fournit un objet avec les mêmes noms
        # de fonctions, sans avoir à mocker un module entier.
        self._perf = perf if perf is not None else performance
        self._refresh_ms = refresh_ms

        # La piste de bips est écrite en wav temporaire UNE SEULE FOIS ici
        # (pas à chaque tour) : son contenu ne change pas d'un tour à
        # l'autre, cf. vision.audio.playback.write_wav_tempfile. Import
        # différé (pas en tête de module) : conversation.py doit rester
        # important sans exiger que vision.audio.playback soit disponible
        # dans TOUS les contextes qui pourraient un jour importer ce module
        # (aucun aujourd'hui, mais évite d'ajouter un couplage silencieux) —
        # en pratique playback.py est pur stdlib+numpy, donc ceci reste sûr
        # même en CI minimal.
        self._beeps_path: Optional[str] = None
        if beeps_pcm:
            from vision.audio.playback import write_wav_tempfile
            self._beeps_path = write_wav_tempfile(beeps_pcm, beeps_rate)

    def _publish_all(self, messages) -> None:
        """publish() ne prend qu'UN SEUL message à la fois (contrat du
        constructeur) ; les fonctions de vision.ai.performance renvoient des
        LISTES (parfois vides, ex: emotion(None)) — ce helper fait le pont,
        dans l'ordre, sans jamais publier quoi que ce soit pour une liste
        vide (une liste vide = "rien à jouer", pas une erreur)."""
        for message in messages:
            self._publish(message)

    def _handle_event(self, event, emotion_params):
        """Traduit UN événement du parseur de flux (Sentence/Didascalie/
        Emotion) en effet de bord (publish + synthèse/lecture), et retourne
        les params d'émotion à retenir (inchangés sauf si `event` EST
        l'Emotion — un seul JSON d'émotion possible par tour, en toute fin de
        flux, cf. stream_parser.flush())."""
        if isinstance(event, Sentence):
            # speaking_start republié à CHAQUE Sentence (pas seulement la
            # première) : sert de rafraîchissement — cf. commentaire
            # chat_animation_refresh_ms dans vision_config.py, l'animation
            # "parle" doit rester active tant que le TTS streame encore.
            self._publish_all(self._perf.speaking_start(self._refresh_ms))
            pcm, sample_rate = self._tts.synthesize(event.text)
            # play() enfile : la synthèse de la Sentence SUIVANTE peut se
            # faire pendant que celle-ci joue encore (pipeline N/N+1 porté
            # par AudioPlayer, cf. vision.audio.playback).
            self._player.play(pcm, sample_rate)
            return emotion_params

        if isinstance(event, Didascalie):
            self._publish_all(self._perf.didascalie(event.action))
            return emotion_params

        if isinstance(event, Emotion):
            return event.params

        return emotion_params

    def run_once(self) -> bool:
        """Un tour complet. Retourne True seulement si le tour a été mené
        jusqu'au bout (émotion publiée) ; False dans tous les cas
        d'abandon : flux micro mort, STT vide/trop court, ou erreur
        LLM/TTS (le spectacle continue, cf. docstring de module)."""
        self._mic.start()

        speech_bytes = self._listen_for_utterance()
        if speech_bytes is None:
            # Flux micro mort en cours d'écoute : on retente un démarrage et
            # on abandonne CE tour (pas d'exception qui remonterait jusqu'à
            # run_forever — un souci matériel ponctuel ne doit pas arrêter la
            # boucle de conversation).
            self._mic.start()
            return False

        # Anti-larsen : le micro est coupé AVANT que Didier ne parle (cf.
        # vision.audio.mic.MicCapture.stop). thinking() est publié ICI, cf.
        # décision documentée en tête de module (avant même de savoir si le
        # STT renverra du texte exploitable).
        self._mic.stop()
        self._publish_all(self._perf.thinking())

        if self._beeps_path is not None:
            # Fire-and-forget : les bips jouent PENDANT le transcribe()
            # bloquant qui suit, cf. vision.audio.playback.play_async_raw.
            self._player.play_async_raw(self._beeps_path)

        text = self._stt.transcribe(speech_bytes, self._mic.sample_rate)

        if not text or len(text.strip()) < 2:
            self._mic.start()
            return False

        return self._speak_reply(text)

    def _listen_for_utterance(self) -> Optional[bytes]:
        """Boucle micro -> VAD jusqu'à détecter la fin d'un énoncé. Retourne
        les octets PCM accumulés depuis le pré-roll, ou None si le flux
        micro est mort avant la fin de l'énoncé."""
        speech_bytes = b""
        in_speech = False

        while True:
            frame = self._mic.read_frame()
            if frame is None:
                return None

            level = self._mic.frame_rms(frame)
            event = self._vad.feed(level)

            if not in_speech:
                # Tant que la parole n'a pas VRAIMENT commencé (VAD encore en
                # CALIBRATING/IDLE), on ne fait qu'alimenter la machine à
                # états — feed() renvoie None, la boucle continue.
                if event is not None and event.kind == "speech_start":
                    in_speech = True
                    # preroll() inclut déjà cette trame de déclenchement
                    # comme entrée la plus récente du ring buffer (cf.
                    # vision.audio.mic.MicCapture.read_frame/preroll) : pas
                    # besoin de la rajouter une seconde fois ici.
                    speech_bytes = self._mic.preroll()
                continue

            speech_bytes += frame
            if event is not None and event.kind == "speech_end":
                return speech_bytes

    def _speak_reply(self, text: str) -> bool:
        """Génère et joue la réponse du LLM pour `text` déjà transcrit ;
        retourne True si le tour est allé jusqu'au bout, False sur erreur
        LLM/TTS (log + retour à l'écoute, le spectacle continue)."""
        parser = StreamPerformanceParser()
        emotion_params = None

        try:
            for delta in self._brain.stream_reply(text):
                for event in parser.feed(delta):
                    emotion_params = self._handle_event(event, emotion_params)
            for event in parser.flush():
                emotion_params = self._handle_event(event, emotion_params)
        except Exception:
            # Le spectacle continue : une panne LLM/TTS ponctuelle ne doit
            # jamais arrêter la conversation, seulement ce tour-ci.
            logging.exception(
                "Erreur pendant la génération/synthèse de la réponse — tour abandonné.")
            self._publish_all(self._perf.speaking_stop())
            self._mic.start()
            return False

        self._player.drain()
        self._publish_all(self._perf.speaking_stop())
        self._publish_all(self._perf.emotion(emotion_params))
        self._mic.start()
        return True

    def run_forever(self, stop_event: threading.Event) -> None:
        """Enchaîne les tours jusqu'à stop_event.set() (typiquement déclenché
        par le node ROS appelant à l'arrêt/désactivation, cf. chat_node V2).
        Pas de thread créé ici, cf. docstring de module."""
        while not stop_event.is_set():
            self.run_once()
