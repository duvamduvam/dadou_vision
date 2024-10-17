#!/usr/bin/env python3
import json
import logging
import logging.config

from vision.files.vision_json_manager import HardDriveJsonManager
from robot.actions.lights import Lights
from vision.vision_config import config, HELMET_LIGHTS
import rclpy
from rclpy.node import Node
from robot_interfaces.msg._string_time import StringTime


from dadou_utils.misc import Misc
from dadou_utils.utils_static import LIGHTS_START_LED, LIGHTS_LED_COUNT, \
    BRIGHTNESS, LIGHTS_PIN, ROBOT_LIGHTS, FACE, LIGHTS_END_LED, JSON_LIGHTS, LIGHTS, LOGGING_FILE_NAME, I2C_ENABLED, \
    DIGITAL_CHANNELS_ENABLED, DURATION
from vision.vision_config import config, JSON_HELMET
from dadou_utils.logging_conf import LoggingConf


class LightsNode(Node):
    def __init__(self):
        node_name = 'lights_node'
        logging.config.dictConfig(LoggingConf.get(config[LOGGING_FILE_NAME], node_name))
        super().__init__(node_name)

        self.enabled = Misc.is_raspberrypi()
        logging.info("init  {} lights i2c enabled {}".format(node_name, self.enabled))

        if not self.enabled:
            return

        #prevent test fail
        import neopixel

        vision_json_manager = HardDriveJsonManager(config)
        pixels = neopixel.NeoPixel(config[LIGHTS_PIN], config[LIGHTS_LED_COUNT], auto_write=False,
                                   brightness=config[BRIGHTNESS])

        self.lights = Lights(config=config, start=config[LIGHTS_START_LED], end=config[LIGHTS_END_LED],
            json_manager=vision_json_manager, global_strip=pixels, light_type=HELMET_LIGHTS, json_light=JSON_HELMET)

        self.lights_subscription = self.create_subscription(
            StringTime, ROBOT_LIGHTS, self.lights_callback, 10)

        self.timer = self.create_timer(0.1, self.timer_callback)

    def lights_callback(self, ros_msg):
        msg = json.loads(ros_msg.msg)
        duration = ros_msg.time
        logging.info('Lights: "%s"' % msg)
        self.lights.update({ROBOT_LIGHTS: msg, DURATION: duration})

    def generic_callback(self, lights_type, ros_msg):
        msg = json.loads(ros_msg.msg)
        action_msg = {lights_type: msg}
        if ros_msg.time != 0:
            action_msg[DURATION] = ros_msg.time
        logging.info("{} send : {}".format(lights_type, ros_msg))
        self.lights.update(action_msg)

    def timer_callback(self):
        try:
            self.lights.process()
        except Exception as e:
            logging.error(e, exc_info=True)



def main(args=None):
    rclpy.init(args=args)
    node = LightsNode()
    try:
        while rclpy.ok():
            try:
                rclpy.spin_once(node)
            except Exception as e:
                logging.error(e, exc_info=True)
    except Exception as e:
        logging.error(e, exc_info=True)
    finally:
        rclpy.shutdown()


if __name__ == '__main__':
    main()
