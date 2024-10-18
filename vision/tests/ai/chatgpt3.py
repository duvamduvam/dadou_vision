import configparser
import logging

import openai
import speech_recognition as sr
import pyttsx3
from openai import OpenAI

from dadou_utils.utils_static import CONFIG_DIRECTORY
from robot.robot_config import config

#config_parser = configparser.ConfigParser()
#logging.error(config[CONFIG_DIRECTORY] + 'secret')
#config_parser.read(config[CONFIG_DIRECTORY] + 'secret')

# Initialisez le moteur de synthèse vocale
engine = pyttsx3.init()

# Fonction pour écouter l'utilisateur via le micro
def listen():
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("Écoute en cours...")
        audio = recognizer.listen(source)
        try:
            print("Reconnaissance vocale...")
            text = recognizer.recognize_google(audio, language='fr-FR')
            print(f"Vous avez dit: {text}")
            return text
        except sr.UnknownValueError:
            print("Je n'ai pas compris ce que vous avez dit.")
            return None
        except sr.RequestError:
            print("Erreur avec le service de reconnaissance vocale.")
            return None

# Fonction pour obtenir une réponse de ChatGPT
def get_response(prompt):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Vous êtes un assistant AI."},
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content.strip()
# Fonction pour parler à l'utilisateur
def speak(text):
    engine.say(text)
    engine.runAndWait()

if __name__ == "__main__":
    while True:
        user_input = listen()
        if user_input:
            response = get_response(user_input)
            print(f"ChatGPT: {response}")
            speak(response)
