from datetime import datetime
import logging

import cv2
import os

from dadou_utils.utils_static import PICTURES_FOLDER
from vision.vision_config import config


class AIPicture:
    def __init__(self):
        self.pictures_folder = config[PICTURES_FOLDER]


    def prendre_photo(self, picture_name=None):
        # Ouvre la caméra

        if not picture_name:
            date_actuelle = datetime.today()
            picture_name = date_actuelle.strftime("%Y-%m-%d_%H-%M-%S.jpg")

        cap = cv2.VideoCapture(0)

        if not cap.isOpened():
            print("Impossible d'accéder à la caméra")
            return

        # Capture une image
        ret, frame = cap.read()

        if ret:
            # Chemin complet du fichier de la photo
            chemin_complet = os.path.join(self.pictures_folder, picture_name)

            # Enregistre l'image dans le chemin spécifié

            cv2.imwrite(chemin_complet, frame)
            logging.info("save photo in {}".format(chemin_complet))

        else:
            print("Échec de la capture de l'image")

        # Libère la caméra
        cap.release()



