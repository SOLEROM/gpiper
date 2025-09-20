# user meta send



smuggle your own metadata inside the H.264 elementary stream so it survives remuxing (MKV→MP4) and stays in-band with the video

Containers tags (Matroska/MP4 “udta/meta”) won’t give you per-frame sync and may get dropped; RTP header extensions only help if you’re using RTP.

## 

 sender/receiver topology H.264 is AU-aligned byte-stream before the muxer—easiest spot to inject SEI.

Inject SEI user_data_unregistered (NAL type 6; payload type = “user_data_unregistered” with a 16-byte UUID + your bytes).

On the receiver, parse the H.264 and extract those SEIs (log them, write sidecar JSON, or re-emit as bus messages).

## test

a tiny gst-python “pad probe” that prepends an SEI NAL before IDR (or every frame) on the sender; another probe on the receiver to parse & read it.

## prod

a 200–300-line C transform element (video/x-h264 → video/x-h264) using gst-codecparsers to inject/extract SEIs cleanly and efficiently.