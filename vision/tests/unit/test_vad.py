"""Tests de vision/audio/vad.py — logique PURE, stdlib uniquement (aucun
micro/pyaudio requis : EnergyVad ne consomme que des niveaux `float` déjà
calculés, fournis en dur par les tests).

frame_ms=50 partout : divise exactement calibration_ms (1000), preroll_ms
(450) et end_silence_ms (600) par défaut de VadConfig, ce qui permet
d'asserter des comptes de frames exacts sans arrondi ambigu.
"""
import statistics

from vision.audio.vad import EnergyVad, VadConfig, VadEvent, VadState

FRAME_MS = 50


def _feed_calibration(vad, config, level=4.0):
    """Nourrit la calibration jusqu'à son terme avec un niveau constant ;
    la calibration n'émet jamais de VadEvent."""
    for _ in range(config.calibration_ms // FRAME_MS):
        assert vad.feed(level) is None
    assert vad.state is VadState.IDLE


def _start_speech(config):
    """Calibre puis déclenche un début de parole (3 frames consécutives fortes).
    Retourne (vad, loud, quiet) — le niveau "loud"/"quiet" est calculé à partir
    du seuil calibré, valable pour toute la suite du test (seuil déjà fixé)."""
    vad = EnergyVad(config, frame_ms=FRAME_MS)
    _feed_calibration(vad, config, level=1.0)
    threshold = vad.threshold
    loud, quiet = threshold + 100.0, threshold - 0.5
    for _ in range(3):
        vad.feed(loud)
    assert vad.state is VadState.SPEECH
    return vad, loud, quiet


# --------------------------------------------------------------------------
# Calibration.
# --------------------------------------------------------------------------

def test_calibration_computes_median_times_factor():
    config = VadConfig(threshold_factor=1.3)
    vad = EnergyVad(config, frame_ms=FRAME_MS)
    assert vad.state is VadState.CALIBRATING
    assert vad.threshold is None

    n = config.calibration_ms // FRAME_MS  # 20 à défaut
    levels = [2.0, 4.0, 6.0]
    fed = (levels * ((n // len(levels)) + 1))[:n]  # séquence déterministe, médiane = 4.0
    for level in fed:
        assert vad.feed(level) is None

    assert vad.state is VadState.IDLE
    assert vad.threshold == statistics.median(fed) * config.threshold_factor


def test_calibration_with_only_silence_uses_min_floor():
    # Bruit de fond nul (que des 0.0) : la médiane vaut 0, en dessous de
    # min_floor -> le seuil doit retomber sur min_floor*threshold_factor, PAS
    # sur 0 (un seuil nul déclencherait sur le moindre souffle résiduel).
    config = VadConfig(threshold_factor=1.3, min_floor=1.0)
    vad = EnergyVad(config, frame_ms=FRAME_MS)
    _feed_calibration(vad, config, level=0.0)

    assert vad.threshold == config.min_floor * config.threshold_factor

    # Seuil stable en IDLE : du bruit nul en continu ne doit jamais déclencher.
    for _ in range(50):
        assert vad.feed(0.0) is None
    assert vad.state is VadState.IDLE


# --------------------------------------------------------------------------
# Déclenchement (IDLE -> SPEECH).
# --------------------------------------------------------------------------

def test_speech_start_after_three_consecutive_frames_above_threshold():
    config = VadConfig()
    vad = EnergyVad(config, frame_ms=FRAME_MS)
    _feed_calibration(vad, config, level=1.0)
    loud = vad.threshold + 100.0

    # Deux frames au-dessus du seuil : pas encore de déclenchement (il en
    # faut 3 consécutives, cf. contrat).
    assert vad.feed(loud) is None
    assert vad.feed(loud) is None
    assert vad.state is VadState.IDLE

    # Troisième frame consécutive : déclenchement, avec le nombre exact de
    # frames de pré-roll demandées à l'appelant (preroll_ms // frame_ms).
    event = vad.feed(loud)
    assert event == VadEvent(kind="speech_start",
                              preroll_frames=config.preroll_ms // FRAME_MS)
    assert vad.state is VadState.SPEECH


def test_non_consecutive_loud_frames_do_not_trigger():
    # Un pic isolé (toux, clic) entrecoupé de niveaux faibles ne doit jamais
    # déclencher : le compteur de frames consécutives doit se réinitialiser.
    config = VadConfig()
    vad = EnergyVad(config, frame_ms=FRAME_MS)
    _feed_calibration(vad, config, level=1.0)
    loud, quiet = vad.threshold + 100.0, vad.threshold - 0.5

    assert vad.feed(loud) is None
    assert vad.feed(quiet) is None  # casse la séquence
    assert vad.feed(loud) is None
    assert vad.feed(loud) is None
    assert vad.state is VadState.IDLE  # toujours pas 3 consécutives


# --------------------------------------------------------------------------
# Fin de phrase (SPEECH -> IDLE), silence et max_duration.
# --------------------------------------------------------------------------

def test_brief_dip_under_600ms_does_not_cut_speech():
    config = VadConfig()
    vad, loud, quiet = _start_speech(config)
    end_silence_frames = config.end_silence_ms // FRAME_MS  # 12 à défaut

    # Silence pendant moins que end_silence_ms (11 frames < 12), puis retour
    # au-dessus du seuil : la phrase ne doit PAS être coupée (le compteur de
    # silence continu doit se réinitialiser sur un niveau fort).
    for _ in range(end_silence_frames - 1):
        assert vad.feed(quiet) is None
    assert vad.feed(loud) is None
    assert vad.state is VadState.SPEECH


def test_speech_ends_after_600ms_of_continuous_silence():
    config = VadConfig()
    vad, loud, quiet = _start_speech(config)
    end_silence_frames = config.end_silence_ms // FRAME_MS

    for _ in range(end_silence_frames - 1):
        assert vad.feed(quiet) is None
    event = vad.feed(quiet)  # dernière frame : silence continu atteint

    assert event == VadEvent(kind="speech_end", reason="silence")
    assert vad.state is VadState.IDLE


def test_max_utterance_ends_speech_with_max_duration_reason():
    # max_utterance_ms court (500 = 10 frames à 50ms) pour un test rapide,
    # avec du son CONTINU au-dessus du seuil (pas de silence) : seul le
    # garde-fou de durée doit couper la phrase. speech_elapsed_ms démarre à 0
    # AU MOMENT du speech_start (la frame de déclenchement elle-même n'est pas
    # comptée, cf. EnergyVad._feed_idle) : il faut donc exactement max_frames
    # frames supplémentaires en SPEECH pour atteindre max_utterance_ms.
    config = VadConfig(max_utterance_ms=500)
    vad, loud, quiet = _start_speech(config)
    max_frames = config.max_utterance_ms // FRAME_MS  # 10

    for _ in range(max_frames - 1):
        assert vad.feed(loud) is None
    event = vad.feed(loud)

    assert event == VadEvent(kind="speech_end", reason="max_duration")
    assert vad.state is VadState.IDLE


# --------------------------------------------------------------------------
# Ré-armement : plusieurs tours de parole successifs.
# --------------------------------------------------------------------------

def test_two_successive_speech_rounds():
    config = VadConfig()
    vad, loud, quiet = _start_speech(config)
    end_silence_frames = config.end_silence_ms // FRAME_MS
    for _ in range(end_silence_frames - 1):
        vad.feed(quiet)
    end_event = vad.feed(quiet)
    assert end_event == VadEvent(kind="speech_end", reason="silence")
    assert vad.state is VadState.IDLE

    # Deuxième tour : le seuil calibré est conservé (pas de recalibration),
    # le déclenchement doit fonctionner à l'identique.
    assert vad.feed(loud) is None
    assert vad.feed(loud) is None
    start_event = vad.feed(loud)
    assert start_event.kind == "speech_start"
    assert vad.state is VadState.SPEECH
