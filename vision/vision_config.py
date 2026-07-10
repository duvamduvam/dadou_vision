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

from vision.audio.vad import VadConfig

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

    # --- Brique conversation temps réel (V2 streaming) ---------------------
    # Toutes les valeurs ci-dessous sont issues du proto validé le 10/07
    # (cf. CLAUDE.md) : mesures faites sur le Pi 5 réel, pas des choix
    # arbitraires — à réviser seulement après un nouveau test scénique si le
    # comportement observé le justifie.

    # Modèle LLM streamé (vision/ai/llm_stream.py, StreamingBrain), via
    # OpenRouter (client OpenAI officiel avec base_url personnalisé — cf.
    # llm_stream.py). Claude Haiku 4.5 : meilleur compromis latence/coût
    # mesuré pour des réponses courtes scéniques (AI_REALTIME_RULES impose
    # 1-3 phrases, pas besoin d'un modèle plus lourd).
    "chat_llm_model": "anthropic/claude-haiku-4.5",
    "chat_llm_base_url": "https://openrouter.ai/api/v1",

    # STT local (vision/ai/stt.py, FasterWhisperStt) : "base" retenu comme
    # meilleur compromis précision/latence au 10/07. Repli documenté : "tiny"
    # si le Pi 5 peine en charge réelle sur une séquence de spectacle complète
    # (plus rapide, plus d'erreurs de transcription) — à arbitrer après un
    # test scénique en conditions réelles, pas en atelier.
    "chat_whisper_model": "base",

    # Voix Piper de Didier (vision/ai/tts_piper.py) : modèle .onnx rangé dans
    # medias/voices/ comme les autres assets propres au personnage (cohérent
    # avec pictures_folder ci-dessus — medias/ = données du personnage,
    # conf/ = config/secrets). Le fichier n'est PAS encore présent dans le
    # dépôt au 10/07 (voix pas encore choisie/entraînée) : ce chemin est la
    # valeur par défaut que tts_piper.py utilisera dès que le modèle sera
    # déposé, pas une garantie qu'il existe déjà sur le disque.
    "chat_piper_voice": os.path.join(REPO_ROOT, "medias", "voices", "didier.onnx"),

    # Périphériques ALSA (alias définis dans /etc/asound.conf du Pi 5, cf.
    # proto validé du 10/07 — noms retenus tels quels, pas de nom de carte
    # brut type "hw:1,0" qui casserait au moindre changement de câblage USB).
    "chat_mic_device": "casque_mic",
    "chat_out_device": "mixette",

    # Durée de rafraîchissement (ms) de l'animation "parle" republiée à
    # chaque Sentence tant que le TTS streame (vision/ai/performance.py
    # speaking_start) : 15 s de marge large — une phrase TTS dure rarement
    # plus de quelques secondes, cette valeur ne sert qu'à ne jamais couper
    # l'animation par accident si le flux LLM ralentit ponctuellement.
    "chat_animation_refresh_ms": 15000,

    # Durée (s) de la piste de bips de réflexion (vision/audio/beeps.py),
    # jouée pendant le STT : 2,0 s mesurées comme la latence typique de
    # FasterWhisperStt "base" sur un énoncé court au 10/07 — assez pour
    # couvrir le silence perçu par le public sans que les bips ne s'arrêtent
    # avant la fin réelle du STT.
    "chat_beep_seconds": 2.0,

    # VAD (vision/audio/vad.py) : instance VadConfig avec ses valeurs par
    # défaut déjà validées (cf. docstring de VadConfig) — un objet complet
    # plutôt que des clés de config éclatées, pour rester la source unique de
    # vérité si VadConfig gagne de nouveaux champs un jour.
    "chat_vad": VadConfig(),
}

WAKE_UP_WORD = config["wake_up_word"]
