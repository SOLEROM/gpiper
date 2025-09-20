

GStreamer In-Band Metadata for MPEG

https://developer.ridgerun.com/wiki/index.php/GStreamer_In-Band_Metadata_for_MPEG_Transport_Stream/Examples/GstLaunch


Sender (MPEG-TS/KLV metadata):

gst-launch-1.0 filesrc location=../demo/test2sec.avi ! decodebin ! x264enc ! mpegtsmux name=mux \
  metasrc metadata='{"user":"data"}' period=1 ! 'meta/x-klv' ! mux.meta_0 \
  mux. ! udpsink host=127.0.0.1 port=5000


Receiver:
gst-launch-1.0 udpsrc port=5000 ! tsdemux name=demux \
  demux. ! queue ! h264parse ! mp4mux ! filesink location=../out/received.mp4 \
  demux.meta_0 ! metasink
