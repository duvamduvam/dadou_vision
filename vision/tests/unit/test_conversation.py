"""Tests de vision/ai/conversation.py (V7) — orchestrateur d'un tour de
conversation. Fakes PURS uniquement : AUCUN subprocess/réseau (mic/vad/stt/
brain/tts/player sont tous des objets scriptés, jamais les vraies
implémentations arecord/aplay/openai/faster-whisper/piper de vision/audio et
vision/ai — celles-ci restent hors de portée de la CI, cf. CLAUDE.md).

TIMELINE : une liste UNIQUE partagée par tous les fakes, où chaque effet de
bord observable (mic start/stop, publish, transcribe, stream_reply,
synthesize, play, drain) ajoute un tuple. Les tests assertent des séquences
ordonnées de cette timeline — c'est l'ordre CROISÉ entre briques (micro coupé
avant thinking, animation republiée avant chaque synthèse, speaking_stop
publié même en cas d'erreur...) qui est le vrai contrat de
ConversationEngine, pas le comportement isolé d'un seul fake.
"""
import json
import os
import threading
import time

import pytest

from dadou_utils_ros.utils_static import ANIMATION, FACE

from vision.ai.conversation import ConversationEngine, has_usable_text
from vision.ai.performance import RosMessage
from vision.audio.vad import VadEvent

REFRESH_MS = 15000
BEEPS_PCM = b"\x00\x01" * 100  # contenu bidon, seule la présence compte ici
BEEPS_RATE = 22050


# ---------------------------------------------------------------------------
# Fakes — un seul rôle chacun, tous n'écrivent que dans la timeline partagée.
# ---------------------------------------------------------------------------

class FakeMic:
    """Micro scripté : consomme une liste FIXE de trames ; frame_rms est sans
    objet ici (le fake VAD ci-dessous ignore le niveau, cf. FakeVad) —
    seul le NOMBRE d'appels à read_frame() doit correspondre au nombre
    d'événements scriptés dans FakeVad (un feed() par read_frame(), cf.
    ConversationEngine._listen_for_utterance)."""

    sample_rate = 16000

    def __init__(self, timeline, frames, preroll=b"PREROLL"):
        self._timeline = timeline
        self._frames = list(frames)
        self._preroll = preroll

    def start(self):
        self._timeline.append(("mic_start",))

    def stop(self):
        self._timeline.append(("mic_stop",))

    def read_frame(self):
        if not self._frames:
            return None
        return self._frames.pop(0)

    def frame_rms(self, frame):
        return 0.0  # valeur sans importance : FakeVad ne l'utilise pas

    def preroll(self):
        return self._preroll


class FakeVad:
    """VAD scripté : renvoie une séquence FIXE de VadEvent/None, un par
    feed() — reproduit une machine à états réelle sans en être une (le
    comportement de EnergyVad est déjà testé indépendamment, cf.
    test_vad.py)."""

    def __init__(self, events):
        self._events = list(events)

    def feed(self, level):
        if not self._events:
            return None
        return self._events.pop(0)


class FakeStt:
    def __init__(self, timeline, text):
        self._timeline = timeline
        self._text = text

    def transcribe(self, pcm, sample_rate):
        self._timeline.append(("stt_transcribe", pcm, sample_rate))
        return self._text


class FakeBrain:
    """Brain scripté : stream_reply() yield une séquence FIXE de deltas
    (indépendante du texte reçu, qui est quand même noté dans la timeline
    pour vérifier qu'il a bien été transmis tel quel) ; peut lever une
    erreur APRÈS avoir tout streamé, pour simuler une panne LLM en cours de
    génération (cf. test_erreur_llm_publie_quand_meme_speaking_stop)."""

    def __init__(self, timeline, deltas, raise_error=False):
        self._timeline = timeline
        self._deltas = deltas
        self._raise_error = raise_error

    def stream_reply(self, user_text):
        self._timeline.append(("brain_stream_reply", user_text))
        for delta in self._deltas:
            yield delta
        if self._raise_error:
            raise RuntimeError("panne LLM simulée (test)")


class FakeTts:
    def __init__(self, timeline):
        self._timeline = timeline

    def synthesize(self, text):
        self._timeline.append(("tts_synthesize", text))
        return (b"PCM:" + text.encode(), 22050)


class FakePlayer:
    def __init__(self, timeline):
        self._timeline = timeline

    def play(self, pcm, sample_rate):
        self._timeline.append(("player_play", pcm, sample_rate))

    def play_async_raw(self, path):
        self._timeline.append(("player_play_async_raw", path))

    def drain(self):
        self._timeline.append(("player_drain",))


