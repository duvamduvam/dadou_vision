"""Tests de vision/ai/performance.py — logique PURE, stdlib uniquement
(json + dadou_utils_ros.utils_static, lui-même stdlib-only : aucun rclpy).

Convention : chaque test vérifie le topic ET le payload EXACTS (json.dumps
littéral), pas seulement "quelque chose a été renvoyé" — ce sont des messages
qui partent tels quels vers le robot, une faute de frappe dans le payload
(ex: "stop" au lieu de False pour speaking_stop) casse silencieusement
l'animation côté robot sans lever d'erreur Python.
"""
import json

from dadou_utils_ros.utils_static import ANIMATION, FACE

from vision.ai.performance import (
    RosMessage,
    didascalie,
    emotion,
    idle,
    speaking_start,
    speaking_stop,
    thinking,
)

# Expressions que ce module suppose présentes dans json/expressions.json du
# repo dadou_robot_ros (PAS de lecture inter-repo ici, cf. consigne — figé en
# dur, à vérifier manuellement si json/expressions.json change côté robot).
EXPRESSIONS_REQUISES = {
    "reflechit", "parle", "joie", "colere", "tristesse", "surprise",
    "glitch total", "amour neon",
}


def test_expressions_requises_est_bien_le_jeu_attendu():
    # Ce test ne vérifie rien côté robot (pas de lecture inter-repo) : il
    # fige juste la liste attendue pour qu'un changement accidentel de ce
    # set soit visible dans une revue de code.
    assert EXPRESSIONS_REQUISES == {
        "reflechit", "parle", "joie", "colere", "tristesse", "surprise",
        "glitch total", "amour neon",
    }


# --------------------------------------------------------------------------
# thinking / speaking_start / speaking_stop / idle : payload et topic exacts.
# --------------------------------------------------------------------------

def test_thinking():
    messages = thinking()
    assert len(messages) == 1
    assert messages[0].topic == FACE
    assert messages[0].payload == json.dumps("reflechit")
    assert messages[0].time_ms == 0


def test_speaking_start_default_refresh():
    messages = speaking_start()
    assert len(messages) == 1
    assert messages[0].topic == ANIMATION
    assert messages[0].payload == json.dumps("parle")
    assert messages[0].time_ms == 15000


def test_speaking_start_custom_refresh():
    messages = speaking_start(refresh_ms=5000)
    assert messages[0].time_ms == 5000


def test_speaking_stop_payload_is_json_false_not_the_string_stop():
    # Piège vérifié sur le robot (cf. CLAUDE.md) : "stop" chercherait une
    # séquence nommée stop (inexistante) ; False déclenche l'arrêt global
    # géré par animations_node.
    messages = speaking_stop()
    assert len(messages) == 1
    assert messages[0].topic == ANIMATION
    assert messages[0].payload == json.dumps(False)
    assert messages[0].payload == "false"
    assert messages[0].payload != json.dumps("stop")


def test_idle():
    messages = idle()
    assert len(messages) == 1
    assert messages[0].topic == FACE
    assert messages[0].payload == json.dumps("stop")


# --------------------------------------------------------------------------
# emotion() : mapping émotion GPT -> expression, cas neutral et inconnu.
# --------------------------------------------------------------------------

def test_emotion_happy_maps_to_joie():
    messages = emotion({"emotion": "happy"})
    assert messages == [RosMessage(FACE, json.dumps("joie"))]


def test_emotion_anger_maps_to_colere():
    messages = emotion({"emotion": "anger"})
    assert messages[0].payload == json.dumps("colere")


def test_emotion_sadness_and_sad_both_map_to_tristesse():
    assert emotion({"emotion": "sad"})[0].payload == json.dumps("tristesse")
    assert emotion({"emotion": "sadness"})[0].payload == json.dumps("tristesse")


def test_emotion_neutral_sends_face_stop():
    messages = emotion({"emotion": "neutral"})
    assert len(messages) == 1
    assert messages[0].topic == FACE
    assert messages[0].payload == json.dumps("stop")


def test_emotion_unknown_value_returns_empty_list():
    assert emotion({"emotion": "confused"}) == []


def test_emotion_none_returns_empty_list():
    assert emotion(None) == []


def test_emotion_empty_dict_returns_empty_list():
    assert emotion({}) == []


def test_emotion_params_without_emotion_key_returns_empty_list():
    # Cas réel : GPT a mis un "name" mais pas d'"emotion" dans son JSON de fin.
    assert emotion({"name": "Stephanie"}) == []


# --------------------------------------------------------------------------
# didascalie() : mots-clés multi-mots, insensibles à la casse.
# --------------------------------------------------------------------------

def test_didascalie_rire_maps_to_joie():
    assert didascalie("rit aux éclats")[0].payload == json.dumps("joie")


def test_didascalie_is_case_insensitive():
    assert didascalie("RIGOLE bruyamment")[0].payload == json.dumps("joie")
    assert didascalie("Colère noire")[0].payload == json.dumps("colere")


def test_didascalie_multi_word_keyword_sets():
    assert didascalie("soupire tristement")[0].payload == json.dumps("tristesse")
    assert didascalie("sursaute violemment")[0].payload == json.dumps("surprise")
    assert didascalie("charme son public")[0].payload == json.dumps("amour neon")
    assert didascalie("l'écran grésille")[0].payload == json.dumps("glitch total")


def test_didascalie_without_known_keyword_returns_empty_list():
    assert didascalie("hausse les épaules") == []


def test_didascalie_empty_string_returns_empty_list():
    assert didascalie("") == []
