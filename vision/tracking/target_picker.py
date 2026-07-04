"""Choix de la cible à suivre + conversion bbox -> azimut/élévation normalisés.

QUOI : logique PURE (aucun import cv2/mediapipe, aucun import de
       vision.tracking.detector) — testable en CI sans dépendance lourde,
       cf. vision/tests/unit/test_target_picker.py qui doit rester vert
       même sur une machine sans mediapipe installé. Les détections passées
       en entrée sont de simples objets avec les attributs x1/y1/x2/y2/score
       (duck-typing : vision.tracking.detector.Detection convient, mais
       n'importe quel objet compatible aussi — c'est volontaire, ça évite
       tout couplage entre ce module et le backend de détection).
POURQUOI séparé de detector.py : c'est la seule partie du pipeline qui doit
       être vérifiable par des tests unitaires rapides et déterministes (pas
       de caméra, pas de modèle .tflite) — le contrat ARCHITECTURE.md
       (/vision/person, x=azimut, y=élévation, z=confiance) est entièrement
       défini ici, indépendamment du choix de backend de détection.

Contrat de sortie (ARCHITECTURE.md) :
  x = azimut normalisé [-1..1], 0 = face caméra, +1 = bord DROIT de l'image
      VU DE LA CAMÉRA (donc PAS mirroré pour un observateur qui ferait face
      à la caméra : le pixel de colonne max de l'image correspond à +1).
      Documenté explicitement ici car le robot (gaze_follower côté
      dadou_robot_ros) en aura besoin pour le sens de rotation du cou — un
      mirroring introduit par erreur ferait tourner la tête du mauvais côté.
  y = élévation normalisée [-1..1], +1 = haut de l'image.
  z = confiance [0..1] de la détection retenue (score brut du backend, PAS
      lissé — seuls x et y sont lissés par EMA, cf. plus bas).
"""
from __future__ import annotations

from typing import Optional


def _azimuth(x1: float, x2: float, image_width: float) -> float:
    """Centre de boîte -> azimut [-1..1]. x pixel 0 (bord gauche de l'image
    telle que vue par la caméra) -> -1 ; x pixel image_width (bord droit) -> +1.
    Pas de mirroring : cf. docstring du module, c'est un choix de contrat
    documenté, pas un oubli."""
    if image_width <= 0:
        return 0.0
    cx = (x1 + x2) / 2.0
    azimuth = 2.0 * (cx / image_width) - 1.0
    return max(-1.0, min(1.0, azimuth))


def _elevation(y1: float, y2: float, image_height: float) -> float:
    """Centre de boîte -> élévation [-1..1]. y pixel 0 (haut de l'image) -> +1
    (les coordonnées image croissent vers le bas, l'élévation croît vers le haut :
    inversion volontaire)."""
    if image_height <= 0:
        return 0.0
    cy = (y1 + y2) / 2.0
    elevation = 1.0 - 2.0 * (cy / image_height)
    return max(-1.0, min(1.0, elevation))


def _area_ratio(x1: float, y1: float, x2: float, y2: float,
                 image_width: float, image_height: float) -> float:
    """Aire de la boîte / aire de l'image, dans [0..1] (borné en cas de boîte
    aberrante). Sert à pondérer le choix de cible : une personne proche de la
    caméra (donc une grosse boîte) ou centrale prime sur une silhouette
    lointaine ou en bord de cadre — plus pertinent pour un robot de théâtre
    qui doit suivre l'acteur/la personne qui LUI FAIT FACE, pas n'importe qui
    qui traverse au fond de la scène."""
    image_area = float(image_width * image_height)
    if image_area <= 0:
        return 0.0
    box_area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    return max(0.0, min(1.0, box_area / image_area))