def _make_publish(timeline):
    def publish(message):
        timeline.append(("publish", message))
    return publish


def _make_engine(timeline, *, frames, vad_events, stt_text, brain_deltas,
                  brain_raises=False, beeps=True):
    """Assemble un ConversationEngine avec des fakes câblés sur la même
    timeline — factorise le câblage répété par les tests ci-dessous.
    L'appelant est responsable de _cleanup_beeps(engine) en fin de test.
    dead_mic_backoff_s=0.0 : pas d'attente réelle dans les tests (la valeur
    par défaut ferait dormir 0,5 s chaque test de flux micro mort)."""
    return ConversationEngine(
        mic=FakeMic(timeline, frames),
        vad=FakeVad(vad_events),
        stt=FakeStt(timeline, stt_text),
        brain=FakeBrain(timeline, brain_deltas, raise_error=brain_raises),
        tts=FakeTts(timeline),
        player=FakePlayer(timeline),
        publish=_make_publish(timeline),
        beeps_pcm=BEEPS_PCM if beeps else b"",
        beeps_rate=BEEPS_RATE,
        refresh_ms=REFRESH_MS,
        dead_mic_backoff_s=0.0,
    )


def _cleanup_beeps(engine):
    """Supprime le wav temporaire des bips écrit une fois au constructeur
    (cf. ConversationEngine.__init__) — sans quoi chaque test laisserait un
    fichier orphelin dans /tmp."""
    path = engine._beeps_path
    if path is not None and os.path.exists(path):
        os.remove(path)


@pytest.fixture
def timeline():
    return []


# --------------------------------------------------------------------------
# Trame micro/VAD commune : 3 trames, speech_start sur la 2e, speech_end sur
# la 3e — suffisant pour déclencher un tour complet dans tous les tests.
# --------------------------------------------------------------------------

def _speech_frames_and_events():
    frames = [b"f0", b"f1", b"f2"]
    events = [
        None,
        VadEvent(kind="speech_start", preroll_frames=2),
        VadEvent(kind="speech_end", reason="silence"),
    ]
    return frames, events


# --------------------------------------------------------------------------
# Tour nominal : ordre exact des publish + pipeline TTS phrase par phrase.
# --------------------------------------------------------------------------

def test_nominal_turn_ordre_exact_des_evenements(timeline):
    frames, events = _speech_frames_and_events()
    # Réponse LLM streamée en UN SEUL delta : "Salut." (phrase confirmée),
    # une didascalie *rit* (mappée sur "joie", cf. performance.py), une
    # deuxième phrase "Comment ça va ?", puis le JSON d'émotion final. Un
    # seul delta suffit à produire tous ces événements dès le feed() (cf.
    # stream_parser.py : seule la partie JSON est retenue pour le flush()).
    deltas = ['Salut. *rit* Comment ça va ? {"emotion": "happy"}']

    engine = _make_engine(
        timeline, frames=frames, vad_events=events,
        stt_text="raconte une blague", brain_deltas=deltas,
    )
    try:
        result = engine.run_once()
    finally:
        _cleanup_beeps(engine)

    assert result is True

    beeps_path = engine._beeps_path
    assert beeps_path is not None

    assert timeline == [
        ("mic_start",),
        ("mic_stop",),
        ("publish", RosMessage(FACE, json.dumps("reflechit"))),
        ("player_play_async_raw", beeps_path),
        ("stt_transcribe", b"PREROLLf2", 16000),
        ("brain_stream_reply", "raconte une blague"),
        ("publish", RosMessage(ANIMATION, json.dumps("parle"), time_ms=REFRESH_MS)),
        ("tts_synthesize", "Salut."),
        ("player_play", b"PCM:Salut.", 22050),
        ("publish", RosMessage(FACE, json.dumps("joie"))),  # didascalie "rit"
        ("publish", RosMessage(ANIMATION, json.dumps("parle"), time_ms=REFRESH_MS)),
        ("tts_synthesize", "Comment ça va ?"),
        # Bytes non-ASCII (ç/à) : littéral b"..." interdit en Python, on
        # encode dynamiquement plutôt que de simplifier le texte de test.
        ("player_play", b"PCM:" + "Comment ça va ?".encode(), 22050),
        ("player_drain",),
        ("publish", RosMessage(ANIMATION, json.dumps(False))),  # speaking_stop
        ("publish", RosMessage(FACE, json.dumps("joie"))),  # emotion happy -> joie
        ("mic_start",),
    ]


