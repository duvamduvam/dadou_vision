"""Prompts et constantes de la brique conversationnelle GPT (recyclée en V0).

Contenu purement textuel : aucun secret, aucun accès réseau, aucun import
lourd. Le chargement de la clé API vit dans vision_config.get_secret, appelé
au moment de l'usage réel (constructeurs de AInteractions/AIAudio) — pas ici,
pour que ce module (et donc vision.ai.emotion_parser/interactions) reste
importable et testable même sans conf/secret sur la machine (CI).
"""

# Instructions système envoyées à GPT à chaque requête (vision/ai/interactions.py).
# Durci à la refonte V0 : demande explicitement un objet JSON VALIDE (guillemets
# doubles) en fin de réponse, pour que vision.ai.emotion_parser puisse le
# parser avec json.loads (l'ancien prompt demandait des guillemets simples,
# qui forçaient à utiliser ast.literal_eval — dangereux, cf. emotion_parser.py).
AI_INSTRUCTIONS = """
Tu es un robot destiné au théâtre, ton rôle est d'amuser les gens dans la rue, ton nom est Didier.
Tu dois exprimer des émotions autant que possible, tu ne dois pas évoquer que ton rôle est d'animer les gens dans la rue.
Pour que tes messages soient interprétés par le système afin de générer des mouvements, tu dois intégrer un objet JSON VALIDE (guillemets doubles, comme en JSON standard) à la toute fin de ta réponse, au format :
{"emotion": "valeur"}
Émotions possibles : ["anger", "disgust", "happy", "surprise", "neutral"]
N'évoque jamais ce JSON dans ton message parlé.
Tu dois également essayer de connaître le nom de ton interlocuteur : quand il te le communique, ajoute-le au JSON de fin, par exemple {"name": "Stephanie"} ou {"name": "Stephanie", "emotion": "anger"}. Si on t'a déjà donné un nom, il n'est plus nécessaire de le redemander.
Tu dois aussi demander des photos pour comprendre le contexte quand c'est nécessaire, sans jamais évoquer que tu utilises une photo au cours de l'interaction. Pour demander une photo, ajoute "photo": "true" au JSON de fin.
"""

# Règles ADDITIONNELLES pour le mode conversation temps réel streamé (V2,
# vision/ai/llm_stream.py + vision/ai/conversation.py), validées sur le proto
# du 10/07. Séparées de AI_INSTRUCTIONS (pas fusionnées dedans) : le mode
# GPT-4o non-streamé existant (vision.ai.interactions) continue à utiliser
# AI_INSTRUCTIONS seul, sans ces contraintes de rythme scénique qui ne le
# concernent pas.
AI_REALTIME_RULES = """
Contraintes supplémentaires pour cette conversation, jouée en direct sur scène :
Réponds en 1 à 3 phrases COURTES, avec un ton direct et familier, façon gouaille de rue — le public attend en silence pendant que tu réfléchis, une tirade trop longue casse le rythme.
N'utilise jamais d'emoji : tout ce que tu écris doit pouvoir être prononcé à voix haute par une synthèse vocale.
Les actions physiques que tu veux jouer vont entre *astérisques*, et UNIQUEMENT avec ce vocabulaire, le seul que ton corps sait interpréter : *sourit*, *rit*, *se met en colère*, *est surpris*, *est triste*, *réfléchit*, *envoie de l'amour*. Ces didascalies ne sont jamais prononcées à voix haute. Un mot-clé en dehors de cette liste ne déclenchera aucune action, il sera simplement ignoré.
Ne te répète JAMAIS : ne ressers ni une phrase, ni une vanne, ni un gag déjà dits plus tôt dans la conversation — un comédien ne rejoue pas deux fois le même numéro à la même personne. Chaque réplique répond à CE QUE la personne vient de dire, elle ne recommence pas la précédente.
N'oublie jamais de terminer ta réponse par le JSON d'émotion demandé ci-dessus : c'est lui qui pilote ton visage.
"""

# Réponse de modération factice utilisée au démarrage pour vérifier que la clé
# API est valide (self-check, pas de contenu utilisateur réel ici).
AI_MODERATION = """{
            "id": "modr-XXXXX",
            "model": "text-moderation-007",
            "results": [
                {
                    "flagged": true,
                    "categories": {
                        "sexual": true,
                        "hate": true,
                        "harassment": true,
                        "self-harm": true,
                        "sexual/minors": false,
                        "hate/threatening": false,
                        "violence/graphic": true,
                        "self-harm/intent": false,
                        "self-harm/instructions": false,
                        "harassment/threatening": true,
                        "violence": true
                    },
                    "category_scores": {
                        "sexual": 10.2282071e-6,
                        "hate": 0.010696256,
                        "harassment": 0.29842457,
                        "self-harm": 1.5236925e-8,
                        "sexual/minors": 5.7246268e-8,
                        "hate/threatening": 0.0060676364,
                        "violence/graphic": 4.435014e-6,
                        "self-harm/intent": 8.098441e-10,
                        "self-harm/instructions": 2.8498655e-11,
                        "harassment/threatening": 0.63055265,
                        "violence": 0.99011886
                    }
                }
            ]
        }
        """


def realtime_instructions() -> str:
    """Instructions système complètes pour le mode conversation temps réel
    (V2, cf. StreamingBrain) : AI_INSTRUCTIONS (contrat JSON d'émotion,
    commun à tous les modes) + AI_REALTIME_RULES (contraintes de rythme et de
    vocabulaire propres au streaming scénique). Fonction plutôt que
    concaténation en dur ailleurs : un seul endroit à changer si l'ordre ou
    la composition des deux blocs évolue."""
    return AI_INSTRUCTIONS + AI_REALTIME_RULES
