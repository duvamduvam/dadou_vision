"""Tests de vision/ai/arbitration.py — logique PURE, stdlib uniquement
(json + dadou_utils_ros.utils_static, comme test_performance.py).

Convention : chaque test nomme explicitement l'ÉTAT animation_state testé et
le comportement ATTENDU pour les 3 familles de messages du chat (face,
lancement/refresh de "parle", stop d'animation) — c'est la matrice complète
de la règle amont (cf. docstring de vision/ai/arbitration.py) qui est le
vrai contrat ici, pas un cas isolé.
"""
import json

from dadou_utils_ros.utils_static import ANIMATION, FACE

from vision.ai.arbitration import (CHAT_ANIMATION, STATE_EXPIRY_MARGIN_S,
                                   allow_message, effective_state,
                                   parse_animation_state, state_expiry)

FACE_PAYLOAD = json.dumps("joie")  # peu importe l'expression exacte ici
PARLE_PAYLOAD = json.dumps(CHAT_ANIMATION)  # lancement/refresh de "parle"
STOP_PAYLOAD = json.dumps(False)  # speaking_stop() — cf. performance.py


# ---------------------------------------------------------------------------
# parse_animation_state
# ---------------------------------------------------------------------------

def test_parse_animation_state_json_nom_de_sequence():
    assert parse_animation_state(json.dumps("parle")) == "parle"


def test_parse_animation_state_json_chaine_vide_est_le_repos():
    assert parse_animation_state(json.dumps("")) == ""


def test_parse_animation_state_brut_non_json_tolere():
    # Pas de guillemets JSON : json.loads échoue, la valeur brute est reprise
    # telle quelle (même tolérance que chat_node._on_chat_cmd sur le topic
    # `chat`).
    assert parse_animation_state("berceuse") == "berceuse"


def test_parse_animation_state_non_chaine_devient_repos():
    # Un producteur qui publierait autre chose qu'une chaîne (nombre, objet,
    # liste, null...) ne doit jamais remonter tel quel jusqu'à allow_message.
    assert parse_animation_state(json.dumps(42)) == ""
    assert parse_animation_state(json.dumps(None)) == ""
    assert parse_animation_state(json.dumps({"nom": "parle"})) == ""
    assert parse_animation_state(json.dumps(["parle"])) == ""


# ---------------------------------------------------------------------------
# allow_message — animation_state is None : jamais reçu -> TOUT passe
# (dégradation douce, comportement historique conservé).
# ---------------------------------------------------------------------------

def test_etat_none_autorise_face():
    assert allow_message(FACE, FACE_PAYLOAD, None) is True


def test_etat_none_autorise_lancement_parle():
    assert allow_message(ANIMATION, PARLE_PAYLOAD, None) is True


def test_etat_none_autorise_stop():
    assert allow_message(ANIMATION, STOP_PAYLOAD, None) is True


# ---------------------------------------------------------------------------
# allow_message — animation_state == "" (repos) : face/parle OK, stop REFUSÉ
# (un stop au repos serait un no-op nocif : arrêt global côté animations_node).
# ---------------------------------------------------------------------------

def test_etat_repos_autorise_face():
    assert allow_message(FACE, FACE_PAYLOAD, "") is True


def test_etat_repos_autorise_lancement_parle():
    assert allow_message(ANIMATION, PARLE_PAYLOAD, "") is True


def test_etat_repos_refuse_stop():
    assert allow_message(ANIMATION, STOP_PAYLOAD, "") is False


# ---------------------------------------------------------------------------
# allow_message — animation_state == "parle" (le chat a déjà la main) : tout
# passe, y compris le stop ciblé (c'est SA propre animation).
# ---------------------------------------------------------------------------

def test_etat_parle_autorise_face():
    assert allow_message(FACE, FACE_PAYLOAD, CHAT_ANIMATION) is True


def test_etat_parle_autorise_refresh_parle():
    assert allow_message(ANIMATION, PARLE_PAYLOAD, CHAT_ANIMATION) is True


def test_etat_parle_autorise_stop():
    assert allow_message(ANIMATION, STOP_PAYLOAD, CHAT_ANIMATION) is True


# ---------------------------------------------------------------------------
# allow_message — animation_state == "berceuse" (une séquence de spectacle,
# PAS celle du chat) : tout est refusé, y compris le stop (S2 : ne jamais
# tuer une séquence en cours qui n'est pas la nôtre).
# ---------------------------------------------------------------------------

def test_etat_autre_sequence_refuse_face():
    assert allow_message(FACE, FACE_PAYLOAD, "berceuse") is False


def test_etat_autre_sequence_refuse_lancement_parle():
    assert allow_message(ANIMATION, PARLE_PAYLOAD, "berceuse") is False


def test_etat_autre_sequence_refuse_stop():
    assert allow_message(ANIMATION, STOP_PAYLOAD, "berceuse") is False


# ---------------------------------------------------------------------------
# payload ANIMATION illisible : refus défensif, MÊME si l'état aurait
# autorisé un stop propre (on ne peut pas distinguer un stop d'un lancement,
# mieux vaut refuser que risquer un arrêt global déguisé).
# ---------------------------------------------------------------------------

def test_payload_animation_illisible_est_refuse_meme_si_le_chat_a_la_main():
    assert allow_message(ANIMATION, "{pas du json", CHAT_ANIMATION) is False


# ---------------------------------------------------------------------------
# Péremption de l'état (garde-fou façon deadman) : un état ACTIF dont
# l'échéance annoncée (remaining_ms + marge) est dépassée redevient le repos
# "" — animations_node est probablement mort, le chat ne doit pas rester muet
# pour toujours. Horloge injectée (now_monotonic) : testable sans sleep.
# ---------------------------------------------------------------------------

def test_state_expiry_ajoute_le_restant_et_la_marge():
    assert state_expiry(5000, now_monotonic=100.0) == 100.0 + 5.0 + STATE_EXPIRY_MARGIN_S


def test_state_expiry_restant_negatif_ou_nul_ne_laisse_que_la_marge():
    # Producteur hors contrat (time absent/0) : 2 s de silence au pire,
    # jamais un mutisme permanent.
    assert state_expiry(0, now_monotonic=100.0) == 100.0 + STATE_EXPIRY_MARGIN_S
    assert state_expiry(-42, now_monotonic=100.0) == 100.0 + STATE_EXPIRY_MARGIN_S


def test_effective_state_actif_non_perime_reste_inchange():
    assert effective_state("berceuse", expiry_monotonic=110.0, now_monotonic=100.0) == "berceuse"


def test_effective_state_actif_perime_redevient_le_repos():
    assert effective_state("berceuse", expiry_monotonic=110.0, now_monotonic=110.1) == ""


def test_effective_state_repos_et_none_ne_periment_jamais():
    # Rien à périmer : "" (repos) et None (jamais reçu) traversent tels
    # quels, même très au-delà de l'échéance.
    assert effective_state("", expiry_monotonic=0.0, now_monotonic=1e9) == ""
    assert effective_state(None, expiry_monotonic=0.0, now_monotonic=1e9) is None
