import os
from glob import glob

from setuptools import find_packages, setup

package_name = 'vision'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        # Launch V1 (vision.launch.py : heartbeat + person_tracker). Le
        # dossier launch/ est bind-monté/copié à la racine du package colcon
        # (cf. docker-compose-arm.yml et Dockerfile-arm) depuis conf/ros2/launch/.
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='dadou',
    maintainer_email='achats@duvam.net',
    description='Cerveau perceptif de Didier (Pi 5) : publie des perceptions caméra en topics ROS standard, ne commande jamais les moteurs.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            # Heartbeat V0 : preuve que la chaîne ROS tourne bout-en-bout sur le Pi 5.
            'vision_status = vision.nodes.vision_status_node:main',
            # Suivi de personne V1 : webcam -> détection -> /vision/person.
            'person_tracker = vision.nodes.person_tracker_node:main',
            # Conversation temps réel V2 : micro -> LLM streamé -> voix +
            # expressions faciales (OFF par défaut dans le launch, cf.
            # conf/ros2/launch/vision.launch.py argument chat_enabled).
            'chat = vision.nodes.chat_node:main',
        ],
    },
)
