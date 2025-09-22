# About


* compressed H.264 inside a container (no raw RTP).
* reincode the src
* use sw encode
* change '''x264enc ''' to your hw encoder



## hw enc

gst-inspect-1.0 | grep 264enc

### common types



    Software:
    x264enc (always there after gstreamer1.0-plugins-ugly)

    Intel iGPU (VAAPI):
    vaapih264enc
    (requires gstreamer1.0-vaapi)

    NVIDIA GPU:
    nvh264enc
    (requires NVIDIA driver + gstreamer1.0-plugins-bad)

    NVIDIA Jetson (NVENC/NvMM):
    omxh264enc or nvv4l2h264enc

    AMD / Mesa VAAPI:
    also vaapih264enc, or radeonsi backend

    ARM SoC with V4L2 M2M (Rockchip, i.MX, RPi, etc.):
    v4l2h264enc


 
