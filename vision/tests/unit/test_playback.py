"""Tests de vision/audio/playback.py — I/O PURE injectable, AUCUN vrai
`aplay` lancé : run_cmd est remplacé par un faux constructeur de process qui
se contente d'enregistrer l'appel (cf. FakeProcess/make_run_cmd).
"""
import os
import threading
import time
import wave

import pytest

from vision.audio.playback import AudioPlayer, write_wav_tempfile


class FakeProcess:
    """Faux Popen : .wait() ne bloque jamais (pas de vrai sous-processus à
    attendre) — le thread lecteur d'AudioPlayer peut donc tourner à pleine
    vitesse dans les tests, sans dépendre d'aplay ni d'un vrai device audio."""

    def __init__(self, cmd):
        self.cmd = cmd

    def wait(self):
        return 0


def _make_run_cmd(calls: list, lock: threading.Lock):
    """run_cmd qui enregistre chaque commande lancée — thread-safe car
    AudioPlayer appelle run_cmd depuis SON thread lecteur, pas celui du test."""
    def run_cmd(cmd, stdout=None):
        with lock:
            calls.append(list(cmd))
        return FakeProcess(cmd)
    return run_cmd


def _wait_until(predicate, timeout=2.0):
    """Attend qu'une condition devienne vraie (le thread lecteur d'AudioPlayer
    tourne en tâche de fond — pas de moyen synchrone d'attendre UN play()
    précis sans exposer un hook de test dans la classe elle-même, cf.
    drain() qui reste le mécanisme de synchronisation normal côté prod)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


# --------------------------------------------------------------------------
# write_wav_tempfile() : wav valide, lisible, contenu fidèle.
# --------------------------------------------------------------------------

def test_write_wav_tempfile_produces_a_valid_readable_wav():
    pcm = bytes(range(256)) * 4
    sample_rate = 22050

    path = write_wav_tempfile(pcm, sample_rate)
    try:
        assert os.path.isfile(path)
        with wave.open(path, "rb") as wav_file:
            assert wav_file.getnchannels() == 1
            assert wav_file.getsampwidth() == 2
            assert wav_file.getframerate() == sample_rate
            assert wav_file.readframes(wav_file.getnframes()) == pcm
    finally:
        os.remove(path)


# --------------------------------------------------------------------------
# play() : passe par la file séquentielle (aplay invoqué avec le bon device).
# --------------------------------------------------------------------------

def test_play_enqueues_and_worker_calls_aplay_with_device():
    calls, lock = [], threading.Lock()
    player = AudioPlayer("mixette", run_cmd=_make_run_cmd(calls, lock))
    try:
        player.play(b"\x00\x01" * 10, 22050)
        player.drain()

        with lock:
            assert len(calls) == 1
            cmd = calls[0]
        assert cmd[0] == "aplay"
        assert "-D" in cmd and "mixette" in cmd
    finally:
        player.stop()


def test_play_removes_the_temp_wav_after_playback():
    calls, lock = [], threading.Lock()
    written_paths = []

    def run_cmd(cmd, stdout=None):
        with lock:
            calls.append(list(cmd))
            written_paths.append(cmd[-1])  # dernier argument = chemin du wav
        return FakeProcess(cmd)

    player = AudioPlayer("mixette", run_cmd=run_cmd)
    try:
        player.play(b"\x00\x01" * 10, 22050)
        player.drain()
    finally:
        player.stop()

    assert written_paths
    assert not os.path.exists(written_paths[0])  # nettoyage best-effort après lecture


def test_play_pipeline_n_plus_1_can_be_enqueued_while_n_plays():
    # Sémantique clé du proto validé : play() ne bloque JAMAIS, même si un
    # précédent play() n'a pas fini de jouer — les deux appels reviennent
    # immédiatement, le thread lecteur les enchaîne dans l'ORDRE d'arrivée.
    calls, lock = [], threading.Lock()
    player = AudioPlayer("mixette", run_cmd=_make_run_cmd(calls, lock))
    try:
        start = time.monotonic()
        player.play(b"N", 22050)
        player.play(b"N+1", 22050)
        elapsed = time.monotonic() - start
        assert elapsed < 0.5  # aucun blocage : les deux enqueue sont quasi instantanés

        player.drain()
        with lock:
            assert len(calls) == 2
    finally:
        player.stop()


# --------------------------------------------------------------------------
# play_async_raw() : fire-and-forget, HORS de la file séquentielle.
# --------------------------------------------------------------------------

def test_play_async_raw_calls_aplay_directly_without_queue():
    calls, lock = [], threading.Lock()
    player = AudioPlayer("mixette", run_cmd=_make_run_cmd(calls, lock))
    try:
        player.play_async_raw("/tmp/bips.wav")
        # Appel synchrone et direct : pas besoin de drain()/d'attente, le
        # run_cmd fake a déjà été invoqué au retour de play_async_raw().
        with lock:
            assert len(calls) == 1
            cmd = calls[0]
        assert cmd == ["aplay", "-q", "-D", "mixette", "/tmp/bips.wav"]
    finally:
        player.stop()


def test_play_async_raw_does_not_block_on_queued_play():
    # Les bips (play_async_raw) doivent pouvoir jouer même si la file
    # séquentielle est occupée à jouer autre chose — ils ne passent pas par
    # elle, cf. docstring de module.
    calls, lock = [], threading.Lock()
    player = AudioPlayer("mixette", run_cmd=_make_run_cmd(calls, lock))
    try:
        player.play(b"N", 22050)  # occupe potentiellement le thread lecteur
        player.play_async_raw("/tmp/bips.wav")
        assert _wait_until(lambda: len(calls) >= 1)
    finally:
        player.stop()


# --------------------------------------------------------------------------
# drain() / stop() : synchronisation et arrêt propre du thread.
# --------------------------------------------------------------------------

def test_drain_blocks_until_queue_is_empty():
    calls, lock = [], threading.Lock()
    player = AudioPlayer("mixette", run_cmd=_make_run_cmd(calls, lock))
    try:
        player.play(b"a", 22050)
        player.play(b"b", 22050)
        player.play(b"c", 22050)
        player.drain()
        with lock:
            assert len(calls) == 3
    finally:
        player.stop()


def test_stop_terminates_the_worker_thread():
    player = AudioPlayer("mixette", run_cmd=_make_run_cmd([], threading.Lock()))
    player.stop()
    assert not player._thread.is_alive()
