"""Configuration UNIQUE de dadou_vision_ros.

Toutes les valeurs runtime (modèle GPT, voix TTS, chemins de données) et les
secrets (clé API...) passent par ce module : aucun autre fichier ne doit lire
`conf/secret` directement ni coder une valeur par défaut en dur.

`conf/secret` est gitignoré (dépôt GitHub PUBLIC) : voir `conf/secret.example`
pour le format attendu — une ligne `cle=valeur` par secret, commentaires `#`
et lignes vides ignorés. Le chargement est volontairement paresseux
(`get_secret` n'est appelé que par les classes qui en ont vraiment besoin,
au moment de l'usage) pour que les modules purs (parsing, config, db) restent
importables et testables même sans `conf/secret` sur la machine (CI).
"""
import os

# Racine du dépôt : vision/vision_config.py -> vision/ -> racine.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRET_FILE = os.path.join(REPO_ROOT, "conf", "secret")


def load_secrets(path):
    """Parse un fichier clé=valeur tolérant (commentaires '#', lignes vides).

    Lève une erreur explicite si le fichier est absent : mieux vaut un crash
    clair au démarrage (avec le chemin et la marche à suivre) qu'une clé vide
    qui échoue plus tard, silencieusement, sur un appel réseau.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(
            "Secret manquant : {}\n"
            "Copiez conf/secret.example vers conf/secret et renseignez vos "
            "clés (fichier gitignoré, jamais commité — dépôt GitHub public)."
            .format(path)
        )
    secrets = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            secrets[key.strip()] = value.strip()
    return secrets


def get_secret(key):
    """Retourne un secret par nom depuis conf/secret (erreur claire si absent/vide)."""
    secrets = load_secrets(SECRET_FILE)
    if not secrets.get(key):
        raise KeyError(
            "Clé '{}' absente ou vide dans {} (voir conf/secret.example)."
            .format(key, SECRET_FILE)
        )
    return secrets[key]


# --- Valeurs par défaut saines (aucune donnée sensible ici) --------------

config = {
    # Brique GPT (vision/ai/interactions.py)
    "gpt_model": "gpt-4o",
    "max_tokens": 70,
    "wake_up_word": "didier",

    # Brique TTS (vision/ai/tts.py)
    "gpt_voice": "alloy",
    "alsa_channel": 1,

    # Historique de conversation (vision/db/chat_db.py) — db/ gardé sur
    # disque (utile V2/streaming) mais gitignoré, jamais commité.
    "db_directory": os.path.join(REPO_ROOT, "db") + os.sep,
    "chat_db": "chat.db",

    # Captures caméra (vision/ai/camera.py)
    "pictures_folder": os.path.join(REPO_ROOT, "medias", "pictures") + os.sep,
}

WAKE_UP_WORD = config["wake_up_word"]
