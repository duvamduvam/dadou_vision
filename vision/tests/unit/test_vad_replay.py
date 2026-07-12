"""Tests de vision/audio/vad_replay.py (lot D0 outillage — rejeu du VAD de
PRODUCTION sur un enregistrement, cf. dadou_robot_ros/docs/
etude-declenchement-conversation.md §5.5/§7).

QUOI : les tests utilisent une VRAIE instance vision.audio.vad.EnergyVad
       (RÈGLE du projet : le rejeu DOIT exécuter le même code que la prod,
       cf. docstring de vad_replay.py) mais avec une VadConfig ACCÉLÉRÉE
       (calibration/silence courts) — la VadConfig de production
       (vision_config.config["chat_vad"]) calibre sur 1 s réelle, bien trop
       long à simuler frame par frame ici. Seule la MACHINE À ÉTATS est
       vérifiée (déjà testée indépendamment dans test_vad.py) ; les vraies
       valeurs de production sont validées par la campagne D0 elle-même,
       hors CI.
"""
import wave

import numpy as np
import pytest

from vision.audio import vad_replay
from vision.audio.playback import write_wav_tempfile
from vision.audio.vad import EnergyVad, VadConfig
from vision.vision_config import config

FRAME_MS = 30
SAMPLE_RATE = 16000
# Nombre d'échantillons par trame de 30 ms à 16 kHz — MÊME formule que
# vision.audio.vad_replay.replay (sample_rate * frame_ms / 1000).
SAMPLES_PER_FRAME = int(round(SAMPLE_RATE * FRAME_MS / 1000))


def _frame(amplitude: int) -> bytes:
    """Une trame mono 16 bits à amplitude CONSTANTE : le RMS d'un signal
    constant vaut exactement son amplitude (frame_rms == amplitude), ce qui
    rend les franchissements de seuil du VAD prévisibles ici au frame près."""
    samples = np.full(SAMPLES_PER_FRAME, amplitude, dtype=np.int16)
    return samples.tobytes()


def _fast_vad_config() -> VadConfig:
    """VadConfig accélérée pour les tests — cf. docstring de module pour le
    pourquoi (calibration/silence de production bien trop longs à simuler)."""
    return VadConfig(
        threshold_factor=1.3, preroll_ms=0, end_silence_ms=60,
        calibration_ms=30, max_utterance_ms=100_000, min_floor=1.0,
    )


def _build_pcm() -> bytes:
    """Silence (1 trame de calibration + 2 trames IDLE) puis salve de bruit
    (5 trames : speech_start confirmé à la 3e, cf. _FRAMES_TO_CONFIRM_SPEECH
    dans vision.audio.vad) puis retour au silence (speech_end confirmé après
    2 trames de silence continu, cf. end_silence_ms=60 ms ci-dessus) + 1
    trame de silence surnuméraire (vérifie qu'aucun évènement ne suit)."""
    silence = _frame(0)
    noise = _frame(5000)  # très au-dessus du seuil calibré (~1.3)
    frames = [
        silence, silence, silence,           # calibration + 2x IDLE
        noise, noise, noise, noise, noise,   # confirmation à la 3e -> speech_start
        silence, silence,                    # confirmation à la 2e -> speech_end
        silence,                             # surnuméraire : aucun évènement attendu
    ]
    return b"".join(frames)


# ---------------------------------------------------------------------------
# replay() : la machine à états EnergyVad tourne bien identiquement en rejeu.
# ---------------------------------------------------------------------------

def test_replay_detects_speech_start_and_speech_end_at_expected_frames():
    pcm = _build_pcm()
    vad = EnergyVad(_fast_vad_config(), frame_ms=FRAME_MS)

    events = vad_replay.replay(pcm, SAMPLE_RATE, FRAME_MS, vad)

    # speech_start confirmé à la fin de la 6e trame (index 5, 0-based) ->
    # t=(5+1)*0.030=0.180s ; speech_end confirmé à la fin de la 10e trame
    # (index 9) -> t=(9+1)*0.030=0.300s. La trame surnuméraire (index 10)
    # ne produit RIEN (déjà de retour en IDLE).
    assert events == [
        (pytest.approx(0.18), "speech_start"),
        (pytest.approx(0.30), "speech_end"),
    ]


def test_replay_wav_synthetique_silence_pur_ne_declenche_rien():
    # Rejeu sur un wav synthétique tout silence (chargé via _load_wav_pcm,
    # donc le VRAI chemin de lecture wav) : aucun évènement, le seuil calibré
    # n'est jamais franchi.
    pcm = _frame(0) * 10
    path = write_wav_tempfile(pcm, SAMPLE_RATE)
    try:
        loaded_pcm, sample_rate = vad_replay._load_wav_pcm(path)
        vad = EnergyVad(_fast_vad_config(), frame_ms=FRAME_MS)
        events = vad_replay.replay(loaded_pcm, sample_rate, FRAME_MS, vad)
    finally:
        import os
        os.remove(path)

    assert events == []


# ---------------------------------------------------------------------------
# _load_wav_pcm() : refus explicite d'un format non conforme (pas de
# resampling, cf. docstring de module — mieux vaut un message clair qu'une
# mesure trompeuse).
# ---------------------------------------------------------------------------

def test_load_wav_pcm_rejects_non_mono_16bit(tmp_path):
    path = str(tmp_path / "stereo.wav")
    with wave.open(path, "wb") as wav_file:
        wav_file.setnchannels(2)   # non conforme : le pipeline chat est mono
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(b"\x00\x00\x00\x00" * 10)

    with pytest.raises(ValueError, match="16 kHz mono"):
        vad_replay._load_wav_pcm(path)


# ---------------------------------------------------------------------------
# main() : CLI bout en bout (résumé imprimé, fichier non conforme signalé
# sans bloquer le traitement des autres — best-effort, cf. docstring).
# ---------------------------------------------------------------------------

def test_main_traite_un_wav_conforme_et_signale_un_wav_non_conforme(
        tmp_path, capsys, monkeypatch):
    # La config globale chat_vad est remplacée par la version accélérée : le
    # test n'a pas à attendre la calibration 1 s réelle de production (même
    # dict que celui lu par main(), cf. import déférré dans vad_replay.main).
    monkeypatch.setitem(config, "chat_vad", _fast_vad_config())

    good_path = write_wav_tempfile(_build_pcm(), SAMPLE_RATE)
    bad_path = str(tmp_path / "stereo.wav")
    with wave.open(bad_path, "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(b"\x00\x00\x00\x00" * 10)

    try:
        exit_code = vad_replay.main([good_path, bad_path])
    finally:
        import os
        os.remove(good_path)

    captured = capsys.readouterr()
    # Le fichier conforme produit un résumé avec ses deux évènements et son
    # décompte de déclenchements.
    assert "speech_start" in captured.out
    assert "speech_end" in captured.out
    assert "Déclenchements (speech_start)  : 1" in captured.out
    # Le fichier non conforme est signalé (stderr) SANS empêcher le résumé
    # du fichier conforme d'être imprimé (best-effort).
    assert "16 kHz mono" in captured.err
    # exit_code non nul : au moins un fichier a échoué (signal pour un script
    # appelant, ex. une future campagne automatisée).
    assert exit_code == 1


def test_main_sans_argument_affiche_l_usage(capsys):
    exit_code = vad_replay.main([])

    assert exit_code == 2
    assert "Usage" in capsys.readouterr().err
