"""Gate de publication AMONT sur le topic `animation_state` — logique PURE
(stdlib uniquement, comme vision.ai.performance : au plus FACE/ANIMATION de
dadou_utils_ros.utils_static, zéro import rclpy).

POURQUOI ce gate existe : étude d'arbitrage des actionneurs du 2026-07-12
(dadou_robot_ros/docs/etude-arbitrage-actionneurs.md, §3/§5/§6) — sur scène,
le visage et la tête sautent/clignotent dès que plusieurs programmes y
publient en même temps, parce qu'aucun arbitre n'existe (contrairement aux
roues, qui ont déjà `twist_mux`). La solution retenue à l'étage AMONT (§5.2) :
`animations_node` (dépôt robot) publie un état latché `animation_state` (nom
de la séquence en cours, "" au repos) ; les comportements autonomes (ici le
chat) s'y abonnent et se TAISENT quand une séquence a la main — règle
scénique simple : « une animation en cours a la main sur le visage et la
tête ». Ce module implémente ce gate côté chat_node, pour couvrir deux
scénarios de collision vérifiés dans le code (étude §3) :
  - S1 : un bruit de salle déclenche thinking() (face="reflechit") PENDANT
    qu'une séquence de spectacle joue -> le chat ne doit PAS écraser son
    visage.
  - S2 : speaking_stop() publie animation=False, qui déclenche un arrêt
    GLOBAL côté animations_node (TOUTES les pistes, pas seulement "parle")
    -> le chat ne doit tuer QUE sa propre animation, jamais une séquence de
    spectacle en cours ni faire un stop global au repos (no-op nocif).

Le node (chat_node) reste responsable de la souscription ROS et du stockage
de l'état ; ce module ne fait QUE la décision pure allow_message(), testée
sans ROS (cf. vision/tests/unit/test_arbitration.py).
"""
from __future__ import annotations

import json
from typing import Optional

from dadou_utils_ros.utils_static import ANIMATION

# Seule séquence que le chat lance et possède (cf. vision.ai.performance.
# speaking_start/speaking_stop) : le stop ciblé ci-dessous ne doit jamais
# pouvoir arrêter une autre séquence que celle-ci.
CHAT_ANIMATION = "parle"

# Marge (s) ajoutée au temps restant annoncé (StringTime.time = remaining_ms)
# pour armer la PÉREMPTION de l'état : la fin de séquence normale arrive par
# un "" sur animation_state, mais si animations_node meurt en pleine séquence
# ce "" ne vient jamais — sans péremption le chat resterait muet pour
# toujours (panne silencieuse). Déclinaison du deadman maison, même motif que
# STATE_EXPIRY_MARGIN_MS côté gaze (dadou_robot_ros/gaze_follower_node.py).
# animations_node RE-publie l'état à chaque (re)démarrage de séquence (même
# nom compris) précisément pour que cette échéance soit réarmée.
STATE_EXPIRY_MARGIN_S = 2.0


def state_expiry(remaining_ms: int, now_monotonic: float) -> float:
    """Échéance (secondes, horloge MONOTONE) au-delà de laquelle un état
    ACTIF est périmé. remaining_ms <= 0 (producteur hors contrat) : seule la
    marge protège — 2 s de silence au pire, jamais muet pour toujours."""
    return now_monotonic + max(remaining_ms, 0) / 1000.0 + STATE_EXPIRY_MARGIN_S


def effective_state(state: Optional[str], expiry_monotonic: float,
                    now_monotonic: float) -> Optional[str]:
    """État à passer à allow_message une fois la péremption appliquée : un
    état ACTIF (nom non vide) dont l'échéance est dépassée est traité comme
    le repos "" (animations_node probablement mort — le chat reprend la
    parole plutôt que de se taire pour toujours). None (jamais reçu) et ""
    (repos) passent inchangés : il n'y a rien à périmer."""
    if state and now_monotonic > expiry_monotonic:
        return ""
    return state


def parse_animation_state(raw: str) -> str:
    """Traduit le payload StringTime brut du topic `animation_state` en nom
    de séquence en cours ("" au repos). Tolérant comme le reste du dépôt
    (cf. chat_node._on_chat_cmd, même contrat StringTime) : json.loads si
    possible (le contrat nominal est json.dumps(nom_ou_"")), valeur brute
    sinon. Tout ce qui n'est PAS une chaîne une fois décodé (nombre, objet,
    liste, None...) -> "" (repos) : un producteur qui publierait un contenu
    inattendu ne doit jamais faire planter l'arbitrage, seulement dégrader
    vers l'hypothèse la plus permissive côté état (le VRAI garde-fou contre
    un état invalide est la règle animation_state is None de allow_message,
    pas ce parsing).
    """
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        value = raw
    return value if isinstance(value, str) else ""


def allow_message(topic: str, payload: str, animation_state: Optional[str]) -> bool:
    """Le message chat (topic FACE ou ANIMATION, payload = json.dumps(valeur),
    cf. RosMessage de vision.ai.performance) a-t-il le droit de partir, vu
    l'état `animation_state` courant ?

    Règles (cf. docstring de module pour le POURQUOI) :
    - `animation_state is None` (jamais reçu : topic absent ou robot pas à
      jour) : TOUT passe — comportement HISTORIQUE conservé, dégradation
      douce plutôt que faire taire le chat indéfiniment faute d'information ;
    - stop d'animation (topic ANIMATION, payload json `false`) : passe
      SEULEMENT si l'animation en cours est CHAT_ANIMATION ("parle") — un
      stop ciblé ne doit JAMAIS tuer une séquence de spectacle (S2), et au
      repos ("") un stop est un no-op NOCIF : animations_node y répond par un
      arrêt GLOBAL sur TOUTES les pistes (face, servos, roues, audio) ;
    - payload ANIMATION illisible (ni `false` ni nom JSON valide) : refusé
      par défaut — même philosophie défensive que le reste du dépôt (cf.
      extract_emotion_json) : on ne peut pas distinguer un stop d'un
      lancement, mieux vaut refuser que risquer un stop global déguisé ;
    - tout le reste (FACE, lancement/refresh de "parle") : passe si l'état
      est "" (repos, personne d'autre n'a la main) ou déjà CHAT_ANIMATION (le
      chat a lancé "parle" lui-même, un refresh périodique est légitime) ;
      refusé si une AUTRE séquence de spectacle est en cours.
    """
    if animation_state is None:
        return True

    if topic == ANIMATION:
        try:
            value = json.loads(payload)
        except (ValueError, TypeError):
            return False  # payload illisible -> refus défensif, cf. docstring
        if value is False:
            return animation_state == CHAT_ANIMATION  # stop ciblé
        # Sinon : lancement/refresh d'une animation par nom (normalement
        # CHAT_ANIMATION) -> même règle "reste" que FACE ci-dessous.
        return animation_state in ("", CHAT_ANIMATION)

    # FACE (ou tout topic non-ANIMATION) : le contenu du payload n'a pas à
    # être inspecté, seule la question "qui a la main" compte.
    return animation_state in ("", CHAT_ANIMATION)
