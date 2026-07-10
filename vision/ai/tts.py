"""TTS OpenAI streaming + effet robot (recyclé de vision/ai/ai_audio.py, gardé tel quel).

Diffuse la réponse GPT en voix synthétique sur la sortie audio ALSA via
PyAudio, avec un effet de modulation ("effet robot") disponible en option.

add_distortion/apply_robotic_effect délèguent désormais à vision.audio.effects
(module PUR, testable en CI sans openai/pyaudio/scipy) — extraction faite pour
que l'algorithme soit vérifiable par des tests unitaires rapides. La signature
PUBLIQUE de apply_robotic_effect (audio_chunk, depth=0.7, rate=35) est
préservée à l'identique pour ne rien changer aux appels existants ; on fixe
explicitement sample_rate=24000 (la valeur que l'ancien code codait en dur
dans la formule du trémolo) et regain_to=clip=3000 (facteur de regain = 1,
donc AUCUN changement de comportement ici — le regain est une amélioration
volontairement réservée aux nouveaux appelants de vision.audio.effects, pas
injectée en douce dans ce chemin existant)."""
import logging
import time

import numpy as np
import openai
import pyaudio
import scipy.signal
from openai import OpenAI

from vision.ai.ai_static import AI_MODERATION
from vision.audio import effects
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
        return effects.add_distortion(audio_data, threshold=threshold)

    def apply_robotic_effect(self, audio_chunk, depth=0.7, rate=35):
        """ Applique un effet robotique (tremolo) au chunk audio.

        Délègue à vision.audio.effects.apply_robotic_effect avec sample_rate=24000
        (ancienne valeur codée en dur) et regain_to=clip=3000 (facteur de regain
        neutre = 1) : comportement bit-à-bit identique à l'ancienne implémentation
        recopiée en dur dans test_effects.py::test_equivalence_avec_ancienne_implementation.
        """
        return effects.apply_robotic_effect(
            audio_chunk, depth=depth, rate_hz=rate, sample_rate=24000,
            clip=3000, regain_to=3000)
