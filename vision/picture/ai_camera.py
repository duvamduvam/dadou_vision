from datetime import datetime
import logging
import cv2

from dadou_utils_ros.utils_static import PICTURES_FOLDER
from vision.files.sftp import Sftp
from vision.vision_config import config, SSH_HOSTNAME, SSH_USERNAME, SSH_KEY


class AICamera:

    sftp = Sftp(
        hostname=SSH_HOSTNAME,
        username=SSH_USERNAME,
        key=SSH_KEY,
    )
    def __init__(self):
        self.pictures_folder = config[PICTURES_FOLDER]
        self.current_photo = None

    def take_photo(self, picture_name=None):
        # Ouvre la caméra
        cap = cv2.VideoCapture(0)

        if not picture_name:
            date_actuelle = datetime.today()
            picture_name = date_actuelle.strftime("%Y-%m-%d_%H-%M-%S.jpg")

        if not cap.isOpened():
            print("Impossible d'accéder à la caméra")
            return

        # Capture une image
        ret, frame = cap.read()

        if ret:
            # Chemin complet du fichier de la photo
            self.current_photo = config[PICTURES_FOLDER] + picture_name

            # Enregistre l'image dans le chemin spécifié
            cv2.imwrite(self.current_photo, frame)
            logging.info("save photo in {}".format(self.current_photo))

        else:
            print("Échec de la capture de l'image")

        # Libère la caméra
        cap.release()
        #return picture_path

    def has_photo(self):
        return self.current_photo is not None

    def take_and_upload_photo(self):
        self.take_photo()
        return self.sftp.upload(self.current_photo)

    def get_current_photo(self):
        photo = None
        if self.current_photo:
            photo = self.current_photo
            self.current_photo = None
        return photo
