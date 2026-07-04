#!/bin/bash

# ROS_DISTRO est fourni par l'image de base (humble, jazzy...) : ne pas coder la distro en dur.
source /opt/ros/${ROS_DISTRO}/setup.sh
cd /home/ros2_ws/

# Sentinelle dans un dossier bind-monté (vision/CHANGE) : sa présence déclenche
# un colcon build, puis elle est supprimée. Recréez-la après une modif de code
# pour forcer un rebuild (cf. leçon du parc, dadou_robot_ros).
CHANGE_FILE=/home/ros2_ws/src/vision/vision/CHANGE
if [ -f "$CHANGE_FILE" ]; then
    echo "CHANGE file found. Running colcon build..."
    colcon build
    rm $CHANGE_FILE
else
    echo "$CHANGE_FILE file not found. Skipping colcon build."
fi

source /home/ros2_ws/install/setup.bash

# V1 : launch file unique (heartbeat vision_status + suivi de personne
# person_tracker), cf. conf/ros2/launch/vision.launch.py — remplace le
# `ros2 run vision vision_status` de V0 (single node). Un seul launch,
# supervision propre de l'arrêt des deux nodes (SIGINT).
ros2 launch vision vision.launch.py
