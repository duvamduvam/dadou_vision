"""Bips de "réflexion" (pendant que GPT génère sa réponse, avant le premier
delta utile) — logique PURE, numpy uniquement (cf. requirements-test.txt).

QUOI : suite de bips sinusoïdaux, notes tirées d'une gamme pentatonique (son
       "electronique/pensif" du prototype validé), enveloppe anti-clic (5 ms
       de fade in/out) pour éviter les craquements audio d'un raccord brutal
       à 0 -> amplitude -> 0, tronquée/complétée pour occuper EXACTEMENT
       duration_s (l'appelant (chat_node V2) sait exactement quand il pourra
       streamer le premier chunk TTS et doit pouvoir aligner le buffer bips
       en conséquence, sans dérive d'une frame).
"""
from __future__ import annotations

import numpy as np

# Gamme pentatonique du prototype validé (do5-ré5-mi5-sol5-la5 environ, en Hz) —
# choisie empiriquement pour un son "réflexion" qui ne sonne ni alarmant
# (pas de dissonance possible dans une gamme pentatonique) ni monotone
# (5 notes distinctes, tirage aléatoire à chaque bip).
PENTATONIC_HZ = (523.25, 659.25, 784.0, 880.0, 1046.5)

# Durée du fade anti-clic (in ET out) sur chaque bip : une transition brutale
# 0 -> amplitude introduit un "clic" audible à haute fréquence (discontinuité
# de la dérivée du signal) — 5 ms est la valeur validée sur le prototype,
# assez courte pour ne pas raccourcir perceptiblement le bip.
_FADE_S = 0.005


def build_thinking_beeps(duration_s: float, *, sample_rate: int = 22050,
                          amplitude: int = 14000, beep_ms: int = 120,
                          gap_ms: int = 180, seed: int | None = None) -> bytes:
    """Construit une piste de bips int16 mono d'EXACTEMENT duration_s secondes.

    seed : fixe la séquence de notes tirées dans PENTATONIC_HZ (déterminisme
           pour les tests et, en prod, pour un rejeu identique si besoin —
           None laisse numpy.random tirer une graine système, comportement
           normal de production)."""
    if duration_s <= 0:
        return b""

    rng = np.random.default_rng(seed)
    total_samples = int(round(duration_s * sample_rate))
    out = np.zeros(total_samples, dtype=np.int16)

    beep_samples = int(round(beep_ms / 1000.0 * sample_rate))
    gap_samples = int(round(gap_ms / 1000.0 * sample_rate))
    fade_samples = max(1, int(round(_FADE_S * sample_rate)))

    pos = 0
    while pos < total_samples:
        # Chaque bip peut être tronqué (n < beep_samples) s'il déborde de la
        # durée totale demandée : c'est ce qui garantit la longueur exacte en
        # sortie, au prix d'un dernier bip potentiellement incomplet.
        n = min(beep_samples, total_samples - pos)
        if n <= 0:
            break

        freq = rng.choice(PENTATONIC_HZ)
        t = np.arange(n) / sample_rate
        wave = amplitude * np.sin(2 * np.pi * freq * t)

        # Enveloppe anti-clic : fade in sur les f premiers échantillons, fade
        # out sur les f derniers (f borné à n//2 pour un bip très court que le
        # troncage aurait réduit à presque rien — évite un chevauchement des
        # deux rampes qui inverserait l'enveloppe).
        f = min(fade_samples, n // 2)
        envelope = np.ones(n)
        if f > 0:
            ramp = np.linspace(0.0, 1.0, f)
            envelope[:f] = ramp
            envelope[-f:] = ramp[::-1]

        out[pos:pos + n] = (wave * envelope).astype(np.int16)
        pos += n + gap_samples

    return out.tobytes()
