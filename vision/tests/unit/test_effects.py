"""Tests de vision/audio/effects.py — logique PURE (numpy seulement, cf.
requirements-test.txt), aucune dépendance openai/pyaudio/scipy.

QUOI : vérifie le comportement général (silence, longueur, borne d'amplitude)
       ET l'équivalence bit-à-bit avec l'ANCIENNE implémentation de
       AIAudio.apply_robotic_effect (vision/ai/tts.py, avant extraction) —
       c'est le test qui a servi de garde-fou pendant la modification de
       tts.py : s'il passe, la délégation n'a rien changé au comportement
       existant.
"""
import numpy as np
import pytest

from vision.audio.effects import add_distortion, apply_robotic_effect


def _sine_chunk(freq_hz=220.0, duration_s=0.1, sample_rate=22050, amplitude=8000):
    """Chunk témoin déterministe : sinusoïde 220 Hz, 0.1 s, int16 mono."""
    t = np.arange(int(duration_s * sample_rate))
    samples = (amplitude * np.sin(2 * np.pi * freq_hz * t / sample_rate)).astype(np.int16)
    return samples.tobytes()


def _old_apply_robotic_effect(audio_chunk, depth=0.7, rate=35):
    """Référence GELÉE : copie exacte de l'ancienne AIAudio.apply_robotic_effect
    (vision/ai/tts.py avant extraction vers vision.audio.effects), sample_rate
    24000 codé en dur inclus. Ne JAMAIS faire évoluer cette fonction : elle
    fige le comportement de référence pour le test d'équivalence ci-dessous."""
    audio_data = np.frombuffer(audio_chunk, dtype=np.int16)
    t = np.arange(len(audio_data))
    tremolo = (1.0 + depth * np.sin(2 * np.pi * rate * t / 24000))
    audio_data = audio_data * tremolo
    audio_data = np.clip(audio_data, -3000, 3000)  # ancien add_distortion(threshold=3000)
    audio_data = np.clip(audio_data, -32768, 32767)
    return audio_data.astype(np.int16).tobytes()


# --------------------------------------------------------------------------
# Comportements généraux.
# --------------------------------------------------------------------------

def test_silence_stays_silence():
    silence = np.zeros(500, dtype=np.int16).tobytes()
    result = apply_robotic_effect(silence)
    assert np.frombuffer(result, dtype=np.int16).tolist() == [0] * 500


def test_length_is_preserved():
    chunk = _sine_chunk()
    result = apply_robotic_effect(chunk)
    assert len(result) == len(chunk)  # même nombre d'échantillons int16 (2 octets chacun)


def test_amplitude_is_bounded_by_regain_to():
    # amplitude d'entrée volontairement forte (32000, proche du max int16) pour
    # que le regain pousse vers la borne haute — vérifie que le clip final
    # protège bien contre un dépassement au-delà de regain_to (à la marge du
    # clip int16 standard ±32768, cf. docstring du module).
    chunk = _sine_chunk(amplitude=32000)
    regain_to = 20000
    result = apply_robotic_effect(chunk, regain_to=regain_to)
    samples = np.frombuffer(result, dtype=np.int16)
    assert np.max(np.abs(samples)) <= regain_to


def test_add_distortion_clips_to_threshold():
    samples = np.array([-5000, -100, 0, 100, 5000], dtype=np.int64)
    clipped = add_distortion(samples, threshold=3000)
    assert clipped.tolist() == [-3000, -100, 0, 100, 3000]


# --------------------------------------------------------------------------
# Équivalence avec l'ancienne implémentation (garde-fou de la refonte tts.py).
# --------------------------------------------------------------------------

def test_equivalence_avec_ancienne_implementation():
    chunk = _sine_chunk()

    # Référence : ancienne implémentation (sans regain, threshold 3000 en dur),
    # puis regain appliqué SÉPARÉMENT (à la main, hors production) pour obtenir
    # ce que la nouvelle implémentation doit produire nativement.
    old_bytes = _old_apply_robotic_effect(chunk, depth=0.7, rate=35)
    old_samples = np.frombuffer(old_bytes, dtype=np.int16)
    regain_to = 20000
    clip = 3000
    regained = np.clip(old_samples.astype(np.float64) * (regain_to / clip), -32768, 32767)
    expected = regained.astype(np.int16).tobytes()

    # Nouvelle implémentation : mêmes paramètres (sample_rate=24000 explicite
    # pour coller à l'ancien codage en dur), regain_to=20000.
    actual = apply_robotic_effect(chunk, depth=0.7, rate_hz=35.0, sample_rate=24000,
                                   clip=clip, regain_to=regain_to)

    assert actual == expected


def test_equivalence_sans_regain_est_identique_a_l_ancienne_implementation():
    # regain_to == clip => facteur de regain = 1 => sortie strictement
    # identique à l'ancienne implémentation, sans même repasser par un calcul
    # "à la main" — c'est exactement ce que fait tts.py après la délégation
    # (cf. vision/ai/tts.py::AIAudio.apply_robotic_effect).
    chunk = _sine_chunk()
    old_bytes = _old_apply_robotic_effect(chunk, depth=0.7, rate=35)
    new_bytes = apply_robotic_effect(chunk, depth=0.7, rate_hz=35.0, sample_rate=24000,
                                      clip=3000, regain_to=3000)
    assert new_bytes == old_bytes
