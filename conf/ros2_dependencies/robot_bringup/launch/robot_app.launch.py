from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    ld = LaunchDescription()

    lights_server_node = Node(
        package="robot",
        executable="lights_node",
        name="lights_node"
    )

    ld.add_action(lights_server_node)

    return ld