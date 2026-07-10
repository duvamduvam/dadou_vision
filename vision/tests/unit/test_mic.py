"""Tests de vision/audio/mic.py — I/O PURE injectable, AUCUN vrai `arecord`
lancé : run_cmd est remplacé par un faux constructeur de process (stdout =
io.BytesIO scripté), cf. FakeProcess ci-dessous.
"""
import io

import numpy as np
import pytest

from vision.audio.mic import MicCapture


class FakeProcess:
    """Faux Popen : stdout est un flux bytes préparé à l'avance. terminate()
    ferme le flux (imite un process tué) ; poll() renvoie None tant que non
    terminé (comme un vrai Popen en cours d'exécution)."""

    def __init__(self, stdout_bytes: bytes):
        self.stdout = io.BytesIO(stdout_bytes)
        self._terminated = False

    def poll(self):
        return None if not self._terminated else 0

    def terminate(self):
        self._terminated = True

    def wait(self):
        return 0


def _make_run_cmd(stdout_bytes: bytes, calls: list):
    """Fabrique un run_cmd qui enregistre l'argv reçu (pour vérifier la
    commande arecord construite) et renvoie toujours un FakeProcess sur le
    même flux scripté."""
    def run_cmd(cmd, stdout=None):
        calls.append(cmd)
        return FakeProcess(stdout_bytes)
    return run_cmd


# --------------------------------------------------------------------------
# start() : construction de la commande arecord, idempotence.
# --------------------------------------------------------------------------

def test_start_builds_expected_arecord_command():
    calls = []
    mic = MicCapture("casque_mic", sample_rate=16000, frame_ms=30,
                      run_cmd=_make_run_cmd(b"", calls))
    mic.start()
    assert calls == [[
        "arecord", "-q",
        "-D", "casque_mic",
        "-f", "S16_LE",
        "-r", "16000",
        "-c", "1",
        "-t", "raw",
    ]]


def test_start_is_idempotent_while_process_alive():
    calls = []
    mic = MicCapture("casque_mic", run_cmd=_make_run_cmd(b"", calls))
    mic.start()
    mic.start()  # deuxième appel : ne doit PAS relancer un process
    assert len(calls) == 1


def test_start_after_stop_relaunches_process():
    calls = []
    mic = MicCapture("casque_mic", run_cmd=_make_run_cmd(b"", calls))
    mic.start()
    mic.stop()
    mic.start()
    assert len(calls) == 2


# --------------------------------------------------------------------------
# read_frame() : taille de trame exacte, flux mort -> None.
# --------------------------------------------------------------------------

def test_read_frame_returns_exact_frame_size_in_bytes():
    sample_rate, frame_ms = 16000, 30
    # 480 échantillons/trame * 2 octets (S16_LE mono) = 960 octets.
    expected_frame_bytes = 960
    stdout_bytes = bytes(range(256)) * 10  # largement assez pour 2 trames

    mic = MicCapture("casque_mic", sample_rate=sample_rate, frame_ms=frame_ms,
                      run_cmd=_make_run_cmd(stdout_bytes, []))
    mic.start()

    frame = mic.read_frame()
    assert frame is not None
    assert len(frame) == expected_frame_bytes


def test_read_frame_returns_none_when_stream_exhausted():
    # Flux trop court pour fournir ne serait-ce qu'une trame complète : EOF
    # immédiat au sens de read_frame (cf. docstring MicCapture.read_frame).
    mic = MicCapture("casque_mic", sample_rate=16000, frame_ms=30,
                      run_cmd=_make_run_cmd(b"\x00" * 10, []))
    mic.start()
    assert mic.read_frame() is None


def test_read_frame_returns_none_when_never_started():
    mic = MicCapture("casque_mic", run_cmd=_make_run_cmd(b"", []))
    assert mic.read_frame() is None


# --------------------------------------------------------------------------
# frame_rms() : silence -> 0, amplitude constante -> RMS = cette amplitude.
# --------------------------------------------------------------------------

def test_frame_rms_of_silence_is_zero():
    mic = MicCapture("casque_mic", run_cmd=_make_run_cmd(b"", []))
    silence = np.zeros(100, dtype=np.int16).tobytes()
    assert mic.frame_rms(silence) == 0.0


def test_frame_rms_of_constant_amplitude_equals_that_amplitude():
    # RMS d'un signal carré d'amplitude constante A vaut A (racine de la
    # moyenne de A^2 partout).
    mic = MicCapture("casque_mic", run_cmd=_make_run_cmd(b"", []))
    samples = np.full(100, 1000, dtype=np.int16).tobytes()
    assert mic.frame_rms(samples) == pytest.approx(1000.0)


def test_frame_rms_of_empty_frame_is_zero():
    mic = MicCapture("casque_mic", run_cmd=_make_run_cmd(b"", []))
    assert mic.frame_rms(b"") == 0.0


# --------------------------------------------------------------------------
# preroll() / ring buffer : dernières trames, purge au stop().
# --------------------------------------------------------------------------

def test_preroll_keeps_only_last_n_frames_in_order():
    # frame_ms=1000/rate*... : on choisit rate/frame_ms pour que chaque trame
    # fasse exactement 2 octets (1 échantillon) — simplifie la lecture du
    # test (chaque trame = un octet-paire identifiable).
    sample_rate, frame_ms = 1000, 1  # 1 échantillon/trame = 2 octets/trame
    frames_data = [bytes([i, 0]) for i in range(5)]  # 5 trames distinctes
    stdout_bytes = b"".join(frames_data)

    mic = MicCapture("casque_mic", sample_rate=sample_rate, frame_ms=frame_ms,
                      preroll_frames=3, run_cmd=_make_run_cmd(stdout_bytes, []))
    mic.start()

    for _ in range(5):
        mic.read_frame()

    # Seules les 3 DERNIÈRES trames (2,3,4) doivent rester, dans l'ordre.
    assert mic.preroll() == frames_data[2] + frames_data[3] + frames_data[4]


def test_preroll_includes_the_frame_just_read():
    # cf. docstring MicCapture.read_frame : preroll() appelé juste après
    # read_frame() inclut cette trame comme entrée la plus récente — évite
    # tout doublon côté appelant (vision.ai.conversation ne fait PAS
    # preroll() + frame, seulement preroll()).
    sample_rate, frame_ms = 1000, 1
    stdout_bytes = bytes([42, 0])

    mic = MicCapture("casque_mic", sample_rate=sample_rate, frame_ms=frame_ms,
                      run_cmd=_make_run_cmd(stdout_bytes, []))
    mic.start()

    frame = mic.read_frame()
    assert mic.preroll().endswith(frame)


def test_stop_purges_the_ring_buffer():
    # Piège documenté (cf. docstring MicCapture.stop) : purge volontaire,
    # anti-larsen — un restart ne doit JAMAIS voir de trames pré-arrêt.
    sample_rate, frame_ms = 1000, 1
    stdout_bytes = bytes([1, 0]) * 5

    mic = MicCapture("casque_mic", sample_rate=sample_rate, frame_ms=frame_ms,
                      run_cmd=_make_run_cmd(stdout_bytes, []))
    mic.start()
    mic.read_frame()
    mic.read_frame()
    assert mic.preroll() != b""

    mic.stop()
    assert mic.preroll() == b""


def test_preroll_empty_before_any_frame_read():
    mic = MicCapture("casque_mic", run_cmd=_make_run_cmd(b"", []))
    assert mic.preroll() == b""
