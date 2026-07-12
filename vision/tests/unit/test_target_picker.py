"""Tests de vision/tracking/target_picker.py — logique PURE, aucune caméra ni
mediapipe requis (le module cible n'importe que dataclasses/typing en tête).

QUOI : ce fichier n'importe QUE vision.tracking.target_picker — volontairement
       PAS vision.tracking.detector (qui n'a pas besoin de mediapipe non plus
       en tête de module, mais le découplage est plus propre et documente
       l'intention : TargetPicker fonctionne avec n'importe quel objet
       duck-typé x1/y1/x2/y2/score, pas seulement detector.Detection).
       `.venv/bin/pytest -q` doit rester vert SANS mediapipe/opencv installés.
"""
from collections import namedtuple

import pytest

from vision.tracking.target_picker import TargetPicker

# Stub minimal de détection (duck-typing : seuls x1/y1/x2/y2/score sont lus
# par TargetPicker, cf. target_picker.py). Named tuple plutôt que la vraie
# dataclass Detection : garde ce test totalement indépendant de detector.py.
Det = namedtuple("Det", "x1 y1 x2 y2 score")

IMG_W = 100.0
IMG_H = 100.0


def _det(x1, y1, x2, y2, score=0.9):
    return Det(x1, y1, x2, y2, score)


# --------------------------------------------------------------------------
# Mapping bbox -> azimut/élévation, y compris les bords de l'image.
# --------------------------------------------------------------------------

def test_bbox_centered_maps_to_zero_azimuth_and_elevation():
    picker = TargetPicker()
    result = picker.update([_det(45, 45, 55, 55, score=0.8)], IMG_W, IMG_H)
    assert result is not None
    azimuth, elevation, confidence, height = result
    assert azimuth == pytest.approx(0.0)
    assert elevation == pytest.approx(0.0)
    assert confidence == pytest.approx(0.8)
    assert height == pytest.approx(0.1)  # boîte de 10 px de haut / image de 100


def test_bbox_at_left_edge_maps_to_azimuth_minus_one():
    # Boîte collée au bord GAUCHE de l'image (x1=x2=0, cas dégénéré mais
    # valide) -> azimut = -1 (bord gauche vu de la caméra, cf. contrat).
    picker = TargetPicker()
    azimuth, _, _, _ = picker.update([_det(0, 45, 0, 55)], IMG_W, IMG_H)
    assert azimuth == pytest.approx(-1.0)


def test_bbox_at_right_edge_maps_to_azimuth_plus_one():
    # Boîte collée au bord DROIT (x1=x2=largeur image) -> azimut = +1, SANS
    # mirroring (contrat ARCHITECTURE.md : +1 = bord droit VU DE LA CAMÉRA).
    picker = TargetPicker()
    azimuth, _, _, _ = picker.update([_det(IMG_W, 45, IMG_W, 55)], IMG_W, IMG_H)
    assert azimuth == pytest.approx(1.0)


def test_bbox_at_top_maps_to_elevation_plus_one():
    picker = TargetPicker()
    _, elevation, _, _ = picker.update([_det(45, 0, 55, 0)], IMG_W, IMG_H)
    assert elevation == pytest.approx(1.0)


def test_bbox_at_bottom_maps_to_elevation_minus_one():
    picker = TargetPicker()
    _, elevation, _, _ = picker.update([_det(45, IMG_H, 55, IMG_H)], IMG_W, IMG_H)
    assert elevation == pytest.approx(-1.0)


# --------------------------------------------------------------------------
# Lissage exponentiel (EMA).
# --------------------------------------------------------------------------

def test_first_measurement_after_reset_is_not_smoothed():
    # Après un reset (état initial ou perte de cible), la première mesure doit
    # être la valeur BRUTE, pas mélangée à un état inexistant (pas de ramping
    # artificiel depuis 0 quand une personne apparaît sur le bord de l'image).
    picker = TargetPicker(ema_alpha=0.4)
    azimuth, _, _, _ = picker.update([_det(0, 45, 20, 55)], IMG_W, IMG_H)  # centre x=10 -> azimut -0.8
    assert azimuth == pytest.approx(-0.8)


def test_ema_smooths_toward_new_value_without_jumping_to_it():
    picker = TargetPicker(ema_alpha=0.4)
    # Frame 1 : centre x=25 -> azimut brut -0.5.
    az1, _, _, _ = picker.update([_det(20, 45, 30, 55)], IMG_W, IMG_H)
    assert az1 == pytest.approx(-0.5)
    # Frame 2 : la même personne s'est déplacée, centre x=75 -> azimut brut +0.5.
    az2, _, _, _ = picker.update([_det(70, 45, 80, 55)], IMG_W, IMG_H)
    # EMA attendu : 0.4*0.5 + 0.6*(-0.5) = -0.1 — ni la valeur brute (+0.5),
    # ni la valeur précédente (-0.5) : preuve que le lissage a bien lieu.
    assert az2 == pytest.approx(-0.1)
    assert az2 != pytest.approx(0.5)


