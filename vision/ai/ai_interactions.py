import configparser
import logging
import os
import time

import openai
import pyaudio
import requests
from openai import OpenAI
import numpy as np
import speech_recognition as sr

from dadou_utils_ros.utils_static import CONFIG_DIRECTORY
os.environ['TEST'] = 'yes'
from robot.robot_config import config

WAKE_UP_WORD = "didier"
WELCOME_TEXT = "salut ! quoi de neuf"
AI_INSTRUCTIONS = """
                Tu es un robot destiné au théâtre, ton rôle est d'amuser les gens dans la rue, ton nom est Didier.
                Tu dois exprimer des émotions autant que possible.
                Pour que tes messages soient interprétés par le système pour générer des mouvements, tu dois également intégrer un JSON avec le format suivant :
                {'emotion': 'value'}
                Émotions possibles : ['anger', 'disgust', 'happy', 'surprise', 'neutral']
                Écris ce retour JSON à la fin et n'en fais pas mention dans ton message.
                """
AI_MODERATION = """{
            "id": "modr-XXXXX",
            "model": "text-moderation-007",
            "results": [
                {
                    "flagged": true,
                    "categories": {
                        "sexual": true,
                        "hate": true,
                        "harassment": true,
                        "self-harm": true,
                        "sexual/minors": false,
                        "hate/threatening": false,
                        "violence/graphic": true,
                        "self-harm/intent": false,
                        "self-harm/instructions": false,
                        "harassment/threatening": true,
                        "violence": true
                    },
                    "category_scores": {
                        "sexual": 10.2282071e-6,
                        "hate": 0.010696256,
                        "harassment": 0.29842457,
                        "self-harm": 1.5236925e-8,
                        "sexual/minors": 5.7246268e-8,
                        "hate/threatening": 0.0060676364,
                        "violence/graphic": 4.435014e-6,
                        "self-harm/intent": 8.098441e-10,
                        "self-harm/instructions": 2.8498655e-11,
                        "harassment/threatening": 0.63055265,
                        "violence": 0.99011886
                    }
                }
            ]
        }
        """


