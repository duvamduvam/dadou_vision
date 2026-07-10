"""Synthèse vocale (TTS) locale via Piper — voix de Didier (V2 streaming).

POURQUOI Piper plutôt que le TTS OpenAI existant (vision/ai/tts.py) : ce
      dernier reste utilisé par le mode GPT-4o non-streamé (vision.ai.
      interactions) ; le mode conversation temps réel (V2) veut une voix
      LOCALE, sans latence réseau ni coût par phrase, dédiée au personnage
      Didier — Piper tourne sur le Pi 5 (proto validé du 10/07).
POURQUOI l'instance PiperVoice est chargée UNE SEULE FOIS, au constructeur
      (et jamais recréée à chaque appel de synthesize) : mesuré sur le proto,
      le CLI `piper` recharge le modèle .onnx à CHAQUE phrase (~2,6 s de
      latence par phrase) — inacceptable pour le rythme scénique visé
      (AI_REALTIME_RULES : 1-3 phrases courtes). Passer par l'API Python
      (PiperVoice.load une fois, réutilisée pour chaque synthesize) élimine
      ce rechargement.
POURQUOI l'import piper est DIFFÉRÉ (dans __init__, pas en tête de module) :
      piper-tts n'est PAS dans requirements-test.txt (poids/wheels ARM hors
      périmètre CI) — un import en tête de module casserait la collecte
      pytest en CI dès qu'un autre fichier importe vision.ai.tts_piper.
"""
from __future__ import annotations

import io
import wave
from typing import Tuple


class PiperTts:
    """Synthèse vocale locale (Piper), voix chargée une seule fois."""

    def __init__(self, voice_path: str):
        # Import différé : voir docstring de module.
        from piper import PiperVoice

        # Chargement UNIQUE du modèle .onnx — cf. docstring de module pour la
        # mesure (2,6 s/phrase) qui justifie ce choix par rapport au CLI.
        self._voice = PiperVoice.load(voice_path)

    def synthesize(self, text: str) -> Tuple[bytes, int]:
        """Synthétise `text` en PCM int16 mono. Retourne (pcm, sample_rate) —
        sample_rate est celui DE LA VOIX chargée (pas une constante fixe :
        chaque modèle Piper a son propre taux d'échantillonnage natif)."""
        buffer = io.BytesIO()
        # synthesize_wav écrit directement dans un wave.Wave_write ouvert :
        # au plus simple, en mémoire (pas de fichier temporaire nécessaire
        # pour ce sens-là, contrairement à stt.py qui doit passer un CHEMIN
        # à faster-whisper).
        with wave.open(buffer, "wb") as wav_writer:
            self._voice.synthesize_wav(text, wav_writer)

        buffer.seek(0)
        with wave.open(buffer, "rb") as wav_reader:
            sample_rate = wav_reader.getframerate()
            pcm = wav_reader.readframes(wav_reader.getnframes())
        return pcm, sample_rate
