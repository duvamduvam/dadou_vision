"""Launch V1 : heartbeat (vision_status) + suivi de personne (person_tracker).

    ros2 launch vision vision.launch.py
    ros2 launch vision vision.launch.py score_threshold:=0.5 ema_alpha:=0.3

POURQUOI un launch file plutôt que deux `ros2 run ... &` dans
conf/scripts/launch-ros-in-docker.sh (option envisagée par la mission V1) :
un seul process `ros2 launch` supervise proprement l'arrêt de tous les nodes
(un SIGINT sur le conteneur arrête les deux proprement, pas de wait manuel à
bash à maintenir), et les paramètres de person_tracker (camera_device,
model_path, score_threshold, ema_alpha) sont déclarés ici avec leurs défauts
plutôt qu'éparpillés en arguments CLI dans le script bash. Pattern déjà en
place côté robot pour la chaîne roues (conf/ros2_dependencies/robot_drive/
launch/drive.launch.py) : même choix pour rester cohérent dans le parc.

Défauts alignés sur person_tracker_node.py (DEFAULT_MODEL_PATH etc.) — s'ils
divergent un jour, ce fichier prime au runtime (les défauts du node ne
servent que pour un lancement direct hors launch, ex. tests manuels).
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    camera_device = LaunchConfiguration("camera_device")
    model_path = LaunchConfiguration("model_path")
    score_threshold = LaunchConfiguration("score_threshold")
    ema_alpha = LaunchConfiguration("ema_alpha")

    return LaunchDescription([
        DeclareLaunchArgument(
            "camera_device", default_value="/dev/video0",
            description="Périphérique V4L2 de la webcam USB (Jieli validée le 2026-07-04)",
        ),
        DeclareLaunchArgument(
            "model_path",
            default_value="/home/ros2_ws/models/efficientdet_lite0.tflite",
            description="Modèle MediaPipe EfficientDet-Lite0 int8 (téléchargé DANS l'image Docker, cf. Dockerfile-arm)",
        ),
        DeclareLaunchArgument(
            "score_threshold", default_value="0.4",
            description="Seuil de confiance MediaPipe pour retenir une détection 'person'",
        ),
        DeclareLaunchArgument(
            "ema_alpha", default_value="0.4",
            description="Coefficient de lissage exponentiel azimut/élévation (vision/tracking/target_picker.py)",
        ),

        # V0 : heartbeat, preuve de vie ROS bout-en-bout (déjà validé sur le
        # Pi 5, gardé tel quel — /vision/status ne doit jamais disparaître,
        # même si person_tracker échoue à démarrer faute de caméra/modèle).
        Node(package="vision", executable="vision_status", name="vision_status"),

        # V1 : suivi de personne -> /vision/person (silence = personne perdue,
        # cf. ARCHITECTURE.md et person_tracker_node.py).
        Node(
            package="vision",
            executable="person_tracker",
            name="person_tracker",
            parameters=[{
                "camera_device": camera_device,
                "model_path": model_path,
                "score_threshold": score_threshold,
                "ema_alpha": ema_alpha,
            }],
        ),
    ])
