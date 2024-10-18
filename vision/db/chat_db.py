import json
import logging

from sqlobject import SQLObject, StringCol, IntCol, PickleCol, BoolCol
from sqlobject.dberrors import DuplicateEntryError
from sqlobject.sqlite import builder
from datetime import date, datetime

from dadou_utils.utils_static import DB_DIRECTORY, SEQUENCES_DB, NAME, SEQUENCES, CHAT_DB, ID
from robot.db.db_manager import DBManager
from vision.vision_config import config

# Connexion à une base de données SQLite persistante
db_file = "{}{}".format(config[DB_DIRECTORY], config[CHAT_DB])
connection = builder()(filename=db_file)


class ChatDB(SQLObject):
    _connection = connection

    history = StringCol(default=None)
    speaker_name = StringCol(default=None)

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
            logging.error(f"Duplicate entry for expression: {sequence_data}")

    def add_interaction(self, speaker_text, ai_text):
        if not self.history:
            self.history = json.dumps({})

        json_history = json.loads(self.history)
        json_history[str(datetime.now())] = {
            'speaker': speaker_text,
            'ai': ai_text}
        self.history = json.dumps(json_history)