def test_micro_coupe_avant_la_parole_et_redemarre_apres(timeline):
    # Même scénario que le tour nominal : on vérifie ICI spécifiquement la
    # règle anti-larsen (cf. vision.audio.mic.MicCapture.stop) — le micro
    # est coupé AVANT toute publication liée à la réponse, et redémarré
    # SEULEMENT après que toute la parole a été jouée (drain + speaking_stop
    # + emotion), jamais entre-temps.
    frames, events = _speech_frames_and_events()
    deltas = ['Salut. {"emotion": "neutral"}']

    engine = _make_engine(
        timeline, frames=frames, vad_events=events,
        stt_text="salut", brain_deltas=deltas,
    )
    try:
        result = engine.run_once()
    finally:
        _cleanup_beeps(engine)

    assert result is True
    tags = [event[0] for event in timeline]

    mic_stop_index = tags.index("mic_stop")
    # Aucun mic_start entre le mic_stop initial et la toute fin du tour.
    assert "mic_start" not in tags[mic_stop_index + 1:-1]
    # Le dernier événement de la timeline est bien le redémarrage du micro.
    assert tags[-1] == "mic_start"
    # Le micro est coupé avant toute action côté parole (bips/STT/LLM/TTS).
    assert mic_stop_index < tags.index("player_play_async_raw")
    assert mic_stop_index < tags.index("stt_transcribe")


# --------------------------------------------------------------------------
# STT inexploitable (vide, trop court, ou PONCTUATION PURE — whisper transcrit
# le bruit en "... ... ...", vécu au premier test micro caméra 2026-07-11) :
# thinking() est publié quand même (décision documentée en tête de
# vision/ai/conversation.py — réaction honnête au fait que le STT tournait
# réellement), PUIS idle() en rattrapage (correctif 2026-07-12, étude
# d'arbitrage des actionneurs côté robot, scénario S1 : le visage ne doit
# plus rester coincé sur "reflechit" après un tour abandonné) — rien d'autre
# après, surtout pas d'appel LLM payant.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("stt_text", ["", "a", "... ... ... ...", " ?! . "])
def test_stt_inexploitable_publie_thinking_puis_idle(timeline, stt_text):
    frames, events = _speech_frames_and_events()

    engine = _make_engine(
        timeline, frames=frames, vad_events=events,
        stt_text=stt_text, brain_deltas=["ne doit jamais être utilisé"],
    )
    try:
        result = engine.run_once()
    finally:
        _cleanup_beeps(engine)

    assert result is False

    tags = [event[0] for event in timeline]
    # thinking() PUIS idle() : ce sont les DEUX SEULS publish de tout le
    # tour (plus rien après le rattrapage, cf. commentaire ci-dessus).
    publishes = [event[1] for event in timeline if event[0] == "publish"]
    assert publishes == [
        RosMessage(FACE, json.dumps("reflechit")),
        RosMessage(FACE, json.dumps("stop")),  # idle()
    ]
    # Le LLM n'a JAMAIS été sollicité : le tour est abandonné avant.
    assert "brain_stream_reply" not in tags
    assert "tts_synthesize" not in tags
    # Le micro est bien redémarré malgré l'abandon, APRÈS le rattrapage idle().
    assert tags[-1] == "mic_start"
    assert tags.count("mic_start") == 2  # le start() initial + le restart
    assert tags.index("publish") < tags.index("mic_start", 1)


# --------------------------------------------------------------------------
# Panne LLM en cours de génération : le spectacle continue (speaking_stop
# publié quand même, tour abandonné proprement, pas d'exception qui remonte).
# --------------------------------------------------------------------------

def test_erreur_llm_publie_quand_meme_speaking_stop(timeline):
    frames, events = _speech_frames_and_events()
    # Un premier delta produit une Sentence complète (donc une synthèse/
    # lecture AVANT la panne) ; le générateur lève ensuite une erreur après
    # avoir tout streamé (cf. FakeBrain.stream_reply).
    deltas = ["Bonjour ! "]

    engine = _make_engine(
        timeline, frames=frames, vad_events=events,
        stt_text="salut", brain_deltas=deltas, brain_raises=True,
    )
    try:
        result = engine.run_once()
    finally:
        _cleanup_beeps(engine)

    assert result is False

    tags = [event[0] for event in timeline]
    # La phrase reçue AVANT la panne a bien été jouée.
    assert ("tts_synthesize", "Bonjour !") in timeline
    assert ("player_play", b"PCM:Bonjour !", 22050) in timeline
    # speaking_stop est publié MALGRÉ l'erreur (dernier publish avant le
    # redémarrage micro) — pas d'emotion() publiée (le tour est abandonné
    # avant flush(), aucun JSON d'émotion n'a jamais été vu).
    publishes = [event[1] for event in timeline if event[0] == "publish"]
    assert publishes[-1] == RosMessage(ANIMATION, json.dumps(False))
    # drain() n'est PAS appelé : on abandonne immédiatement sur erreur, sans
    # attendre la fin de la lecture de ce qui est déjà en file.
    assert "player_drain" not in tags
    assert tags[-1] == "mic_start"


