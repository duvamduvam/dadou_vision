"""Tests du chargement de la configuration (vision/vision_config.py).

Aucun appel réseau, aucune dépendance au conf/secret réel de la machine : on
pointe explicitement vers des chemins de test (tmp_path, conf/secret.example)
pour que le résultat soit le même en local et en CI (où conf/secret n'existe
pas, puisque gitignoré).
"""
import os

import pytest

from vision import vision_config

SECRET_EXAMPLE = os.path.join(vision_config.REPO_ROOT, "conf", "secret.example")


def test_load_secrets_missing_file_raises_clear_error(tmp_path):
    missing = tmp_path / "does-not-exist"
    with pytest.raises(FileNotFoundError, match="conf/secret.example"):
        vision_config.load_secrets(str(missing))


def test_load_secrets_parses_example_file():
    secrets = vision_config.load_secrets(SECRET_EXAMPLE)
    assert "chatgpt_key" in secrets
    assert secrets["chatgpt_key"]  # valeur factice non vide


def test_load_secrets_ignores_comments_and_blank_lines(tmp_path):
    secret_file = tmp_path / "secret"
    secret_file.write_text("# commentaire\n\nchatgpt_key=une-cle-de-test\n")

    secrets = vision_config.load_secrets(str(secret_file))

    assert secrets == {"chatgpt_key": "une-cle-de-test"}


def test_get_secret_missing_key_raises_key_error(tmp_path, monkeypatch):
    secret_file = tmp_path / "secret"
    secret_file.write_text("chatgpt_key=une-cle-de-test\n")
    monkeypatch.setattr(vision_config, "SECRET_FILE", str(secret_file))

    assert vision_config.get_secret("chatgpt_key") == "une-cle-de-test"
    with pytest.raises(KeyError):
        vision_config.get_secret("inexistant")


def test_default_config_has_no_hardcoded_secret():
    # Le dict `config` ne doit contenir que des valeurs par défaut publiques.
    assert "chatgpt_key" not in vision_config.config
    assert vision_config.config["gpt_model"] == "gpt-4o"
    assert vision_config.config["gpt_voice"] == "alloy"
