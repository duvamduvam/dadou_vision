import logging

# '{}_{}_{}_{}'.format(s1, i, s2, f)
from dadou_utils.files.abstract_json_manager import AbstractJsonManager
from dadou_utils.utils_static import COLOR, JSON_LIGHTS_BASE
from dadou_utils.utils_static import JSON_AUDIOS, JSON_COLORS, JSON_MAPPINGS, \
    JSON_LIGHTS
from vision.vision_config import JSON_HELMET


class HardDriveJsonManager(AbstractJsonManager):
    logging.info("start json manager")

    colors = None
    lights = None
    lights_seq = None

    def __init__(self, config):
        self.config = config
        component = [self.config[JSON_COLORS], config[JSON_LIGHTS_BASE], JSON_HELMET]

        super().__init__(config, component)

