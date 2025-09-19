# about

* [gstreamer tools](./gtools/readme.md) 

## deps

```
sudo apt update
sudo apt install -y \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav
```

* !!! ``` conda deactivate ``` as it breaks gstreamer ref !!!

## default plugins

```
    gstreamer1.0-tools → gives gst-launch-1.0, gst-inspect-1.0

    base → core elements like videoconvert, audioconvert

    good → widely used plugins (UDP, RTP, autovideosink, etc.)

    bad → newer/less stable but essential (rtpjitterbuffer, MPEG-TS mux)

    ugly → plugins with licensing issues (x264enc)

    libav → ffmpeg-based decoder/encoder fallback (avdec_h264, etc.)
```

## tests

* simp1:  rtp over udp ; smoke test to move file
* simp2:  mp4 tp mp4 over rtp/udp
* simp3:  avi to mp4 sw reencode