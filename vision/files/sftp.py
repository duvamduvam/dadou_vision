import logging
from pathlib import Path

import pysftp
from urllib.parse import urlparse
import os

from vision.vision_config import UPLOAD_FOLDER, BASE_URL


class Sftp:
    def __init__(self, hostname, username, key, port=22):
        """Constructor Method"""
        self.connection = None
        self.hostname = hostname
        self.username = username
        self.key = key
        self.port = port

    def connect(self):
        """Connects to the sftp server and returns the sftp connection object"""
        try:
            # Options to ignore hostkey verification (for testing/development)
            cnopts = pysftp.CnOpts()
            cnopts.hostkeys = None  # Disable hostkey verification

            # Get the sftp connection object
            self.connection = pysftp.Connection(
                host=self.hostname,
                username=self.username,
                private_key=self.key,
                port=self.port,
                cnopts=cnopts
            )
            print(f"Connected to {self.hostname} as {self.username}.")

        except Exception as err:
            raise Exception(f"Failed to connect to {self.hostname}: {err}")

    def disconnect(self):
        """Closes the sftp connection"""
        if self.connection:
            self.connection.close()
            print(f"Disconnected from host {self.hostname}")

    def listdir(self, remote_path):
        """Lists all the files and directories in the specified remote path"""
        try:
            return self.connection.listdir(remote_path)
        except Exception as err:
            raise Exception(f"Failed to list directory {remote_path}: {err}")

    def listdir_attr(self, remote_path):
        """Lists all files and directories (with attributes) in the specified path"""
        try:
            return self.connection.listdir_attr(remote_path)
        except Exception as err:
            raise Exception(f"Failed to list directory with attributes: {remote_path}: {err}")

    def download(self, remote_path, target_local_path):
        """Downloads the file from remote SFTP server to local path"""
        try:
            print(
                f"Downloading from {self.hostname} as {self.username} [(remote: {remote_path}); (local: {target_local_path})]")

            # Create the target directory if it does not exist
            path, _ = os.path.split(target_local_path)
            if not os.path.isdir(path):
                os.makedirs(path)

            # Download the file
            self.connection.get(remote_path, target_local_path)
            print("Download completed")

        except Exception as err:
            raise Exception(f"Failed to download file {remote_path}: {err}")

    def upload(self, source_local_path, remote_path=UPLOAD_FOLDER):
        """Uploads a file from local to the SFTP server"""
        file_name = Path(source_local_path).name
        remote_path += file_name
        self.connect()
        try:
            logging.info("Uploading to {} as {} [(remote: {}); (local: {})]".format(self.hostname, self.username, remote_path, source_local_path))

            # Upload the file
            self.connection.put(source_local_path, remote_path)
            logging.info("Upload completed")

        except Exception as err:
            raise Exception(f"Failed to upload file {source_local_path}: {err}")

        self.disconnect()
        return BASE_URL+file_name


