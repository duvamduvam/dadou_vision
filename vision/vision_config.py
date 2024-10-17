import os

import board

from dadou_utils.utils_static import BASE_PATH, I2C_ENABLED, JSON_LIGHTS_SEQUENCE, \
    JSON_LIGHTS, JSON_COLORS, MAIN_LOOP_SLEEP, STOP_KEY, RIGHT_ARM_NB, LEFT_ARM_NB, WHEEL_RIGHT_DIR, \
    WHEEL_LEFT_DIR, WHEEL_RIGHT_PWM, WHEEL_LEFT_PWM, HEAD_PWM_NB, STATUS_LED_PIN, RESTART_PIN, SHUTDOWN_PIN, \
    DIGITAL_CHANNELS_ENABLED, PWM_CHANNELS_ENABLED, LIGHTS_PIN, LIGHTS_START_LED, \
    LIGHTS_END_LED, JSON_DIRECTORY, LOGGING_CONFIG_FILE, LOGGING_CONFIG_TEST_FILE, LOGGING_FILE_NAME, BRIGHTNESS, \
    JSON_LIGHTS_BASE, SINGLE_THREAD, SRC_DIRECTORY, PROJECT_DIRECTORY, LIGHTS_LED_COUNT, LOGGING_TEST_FILE_NAME

config = {}

print(dir(board))

board_list = dir(board)

HELMET_LIGHTS = 'helmet_lights'

config[I2C_ENABLED] = True
config[PWM_CHANNELS_ENABLED] = True
config[DIGITAL_CHANNELS_ENABLED] = False

config[SINGLE_THREAD] = True

GLOBAL_LIGHTS_COUNT = 128
HELMET_LIGHT_START = 65
HELMET_LIGHT_END = 128

config[BRIGHTNESS] = 0.2

config[LIGHTS_START_LED] = 0
config[LIGHTS_END_LED] = 150

config[LIGHTS_LED_COUNT] = 150

######### PROCESS ########
DISK = 'disk'
HELMET = 'helmet'
SHUTDOWN = 'shutdown'

PROCESS_LIST = [DISK, HELMET, SHUTDOWN]

########## RPI PINS #########

config[LIGHTS_PIN] = board.D18
config[SHUTDOWN_PIN] = board.D12
config[STATUS_LED_PIN] = board.D16

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

if os.path.isdir("/home/ros2_ws/"):
    config[BASE_PATH] = "/home/ros2_ws/"
else:
    config[BASE_PATH] = "/home/pi/ros2_ws/"

config[BASE_PATH] = config[BASE_PATH].replace('/tests', '')
config[SRC_DIRECTORY] = config[BASE_PATH] + "src/"

config[PROJECT_DIRECTORY] = config[SRC_DIRECTORY] + "vision"

config[BASE_PATH] = os.getcwd()
config[BASE_PATH] = config[BASE_PATH].replace('/tests', '')
config[LOGGING_CONFIG_TEST_FILE] = config[BASE_PATH]+'/../conf/logging-test.conf'
config[LOGGING_CONFIG_FILE] = config[BASE_PATH]+'/conf/logging/logging.conf'
config[JSON_DIRECTORY] = config[PROJECT_DIRECTORY]+ '/json/'
config[LOGGING_FILE_NAME] = config[BASE_PATH] + "/log/vision.log"

config[LOGGING_TEST_FILE_NAME] = '/home/pi/test/logs/vision-test.log'

############### JSON FILES ###############

config[JSON_COLORS] = 'colors.json'
config[JSON_LIGHTS_BASE] = 'lights_base.json'

JSON_HELMET = 'lights_helmet.json'
