"""Extraction du JSON d'émotion en fin de réponse GPT — logique PURE.

Le prompt système (vision.ai.ai_static.AI_INSTRUCTIONS) demande à GPT de
terminer sa réponse par un objet JSON valide, ex: {"emotion": "happy"} ou
{"name": "Stephanie", "emotion": "happy", "photo": "true"}.

Durci à la refonte V0 : json.loads (et non plus ast.literal_eval, qui évalue
n'importe quel littéral Python — dangereux si la réponse contenait autre
chose qu'un dict) + gestion explicite de l'absence de JSON, un cas normal
(GPT n'ajoute pas toujours le bloc), pas une erreur.

Isolée dans son propre module (aucun import lourd : json + logging stdlib
uniquement) pour rester testable sans OpenAI/opencv/pyaudio/sqlobject —
vision.ai.interactions l'importe pour l'orchestration réelle.
"""
import json
import logging

NAME_KEY = "name"
PHOTO_KEY = "photo"
EMOTION_KEY = "emotion"


def extract_emotion_json(message):
    """Sépare le texte à dire du JSON de paramètres en fin de message.

    Retourne (texte, parametres) :
      - si un JSON valide est trouvé en fin de message : (texte sans le
        JSON, dict des paramètres) ;
      - sinon (pas de JSON, ou JSON invalide) : (message intact, None).
    """
    if not message:
        return message, None

    start = message.rfind("{")
    end = message.rfind("}")
    if start == -1 or end == -1 or end < start:
        return message, None

    try:
        parameters = json.loads(message[start:end + 1])
    except json.JSONDecodeError:
        logging.warning("Bloc JSON d'émotion invalide ignoré : %r", message[start:end + 1])
        return message, None

    if not isinstance(parameters, dict):
        return message, None

    text = message[:start].rstrip()
    return text, parameters
