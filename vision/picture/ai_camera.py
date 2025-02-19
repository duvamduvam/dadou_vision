from datetime import datetime
import logging

import asyncssh
import cv2
import os

import paramiko
import pysftp

from dadou_utils.utils_static import PICTURES_FOLDER
from vision.vision_config import config


class AICamera:
    def __init__(self):
        self.pictures_folder = config[PICTURES_FOLDER]
        self.current_photo = None

    def take_photo(self, picture_name=None):
        # Ouvre la caméra

        if not picture_name:
            date_actuelle = datetime.today()
            self.current_photo = date_actuelle.strftime("%Y-%m-%d_%H-%M-%S.jpg")

        cap = cv2.VideoCapture(0)

        if not cap.isOpened():
            print("Impossible d'accéder à la caméra")
            return

        # Capture une image
        ret, frame = cap.read()

        if ret:
            # Chemin complet du fichier de la photo
            picture_path = os.path.join(self.pictures_folder, self.current_photo)

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

    def get_current_photo(self):
        photo = None
        if self.current_photo:
            photo = self.current_photo
            self.current_photo = None
        return photo

    @staticmethod
    def upload():

        hostname = 'cloud.duvam.net'
        port = 22
        username = 'david'

        local_image_path = '/home/dadou/Nextcloud/Didier/python/dadou_vision/medias/pictures/2024-10-19_13-04-00.jpg'
        remote_image_path = '.'

        try:
            # Création d'un client SSH
            ssh = paramiko.SSHClient()

            # Ajoute automatiquement les clés du serveur s'il n'est pas déjà dans known_hosts
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # Connexion au serveur SSH
            key = paramiko.RSAKey.from_private_key_file('/home/dadou/Nextcloud/divers/keys/kimsufi')
            ssh.connect(hostname, port, username, pkey=key)

            # Ouverture de la connexion SFTP
            sftp = ssh.open_sftp()

            # Transfert du fichier image
            sftp.put(local_image_path, remote_image_path)
            print(f"Image transférée avec succès à {remote_image_path}")

            # Fermeture de la connexion SFTP
            sftp.close()
            ssh.close()

        except Exception as e:
            logging.error('exception {}'.format(e), exc_info=True)

    async def upload2(self):
        hostname = 'cloud.duvam.net'
        username = 'david'

        # Chemin vers la clé privée
        private_key_path = '/home/dadou/Nextcloud/divers/keys/kimsufi'

        # Chemins des fichiers
        local_image_path = '/home/dadou/Nextcloud/Didier/python/dadou_vision/medias/pictures/2024-10-19_13-04-00.jpg'
        remote_image_path = '.'

        # Connexion SSH avec clé privée
        try:
            async with asyncssh.connect(hostname, username=username, client_keys=private_key_path) as conn:
                async with conn.start_sftp_client() as sftp:
                    await sftp.put(local_image_path, remote_image_path)
                    logging.info("Image transférée avec succès !")
        except Exception as e:
            logging.error('exception {}'.format(e), exc_info=True)

    async def upload3(self):
        hostname = 'cloud.duvam.net'
        username = 'david'

        # Chemin vers la clé privée
        private_key_path = '/home/dadou/Nextcloud/divers/keys/kimsufi'

        # Chemins des fichiers
        local_image_path = '/home/dadou/Nextcloud/Didier/python/dadou_vision/medias/pictures/2024-10-19_13-04-00.jpg'
        remote_image_path = './medias/'

        # Connexion SSH avec clé privée
        try:
            with pysftp.Connection(hostname, username=username, private_key_pass=private_key_path) as sftp:
                sftp.put(local_image_path, remote_image_path)
                print("Image transférée avec succès !")
        except Exception as e:
            logging.error('exception {}'.format(e), exc_info=True)