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
        ],
    },
)
