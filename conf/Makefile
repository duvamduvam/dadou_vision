#PROJECT = vision
#SERVER = ai
#PROJECT_DIR = /home/dadou/Nextcloud/dev/didier/python/dadou_vision

include /home/dadou/Nextcloud/dev/didier/python/dadou_utils_ros/ansible/templates/Makefile

dc:
	#pwd
	ansible-playbook ${PROJECT_DIR}/conf/ansible/deploy-cloud.yml --ask-become-pass -vv -i ${PROJECT_DIR}/conf/ansible/hosts
ck:
	scp  /home/dadou/Nextcloud/divers/keys/kimsufi ${SERVER}:/home/pi/test/conf
lv:
	ffmpeg -f v4l2 -thread_queue_size 512 -s 640x360 -i /dev/video0 -f alsa -thread_queue_size 512 -i plughw:2,0 -ac 1 -ar 48000 -vcodec libvpx -b:v 500k -r 15 -acodec libopus -b:a 128k -f rtsp -rtsp_transport tcp rtsp://myuser:password@[2001:41d0:e:78b::1]:8554/stream
