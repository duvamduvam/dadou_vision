"""Tests de vision/ai/stream_parser.py — logique PURE (re/dataclasses stdlib
+ vision.ai.emotion_parser, lui-même stdlib-only), aucun appel réseau ni
dépendance lourde.

Convention : chaque test envoie une séquence de deltas via feed(), termine
TOUJOURS par flush() (fin de flux réelle), et compare la liste CONCATÉNÉE de
tous les événements obtenus — la césure exacte entre ce qu'un feed() donné
retourne et ce que flush() retourne en dernier n'est pas un contrat testé ici
(seul l'ordre et le contenu final des événements comptent), sauf mention
contraire explicite dans un test.
"""
from vision.ai.stream_parser import (
    Didascalie,
    Emotion,
    Sentence,
    StreamPerformanceParser,
)


def _run(*deltas):
    """Envoie chaque delta à un parser frais, termine par flush(), retourne
    la liste concaténée de tous les événements produits."""
    parser = StreamPerformanceParser()
    events = []
    for delta in deltas:
        events.extend(parser.feed(delta))
    events.extend(parser.flush())
    return events


# --------------------------------------------------------------------------
# Phrases simples.
# --------------------------------------------------------------------------

def test_simple_sentence():
    events = _run("Bonjour, comment ça va ?")
    assert events == [Sentence(text="Bonjour, comment ça va ?")]


def test_multiple_sentences_in_one_delta():
    events = _run("Phrase un. Phrase deux.")
    assert events == [Sentence(text="Phrase un."), Sentence(text="Phrase deux.")]


def test_sentence_split_across_three_deltas():
    events = _run("Bonjour ", "tout le ", "monde.")
    assert events == [Sentence(text="Bonjour tout le monde.")]


def test_sentence_terminator_ellipsis():
    events = _run("Attends voir…")
    assert events == [Sentence(text="Attends voir…")]


def test_flush_without_punctuation_emits_leftover_as_sentence():
    # Fin de flux sans ponctuation terminale : le reliquat est quand même
    # restitué comme une phrase (pas perdu).
    events = _run("Bonjour")
    assert events == [Sentence(text="Bonjour")]


# --------------------------------------------------------------------------
# Didascalies.
# --------------------------------------------------------------------------

def test_didascalie_split_across_two_deltas():
    events = _run("*rit aux ", "éclats* Bonjour.")
    assert events == [Didascalie(action="rit aux éclats"), Sentence(text="Bonjour.")]


def test_didascalie_alone():
    events = _run("*rigole*")
    assert events == [Didascalie(action="rigole")]


def test_didascalie_across_sentence_boundary():
    # La didascalie est extraite AVANT toute détection de frontière de
    # phrase : le texte entre astérisques ne doit jamais apparaître dans une
    # Sentence, même s'il contient de la ponctuation de phrase.
    events = _run("Salut. *soupire longuement.* À plus.")
    assert events == [
        Sentence(text="Salut."),
        Didascalie(action="soupire longuement."),
        Sentence(text="À plus."),
    ]


# --------------------------------------------------------------------------
# JSON d'émotion (holdback dès le premier '{' hors didascalie).
# --------------------------------------------------------------------------

def test_json_complete_in_one_delta():
    events = _run('Bonjour ! {"emotion": "happy"}')
    assert events == [Sentence(text="Bonjour !"), Emotion(params={"emotion": "happy"})]


def test_json_split_across_three_deltas():
    events = _run('Content de te voir. {"emo', 'tion": ', '"happy"}')
    assert events == [
        Sentence(text="Content de te voir."),
        Emotion(params={"emotion": "happy"}),
    ]


def test_incomplete_json_at_flush_becomes_sentence_not_emotion():
    # Flux coupé en plein milieu du JSON (jamais de '}') : le texte retenu,
    # accolade comprise, redevient une Sentence — pas d'Emotion. Pas de
    # ponctuation de phrase avant le '{' (volontaire) : "Salut " n'a jamais
    # été confirmé comme phrase complète, il reste donc attaché au texte
    # retenu plutôt que d'être émis à part.
    events = _run('Salut {"emotion": "hap')
    assert events == [Sentence(text='Salut {"emotion": "hap')]
    assert not any(isinstance(e, Emotion) for e in events)


def test_stray_brace_in_text_followed_by_real_final_json():
    # Une accolade parlée (pas du JSON) déclenche quand même le holdback (on
    # ne peut pas savoir à l'avance que ce n'est pas le début du JSON final),
    # mais extract_emotion_json ne garde que le DERNIER bloc {...} valide : le
    # vrai JSON final est donc correctement extrait, l'accolade parlée reste
    # dans le texte de la Sentence.
    events = _run('Regarde { là-bas, incroyable non ? {"emotion": "surprise"}')
    assert events == [
        Sentence(text="Regarde { là-bas, incroyable non ?"),
        Emotion(params={"emotion": "surprise"}),
    ]


def test_brace_inside_didascalie_does_not_trigger_holdback():
    # Un '{' à l'intérieur d'une didascalie ne doit PAS déclencher le
    # holdback (règle explicite : "hors didascalie" uniquement) — la
    # didascalie doit rester purement de la didascalie, et le texte qui suit
    # doit être traité normalement, y compris le vrai JSON de fin.
    events = _run('*bug { grésille}* Tout va bien. {"emotion": "neutral"}')
    assert events == [
        Didascalie(action="bug { grésille}"),
        Sentence(text="Tout va bien."),
        Emotion(params={"emotion": "neutral"}),
    ]
