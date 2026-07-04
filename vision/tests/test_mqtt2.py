import unittest
import time
import paho.mqtt.client as mqtt

# 🔹 Configuration du serveur MQTT
BROKER = "admin.duvam.net"  # Adresse du serveur
PORT = 1883  # Port standard MQTT (ou 8883 si TLS)
USERNAME = "david"  # 🔑 Remplace par ton login
PASSWORD = "CHANGE_ME"  # jamais de secret en dur : lire conf/secret
TOPIC = "test/unit"
PAYLOAD = "Hello MQTT Test"

class TestMosquittoConnection(unittest.TestCase):

    def setUp(self):
        """Configuration du client MQTT avant chaque test"""
        self.client = mqtt.Client()
        self.client.username_pw_set(USERNAME, PASSWORD)  # Ajout des identifiants
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.received_message = None  # Stocke le message reçu

    def on_connect(self, client, userdata, flags, rc):
        """Callback de connexion"""
        self.assertEqual(rc, 0, f"❌ Connexion refusée, code : {rc}")
        print("✅ Connexion au serveur MQTT réussie !")
        client.subscribe(TOPIC)  # S'abonner au topic

    def on_message(self, client, userdata, message):
        """Callback de réception de message"""
        self.received_message = message.payload.decode()

    def test_publish_subscribe(self):
        """Test : Publier et recevoir un message MQTT"""
        self.client.connect(BROKER, PORT, 60)
        self.client.loop_start()
        time.sleep(2)  # Attendre la connexion

        # Publier un message
        self.client.publish(TOPIC, PAYLOAD)
        time.sleep(2)  # Attendre la réception du message

        # Vérifier que le message reçu est bien celui envoyé
        self.assertEqual(self.received_message, PAYLOAD, "❌ Le message reçu ne correspond pas !")
        print("✅ Test de publication/souscription réussi !")

    def tearDown(self):
        """Nettoyage après chaque test"""
        self.client.loop_stop()
        self.client.disconnect()
        print("🔄 Déconnexion du client MQTT")

if __name__ == "__main__":
    unittest.main()
