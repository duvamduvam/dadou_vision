"""Effets audio (trémolo + distorsion) — logique PURE, extraite de
vision/ai/tts.py (AIAudio.apply_robotic_effect/add_distortion) pour devenir
testable en CI sans openai/pyaudio/scipy (seul numpy est requis, déjà
nécessaire ailleurs — cf. requirements-test.txt).

QUOI : même algorithme que l'ancienne méthode (trémolo sinusoïdal + clip de
       distorsion), mais avec deux différences volontaires par rapport à
       AIAudio.apply_robotic_effect d'origine :
         1. sample_rate est un PARAMÈTRE (l'ancien code codait 24000 en dur
            dans la formule du trémolo, alors même que stream_to_speakers
            ouvre le flux de sortie à 44100 Hz — un mélange jamais corrigé).
            tts.py continue à passer 24000 explicitement pour ne rien changer
            au comportement des appels existants (cf. commentaire dans tts.py).
         2. un REGAIN final ×(regain_to/clip) est appliqué après la distorsion,
            avant le clip int16 définitif. POURQUOI : validé sur le robot, le
            clip de distorsion à ±3000 (échelle int16 ±32767) laissait un
            niveau de sortie autour de -21 dB, beaucoup trop faible pour la
            scène — le regain ramène le signal distordu vers une amplitude
            exploitable (regain_to=20000 par défaut) sans changer la FORME du
            signal (la distorsion a déjà eu lieu à l'échelle ±clip, le regain
            est une simple mise à l'échelle post-distorsion).
"""
from __future__ import annotations

import numpy as np


def add_distortion(samples: np.ndarray, threshold: int = 3000) -> np.ndarray:
    """Écrête les échantillons au-delà de ±threshold (effet de distorsion).

    Identique à AIAudio.add_distortion d'origine — extrait ici tel quel pour
    que apply_robotic_effect puisse la réutiliser sans dépendre de tts.py."""
    return np.clip(samples, -threshold, threshold)


def apply_robotic_effect(chunk: bytes, *, depth: float = 0.7, rate_hz: float = 35.0,
                          sample_rate: int = 22050, clip: int = 3000,
                          regain_to: int = 20000) -> bytes:
    """Trémolo sinusoïdal + distorsion + regain, sur un chunk audio int16 mono.

    Pipeline (dans cet ordre, important pour l'équivalence avec l'ancienne
    implémentation — cf. test_effects.py::test_equivalence_avec_ancienne_implementation) :
      1. trémolo : audio * (1 + depth*sin(2*pi*rate_hz*t/sample_rate))
      2. distorsion : clip à ±clip (add_distortion)
      3. clip int16 large (±32768/32767) — hérité de l'ancien code, redondant
         une fois l'étape 2 passée (clip <= 32768 en pratique) mais conservé
         pour rester bit-à-bit identique à l'ancienne implémentation à ce stade
      4. cast en int16 : c'est ICI que se produit la quantification (troncature),
         AVANT le regain — le regain doit donc s'appliquer sur des échantillons
         déjà quantifiés en int16 pour que le test d'équivalence (qui rejoue le
         regain "à la main" sur la sortie de l'ancienne implémentation, donc
         elle aussi déjà quantifiée) retombe exactement sur les mêmes octets.
      5. regain : ×(regain_to/clip), reclip ±32768/32767, recast int16.
    """
    audio_data = np.frombuffer(chunk, dtype=np.int16)

    t = np.arange(len(audio_data))
    tremolo = 1.0 + depth * np.sin(2 * np.pi * rate_hz * t / sample_rate)

    audio_data = audio_data * tremolo
    audio_data = add_distortion(audio_data, threshold=clip)
    audio_data = np.clip(audio_data, -32768, 32767)
    # Quantification en int16 AVANT le regain (cf. docstring ci-dessus) : c'est
    # la sortie bit-à-bit de l'ancienne implémentation (sans regain).
    base = audio_data.astype(np.int16)

    if clip == 0:
        # Pas de distorsion configurée (clip désactivé) : le regain n'a pas de
        # référence d'échelle sensée, on renvoie la base telle quelle plutôt
        # que de diviser par zéro.
        return base.tobytes()

    regained = base.astype(np.float64) * (regain_to / clip)
    regained = np.clip(regained, -32768, 32767).astype(np.int16)
    return regained.tobytes()
