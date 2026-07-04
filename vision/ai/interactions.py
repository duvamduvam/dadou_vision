"""Brique GPT (recyclée de vision/ai/ai_interactions.py, durcie en V0).

Orchestration d'une conversation avec ChatGPT : historique (ChatDB), appel à
l'API Chat Completions, extraction du JSON d'émotion de fin de réponse via
vision.ai.emotion_parser (durci : json.loads plutôt qu'ast.literal_eval).

STT (reconnaissance vocale micro) est un chantier V2 séparé (vision/ai/stt.py,
bench faster-whisper local vs API à faire) : volontairement absent ici pour
garder le socle V0 sans dépendance microphone/speech_recognition. L'ancienne
`listen_to_text`/`process()` (écoute micro -> GPT -> TTS) sera réintroduite en
V2 par chat_node, une fois le choix STT tranché.
"""
import json
import logging

import openai
from openai import OpenAI

from vision.ai.ai_static import AI_MODERATION, AI_INSTRUCTIONS
from vision.ai.camera import AICamera
from vision.ai.emotion_parser import extract_emotion_json, NAME_KEY, PHOTO_KEY
from vision.ai.tts import AIAudio
from vision.db.chat_db import ChatDB
from vision.vision_config import config, get_secret


class AInteractions:
    """Orchestration d'une conversation GPT pour Didier (branchée en V2 par chat_node)."""

    def __init__(self):
        chatgpt_key = get_secret("chatgpt_key")
        openai.api_key = chatgpt_key
        self.assistant = OpenAI(api_key=chatgpt_key)
        self.assistant.moderations.create(input=AI_MODERATION)

        self.current_history = ChatDB.create({})
        self.interactions_nb = 0
        self.parameters = {}

        self.camera_manager = AICamera()
        self.ai_audio = AIAudio()

    def summarize_history(self):
        self.interactions_nb += 1
        logging.info("nombre d'interactions : %d", self.interactions_nb)
        if self.interactions_nb < 2:
            return None
        instructions = "resume ceci en gardant la structure json{}".format(self.current_history.get_history())
        response = self.generate_request(instructions=instructions, add_history=False)
        summary = response.choices[0].message.content
        logging.info(summary)
        return summary

    def check_models(self):
        """Liste les modèles disponibles pour la clé API configurée (diagnostic).

        Utilise le client officiel OpenAI (déjà une dépendance obligatoire)
        plutôt qu'un appel `requests` manuel à l'API REST : une dépendance en
        moins dans conf/requirements.txt.
        """
        return self.assistant.models.list().model_dump()

    def chatgpt_request(self, msg, new_photo=False):
        # Ajoute le message utilisateur à l'historique
        if self.current_history.speaker_name:
            msg = json.dumps({NAME_KEY: self.current_history.speaker_name}) + msg

        if new_photo:
            photo_path = self.camera_manager.take_photo()
            self.current_history.add_user_img_base64(photo_path, msg)
        else:
            self.current_history.add_user_text(msg)

        chat_completion = self.generate_request(AI_INSTRUCTIONS, add_history=True)

        text, parameters = extract_emotion_json(chat_completion.choices[0].message.content)
        self.parameters = parameters or {}
        if not self.current_history.speaker_name and NAME_KEY in self.parameters:
            self.current_history.speaker_name = self.parameters[NAME_KEY]

        new_msg = text.lower()
        self.current_history.tokens = chat_completion.usage.total_tokens
        logging.info(new_msg)
        self.current_history.add_system_text(new_msg)

        return new_msg

    def generate_request(self, instructions, add_history=False):
        history = self.current_history.get_history() if add_history else []
        messages = [{"role": "system", "content": instructions}] + history

        # temperature/max_tokens sont des paramètres de la REQUÊTE, pas du
        # message system : l'API rejette les champs inconnus dans un message
        # (bug hérité du code 2025, jamais déclenché car jamais branché).
        return self.assistant.chat.completions.create(
            messages=messages,
            model=config["gpt_model"],
            temperature=0.9,
            max_tokens=config["max_tokens"],
        )

    def launch_actions(self):
        """Déclenche les actions demandées par GPT (ex: prendre une photo)."""
        if PHOTO_KEY in self.parameters:
            self.camera_manager.take_photo()
