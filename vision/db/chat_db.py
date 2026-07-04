"""Historique des conversations (SQLite via SQLObject) — gardé de la V précédente.

Une session de chat = une ligne ChatDB avec l'historique JSON (liste de
messages format GPT), le nom du locuteur si connu, et le nombre de tokens
consommés. Le fichier SQLite de production vit dans db/ (gardé sur disque,
gitignoré). `configure()` permet de rediriger la connexion vers un fichier
temporaire en test (jamais le fichier de prod).
"""
import base64
import json
import logging
import os

from sqlobject import SQLObject, StringCol, IntCol
from sqlobject.dberrors import DuplicateEntryError
from sqlobject.sqlite import builder

from vision.vision_config import config

ROLE = "role"
SYSTEM = "system"
USER = "user"
CONTENT = "content"


class ChatDB(SQLObject):
    """Historique d'une conversation avec Didier (JSON, format messages GPT)."""

    history = StringCol(default=None)
    speaker_name = StringCol(default=None)
    tokens = IntCol(default=0)

    @classmethod
    def configure(cls, db_path):
        """(Re)connecte la classe à un fichier SQLite donné (prod ou test)."""
        directory = os.path.dirname(db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        cls._connection = builder()(filename=db_path)
        cls.createTable(ifNotExists=True)

    @staticmethod
    def create(sequence_data):
        try:
            entry = ChatDB(**sequence_data)
            logging.info("Nouvelle session de chat créée : %s", sequence_data)
            return entry
        except DuplicateEntryError:
            logging.error("Entrée en doublon pour l'historique de chat : %s", sequence_data)
        except Exception:
            logging.exception("Erreur de création de l'historique de chat : %s", sequence_data)

    def get_history(self):
        if not self.history:
            self.history = json.dumps([])
        return json.loads(self.history)

    def set_history(self, history):
        self.history = json.dumps(history)

    def add_interaction(self, message):
        history = self.get_history()
        history.append(message)
        self.set_history(history)

    def add_system_text(self, text):
        self.add_interaction({ROLE: SYSTEM, CONTENT: text})

    def add_user_text(self, text):
        self.add_interaction({ROLE: USER, CONTENT: text})

    def encode_image(self, image_path):
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def add_user_img_base64(self, image_path, text):
        base64_image = self.encode_image(image_path)
        self.add_interaction({ROLE: USER, CONTENT: [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,{}".format(base64_image)}},
        ]})

    def add_image_and_text(self, image_url, text):
        self.add_interaction({ROLE: USER, CONTENT: [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": image_url}},
        ]})


# Connexion de production par défaut (db/chat.db, gardé sur disque, gitignoré).
ChatDB.configure(config["db_directory"] + config["chat_db"])
