from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    ld = LaunchDescription()

    ai_server_node = Node(
        package="robot",
        executable="ai_node",
        name="ai_node"
    )

    ld.add_action(ai_server_node)

    return ld