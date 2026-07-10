"""Reconnaissance vocale (STT) — interface + implémentation faster-whisper locale.

QUOI le Protocol SttEngine : point de swap explicite. Ce module fixe le
      CONTRAT (pcm + sample_rate -> texte), pas l'implémentation — la
      migration prévue vers whisper_ros (V3, cf. ARCHITECTURE.md) n'aura qu'à
      fournir une nouvelle classe respectant ce même Protocol, sans toucher à
      vision.ai.conversation (qui ne connaît que l'interface, injectée au
      constructeur de ConversationEngine). FasterWhisperStt est le choix
      RETENU pour V2 (local, pas d'appel réseau ni de latence API), mais n'est
      pas la seule implémentation possible.
POURQUOI l'import faster_whisper est DIFFÉRÉ (dans __init__, pas en tête de
      module) : faster_whisper n'est PAS dans requirements-test.txt (poids/
      compilation ARM hors du périmètre CI) — un import en tête de module
      casserait la collecte pytest en CI dès qu'un autre fichier importe
      vision.ai.stt (même sans jamais instancier FasterWhisperStt).
"""
from __future__ import annotations

import os
import tempfile
import wave
from typing import Protocol


class SttEngine(Protocol):
    """Contrat minimal attendu par vision.ai.conversation.ConversationEngine."""

    def transcribe(self, pcm: bytes, sample_rate: int) -> str:
        ...


class FasterWhisperStt:
    """STT local via faster-whisper (backend CTranslate2, CPU int8 — cible
    Raspberry Pi, pas de GPU)."""

    def __init__(self, model_name: str = "base", language: str = "fr"):
        # Import différé : voir docstring de module.
        from faster_whisper import WhisperModel

        # device="cpu" + compute_type="int8" : seule combinaison réaliste sur
        # un Pi (pas de CUDA) — int8 réduit la mémoire/latence au prix d'une
        # légère perte de précision, acceptable pour des réponses courtes
        # scéniques (cf. AI_REALTIME_RULES).
        self._model = WhisperModel(model_name, device="cpu", compute_type="int8")
        self._language = language

    def transcribe(self, pcm: bytes, sample_rate: int) -> str:
        # faster-whisper attend un chemin de fichier (ou un tableau numpy) :
        # on passe par un wav temporaire, le plus simple pour rester
        # cohérent avec le reste du repo (vision.audio.playback fait de même).
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            with wave.open(path, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(pcm)

            # beam_size=1 : recherche gloutonne (pas de beam search) — plus
            # rapide, seul compromis tenable pour une latence scénique
            # acceptable (proto validé du 10/07) ; la qualité perdue est
            # marginale sur des énoncés courts.
            segments, _ = self._model.transcribe(path, language=self._language, beam_size=1)
            return " ".join(segment.text.strip() for segment in segments).strip()
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
