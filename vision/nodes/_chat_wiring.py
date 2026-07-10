"""Helpers PURS de câblage pour vision/nodes/chat_node.py — AUCUN import
rclpy ni robot_interfaces ici.

QUOI : chat_node.py importe rclpy en tête de module (comme tous les nodes du
       repo, cf. vision/nodes/person_tracker_node.py) — son import échoue
       donc systématiquement en CI (rclpy absent du host, cf. CLAUDE.md :
       "tests unitaires (host, sans ROS ni matériel)"). Ce module-ci reste
       importable PARTOUT (mêmes garanties que vision.ai.performance : stdlib
       + vision_config, rien de plus) : les deux bouts de logique du node qui
       peuvent être testés sans ROS vivent ici, et vision/tests/unit/
       test_chat_node.py n'importe QUE ce module.
POURQUOI pas dans vision/ai/performance.py : performance.py traduit déjà
       événements de jeu (Sentence/Didascalie/Emotion) -> RosMessage — une
       logique PRODUIT (quelle expression pour quelle émotion), déjà testée
       par test_performance.py. Ce module-ci fait un travail différent, plus
       proche du câblage ROS que du contenu : RosMessage -> kwargs
       StringTime, et défauts de paramètres ROS -> config. Mélanger les deux
       rendrait performance.py moins lisible pour des lots qui n'ont rien à
       voir avec son objet.
"""
from __future__ import annotations

from typing import Any, Dict

from vision.ai.performance import RosMessage
from vision.vision_config import config


def ros_message_to_string_time_kwargs(message: RosMessage) -> Dict[str, Any]:
    """Traduit un RosMessage (topic/payload/durée, cf. vision.ai.performance)
    en kwargs prêts pour `robot_interfaces.msg.StringTime(**kwargs)`.

    anim=False FIXE (jamais autre chose ici) : côté robot, ce champ marque
    qu'un message provient d'une SÉQUENCE d'animation rejouée par
    animations_node (cf. dadou_robot_ros/robot/nodes/animations_node.py,
    send_msgs — msg.anim = animations_msg[ANIMATION], utilisé ensuite pour
    armer le deadman roues sur la durée restante de la séquence). chat_node
    ne rejoue jamais de séquence : il publie des commandes ponctuelles (une
    expression faciale, le déclenchement par NOM d'une animation existante
    comme "parle") — anim doit donc toujours valoir False de ce côté-là, le
    champ par défaut du message StringTime.
    """
    return {"msg": message.payload, "time": message.time_ms, "anim": False}


def default_chat_parameters() -> Dict[str, Any]:
    """Valeurs par défaut des paramètres ROS de chat_node, lues depuis la
    config UNIQUE du dépôt (vision.vision_config.config) — jamais de valeur
    dupliquée en dur ici, cf. docstring de vision_config.py ("aucun autre
    fichier ne doit... coder une valeur par défaut en dur"). Fonction PURE
    (aucun rclpy) : ChatNode.__init__ appelle declare_parameter(nom,
    default_chat_parameters()[nom]) pour chaque paramètre — un seul endroit à
    changer si un nom de clé de config évolue.
    """
    return {
        "llm_model": config["chat_llm_model"],
        "llm_base_url": config["chat_llm_base_url"],
        "whisper_model": config["chat_whisper_model"],
        "piper_voice": config["chat_piper_voice"],
        "mic_device": config["chat_mic_device"],
        "out_device": config["chat_out_device"],
        "refresh_ms": config["chat_animation_refresh_ms"],
        "beep_seconds": config["chat_beep_seconds"],
    }