class TargetPicker:
    """Sélectionne une personne à suivre parmi les détections d'une frame,
    lisse azimut/élévation par EMA, et réinitialise son état quand la cible
    est perdue.

    Paramètres :
      ema_alpha : poids de la NOUVELLE mesure dans le lissage exponentiel
          (ema = alpha*brut + (1-alpha)*ema_précédent). ~0.4 par défaut :
          assez réactif pour suivre un déplacement réel, assez lissé pour
          que le cou du robot ne vibre pas au bruit de détection frame à
          frame (bbox qui gigote de quelques pixels d'une frame à l'autre).
      adherence_radius : distance MAXIMALE en azimut brut (unité normalisée
          [-1..1], donc 0.3 ~ 30% de la largeur d'image) entre une détection
          et le dernier azimut retenu pour bénéficier du bonus d'adhérence.
      adherence_bonus : multiplicateur de score appliqué à une détection
          proche de la cible précédente. POURQUOI l'adhérence : avec du
          public devant la caméra, plusieurs personnes peuvent avoir des
          boîtes de score/aire comparables d'une frame à l'autre ; sans
          préférence pour la continuité, la cible choisie sauterait d'une
          personne à l'autre à chaque frame (choix instable, cou qui
          "saccade" d'une personne à l'autre au lieu de suivre calmement
          celle déjà engagée).
    """

    def __init__(self, ema_alpha: float = 0.4, adherence_radius: float = 0.3,
                 adherence_bonus: float = 1.5):
        self._ema_alpha = ema_alpha
        self._adherence_radius = adherence_radius
        self._adherence_bonus = adherence_bonus
        self._reset_state()

    def _reset_state(self) -> None:
        self._ema_azimuth: Optional[float] = None
        self._ema_elevation: Optional[float] = None
        # Azimut BRUT (pas lissé) de la dernière cible retenue : sert de
        # référence à l'adhérence, comparé à l'azimut BRUT des nouvelles
        # détections (comparer du brut à du brut, pas du brut à du lissé).
        self._last_raw_azimuth: Optional[float] = None

    def reset(self) -> None:
        """Repart de zéro : appelé explicitement en cas de perte de la cible.
        POURQUOI un reset et pas juste "arrêter de publier" : si on gardait
        le vieux lissage EMA, la PROCHAINE personne détectée hériterait d'un
        état lissé qui n'a rien à voir avec elle (fantôme de la personne
        précédente) — reset garantit que la nouvelle personne repart d'une
        mesure brute, pas d'un mélange avec le passé."""
        self._reset_state()

    def update(self, detections: list, image_width: float,
               image_height: float) -> Optional[tuple]:
        """Traite les détections d'UNE frame. Retourne (azimut, élévation,
        confiance) lissés, ou None si aucune détection (silence = personne
        perdue, cf. contrat ARCHITECTURE.md — c'est à l'appelant [le node] de
        ne rien publier dans ce cas, ce module se contente de renvoyer None)."""
        if not detections:
            self.reset()
            return None

        best_weight = None
        best = None  # (azimuth_brut, elevation_brut, score)
        for det in detections:
            azimuth = _azimuth(det.x1, det.x2, image_width)
            elevation = _elevation(det.y1, det.y2, image_height)
            area_ratio = _area_ratio(det.x1, det.y1, det.x2, det.y2,
                                      image_width, image_height)
            weight = area_ratio * det.score
            if (self._last_raw_azimuth is not None
                    and abs(azimuth - self._last_raw_azimuth) <= self._adherence_radius):
                weight *= self._adherence_bonus
            if best_weight is None or weight > best_weight:
                best_weight = weight
                best = (azimuth, elevation, det.score)

        azimuth, elevation, confidence = best

        # EMA : pas de valeur précédente (premier calcul après un reset) ->
        # on part directement de la mesure brute, ne PAS lisser artificiellement
        # vers 0 (une personne qui apparaît sur le bord de l'image ne doit pas
        # sembler démarrer du centre).
        self._ema_azimuth = (
            azimuth if self._ema_azimuth is None
            else self._ema_alpha * azimuth + (1.0 - self._ema_alpha) * self._ema_azimuth
        )
        self._ema_elevation = (
            elevation if self._ema_elevation is None
            else self._ema_alpha * elevation + (1.0 - self._ema_alpha) * self._ema_elevation
        )
        self._last_raw_azimuth = azimuth

        return (self._ema_azimuth, self._ema_elevation, confidence)
