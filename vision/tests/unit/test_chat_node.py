"""Tests de vision/nodes/_chat_wiring.py — SANS rclpy.

QUOI : vision/nodes/chat_node.py importe rclpy en tête de module (comme tous
       les nodes du repo) — son import échoue systématiquement en CI (rclpy
       absent du host, cf. CLAUDE.md "tests unitaires (host, sans ROS ni
       matériel)"). Les deux bouts de logique de chat_node testables sans ROS
       (traduction RosMessage -> kwargs StringTime, construction des défauts
       de paramètres ROS depuis la config) ont donc été extraits dans
       vision/nodes/_chat_wiring.py, un module PUR (aucun rclpy ni
       robot_interfaces) — ce fichier de test n'importe QUE lui, jamais
       vision.nodes.chat_node.
"""
from vision.ai.performance import RosMessage
from vision.nodes._chat_wiring import (decode_persona_command, default_chat_parameters,
                                        ros_message_to_string_time_kwargs)
from vision.vision_config import config


# ---------------------------------------------------------------------------
# ros_message_to_string_time_kwargs
# ---------------------------------------------------------------------------

def test_ros_message_to_string_time_kwargs_payload_et_duree():
    message = RosMessage(topic="face", payload='"joie"', time_ms=1500)

    kwargs = ros_message_to_string_time_kwargs(message)

    assert kwargs == {"msg": '"joie"', "time": 1500, "anim": False}


def test_ros_message_to_string_time_kwargs_duree_par_defaut():
    # RosMessage.time_ms par défaut = 0 (cf. vision.ai.performance.thinking,
    # qui ne fixe pas de durée) : le kwarg "time" doit refléter cette valeur
    # telle quelle, pas une valeur magique différente.
    message = RosMessage(topic="face", payload='"reflechit"')

    kwargs = ros_message_to_string_time_kwargs(message)

    assert kwargs["time"] == 0


def test_ros_message_to_string_time_kwargs_anim_toujours_false():
    # anim=False FIXE quel que soit le topic (cf. docstring du module :
    # chat_node ne rejoue jamais de SÉQUENCE d'animation, seulement des
    # commandes ponctuelles) — vérifié aussi bien sur face que sur animation.
    face_kwargs = ros_message_to_string_time_kwargs(RosMessage(topic="face", payload="1"))
    animation_kwargs = ros_message_to_string_time_kwargs(RosMessage(topic="animation", payload="1"))

    assert face_kwargs["anim"] is False
    assert animation_kwargs["anim"] is False


# ---------------------------------------------------------------------------
# default_chat_parameters
# ---------------------------------------------------------------------------

def test_default_chat_parameters_reprend_la_config_unique():
    # Chaque valeur DOIT venir de vision_config.config (source unique, cf.
    # docstring vision_config.py) — pas une copie qui pourrait diverger si
    # config["chat_*"] change un jour sans que ce module soit mis à jour.
    defaults = default_chat_parameters()

    assert defaults["llm_model"] == config["chat_llm_model"]
    assert defaults["llm_base_url"] == config["chat_llm_base_url"]
    assert defaults["whisper_model"] == config["chat_whisper_model"]
    assert defaults["piper_voice"] == config["chat_piper_voice"]
    assert defaults["mic_device"] == config["chat_mic_device"]
    assert defaults["out_device"] == config["chat_out_device"]
    assert defaults["refresh_ms"] == config["chat_animation_refresh_ms"]
    assert defaults["beep_seconds"] == config["chat_beep_seconds"]
    assert defaults["persona"] == config["chat_persona"]


def test_default_chat_parameters_couvre_exactement_les_parametres_ros():
    # Fige la liste des 9 paramètres ROS déclarés par ChatNode.__init__ : un
    # ajout/retrait de paramètre ROS doit être visible ici en revue, pas
    # découvert au runtime sur le robot. ("persona" ajouté au lot D3,
    # atelier du 2026-07-13.)
    assert set(default_chat_parameters().keys()) == {
        "llm_model", "llm_base_url", "whisper_model", "piper_voice",
        "mic_device", "out_device", "refresh_ms", "beep_seconds", "persona",
    }


# ---------------------------------------------------------------------------
# decode_persona_command (lot D3 : topic `persona`, changement de
# personnalité à chaud)
# ---------------------------------------------------------------------------

def test_decode_persona_command_brut_et_json():
    # La console web envoie du brut, un `ros2 topic pub` de débogage envoie
    # souvent du JSON avec guillemets : les deux doivent donner le même nom.
    assert decode_persona_command("bougon") == "bougon"
    assert decode_persona_command('"bougon"') == "bougon"


def test_decode_persona_command_normalise_casse_et_espaces():
    # « Bougon » tapé à la main dans un ros2 topic pub doit matcher la clé
    # ASCII minuscule de vision.ai.personas.
    assert decode_persona_command("  Bougon ") == "bougon"
    assert decode_persona_command('" NAIF"') == "naif"


def test_decode_persona_command_ne_valide_pas():
    # La validation appartient à personas.compose_system_prompt (le node
    # loggue un warning sur ValueError) : ici un nom inconnu ressort
    # normalisé, jamais une exception.
    assert decode_persona_command("grincheux") == "grincheux"
