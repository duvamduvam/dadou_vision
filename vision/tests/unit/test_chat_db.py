"""Tests de ChatDB (SQLite isolé en tmp_path — jamais le fichier de prod db/chat.db)."""
from vision.db.chat_db import ChatDB


def test_create_insert_and_history_summary(tmp_path):
    ChatDB.configure(str(tmp_path / "test_chat.db"))

    entry = ChatDB.create({})
    assert entry is not None
    assert entry.speaker_name is None

    entry.add_user_text("salut Didier")
    entry.add_system_text("salut, comment vas-tu ?")

    history = entry.get_history()
    assert history == [
        {"role": "user", "content": "salut Didier"},
        {"role": "system", "content": "salut, comment vas-tu ?"},
    ]


def test_tokens_defaults_to_zero_and_is_settable(tmp_path):
    ChatDB.configure(str(tmp_path / "test_chat_tokens.db"))

    entry = ChatDB.create({})
    assert entry.tokens == 0

    entry.tokens = 42
    assert entry.tokens == 42


def test_configure_creates_missing_directory(tmp_path):
    # db/ est gitignoré : sur une machine fraîche (CI), le dossier n'existe
    # pas encore. configure() doit le créer plutôt que planter.
    db_path = tmp_path / "nested" / "does" / "not" / "exist" / "chat.db"

    ChatDB.configure(str(db_path))

    assert db_path.parent.is_dir()
