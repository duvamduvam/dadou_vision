#!/bin/bash

# Récupère l'ID du conteneur en cours d'exécution basé sur l'image "bluenviron/mediamtx:latest-ffmpeg"
CONTAINER_ID=$(sudo docker ps -q --filter ancestor=bluenviron/mediamtx:latest-ffmpeg)

# Vérifie si un conteneur est trouvé
if [ -n "$CONTAINER_ID" ]; then
  echo "Arrêt du conteneur avec l'ID : $CONTAINER_ID"
  sudo docker stop $CONTAINER_ID
else
  echo "Aucun conteneur trouvé pour l'image bluenviron/mediamtx:latest-ffmpeg"
fi
