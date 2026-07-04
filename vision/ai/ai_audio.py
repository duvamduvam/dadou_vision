import logging
import time

import numpy as np
import openai
import pyaudio
from openai import OpenAI
import scipy.signal

from dadou_utils_ros.utils_static import GPT_VOICE, ALSA_CHANNEL
from vision.ai.ai_static import AI_MODERATION, AI_INSTRUCTIONS, CHAT_GPT_KEY
from vision.vision_config import config


class AIAudio:

    def __init__(self):

        self.chatgpt_key = CHAT_GPT_KEY
        openai.api_key = CHAT_GPT_KEY
        self.assistant = OpenAI(api_key=CHAT_GPT_KEY)
        self.assistant.moderations.create(input=AI_MODERATION)

    def stream_to_speakers(self, msg, robot_effect=False) -> None:
        p = pyaudio.PyAudio()
        player_stream = None
        try:
            player_stream = p.open(format=pyaudio.paInt16, channels=1, rate=44100, output=True)
            start_time = time.time()

            with openai.audio.speech.with_streaming_response.create(
                    model="tts-1",
                    voice=config[GPT_VOICE],
                    response_format="wav",
                    input=msg
            ) as response:
                logging.info(f"Time to first byte: {int((time.time() - start_time) * 1000)}ms")
                for chunk in response.iter_bytes(chunk_size=1024):
                    player_stream.write(chunk)

            logging.info("Lecture terminée.")

        except Exception as e:
            logging.error(f"Erreur PyAudio: {e}")

        #finally:
        #    player_stream.stop_stream()
        #    player_stream.close()
        #    p.terminate()

        logging.info(f"Done in {int((time.time() - start_time) * 1000)}ms.")

    def resample_audio(self, audio_bytes, input_rate=24000, output_rate=44100):
        """ Convertit un flux audio brut de input_rate à output_rate """
        audio_np = np.frombuffer(audio_bytes, dtype=np.int16)
        resampled_audio = scipy.signal.resample(audio_np, int(len(audio_np) * output_rate / input_rate))
        return resampled_audio.astype(np.int16).tobytes()

    def add_distortion(self, audio_data, threshold=3000):
        """ Applique un effet de distorsion en écrêtant les échantillons au-delà d'un seuil. """
        # Limite les valeurs audio au seuil spécifié
        audio_data = np.clip(audio_data, -threshold, threshold)
        return audio_data

    def apply_robotic_effect(self, audio_chunk, depth=0.7, rate=35):
        """ Applique un effet robotique (tremolo) au chunk audio. """
        # Conversion de l'audio en numpy array pour le traitement
        audio_data = np.frombuffer(audio_chunk, dtype=np.int16)

        # Calcul de la taille du chunk et création de l'onde correspondante
        t = np.arange(len(audio_data))
        # Création d'une onde sinusoïdale pour le tremolo
        tremolo = (1.0 + depth * np.sin(2 * np.pi * rate * t / 24000))

        # Appliquer le tremolo à l'audio
        audio_data = audio_data * tremolo

        # Appliquer la distorsion si nécessaire
        audio_data = self.add_distortion(audio_data)

        # Assurer que les valeurs sont dans la plage correcte pour int16
        audio_data = np.clip(audio_data, -32768, 32767)

        # Retourner le buffer modifié en bytes pour PyAudio
        return audio_data.astype(np.int16).tobytes()