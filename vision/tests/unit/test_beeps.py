"""Tests de vision/audio/beeps.py — logique PURE, numpy uniquement (cf.
requirements-test.txt).
"""
import numpy as np

from vision.audio.beeps import build_thinking_beeps


def test_length_is_exact_in_bytes():
    # int16 mono = 2 octets/échantillon ; longueur attendue = round(duration_s
    # * sample_rate) échantillons, PAS un multiple approximatif de beep+gap
    # (le dernier bip est tronqué pour tomber pile sur cette longueur).
    sample_rate = 22050
    duration_s = 0.5
    result = build_thinking_beeps(duration_s, sample_rate=sample_rate, seed=1)
    expected_samples = round(duration_s * sample_rate)
    assert len(result) == expected_samples * 2


def test_length_is_exact_for_various_durations():
    sample_rate = 16000
    for duration_s in (0.05, 0.3, 1.0, 2.37):
        result = build_thinking_beeps(duration_s, sample_rate=sample_rate, seed=1)
        expected_samples = round(duration_s * sample_rate)
        assert len(result) == expected_samples * 2, duration_s


def test_max_amplitude_does_not_exceed_amplitude_param():
    amplitude = 14000
    result = build_thinking_beeps(1.0, amplitude=amplitude, seed=42)
    samples = np.frombuffer(result, dtype=np.int16)
    assert np.max(np.abs(samples)) <= amplitude


def test_deterministic_with_fixed_seed():
    a = build_thinking_beeps(1.0, seed=7)
    b = build_thinking_beeps(1.0, seed=7)
    assert a == b


def test_different_seeds_can_produce_different_output():
    # Pas garanti à 100% en théorie (collision de tirage), mais avec 5 notes
    # possibles et plusieurs bips sur 1 seconde, la probabilité de collision
    # totale est négligeable — sert de garde-fou contre un seed ignoré par erreur.
    a = build_thinking_beeps(1.0, seed=1)
    b = build_thinking_beeps(1.0, seed=2)
    assert a != b


def test_zero_duration_returns_empty_bytes():
    assert build_thinking_beeps(0.0) == b""


def test_negative_duration_returns_empty_bytes():
    assert build_thinking_beeps(-1.0) == b""
