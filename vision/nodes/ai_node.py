#!/usr/bin/env python3
import logging

import rclpy
from rclpy.node import Node

from dadou_utils_ros.utils_static import RELAYS, SHUTDOWN_PIN, STATUS_LED_PIN, RESTART_PIN, SYSTEM, I2C_ENABLED, \
    DIGITAL_CHANNELS_ENABLED, AI
from robot.nodes.abstract_subscriber import SubscriberNode

from vision.ai.ai_interactions import AInteractions
from vision.vision_config import config


class AINode(SubscriberNode):
    def __init__(self):
        self.ai = AInteractions(config)

        super().__init__(config, AI, AI, self.ai)


def main(args=None):

    rclpy.init(args=args)
    node = AINode()
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

















