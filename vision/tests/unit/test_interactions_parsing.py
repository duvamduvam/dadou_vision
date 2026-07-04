"""Tests du parsing du JSON d'émotion en fin de réponse GPT.

La fonction vit dans vision/ai/emotion_parser.py (logique pure, sans appel
réseau ni dépendance lourde) pour rester testable indépendamment de
vision/ai/interactions.py, qui orchestre l'appel réel à l'API OpenAI.
Durcie à la refonte V0 : json.loads (et non plus ast.literal_eval) + gestion
explicite de l'absence de JSON. Aucun appel API dans ces tests — uniquement
des réponses GPT simulées (chaînes de caractères en dur).
"""
from vision.ai.emotion_parser import extract_emotion_json


def test_extracts_simple_emotion():
    text, params = extract_emotion_json('Je suis content de te voir ! {"emotion": "happy"}')
    assert text == "Je suis content de te voir !"
    assert params == {"emotion": "happy"}


def test_extracts_name_and_emotion():
    message = 'Enchanté Stephanie ! {"name": "Stephanie", "emotion": "happy"}'
    text, params = extract_emotion_json(message)
    assert text == "Enchanté Stephanie !"
    assert params == {"name": "Stephanie", "emotion": "happy"}


def test_photo_request_flag():
    message = 'Montre-moi une photo. {"photo": "true"}'
    _, params = extract_emotion_json(message)
    assert params == {"photo": "true"}


def test_no_json_returns_message_untouched():
    text, params = extract_emotion_json("Juste une phrase sans aucun JSON.")
    assert text == "Juste une phrase sans aucun JSON."
    assert params is None


def test_invalid_json_is_ignored_not_raised():
    # Ancien format (guillemets simples, invalide en JSON strict) : on ignore
    # proprement plutôt que de planter — c'était le risque d'ast.literal_eval
    # (qui évalue n'importe quel littéral Python, pas seulement des dicts).
    message = "Une réponse bancale {'emotion': 'happy'}"
    text, params = extract_emotion_json(message)
    assert params is None
    assert text == message


def test_empty_message():
    text, params = extract_emotion_json("")
    assert text == ""
    assert params is None


def test_only_the_last_json_block_is_used():
    # Le prompt (ai_static.AI_INSTRUCTIONS) demande le JSON en toute fin de
    # réponse : si le texte parlé contient lui-même des accolades, seul le
    # dernier bloc {...} doit être interprété comme les paramètres.
    message = 'Réponse étrange {"a": 1}{"b": [1, 2]}'
    text, params = extract_emotion_json(message)
    assert params == {"b": [1, 2]}
    assert text == 'Réponse étrange {"a": 1}'
