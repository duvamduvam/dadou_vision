"""Capture photo depuis la webcam USB (recyclée de vision/picture/ai_camera.py).

L'upload SFTP vers le VPS (ancien vision/files/sftp.py, dépendait de pysftp,
non maintenu) a été retiré à la refonte V0 : la V2 enverra les photos
directement à l'API OpenAI en base64 (cf. ChatDB.add_user_img_base64) plutôt
que de les héberger sur un serveur tiers.
"""
import logging
from datetime import datetime

import cv2

from vision.vision_config import config


class AICamera:
    """Capture une image depuis la webcam USB (/dev/video0)."""

    def __init__(self):
        self.pictures_folder = config["pictures_folder"]
        self.current_photo = None

    def take_photo(self, picture_name=None):
        """Capture une image et la sauvegarde sur disque. Retourne le chemin, ou None si échec."""
        cap = cv2.VideoCapture(0)

        if not picture_name:
            picture_name = datetime.today().strftime("%Y-%m-%d_%H-%M-%S.jpg")

        if not cap.isOpened():
            logging.error("Impossible d'accéder à la caméra")
            return None

        ret, frame = cap.read()
        cap.release()

        if not ret:
            logging.error("Échec de la capture de l'image")
            return None

        self.current_photo = self.pictures_folder + picture_name
        cv2.imwrite(self.current_photo, frame)
        logging.info("Photo enregistrée dans %s", self.current_photo)

        return self.current_photo

    def has_photo(self):
        return self.current_photo is not None

    def get_current_photo(self):
        photo = self.current_photo
        self.current_photo = None
        return photo
