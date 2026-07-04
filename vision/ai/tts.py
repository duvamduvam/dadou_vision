"""TTS OpenAI streaming + effet robot (recyclé de vision/ai/ai_audio.py, gardé tel quel).

Diffuse la réponse GPT en voix synthétique sur la sortie audio ALSA via
PyAudio, avec un effet de modulation ("effet robot") disponible en option.
"""
import logging
import time

import numpy as np
import openai
import pyaudio
import scipy.signal
from openai import OpenAI

from vision.ai.ai_static import AI_MODERATION
from vision.vision_config import config, get_secret


class AIAudio:
    """Synthèse vocale (TTS) OpenAI avec effet de voix robotique optionnel."""

    def __init__(self):
        chatgpt_key = get_secret("chatgpt_key")
        openai.api_key = chatgpt_key
        self.assistant = OpenAI(api_key=chatgpt_key)
        self.assistant.moderations.create(input=AI_MODERATION)

    def stream_to_speakers(self, msg, robot_effect=False) -> None:
        p = pyaudio.PyAudio()
        player_stream = None
        start_time = time.time()
        try:
            player_stream = p.open(format=pyaudio.paInt16, channels=1, rate=44100, output=True)

            with openai.audio.speech.with_streaming_response.create(
                    model="tts-1",
                    voice=config["gpt_voice"],
                    response_format="wav",
                    input=msg
            ) as response:
                logging.info("Time to first byte: %dms", int((time.time() - start_time) * 1000))
                for chunk in response.iter_bytes(chunk_size=1024):
                    player_stream.write(chunk)

            logging.info("Lecture terminée.")

        except Exception as e:
            logging.error("Erreur PyAudio: %s", e)

        #finally:
        #    player_stream.stop_stream()
        #    player_stream.close()
        #    p.terminate()

        logging.info("Done in %dms.", int((time.time() - start_time) * 1000))

    def resample_audio(self, audio_bytes, input_rate=24000, output_rate=44100):
        """ Convertit un flux audio brut de input_rate à output_rate """
        audio_np = np.frombuffer(audio_bytes, dtype=np.int16)
        resampled_audio = scipy.signal.resample(audio_np, int(len(audio_np) * output_rate / input_rate))
        return resampled_audio.astype(np.int16).tobytes()

    def add_distortion(self, audio_data, threshold=3000):
        """ Applique un effet de distorsion en écrêtant les échantillons au-delà d'un seuil. """
        audio_data = np.clip(audio_data, -threshold, threshold)
        return audio_data

    def apply_robotic_effect(self, audio_chunk, depth=0.7, rate=35):
        """ Applique un effet robotique (tremolo) au chunk audio. """
        audio_data = np.frombuffer(audio_chunk, dtype=np.int16)

        t = np.arange(len(audio_data))
        tremolo = (1.0 + depth * np.sin(2 * np.pi * rate * t / 24000))

        audio_data = audio_data * tremolo
        audio_data = self.add_distortion(audio_data)
        audio_data = np.clip(audio_data, -32768, 32767)

        return audio_data.astype(np.int16).tobytes()
