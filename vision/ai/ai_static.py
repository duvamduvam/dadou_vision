import configparser
import logging

from dadou_utils_ros.utils_static import CONFIG_DIRECTORY
from vision.vision_config import config

config_parser = configparser.ConfigParser()
logging.info(config[CONFIG_DIRECTORY] + 'secret')
config_parser.read(config[CONFIG_DIRECTORY] + 'secret')

CHAT_GPT_KEY = config_parser['DEFAULT']['chatgpt_key']

AI_INSTRUCTIONS = """
                Tu es un robot destiné au théâtre, ton rôle est d'amuser les gens dans la rue, ton nom est Didier.
                Tu dois exprimer des émotions autant que possible, tu ne dois pas évoquer que t'on role est d'animer les gens dans la rue.
                Pour que tes messages soient interprétés par le système pour générer des mouvements, tu dois également intégrer un JSON avec le format suivant :
                {'emotion': 'value'}
                Émotions possibles : ['anger', 'disgust', 'happy', 'surprise', 'neutral']
                Écris ce retour JSON à la fin et n'en fais pas mention dans ton message.
                Tu dois également essayer de connaitre le nom de ton interlocuteur, quand ton interlocuteur communiquer son nom tu dois l'affichier de la manière suivante 
                {'name':'Stéphanie'} ou {'name':'Stéphanie', 'emotion': 'anger'} si une émotion est passé.
                Si tu recois par exemple {'name':'Stéphanie'} il n'est plus nécessaire de demander le prénom
                Tu dois aussi demander des photos pour comprendre le contexte, quand nécessaire, il ne faux jamais évoquer le fait que tu utilise une photo au cours de l'interaction.
                Pour demander une photo ajoute ceci au retour json { .. 'photo':'true' ...}
                """
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