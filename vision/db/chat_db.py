import base64
import json
import logging

from sqlobject import SQLObject, StringCol, IntCol, PickleCol, BoolCol
from sqlobject.dberrors import DuplicateEntryError
from sqlobject.sqlite import builder
from datetime import date, datetime

from dadou_utils.utils_static import DB_DIRECTORY, SEQUENCES_DB, NAME, SEQUENCES, CHAT_DB, ID, ROLE, SYSTEM, USER, \
    CONTENT, DATE
from robot.db.db_manager import DBManager
from vision.vision_config import config

# Connexion à une base de données SQLite persistante
db_file = "{}{}".format(config[DB_DIRECTORY], config[CHAT_DB])
connection = builder()(filename=db_file)


class ChatDB(SQLObject):
    _connection = connection

    history = StringCol(default=None)
    speaker_name = StringCol(default=None)
    tokens = IntCol(default=0)

    def print(self):
        for field, col in self.sqlmeta.columns.items():
            print(f"{field}: {getattr(self, field)}")

    @staticmethod
    def create(sequence_data):
        try:
            entry = ChatDB(**sequence_data)
            logging.info(f"Inserted sequence: {sequence_data}")
            return entry
        except DuplicateEntryError as e:
            logging.error(f"Duplicate entry for chat history: {sequence_data}")
        except Exception as e:
            logging.error(f"creating chat history error: {e}")

    def get_history(self):
        if not self.history:
            self.history = json.dumps([])
        history = json.loads(self.history)

        return history

    def set_history(self, history):
        self.history = json.dumps(history)

    def add_interaction(self, text):
        history = self.get_history()
        new_interaction = [text]
        history.extend(new_interaction)
        self.set_history(history)

    def add_system_text(self, text):
        self.add_interaction({ROLE: SYSTEM, CONTENT: text})

    def add_user_text(self, text):
        self.add_interaction({ROLE: USER, CONTENT: text})

    def encode_image(self, image_path):
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def add_user_img_base64(self, image_path, text):

        base64_image = self.encode_image(image_path)

        self.add_interaction({ROLE: USER, CONTENT: [
            {"type": "text", "text": text},
            {"type": "image_url",
              "image_url": {
                "url": f"data:image/jpeg;base64,{base64_image}"
              },
            },
          ]})

    def add_user_img(self, image_url, text):

        self.add_interaction({ROLE: USER, CONTENT: [
            {"type": "text", "text": text},
            {"type": "image_url",
              "image_url": {
                "url": image_url
              },
            },
          ]})