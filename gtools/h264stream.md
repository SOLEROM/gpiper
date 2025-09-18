# get only the stream from a mp4 file


```
 gst-launch-1.0 -q filesrc location=../demo/test2sec.mp4 ! \
  qtdemux ! h264parse config-interval=-1 \
  ! video/x-h264,stream-format=byte-stream,alignment=au \
  ! filesink location=/tmp/orig.h264
```