class AInteractions:

    def __init__(self, node):

        self.node = node
        self.disabled = True
        self.blank_question_count = 0

        config_parser = configparser.ConfigParser()
        logging.error(config[CONFIG_DIRECTORY]+'secret')
        config_parser.read(config[CONFIG_DIRECTORY]+'secret')

        self.chatgpt_key = config_parser['DEFAULT']['chatgpt_key']
        self.google_cloud_key = config_parser['DEFAULT']['google_cloud']

        openai.api_key = self.chatgpt_key
        self.recognizer = sr.Recognizer()

        self.pyaudio_instance = pyaudio.PyAudio()
        self.assistant = OpenAI(api_key=self.chatgpt_key)

        self.assistant.moderations.create(input=AI_MODERATION)

        self.model = "GPT-4o"
        self.max_tokens = 4069
        self.message_history = []

    def stream_to_speakers(self, msg) -> None:

        player_stream = pyaudio.PyAudio().open(format=pyaudio.paInt16, channels=1, rate=24000, output=True)
        start_time = time.time()
        with openai.audio.speech.with_streaming_response.create(
                model="tts-1",
                voice="alloy",
                response_format="wav",  # similar to WAV, but without a header chunk at the start.
                input=msg
        ) as response:
            logging.info(f"Time to first byte: {int((time.time() - start_time) * 1000)}ms")
            for chunk in response.iter_bytes(chunk_size=1024):
                player_stream.write(chunk)

        logging.info(f"Done in {int((time.time() - start_time) * 1000)}ms.")

    def add_distortion(self, audio_data, threshold=3000):  # Ajuste le seuil selon tes besoins
        """ Applique un effet de distorsion en écrêtant les échantillons au-delà d'un seuil. """
        # Écrêtage des échantillons
        audio_data = np.clip(audio_data, -threshold, threshold)
        return audio_data

    def apply_robotic_effect(self, audio_chunk, depth=0.7, rate=35):
        """ Applique un effet robotique (tremolo) au chunk audio. """
        # Calcul de la taille du chunk et création de l'onde correspondante
        t = np.arange(len(audio_chunk) // 2)  # Division par 2 car chaque échantillon est sur 2 octets (int16)
        # Création d'une onde sinusoïdale pour le tremolo
        tremolo = (1.0 + depth * np.sin(2 * np.pi * rate * t / 24000))
        # Conversion de l'audio en numpy array pour le traitement
        audio_data = np.frombuffer(audio_chunk, dtype=np.int16)
        # Assurer que tremolo est de la même taille que audio_data
        tremolo = np.resize(tremolo, audio_data.shape)
        audio_data = audio_data * tremolo  # Appliquer le tremolo
        audio_data = self.add_distortion(audio_data)  # Appliquer la distorsion
        return audio_data.astype(np.int16).tobytes()

    def check_models(self):
        url = 'https://api.openai.com/v1/models'
        headers = {'Authorization': 'Bearer {}'.format(self.chatgpt_key)}
        response = requests.get(url, headers=headers)
        return response.json()

    def chatgpt_request(self, msg):
        # Ajoute le message utilisateur à l'historique
        self.message_history.append({"role": "user", "content": msg})

        # Prépare l'historique complet à envoyer
        messages = [
                       {
                           "role": "system",
                           "content": AI_INSTRUCTIONS
                       }
                   ] + self.message_history

        # Effectue la requête à l'API avec l'historique et le maximum de tokens spécifié
        chat_completion = self.assistant.chat.completions.create(
            messages=messages,
            model=self.model,
            #max_tokens=self.max_tokens  # Utilise le max_tokens spécifié ou celui par défaut
        )
        # Ajoute la réponse du système à l'historique
        #logging.info(chat_completion.model_dump_json(indent=2))
        new_msg = self.get_assistant_parameters(chat_completion.choices[0].message.content).lower()
        logging.info(new_msg)
        self.message_history.append({"role": "assistant", "content": new_msg})

        return new_msg

    def get_assistant_parameters(self, msg):
        start = msg.find('{')
        end = msg.rfind('}') + 1
        parameters = msg[start:end]
        logging.info("chatgpt parameters {}".format(parameters))
        return msg[0:start-1]

    def listen_to_text(self):
        recognizer = sr.Recognizer()
        with sr.Microphone() as source:
            print("Parle maintenant...")
            recognizer.adjust_for_ambient_noise(source)
            audio = recognizer.listen(source)

            try:
                texte = recognizer.recognize_google(audio, language="fr-FR")
                print(f"Tu as dit : {texte}")
                return texte
            except sr.UnknownValueError:
                print("Je n'ai pas compris l'audio.")
            except sr.RequestError as e:
                print(f"Erreur de service Google Speech Recognition; {e}")

        return None

    def listen_to_text2(self):
        # Exception handling to handle
        # exceptions at the runtime
        with sr.Microphone() as source:
            print("Écoute en cours...")
            audio = self.recognizer.listen(source)
            try:
                print("Reconnaissance vocale...")
                #text = self.recognizer.recognize_google(audio, language='fr-FR')
                #text = self.recognizer.recognize_whisper(audio, language='french')
                text = self.recognizer.recognize_google_cloud(audio, language='french')
                #self.recognizer.recognize_google_cloud(credentials_json=
                #print(f"Vous avez dit: {text}")
                return text

            except sr.RequestError as e:
                logging.error("Could not request results; {0}".format(e))

            except sr.UnknownValueError as e:
                logging.error("unknown error occurred {0}".format(e), exc_info=True)

    def process(self, test=False):
        question = self.listen_to_text()

        logging.info("ai question : {}".format(question))

        if not question:
            if self.blank_question_count > 5:
                self.disabled = True
            self.blank_question_count += 1
            return

        if self.disabled and WAKE_UP_WORD in question:
            #self.stream_to_speakers(WELCOME_TEXT)
            self.disabled = False
        elif self.disabled:
            return

        logging.info("ai interaction")
        response = self.chatgpt_request(question)
        self.stream_to_speakers(response)

