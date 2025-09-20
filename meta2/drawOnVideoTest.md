

## receive and display video with GStreamer

gst-launch-1.0 udpsrc port=5000 ! tsdemux ! h264parse ! avdec_h264 ! autovideosink

## send video with GStreamer

gst-launch-1.0 videotestsrc ! textoverlay text="HELLO FROM THE OTHER SIDE" ! x264enc ! h264parse ! mpegtsmux ! udpsink host=127.0.0.1 port=5000


![alt text](image.png)
