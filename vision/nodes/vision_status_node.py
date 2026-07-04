#!/usr/bin/env python3
"""Node 'vision_status' : heartbeat minimal prouvant la chaîne ROS bout-en-bout.

Publie un std_msgs/String sur /vision/status toutes les 5 s (hostname +
uptime). C'est la démo de fin de lot V0 : sur le Pi 5, `ros2 topic list` doit
lister /vision/status et `ros2 topic echo /vision/status` doit l'afficher en
continu, avant de passer à V1 (suivi de personne).

Node volontairement fin : aucune logique métier ici, elle vit dans
vision/status.py (testable sans ROS).
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from vision.status import build_status_message

PUBLISH_PERIOD_SECONDS = 5.0


class VisionStatusNode(Node):
    def __init__(self):
        super().__init__("vision_status")
        self.publisher_ = self.create_publisher(String, "/vision/status", 10)
        self.timer = self.create_timer(PUBLISH_PERIOD_SECONDS, self._publish_status)

    def _publish_status(self):
        msg = String()
        msg.data = build_status_message()
        self.publisher_.publish(msg)
        self.get_logger().info(msg.data)


def main(args=None):
    rclpy.init(args=args)
    node = VisionStatusNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
