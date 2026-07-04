import logging
import logging.config
import unittest

from dadou_utils_ros.logging_conf import LoggingConf
from dadou_utils_ros.utils_static import LOGGING_TEST_FILE
from vision.ai.ai_audio import AIAudio
from vision.vision_config import config


class TestAudio(unittest.TestCase):

    logging.config.dictConfig(LoggingConf.get(config[LOGGING_TEST_FILE], "test_audio"))
    #robot_dialog = AInteractions(None)
    #chat_db = ChatDB()
    #db_manager = DBManager()
    ai_audio = AIAudio()

    def test_text_to_audio(self):
        self.ai_audio.stream_to_speakers("Alors ce test ca marche ou quoi ?")

    def test_text_to_audio_effect(self):
        self.ai_audio.stream_to_speakers("Alors ce test ca marche ou quoi ?", robot_effect=True)


if __name__ == '__main__':
    unittest.main()
