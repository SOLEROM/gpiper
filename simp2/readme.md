
* use mp4 h264 instead of avi container
* MP4 already contains H.264, you can remux (no re-encode) over RTP and rebuild an MP4 on the other side

rtph264depay pulls raw H.264 out of RTP.
h264parse stream-format=avc alignment=au converts to the AVC format MP4 expects (annex-B → avcC as needed).
mp4mux faststart=true writes a normal MP4 (with moov up front). -e ensures the muxer is finalized.