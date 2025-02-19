PROJECT = vision
SERVER = ai
PROJECT_DIR = /home/dadou/Nextcloud/Didier/python/dadou_vision

include /home/dadou/Nextcloud/Didier/python/dadou_utils_ros/ansible/templates/Makefile

dc:
	#pwd
	ansible-playbook ${PROJECT_DIR}/conf/ansible/deploy-cloud.yml --ask-become-pass -vv -i ${PROJECT_DIR}/conf/ansible/hosts
ck:
	scp  /home/dadou/Nextcloud/divers/keys/kimsufi ${SERVER}:/home/pi/test/conf