# --------------------------------------------------------------------------
# Reset de l'état quand la cible est perdue.
# --------------------------------------------------------------------------

def test_no_detections_returns_none_and_resets_state():
    picker = TargetPicker(ema_alpha=0.4)
    picker.update([_det(20, 45, 30, 55)], IMG_W, IMG_H)  # azimut -0.5, établit un état

    result = picker.update([], IMG_W, IMG_H)  # personne perdue

    assert result is None


def test_next_person_after_loss_starts_fresh_not_blended_with_ghost():
    # Sans reset, la prochaine personne détectée hériterait d'un lissage EMA
    # qui n'a rien à voir avec elle (fantôme de la personne précédente).
    picker = TargetPicker(ema_alpha=0.4)
    picker.update([_det(20, 45, 30, 55)], IMG_W, IMG_H)  # personne A, azimut -0.5
    assert picker.update([], IMG_W, IMG_H) is None  # A disparaît

    # Personne B apparaît à l'opposé de l'image (azimut brut +0.5) : si l'état
    # n'avait pas été réinitialisé, le résultat serait mélangé à -0.5 (comme
    # dans test_ema_smooths_toward_new_value_without_jumping_to_it : -0.1).
    azimuth, _, _, _ = picker.update([_det(70, 45, 80, 55)], IMG_W, IMG_H)
    assert azimuth == pytest.approx(0.5)


# --------------------------------------------------------------------------
# Adhérence à la cible précédente (évite de sauter d'une personne à l'autre).
# --------------------------------------------------------------------------

def test_adherence_prefers_detection_close_to_previous_target():
    # Bonus fort et alpha=1 (pas de lissage) pour un calcul déterministe :
    # ce test vérifie la logique d'adhérence isolément de l'EMA.
    picker = TargetPicker(ema_alpha=1.0, adherence_radius=0.3, adherence_bonus=3.0)

    # Frame 1 : une seule personne, au centre (azimut 0) -> établit la cible.
    picker.update([_det(45, 45, 55, 55, score=0.5)], IMG_W, IMG_H)

    # Frame 2 : deux détections de même score.
    #   A : proche de la cible précédente (azimut 0), petite boîte (aire 200 -> ratio 0.02)
    #       poids brut = 0.02*0.5 = 0.01 ; avec bonus d'adhérence (distance 0 <= 0.3) : 0.01*3 = 0.03
    #   B : loin de la cible précédente (azimut 0.7), boîte plus grande (aire 500 -> ratio 0.05)
    #       poids brut = 0.05*0.5 = 0.025 ; pas de bonus (distance 0.7 > 0.3)
    # Sans adhérence, B (0.025) l'emporterait sur A (0.01) malgré la même
    # confiance — c'est précisément ce que l'adhérence doit empêcher ici :
    # avec le bonus, A (0.03) l'emporte sur B (0.025).
    det_a_near_previous = _det(40, 45, 60, 55, score=0.5)  # centre x=50 -> azimut 0
    det_b_far_bigger = _det(70, 40, 95, 60, score=0.5)     # centre x=82.5 -> azimut 0.65

    azimuth, _, _, _ = picker.update([det_a_near_previous, det_b_far_bigger], IMG_W, IMG_H)

    assert azimuth == pytest.approx(0.0)  # A choisie, pas B (0.65)


# --------------------------------------------------------------------------
# Hauteur de silhouette (proxy de distance pour le suivi roues, 2026-07-11).
# --------------------------------------------------------------------------

def test_height_ratio_proche_et_loin():
    # Personne PROCHE : boîte qui remplit presque l'image en hauteur.
    picker = TargetPicker()
    target = picker.update([_det(40, 5, 60, 95)], IMG_W, IMG_H)
    assert target.height == pytest.approx(0.9)

    # Personne LOIN : petite silhouette (nouveau picker : pas de lissage hérité).
    picker = TargetPicker()
    target = picker.update([_det(45, 40, 55, 60)], IMG_W, IMG_H)
    assert target.height == pytest.approx(0.2)


def test_height_est_lissee_par_ema_comme_l_azimut():
    picker = TargetPicker(ema_alpha=0.4)
    t1 = picker.update([_det(40, 10, 60, 90)], IMG_W, IMG_H)  # hauteur brute 0.8
    assert t1.height == pytest.approx(0.8)  # 1re mesure : brute (pas de ramping depuis 0)
    t2 = picker.update([_det(40, 30, 60, 70)], IMG_W, IMG_H)  # hauteur brute 0.4
    # EMA : 0.4*0.4 + 0.6*0.8 = 0.64 — ni brute ni précédente.
    assert t2.height == pytest.approx(0.64)


def test_height_bornee_boite_aberrante():
    # y2 < y1 (boîte inversée) -> 0, pas de valeur négative qui ferait
    # reculer le robot sur une détection corrompue.
    picker = TargetPicker()
    target = picker.update([_det(40, 80, 60, 20)], IMG_W, IMG_H)
    assert target.height == pytest.approx(0.0)
