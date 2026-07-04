import ast
import configparser
import json
import logging
import os

import openai
import pyaudio
import requests
from openai import OpenAI
import speech_recognition as sr

from dadou_utils_ros.utils_static import CONFIG_DIRECTORY, GPT_MODEL, NAME, MAX_TOKEN, PHOTO
from vision.ai.ai_audio import AIAudio
from vision.ai.ai_static import AI_MODERATION, AI_INSTRUCTIONS, CHAT_GPT_KEY
from vision.db.chat_db import ChatDB
from vision.picture.ai_camera import AICamera

os.environ['TEST'] = 'yes'
from vision.vision_config import config, WAKE_UP_WORD


class AInteractions:

    def __init__(self, node):

        self.node = node
        self.disabled = True
        self.blank_question_count = 0

        self.chatgpt_key = CHAT_GPT_KEY
        openai.api_key = CHAT_GPT_KEY
        self.assistant = OpenAI(api_key=CHAT_GPT_KEY)
        self.assistant.moderations.create(input=AI_MODERATION)

        self.current_history = ChatDB.create({})

        self.interactions_nb = 0
        self.parameters = None
        self.new_image = False

        self.camera_manager = AICamera()
        self.ai_audio = AIAudio()

        self.chat_db = ChatDB()

    def summarize_history(self):
        self.interactions_nb += 1
        logging.info("nombre d'interaction {}".format(self.interactions_nb))
        if self.interactions_nb < 2:
            return
        # Concatène l'historique en une seule chaîne de texte
        #full_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in self.current_history.get_history()])
        instructions = "resume ceci en gardand la structure json{}".format(self.current_history.get_history())
        logging.info(instructions)
        response = self.generate_request(instructions=instructions, add_history=False)
        summary = response.choices[0].message.content
        logging.info(summary)
        return summary

    def check_models(self):
        url = 'https://api.openai.com/v1/models'
        headers = {'Authorization': 'Bearer {}'.format(self.chatgpt_key)}
        response = requests.get(url, headers=headers)
        return response.json()

    def chatgpt_request(self, msg, new_photo=False):
        # Ajoute le message utilisateur à l'historique

        if self.current_history.speaker_name:
            msg = json.dumps({NAME: self.current_history.speaker_name})+msg

        if new_photo:
            url = self.camera_manager.take_and_upload_photo()
            self.current_history.add_image_and_text(url, msg)
        else:
            self.current_history.add_user_text(msg)

        chat_completion = self.generate_request(AI_INSTRUCTIONS, add_history=True)

        # Ajoute la réponse du système à l'historique
        #logging.info(chat_completion.model_dump_json(indent=2))
        new_msg = self.get_assistant_parameters(chat_completion.choices[0].message.content).lower()
        self.current_history.tokens = chat_completion.usage.total_tokens
        logging.info(new_msg)
        self.current_history.add_system_text(new_msg)

        return new_msg

    def generate_request(self, instructions, add_history=False):
        history = []
        if add_history:
            history = self.current_history.get_history()
        messages = ([
                       {
                           "role": "system",
                           "content": instructions,
                           "temperature": 0.9,
                           "max_tokens": config[MAX_TOKEN],
                       }
                   ] + history)

        # Effectue la requête à l'API avec l'historique et le maximum de tokens spécifié
        chat_completion = self.assistant.chat.completions.create(
            messages=messages,
            model=config[GPT_MODEL]
            #max_tokens=self.max_tokens  # Utilise le max_tokens spécifié ou celui par défaut
        )
        return chat_completion

    def get_assistant_parameters(self, msg):
        start = msg.find('{')
        end = msg.rfind('}') + 1
        try:
            self.parameters = ast.literal_eval(msg[start:end])
        except Exception as e:
            logging.error(f"parameters conversion error; {e}")
        logging.info("chatgpt parameters {}".format(self.parameters))
        if not self.current_history.speaker_name and NAME in self.parameters:
            self.current_history.speaker_name = self.parameters[NAME]
        return msg[0:start-1]

    def listen_to_text(self):
        recognizer = sr.Recognizer()
        with sr.Microphone() as source:
            logging.info("Parle maintenant...")
            recognizer.adjust_for_ambient_noise(source)
            try:
                audio = recognizer.listen(source, timeout=10, phrase_time_limit=5)
                text = recognizer.recognize_google(audio, language="fr-FR")
                logging.info(f"Tu as dit : {text}")
                return text
            except sr.UnknownValueError:
                logging.error("Je n'ai pas compris l'audio.")
            except sr.RequestError as e:
                logging.error(f"Erreur de service Google Speech Recognition; {e}")
            except Exception as e:
                logging.error(f"Erreur de service Google Speech Recognition; {e}")
        return None

    def lunch_actions(self):
        if PHOTO in self.parameters:
            self.camera_manager.take_photo()

    def process(self, test=False):
        question = self.listen_to_text()

        logging.info("ai question : {}".format(question))

        if not question:
            if self.blank_question_count > 5:
                self.disabled = True
            self.blank_question_count += 1
            return

        if self.disabled and WAKE_UP_WORD in question.lower():
            self.disabled = False
            self.current_history = self.chat_db.create({})
            self.interactions_nb = 0
        elif self.disabled:
            return

        logging.info("ai interaction")
        response = self.chatgpt_request(question)
        self.ai_audio.stream_to_speakers(response, robot_effect=True)
        self.summarize_history()
#        self.current_history.add_interaction(question, response)