# --------------------------------------------------------------------------
# Flux micro mort en cours d'écoute : abandon propre, pas d'exception.
# --------------------------------------------------------------------------

def test_flux_micro_mort_abandonne_le_tour_proprement(timeline, caplog):
    # Une seule trame puis plus rien (read_frame() renverra None ensuite) :
    # aucun speech_start n'est jamais atteint.
    frames = [b"f0"]
    vad_events = [None]

    engine = _make_engine(
        timeline, frames=frames, vad_events=vad_events,
        stt_text="jamais utilisé", brain_deltas=["jamais utilisé"],
    )
    try:
        with caplog.at_level("WARNING", logger="vision.ai.conversation"):
            result = engine.run_once()
    finally:
        _cleanup_beeps(engine)

    assert result is False
    tags = [event[0] for event in timeline]
    assert "publish" not in tags  # même thinking() n'est pas atteint ici
    assert "stt_transcribe" not in tags
    assert tags == ["mic_start", "mic_start"]  # start initial + restart sur flux mort
    # L'incident est VISIBLE dans les logs (le premier test réel a montré
    # qu'une boucle micro-mort silencieuse est indiagnosticable en direct).
    assert any("micro mort" in record.message for record in caplog.records)


# --------------------------------------------------------------------------
# Filtre de texte STT exploitable : au moins 2 caractères alphanumériques
# (whisper transcrit le bruit pur en ponctuation, cf. has_usable_text).
# --------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    (None, False),
    ("", False),
    ("a", False),                    # 1 seul alphanumérique
    ("... ... ... ...", False),      # bruit transcrit en ponctuation pure
    (" ?! . ", False),
    ("ça", True),                    # 2 alphanumériques (accentué compris)
    ("Salut Didier !", True),
    ("a1", True),
])
def test_has_usable_text(text, expected):
    assert has_usable_text(text) is expected


# --------------------------------------------------------------------------
# Mode interactif (toggle chat on/off, cf. chat_node) : en pause, AUCUN tour
# ne démarre et le micro est maintenu coupé ; une coupure micro volontaire
# (OFF pendant l'écoute) n'est PAS traitée comme un incident.
# --------------------------------------------------------------------------

def test_run_forever_en_pause_ne_lance_aucun_tour_et_coupe_le_micro(timeline):
    engine = _make_engine(
        timeline, frames=[b"f0"], vad_events=[None],
        stt_text="jamais utilisé", brain_deltas=["jamais utilisé"],
    )
    stop_event = threading.Event()
    enabled = threading.Event()  # baissé = mode interactif désactivé

    thread = threading.Thread(
        target=engine.run_forever, args=(stop_event, enabled), daemon=True)
    try:
        thread.start()
        time.sleep(0.05)  # laisse la boucle de pause tourner quelques cycles
        stop_event.set()
        thread.join(timeout=2.0)
        assert not thread.is_alive()
    finally:
        stop_event.set()
        _cleanup_beeps(engine)

    tags = [event[0] for event in timeline]
    # Aucun tour n'a démarré (pas de mic_start = pas de run_once) ; le micro
    # a été activement maintenu coupé pendant la pause.
    assert "mic_start" not in tags
    assert "mic_stop" in tags


def test_micro_coupe_volontairement_pas_de_restart_ni_warning(timeline, caplog):
    # Coupure volontaire : l'interrupteur est BAISSÉ au moment où le flux
    # micro meurt (scénario toggle OFF pendant l'écoute, cf.
    # chat_node._on_chat_cmd qui fait mic.stop()).
    engine = _make_engine(
        timeline, frames=[b"f0"], vad_events=[None],
        stt_text="jamais utilisé", brain_deltas=["jamais utilisé"],
    )
    engine._enabled = threading.Event()  # posé normalement par run_forever

    try:
        with caplog.at_level("INFO", logger="vision.ai.conversation"):
            result = engine.run_once()
    finally:
        _cleanup_beeps(engine)

    assert result is False
    tags = [event[0] for event in timeline]
    # PAS de restart micro : il doit rester coupé pendant toute la pause.
    assert tags == ["mic_start"]  # uniquement le start initial du tour
    # Pas de warning « micro mort » : ce n'est pas un incident.
    assert not any(record.levelname == "WARNING" for record in caplog.records)
