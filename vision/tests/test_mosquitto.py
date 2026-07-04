import unittest
import time
import paho.mqtt.client as mqtt

BROKER = "admin.duvam.net"  # Adresse du broker Mosquitto
PORT = 1883
TOPIC = "test/unit"
PAYLOAD = "Hello MQTT"

class TestMosquitto(unittest.TestCase):

    def setUp(self):
        """Configuration du client MQTT avant chaque test"""
        self.client = mqtt.Client()
        self.client.connect(BROKER, PORT, 60)
        self.client.loop_start()
        self.received_message = None  # Variable pour stocker le message reçu

    def on_message(self, client, userdata, message):
        """Callback appelée lors de la réception d'un message"""
        self.received_message = message.payload.decode()

    def test_publish_subscribe(self):
        """Test publication et réception d'un message MQTT"""
        self.client.subscribe(TOPIC)
        self.client.on_message = self.on_message

        # Publier un message
        self.client.publish(TOPIC, PAYLOAD)
        time.sleep(1)  # Attendre que le message soit reçu

        # Vérifier si le message a bien été reçu
        self.assertEqual(self.received_message, PAYLOAD)

    def tearDown(self):
        """Nettoyage après chaque test"""
        self.client.loop_stop()
        self.client.disconnect()

if __name__ == "__main__":
    unittest.main()
