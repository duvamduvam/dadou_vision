import logging
import time

import numpy as np
import openai
import pyaudio

from dadou_utils.utils_static import GPT_VOICE
from vision.vision_config import config


class AIAudio:

    def stream_to_speakers(self, msg, robot_effect=False) -> None:

        player_stream = pyaudio.PyAudio().open(format=pyaudio.paInt16, channels=1, rate=24000, output=True)
        start_time = time.time()
        with openai.audio.speech.with_streaming_response.create(
                model="tts-1",
                voice=config[GPT_VOICE],
                response_format="wav",  # similar to WAV, but without a header chunk at the start.
                input=msg
        ) as response:
            logging.info(f"Time to first byte: {int((time.time() - start_time) * 1000)}ms")
            for chunk in response.iter_bytes(chunk_size=1024):
                if robot_effect:
                    player_stream.write(self.apply_robotic_effect(chunk))
                else:
                    player_stream.write(chunk)

        logging.info(f"Done in {int((time.time() - start_time) * 1000)}ms.")


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