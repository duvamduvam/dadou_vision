import unittest

from robot.db.db_manager import DBManager
from vision.db.chat_db import ChatDB


class MyTestCase(unittest.TestCase):
    def test_add_db_conversation(self):
        ChatDB.createTable(ifNotExists=True)
        ai_text = "ai text truc machin"
        speaker_text = "speaker text truc machin"
        entry = ChatDB.create({})
        #entry = DBManager.insert(ChatDB, {})
        entry.add_user_text(speaker_text)
        entry.add_system_text(ai_text)
        entry.add_user_text(speaker_text)
        entry.add_system_text(ai_text)

if __name__ == '__main__':
    unittest.main()


