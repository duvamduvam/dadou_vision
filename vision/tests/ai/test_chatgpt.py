import logging
import logging.config
import os
import unittest

from dadou_utils.logging_conf import LoggingConf
from dadou_utils.utils_static import LOGGING_TEST_FILE_NAME, LOGGING_LAPTOP_TEST_FILE_NAME
from robot.ai.ai_interactions import AInteractions

os.environ['TEST'] = "yes"
from vision.vision_config import config


class TestChatgpt(unittest.TestCase):



    logging.config.dictConfig(LoggingConf.get(config[LOGGING_LAPTOP_TEST_FILE_NAME], "test_chat_gpt"))
    robot_dialog = AInteractions(None, config)

    def test_assistant_listen_speak(self):
        for i in range(1, 6):
            logging.info("test")
            self.robot_dialog.process()

    def test_chatgpt_models(self):
        logging.info(self.robot_dialog.check_models())

    def test_text_request(self):
        #response = self.robot_dialog.request2("comment vas tu ?")
        #response = self.robot_dialog.request2("n'est tu pas triste de ne pas pouvoir sentir des émtions comme les humains ?")
        response = self.robot_dialog.chatgpt_request("comment t'appeles tu ?")
        logging.info(response.text())
        #logging.info(response.choices[0].message.content)

    def test_assistant_speak(self):
        response = self.robot_dialog.chatgpt_request("est ce que les mouches petent ?")
        self.robot_dialog.stream_to_speakers(response)

    def test_assistant_speak_robot(self):
        response = self.robot_dialog.chatgpt_request("pourquoi la tartine tombe toujours du mauvais côté ?")
        self.robot_dialog.stream_to_speakers(response, robot_effect=True)

    def test_assistant_listen(self):
        for i in range(1, 11):
            logging.info("test")
            question = self.robot_dialog.listen_to_text()
            logging.info(question)

    def test_simple_request_google_audio(self):
        self.robot_dialog.request_to_audio("c'est l'histoire dans la révolutino francaise en 5 lignes?", "google")

    def test_simple_request_whisper_audio(self):
        self.robot_dialog.request_to_audio("c'est quoi l'histoire du funk ?")


    def test_translate(self):
        f = open("/home/dadou/tmp/chaco-modif3.txt", "r")
        logging.info(f.read())
        self.robot_dialog.translate(f.read())

if __name__ == '__main__':
    unittest.main()
