"""Traduction des événements de jeu (vision.ai.stream_parser) en messages
StringTime ROS pour le robot — logique PURE, stdlib uniquement.

QUOI : ce module ne PUBLIE rien lui-même (aucun import rclpy) — il produit
       des RosMessage (topic/payload/durée) que le node appelant (chat_node,
       V2) transmettra tel quel à ses publishers `face`/`animation` déjà
       existants côté robot (dadou_robot_ros, lights_node.py/animations_node.py
       : StringTime.msg = json.dumps(valeur), StringTime.time = durée en ms).
       Zéro nouveau topic : on réutilise les topics FACE/ANIMATION du robot,
       cf. ARCHITECTURE.md ("V2 : émotions et parole via les topics EXISTANTS
       du robot — zéro modif côté robot").
POURQUOI séparé de stream_parser.py : stream_parser ne connaît que le texte
       (Sentence/Didascalie/Emotion), il ignore tout des topics ROS et du
       vocabulaire d'expressions du robot (joie/colere/...) — ce module fait
       la traduction, et lui seul a besoin des constantes FACE/ANIMATION.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import List, Optional

from dadou_utils_ros.utils_static import ANIMATION, FACE


@dataclass(frozen=True)
class RosMessage:
    topic: str
    payload: str
    time_ms: int = 0


# Émotion GPT (vision.ai.ai_static.AI_INSTRUCTIONS demande explicitement une
# valeur parmi ["anger", "disgust", "happy", "surprise", "neutral"], mais on
# tolère aussi "sad"/"sadness"/"love" ici — plus permissif que le prompt
# actuel, pour ne pas avoir à retoucher ce mapping si le prompt évolue) ->
# nom d'expression dans json/expressions.json (repo dadou_robot_ros).
# neutral -> None : cas spécial, cf. emotion() ci-dessous (stop, pas de face).
EMOTION_TO_EXPRESSION = {
    "happy": "joie",
    "anger": "colere",
    "sad": "tristesse",
    "sadness": "tristesse",
    "surprise": "surprise",
    "disgust": "glitch total",
    "love": "amour neon",
    "neutral": None,
}

# Mots-clés (français, en minuscules) reconnus dans le texte d'une didascalie
# GPT (*rit*, *soupire*...) -> expression faciale à jouer. Recherche par
# SOUS-CHAÎNE (pas de gestion des accents : "non requis" côté spec — la
# détection insensible à la casse suffit, cf. didascalie() ci-dessous) : un
# choix de prototype volontairement simple, au prix d'un risque mineur de
# faux positif sur un mot contenant la sous-chaîne (accepté ici, portée
# faible : ce ne sont que des indices d'ambiance, pas une commande critique).
DIDASCALIE_KEYWORDS = {
    ("rire", "rit", "rigole", "éclate"): "joie",
    ("colère", "fâche", "grogne", "énerve"): "colere",
    ("triste", "soupire", "pleure"): "tristesse",
    ("surpris", "étonné", "sursaute"): "surprise",
    ("amour", "cœur", "charme"): "amour neon",
    ("bug", "plante", "grésille"): "glitch total",
}


def thinking() -> List[RosMessage]:
    """GPT est en train de générer une réponse (avant le premier delta utile) :
    expression "reflechit" sur le topic face, sans durée particulière (pas de
    time_ms : l'appelant décidera de la prochaine expression à jouer, pas de
    minuterie de retour automatique nécessaire ici contrairement à speaking)."""
    return [RosMessage(FACE, json.dumps("reflechit"))]


def speaking_start(refresh_ms: int = 15000) -> List[RosMessage]:
    """Démarre l'animation de bouche "parle" (topic animation), avec une
    durée de rafraîchissement — POURQUOI une durée : contrairement à face
    (piloté par événement explicite), l'animation "parle" doit continuer tant
    que le TTS streame, sans qu'on sache à l'avance combien de temps ça va
    durer ; refresh_ms est une durée de sécurité que l'appelant doit
    reproclamer périodiquement tant que ça parle (cf. chat_node V2)."""
    return [RosMessage(ANIMATION, json.dumps("parle"), time_ms=refresh_ms)]


def speaking_stop() -> List[RosMessage]:
    """Coupe l'animation de parole. PIÈGE VÉRIFIÉ : le payload doit être
    json.dumps(False) (booléen), PAS json.dumps("stop") — "stop" serait
    interprété comme le NOM d'une séquence d'animation à chercher (il n'y en
    a pas), alors que False déclenche l'arrêt global géré par
    animations_node (dadou_robot_ros) — cf. CLAUDE.md du parc, section
    "Prochaines étapes"."""
    return [RosMessage(ANIMATION, json.dumps(False))]


def emotion(params: Optional[dict]) -> List[RosMessage]:
    """Traduit les paramètres d'émotion extraits par
    vision.ai.emotion_parser.extract_emotion_json en expression faciale.
    - params vide/None : rien à jouer, liste vide (pas d'erreur : c'est l'état
      normal quand GPT n'a pas mis de clé "emotion" dans son JSON de fin).
    - "neutral" : cas spécial, face "stop" (pas d'expression figée, retour à
      l'état neutre du visage — différent de idle() ci-dessous seulement par
      intention documentée, même payload en pratique).
    - valeur inconnue du mapping : liste vide (on ignore plutôt que planter —
      même philosophie défensive que extract_emotion_json)."""
    if not params:
        return []
    key = params.get("emotion") if isinstance(params, dict) else None
    if key not in EMOTION_TO_EXPRESSION:
        return []
    expression = EMOTION_TO_EXPRESSION[key]
    if expression is None:  # neutral
        return [RosMessage(FACE, json.dumps("stop"))]
    return [RosMessage(FACE, json.dumps(expression))]


def didascalie(action: str) -> List[RosMessage]:
    """Traduit le texte d'une didascalie (*rit*, *soupire*...) en expression
    faciale si un mot-clé reconnu y figure ; liste vide sinon (une didascalie
    sans mot-clé connu ne déclenche aucune action visuelle — elle reste
    ignorée plutôt que de faire planter la performance)."""
    normalized = (action or "").lower()
    for keywords, expression in DIDASCALIE_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            return [RosMessage(FACE, json.dumps(expression))]
    return []


def idle() -> List[RosMessage]:
    """Retour à l'état neutre du visage (fin d'interaction, pas de GPT en
    cours) : face "stop"."""
    return [RosMessage(FACE, json.dumps("stop"))]
