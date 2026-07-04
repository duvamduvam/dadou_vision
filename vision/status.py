"""Logique pure du heartbeat 'vision_status' (testable sans ROS ni matériel).

Construit le message périodique publié sur /vision/status : la preuve que la
chaîne ROS tourne de bout en bout sur le Pi 5 (démo de fin de lot V0).
Séparée du node (vision/nodes/vision_status_node.py) qui ne fait que l'I/O
ROS, conformément au principe « nodes fins, logique ailleurs ».
"""
import socket
import time

# Horodatage de chargement du module ~= démarrage du process (le node vit le
# temps du conteneur) : sert de référence pour calculer l'uptime publié.
_PROCESS_START = time.time()


def build_status_message(hostname=None, uptime_seconds=None, now=None):
    """Formate le message '<hostname> uptime=<secondes>s' publié sur /vision/status.

    Les paramètres sont injectables (tests) ; par défaut, hostname et uptime
    réels de la machine/processus courant.
    """
    if hostname is None:
        hostname = socket.gethostname()
    if uptime_seconds is None:
        current_time = time.time() if now is None else now
        uptime_seconds = current_time - _PROCESS_START
    return "{} uptime={}s".format(hostname, int(uptime_seconds))
