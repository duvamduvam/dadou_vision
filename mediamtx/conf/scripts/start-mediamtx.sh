#!/bin/bash

#!/bin/bash
echo "Démarrage de mediamtx" >> /home/david/mediamtx/logs/mediamtx.log
/usr/bin/docker run --rm -i --network=host \
    -v /home/david/mediamtx/mediamtx.yml:/mediamtx.yml \
    bluenviron/mediamtx:latest-ffmpeg >> /home/david/mediamtx/logs/mediamtx.log 2>&1
