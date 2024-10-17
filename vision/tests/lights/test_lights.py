import logging
import os

import board

from dadou_utils.logging_conf import LoggingConf
from dadou_utils.utils.time_utils import TimeUtils

from dadou_utils.utils_static import LIGHTS_PIN, LIGHTS_LED_COUNT, BRIGHTNESS, LIGHTS_START_LED, LIGHTS_END_LED, \
    LOGGING_TEST_FILE_NAME, DEFAULT
from vision.files.vision_json_manager import HardDriveJsonManager
from vision.vision_config import config, JSON_HELMET, HELMET_LIGHTS
from robot.actions.lights import Lights
from robot.tests.conf_test import TestSetup
import neopixel

#TestSetup()

import time
import unittest



class LightsTest(unittest.TestCase):

    logging.config.dictConfig(LoggingConf.get(config[LOGGING_TEST_FILE_NAME], "test_light"))

    #print(dir(board))

    RED = (255, 0, 0)
    YELLOW = (255, 150, 0)
    GREEN = (0, 255, 0)
    CYAN = (0, 255, 255)
    BLUE = (0, 0, 255)
    PURPLE = (180, 0, 255)
    BLACK = (0, 0, 0)

    base_path = os.getcwd()

    vision_json_manager = HardDriveJsonManager(config)
    pixels = neopixel.NeoPixel(config[LIGHTS_PIN], config[LIGHTS_LED_COUNT], auto_write=False,
                               brightness=config[BRIGHTNESS])

    lights = Lights(config=config, start=config[LIGHTS_START_LED], end=config[LIGHTS_END_LED],
                         json_manager=vision_json_manager, global_strip=pixels, light_type=HELMET_LIGHTS,
                         json_light=JSON_HELMET)

    def test_lights_key(self):

        #print(dir(board))

        current_time = TimeUtils.current_milli_time()
        while not TimeUtils.is_time(current_time, 2000):
            self.lights.process()

        list = [{HELMET_LIGHTS: DEFAULT}, {HELMET_LIGHTS: "heidi"}]
        for k in list:
            #logging.info("test lights key " + k)
            self.lights.update(k)
            current_time = TimeUtils.current_milli_time()
            while not TimeUtils.is_time(current_time, 10000):
                self.lights.process()

    def test_lights_default(self):
        # self.lights.update("B1")
        while True:
            self.lights.process()
