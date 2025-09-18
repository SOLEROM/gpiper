# About

* use mp4 h264 instead of avi container
* MP4 already contains H.264, you can remux (no re-encode) over RTP and rebuild an MP4 on the other side

```
rtph264depay pulls raw H.264 out of RTP.
h264parse stream-format=avc alignment=au converts to the AVC format MP4 expects (annex-B → avcC as needed).
mp4mux faststart=true writes a normal MP4 (with moov up front). -e ensures the muxer is finalized.
```
## run

* start receiver then sender

```
22072  ../demo/test2sec.mp4
18806 ../out/received.mp4
```

diff sizes:

Your sender demuxes video only (demux.video_0). If ../demo/test2sec.mp4 had audio or other tracks, the original file is naturally bigger.

Even if the source had only video, the MP4 boxes (moov/mdat, sample tables, edit lists, etc.) written by mp4mux won’t match the original layout/overhead.

h264parse and mp4mux may strip or move some NALs (AUD/SEI, repeated SPS/PPS) from the elementary stream into MP4’s avcC—so the bitstream-in-file can be slightly different while the decoded video is identical.

With RTP/UDP, late packets can be dropped by rtpjitterbuffer, shrinking the result.
