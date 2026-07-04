import logging
import logging.config
import unittest

from dadou_utils_ros.logging_conf import LoggingConf
from dadou_utils_ros.utils_static import LOGGING_TEST_FILE_NAME, LOGGING_LAPTOP_TEST_FILE_NAME, LOGGING_TEST_FILE
from vision.ai.ai_interactions import AInteractions
from vision.ai.ai_static import AI_INSTRUCTIONS
from vision.db.chat_db import ChatDB
from vision.files.sftp import Sftp
from vision.picture.ai_camera import AICamera
from vision.vision_config import config, SSH_HOSTNAME, SSH_USERNAME, SSH_KEY


class TestAIPictures(unittest.TestCase):

    logging.config.dictConfig(LoggingConf.get(config[LOGGING_TEST_FILE], "test_ai_pictures"))

    sftp = Sftp(
        hostname=SSH_HOSTNAME,
        username=SSH_USERNAME,
        key=SSH_KEY,
    )

    def test_take_picture(self):
        # Exemple d'utilisation de la classe
        self.robot_dialog = AInteractions(None)
        camera = AICamera()
        camera.take_photo()

    def test_upload(self):
        camera = AICamera()
        camera.take_photo()
        self.sftp.upload(camera.current_photo)

    def test_photo(self):

        entry = ChatDB.get(25)
        question = "d'écrit la photo ?"

        local_file = '/home/dadou/Nextcloud/dev/didier/python/dadou_vision/medias/pictures/2024-10-19_00-59-17.jpg'

        self.robot_dialog.current_history = entry
        self.robot_dialog.current_history.add_user_img(local_file, question)

        response = self.robot_dialog.generate_request(AI_INSTRUCTIONS, add_history=True)
        logging.info(response)

if __name__ == '__main__':
    unittest.main()
