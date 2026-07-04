import configparser
import os
import sys

from dadou_utils_ros.misc import Misc
from dadou_utils_ros.utils_static import BASE_PATH, I2C_ENABLED, JSON_LIGHTS_SEQUENCE, \
    JSON_LIGHTS, JSON_COLORS, MAIN_LOOP_SLEEP, STOP_KEY, RIGHT_ARM_NB, LEFT_ARM_NB, WHEEL_RIGHT_DIR, \
    WHEEL_LEFT_DIR, WHEEL_RIGHT_PWM, WHEEL_LEFT_PWM, HEAD_PWM_NB, STATUS_LED_PIN, RESTART_PIN, SHUTDOWN_PIN, \
    DIGITAL_CHANNELS_ENABLED, PWM_CHANNELS_ENABLED, LIGHTS_PIN, LIGHTS_START_LED, \
    LIGHTS_END_LED, JSON_DIRECTORY, LOGGING_CONFIG_FILE, LOGGING_CONFIG_TEST_FILE, LOGGING_FILE_NAME, BRIGHTNESS, \
    JSON_LIGHTS_BASE, SINGLE_THREAD, SRC_DIRECTORY, PROJECT_DIRECTORY, LIGHTS_LED_COUNT, LOGGING_TEST_FILE_NAME, \
    LOGGING_LAPTOP_TEST_FILE_NAME, CONFIG_DIRECTORY, MEDIAS_DIRECTORY, GPT_MODEL, GPT_VOICE, DB_DIRECTORY, CHAT_DB, \
    PICTURES_FOLDER, MAX_TOKEN, LOGGING_FILE, LOGGING_TEST_FILE, ALSA_CHANNEL

config = {}

#print(dir(board))
#board_list = dir(board)

config[ALSA_CHANNEL] = 1

######## AI ########
config[GPT_MODEL] = "gpt-4o"
config[GPT_VOICE] = "alloy"
#config[GPT_VOICE] = "fable"
config[CHAT_DB] = "chat.db"
config[MAX_TOKEN] = 70
WAKE_UP_WORD = "didier"

######## SSH #######
SSH_HOSTNAME = "cloud.duvam.net"
SSH_USERNAME = "david"

if Misc.is_raspberrypi():
    SSH_KEY = '/home/pi/test/conf/kimsufi'
else:
    SSH_KEY = '/home/dadou/Nextcloud/divers/keys/kimsufi'
UPLOAD_FOLDER = '/var/www/yellow/media/images/upload/'
BASE_URL = 'https://admin.duvam.net/yellow/media/images/upload/'

######### PROCESS ########
DISK = 'disk'
HELMET = 'helmet'
SHUTDOWN = 'shutdown'

PROCESS_LIST = [DISK, HELMET, SHUTDOWN]

########## RPI PINS #########
#if Misc.is_raspberrypi():
#    config[LIGHTS_PIN] = board.D18
#    config[SHUTDOWN_PIN] = board.D12
#    config[STATUS_LED_PIN] = board.D16

########## I2C SERVO NUMBER #########

config[HEAD_PWM_NB] = 4
config[WHEEL_LEFT_PWM] = 1
config[WHEEL_RIGHT_PWM] = 2
config[WHEEL_LEFT_DIR] = 0
config[WHEEL_RIGHT_DIR] = 3
config[LEFT_ARM_NB] = 8
config[RIGHT_ARM_NB] = 9

config[STOP_KEY] = "Db"
config[MAIN_LOOP_SLEEP] = 0.001

config[BASE_PATH] = "/home/ros2_ws/"
config[BASE_PATH] = config[BASE_PATH].replace('/tests', '')
config[SRC_DIRECTORY] = config[BASE_PATH] + "src/"

config[PROJECT_DIRECTORY] = config[SRC_DIRECTORY] + "vision/"

if 'unittest' in sys.modules:
    if Misc.is_raspberrypi():
        config[PROJECT_DIRECTORY] = "/home/pi/test/"
        config[LOGGING_TEST_FILE] = '/home/pi/test/logs/vision-test.log'
    else:
        config[BASE_PATH] = "/home/dadou/"
        config[PROJECT_DIRECTORY] = config[BASE_PATH]+ "Nextcloud/dev/didier/python/dadou_vision_ros/"
        config[LOGGING_TEST_FILE] = '/home/dadou/tmp/logs/vision-test.log'

config[CONFIG_DIRECTORY] = config[PROJECT_DIRECTORY] + "conf/"
config[JSON_DIRECTORY] = config[PROJECT_DIRECTORY] + "json/"
config[MEDIAS_DIRECTORY] = config[PROJECT_DIRECTORY] + 'medias/'
config[PICTURES_FOLDER] = config[MEDIAS_DIRECTORY] + 'pictures/'
config[DB_DIRECTORY] = config[PROJECT_DIRECTORY] + 'db/'

config[BASE_PATH] = config[BASE_PATH].replace('/tests', '')
config[SRC_DIRECTORY] = config[BASE_PATH] + "src/"

config[PROJECT_DIRECTORY] = config[SRC_DIRECTORY] + "vision"

config[BASE_PATH] = os.getcwd()
config[BASE_PATH] = config[BASE_PATH].replace('/tests', '')
config[LOGGING_CONFIG_TEST_FILE] = config[BASE_PATH]+'/../conf/logging-test.conf'
config[LOGGING_CONFIG_FILE] = config[BASE_PATH]+'/conf/logging/logging.conf'
config[JSON_DIRECTORY] = config[PROJECT_DIRECTORY]+ '/json/'
config[LOGGING_FILE_NAME] = config[BASE_PATH] + '/log/vision.log'
#config[LOGGING_FILE_NAME] = "/home/ros2_ws/log/vision.log"

############### JSON FILES ###############

config[JSON_COLORS] = 'colors.json'
config[JSON_LIGHTS_BASE] = 'lights_base.json'

JSON_HELMET = 'lights_helmet.json'
