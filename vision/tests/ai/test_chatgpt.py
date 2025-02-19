import json
import logging
import logging.config
import os
import unittest

from dadou_utils.logging_conf import LoggingConf
from dadou_utils.utils_static import LOGGING_TEST_FILE_NAME, LOGGING_LAPTOP_TEST_FILE_NAME, ID
from robot.db.db_manager import DBManager
from vision.ai.ai_interactions import AInteractions
from vision.ai.ai_static import AI_INSTRUCTIONS
from vision.db.chat_db import ChatDB

os.environ['TEST'] = "yes"
from vision.vision_config import config


class TestChatgpt(unittest.TestCase):



    logging.config.dictConfig(LoggingConf.get(config[LOGGING_LAPTOP_TEST_FILE_NAME], "test_chat_gpt"))
    robot_dialog = AInteractions(None)
    chat_db = ChatDB()
    db_manager = DBManager()

    def test_assistant_listen_speak(self):
        for i in range(1, 8):
            logging.info("test")
            self.robot_dialog.process()

    def test_chatgpt_models(self):
        logging.info(json.dumps(self.robot_dialog.check_models(), indent=4))

    def test_text_request(self):
        #response = self.robot_dialog.request2("comment vas tu ?")
        #response = self.robot_dialog.request2("n'est tu pas triste de ne pas pouvoir sentir des émtions comme les humains ?")
        response = self.robot_dialog.chatgpt_request("comment t'appeles tu ?")
        logging.info(response.text())
        #logging.info(response.choices[0].message.content)

    def test_summarize(self):
        entry = ChatDB.get(25)
        self.robot_dialog.current_history = entry
        self.robot_dialog.interactions_nb = 10
        print(json.dumps(entry.get_history(), indent=4))
        print(print(len(entry.history)))
        #logging.info(json.dumps(self.robot_dialog.check_models(), indent=4))
        summarized = self.robot_dialog.summarize_history()
        summarized = summarized.replace("```json", "")
        summarized = summarized.replace("```", "")
        print(summarized)
        print(len(summarized))
        #print(summarized)
    def test_summarize2(self):
        summarized = '```json\n[\n    {\'role\': \'user\', \'content\': \'salut Didier comment ça va\'}, \n    {\'role\': \'system\', \'con...ne, comparant ce spectacle à un bal lumineux et magique remplissant l\'univers de joie et d\'émerveillement."}\n]\n```'
        summarized.replace("```json", "")
        summarized.replace("```", "")
        print(summarized)

    def test_request(self):

        entry = ChatDB.get(25)
        question = "pourquoi la tartine tombe toujours du mauvais côté ?"

        self.robot_dialog.current_history = entry
        self.robot_dialog.current_history.add_user_text(question)

        response = self.robot_dialog.generate_request(AI_INSTRUCTIONS, add_history=True)
        logging.info(response)

    def test_photo(self):

        entry = ChatDB.get(25)
        question = "d'écrit la photo ?"

        local_file = '/home/dadou/Nextcloud/Didier/python/dadou_vision/medias/pictures/2024-10-19_00-59-17.jpg'

        self.robot_dialog.current_history = entry
        self.robot_dialog.current_history.add_user_img(local_file, question)

        response = self.robot_dialog.generate_request(AI_INSTRUCTIONS, add_history=True)
        logging.info(response)

    def test_assistant_listen(self):
        for i in range(1, 11):
            logging.info("test")
            question = self.robot_dialog.listen_to_text()
            logging.info(question)



if __name__ == '__main__':
    unittest.main()
