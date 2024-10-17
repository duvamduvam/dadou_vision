

envoi video / audio
ffmpeg -f v4l2 -thread_queue_size 512 -video_size 640x480 -i /dev/video0 -f alsa -thread_queue_size 512 -ac 1 -i plughw:2,0 -c:v h264 -b:v 500k -c:a aac -b:a 64k -f mpegts - | nc -w 2 192.168.1.131 5000

### gestreamer côté rpi
gst-launch-1.0 -v v4l2src ! image/jpeg,width=640,height=480,framerate=30/1 ! jpegdec ! videoconvert ! x264enc speed-preset=ultrafast tune=zerolatency ! rtph264pay ! udpsink host=192.168.1.131 port=5000

#### côté debian
gst-launch-1.0 -v udpsrc port=5000 caps="application/x-rtp, media=(string)video, encoding-name=(string)H264, payload=(int)96" ! rtph264depay ! avdec_h264 ! videoconvert ! autovideosink

####gestreamer audio
gst-launch-1.0 -v alsasrc device=hw:2,0 ! audioconvert ! audioresample ! audio/x-raw,format=S16LE,channels=1,rate=48000 ! opusenc ! rtpopuspay ! udpsink host=192.168.1.131 port=5001

##### reception
gst-launch-1.0 -v udpsrc port=5001 caps="application/x-rtp, media=(string)audio, encoding-name=(string)OPUS, payload=(int)96" ! rtpopusdepay ! opusdec ! audioconvert ! audioresample ! autoaudiosink

##### envoie video et audio
ffmpeg -f v4l2 -thread_queue_size 512 -s 640x360 -i /dev/video0 -f alsa -thread_queue_size 512 -i plughw:2,0 -ac 1 -ar 48000 -vcodec libvpx -b:v 500k -r 15 -acodec libopus -b:a 128k -f rtsp -rtsp_transport tcp rtsp://192.168.1.131:8554/stream
ffmpeg -f v4l2 -thread_queue_size 512 -s 640x360 -i /dev/video0 -f alsa -thread_queue_size 512 -i plughw:2,0 -ac 1 -ar 48000 -vcodec libvpx -b:v 500k -r 15 -acodec libopus -b:a 128k -f rtsp -rtsp_transport tcp rtsp://myuser:password@[2001:41d0:e:78b::1]:8554/stream

#### lance mediamtx // local asus rog
sudo docker run --rm -it --network=host -v /home/dadou/Nextcloud/Didier/python/dadou_vision/mediamtx/mediamtx.yml:/mediamtx.yml bluenviron/mediamtx:latest-ffmpeg

#### lance mediamtx // cloud
sudo docker run --rm -it --network=host -v /home/david/mediamtx/mediamtx.yml:/mediamtx.yml bluenviron/mediamtx:latest-ffmpeg

##### envoie audio depuis debian
ffmpeg -f alsa -thread_queue_size 512 -i plughw:4,0 -ac 1 -ar 48000 -acodec libopus -b:a 128k -f rtsp -rtsp_transport tcp rtsp://192.168.1.131:8554/audio_stream
ffmpeg -f alsa -thread_queue_size 512 -i plughw:4,0 -ac 1 -ar 48000 -acodec libopus -b:a 128k -f rtsp -rtsp_transport tcp rtsp://myuser:password@[2001:41d0:e:78b::1]:8554/audio_stream

##### envoie audio depuis debian mot de pass
ffmpeg -f alsa -thread_queue_size 512 -i plughw:0,0 -ac 1 -ar 48000 -acodec libopus -b:a 128k -f rtsp -rtsp_transport tcp rtsp://myuser:password@192.168.1.131:8554/audio_stream

#### lecture depuis rapsberry
ffmpeg -i rtsp://192.168.1.131:8554/audio_stream -f alsa default

#### navigateur
http://localhost:8889/audio_stream/

http://[2001:41d0:e:78b::1]:8889/stream/

http://[2001:41d0:e:78b::1]:8889/audio_stream/

