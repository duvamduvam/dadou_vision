import unittest
import logging.config

from dadou_utils.logging_conf import LoggingConf
from dadou_utils.utils_static import LOGGING_LAPTOP_TEST_FILE_NAME, LOGGING_TEST_FILE_NAME
from vision.files.sftp import Sftp
from vision.vision_config import SSH_HOSTNAME, SSH_USERNAME, SSH_KEY, config


class testSFTP(unittest.TestCase):
    logging.config.dictConfig(LoggingConf.get(config[LOGGING_TEST_FILE_NAME], "test_sftp"))

    sftp = Sftp(
        hostname=SSH_HOSTNAME,
        username=SSH_USERNAME,
        key=SSH_KEY,
    )
    def test_transfer(self):
        # Connect to SFTP

        self.sftp.connect()

        # List files and directories in the root directory "/"
        #remote_path = "/"
        #print(f"List of files at location {remote_path}:")
        #for file in self.sftp.listdir(remote_path):
        #    print(file)

        # Upload a file to the SFTP server
        local_file = '/home/pi/test/medias/pictures/2024-10-19_00-59-17.jpg'
        remote_file = '/var/www/wordpress__5/wp-content/uploads/medias/2024-10-19_00-59-16.jpg'

        # List files and their attributes
        #print(f"List of files with attributes at location {remote_path}:")
        #for attr in self.sftp.listdir_attr(remote_path):
        #    print(attr.filename, attr.st_size, attr.st_mtime)

        self.sftp.upload(local_file, remote_file)

        # Download a file from the SFTP server
        #self.sftp.download(remote_file, local_file + '.backup')

        # Disconnect from SFTP
        self.sftp.disconnect()


if __name__ == '__main__':
    unittest.main()
