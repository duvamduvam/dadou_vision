"""Découpage d'un flux LLM (deltas de streaming) en événements de jeu :
phrases à dire, didascalies (*...*) à jouer, émotion JSON de fin de message.

QUOI : logique PURE, stdlib uniquement (re/dataclasses) + réutilise
       vision.ai.emotion_parser.extract_emotion_json (déjà stdlib-only) pour
       ne PAS dupliquer le contrat "dernier bloc {...} valide gagne" — ce
       module ne fait qu'orchestrer QUAND appeler extract_emotion_json (au
       flush, sur le texte retenu) plutôt que de réimplémenter le parsing JSON.
POURQUOI en streaming : le TTS doit pouvoir commencer à parler dès la première
       phrase complète reçue de l'API, sans attendre la fin de la réponse —
       mais les didascalies (*rit*) et le JSON d'émotion de fin ne doivent
       JAMAIS être lus à voix haute, et peuvent être coupés n'importe où par
       les frontières de deltas de l'API (un delta peut s'arrêter au milieu
       d'un mot, d'une astérisque, ou d'un caractère JSON).

Machine à états à 3 régimes, mutuellement exclusifs :
  - NORMAL      : les caractères s'accumulent dans le buffer de phrase, une
                  frontière de phrase (SENTENCE_BOUNDARY) déclenche l'émission
                  d'une Sentence dès qu'elle est vue (pas besoin d'attendre le
                  flush).
  - DIDASCALIE  : entre deux '*', les caractères s'accumulent à part (jamais
                  mêlés au texte à dire) ; le '*' fermant émet la Didascalie.
  - HOLDBACK    : dès qu'un '{' apparaît HORS didascalie, tout ce qui suit
                  (dans le delta courant ET tous les suivants) est retenu tel
                  quel, sans plus AUCUNE détection de phrase/didascalie — on
                  ne sait pas encore si c'est vraiment le JSON de fin ou juste
                  une accolade parlée, seul le flush (fin de flux garantie)
                  peut trancher via extract_emotion_json (qui gère déjà le cas
                  "plusieurs blocs {...} : seul le dernier compte", donc une
                  accolade parlée AVANT le vrai JSON final ne pose pas
                  problème : elle finit simplement dans le texte de la Sentence
                  retournée par extract_emotion_json).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from vision.ai.emotion_parser import extract_emotion_json

# Frontière de phrase : un ou plusieurs espaces PRÉCÉDÉS d'un terminateur de
# phrase (., !, ?, …). Lookbehind (pas consommé par le split) : le
# terminateur reste attaché à la phrase qui se termine, pas à celle qui suit.
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?…])\s+")


@dataclass(frozen=True)
class Sentence:
    text: str


@dataclass(frozen=True)
class Didascalie:
    action: str  # sans les astérisques


@dataclass(frozen=True)
class Emotion:
    params: dict


class StreamPerformanceParser:
    """Consomme un flux LLM delta par delta. Pas de recharge possible après
    flush() : instancier un nouveau parser pour un nouveau message (le flux
    de conversation en crée un par tour, cf. chat_node V2)."""

    def __init__(self):
        # Texte en attente : buffer de phrase en régime NORMAL, ou texte
        # retenu tel quel (accolade comprise) une fois en régime HOLDBACK.
        self._buffer = ""
        self._in_didascalie = False
        self._didascalie_buffer = ""
        self._holdback = False

    def feed(self, delta: str) -> List[object]:
        """Traite un nouveau fragment de texte reçu du LLM. Retourne la liste
        des événements (Sentence/Didascalie) que ce fragment a permis de
        conclure — jamais d'Emotion ici, elle n'est produite qu'au flush()."""
        events: List[object] = []

        for idx, ch in enumerate(delta):
            if self._holdback:
                # Régime HOLDBACK déjà actif (reliquat d'un delta précédent) :
                # plus aucune interprétation, tout le reste part tel quel.
                self._buffer += delta[idx:]
                break

            if self._in_didascalie:
                self._consume_didascalie_char(ch, events)
                continue

            if ch == "*":
                # On quitte le régime NORMAL : vider tout de suite les phrases
                # déjà complètes du buffer (sinon elles seraient émises APRÈS
                # la Didascalie qui les suit dans le texte, en fin de feed() —
                # un décalage d'ordre chronologique, cf. test
                # test_didascalie_across_sentence_boundary).
                events.extend(self._extract_sentences())
                self._in_didascalie = True
                self._didascalie_buffer = ""
                continue

            if ch == "{":
                # Bascule en HOLDBACK : même raison de vider d'abord les
                # phrases complètes (ordre chronologique). Seul le reliquat
                # incomplet de self._buffer (pas de frontière de phrase vue)
                # part avec le '{' et la suite dans le holdback — le texte
                # déjà confirmé comme phrase a été émis juste avant.
                events.extend(self._extract_sentences())
                self._holdback = True
                self._buffer += delta[idx:]
                break

            self._buffer += ch

        if not self._holdback:
            events.extend(self._extract_sentences())

        return events

    def _consume_didascalie_char(self, ch: str, events: List[object]) -> None:
        """Un seul caractère traité en régime DIDASCALIE : accumule, ou émet
        la Didascalie complète si `ch` est le '*' fermant."""
        if ch == "*":
            events.append(Didascalie(action=self._didascalie_buffer.strip()))
            self._didascalie_buffer = ""
            self._in_didascalie = False
        else:
            self._didascalie_buffer += ch

    def flush(self) -> List[object]:
        """Fin de flux : vide tout ce qui reste en attente. Une didascalie
        jamais refermée ou un JSON incomplet/invalide dégradent proprement en
        texte parlé plutôt que d'être perdus silencieusement."""
        events: List[object] = []

        if self._in_didascalie:
            # Cas limite (non attendu du LLM en pratique, mais ne doit pas
            # faire disparaître le texte) : didascalie jamais refermée.
            if self._didascalie_buffer.strip():
                events.append(Didascalie(action=self._didascalie_buffer.strip()))
            self._didascalie_buffer = ""
            self._in_didascalie = False

        if self._holdback:
            text, params = extract_emotion_json(self._buffer)
            if params is not None:
                if text.strip():
                    events.append(Sentence(text=text.strip()))
                events.append(Emotion(params=params))
            else:
                # Pas de JSON valide (absent, incomplet ou invalide) : le
                # texte retenu — accolade comprise — redevient une Sentence
                # normale plutôt que d'être perdu.
                if self._buffer.strip():
                    events.append(Sentence(text=self._buffer.strip()))
            self._buffer = ""
            self._holdback = False
        else:
            if self._buffer.strip():
                events.append(Sentence(text=self._buffer.strip()))
            self._buffer = ""

        return events

    def _extract_sentences(self) -> List[object]:
        """Émet une Sentence pour chaque segment CONFIRMÉ terminé (frontière
        de phrase déjà vue) dans self._buffer ; garde le reliquat (dernier
        segment, potentiellement incomplet) pour le prochain feed()/flush()."""
        parts = SENTENCE_BOUNDARY.split(self._buffer)
        if len(parts) <= 1:
            return []  # aucune frontière de phrase encore vue

        events: List[object] = []
        for part in parts[:-1]:
            text = part.strip()
            if text:
                events.append(Sentence(text=text))
        self._buffer = parts[-1]
        return events
