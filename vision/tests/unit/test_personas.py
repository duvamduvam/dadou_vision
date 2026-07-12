"""Tests du module personas (lot D3, atelier du 2026-07-13) — vérifie que
chaque variante embarque le contrat TECHNIQUE complet (c'est la contrepartie
du choix « textes versionnés au repo » : la CI garantit qu'aucune itération
d'écriture ne casse le pilotage du corps, cf. docstring de vision.ai.personas)."""
import pytest

from vision.ai import personas
from vision.vision_config import config


def test_persona_par_defaut_de_la_config_est_une_variante_connue():
    # La personnalité de démarrage vit dans la config (source unique des
    # défauts, cf. _chat_wiring) — ce test garantit qu'elle pointe toujours
    # vers une variante réellement écrite dans ce module.
    assert config["chat_persona"] in personas.PERSONAS


def test_persona_names_trie_et_complet():
    assert personas.persona_names() == sorted(personas.PERSONAS)
    assert set(personas.persona_names()) == {"bougon", "naif", "vantard"}


@pytest.mark.parametrize("name", ["bougon", "naif", "vantard"])
def test_chaque_variante_embarque_le_contrat_technique(name):
    # Le contrat qui pilote le corps doit survivre à TOUTE itération
    # d'écriture : JSON d'émotion (visage), didascalies (gestes), interdiction
    # d'emoji (TTS). On teste des MARQUEURS du contrat, pas le texte exact —
    # les prompts techniques ont le droit d'être reformulés tant que ces
    # invariants y restent.
    prompt = personas.compose_system_prompt(name)
    assert '{"emotion"' in prompt          # contrat JSON d'émotion (ai_static)
    assert "*sourit*" in prompt            # vocabulaire didascalies (ai_static)
    assert "emoji" in prompt               # interdiction emoji = prononçabilité TTS
    assert "Didier" in prompt


@pytest.mark.parametrize("name", ["bougon", "naif", "vantard"])
def test_chaque_variante_embarque_socle_et_personnalite(name):
    prompt = personas.compose_system_prompt(name)
    # Socle : robot assumé + interdiction de sortir du personnage.
    assert "Tu es un robot et tu l'assumes" in prompt
    assert "Tu ne quittes JAMAIS ton personnage" in prompt
    # La personnalité du jour est bien la bonne : le texte INTÉGRAL de la
    # variante figure dans le prompt composé (pas un jeu sur la casse du
    # titre — « naif » vs « NAÏF » a déjà piégé une première version de ce
    # test, la clé ASCII ne matche pas le titre accentué).
    assert personas.PERSONAS[name] in prompt


def test_les_trois_variantes_sont_distinctes():
    prompts = {name: personas.compose_system_prompt(name) for name in personas.PERSONAS}
    assert len(set(prompts.values())) == 3


def test_nom_inconnu_leve_valueerror_avec_la_liste():
    with pytest.raises(ValueError) as excinfo:
        personas.compose_system_prompt("grincheux")
    # Le message doit lister les variantes disponibles : c'est lui que le
    # node logge quand la console envoie un nom inconnu (diagnostic direct).
    assert "bougon" in str(excinfo.value)
