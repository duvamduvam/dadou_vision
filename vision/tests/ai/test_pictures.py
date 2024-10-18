import logging
import logging.config
import unittest

from dadou_utils.logging_conf import LoggingConf
from dadou_utils.utils_static import LOGGING_TEST_FILE_NAME, LOGGING_LAPTOP_TEST_FILE_NAME
from vision.picture.ai_picture import AIPicture
from vision.vision_config import config


class TestAIPictures(unittest.TestCase):

    logging.config.dictConfig(LoggingConf.get(config[LOGGING_LAPTOP_TEST_FILE_NAME], "test_ai_pictures"))
    def test_take_picture(self):
        # Exemple d'utilisation de la classe
        camera = AIPicture()
        camera.prendre_photo()


if __name__ == '__main__':
    unittest.main()
