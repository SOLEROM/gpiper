#  timed metadata / subtitle track

Concept: push your compressed H.264 stream as usual and also push metadata events into a second source that you send to the same multiplexer (mp4mux or matroskamux). The muxer will create a second track (text/metadata) inside MP4


pseudo pipeline

    Video: filesrc ! decodebin ! videoconvert ! x264enc ! h264parse ! queue ! mp4mux name=mux ! filesink location=out.mp4

    Metadata: appsrc (timed JSON buffers with timestamps) ! some parser/encoder into a text/timed-metadata format ! mux.


## example code

    sender.py — reads a video file, encodes it to H.264, and muxes a WebVTT subtitle track created on the fly using appsrc. The WebVTT cues are JSON payloads (one small JSON per cue) timestamped to align with frames.

    receiver.py — reads the .mkv, demuxes, and uses appsink to capture the WebVTT subtitle stream, parsing each cue and writing the JSON payloads out into a .jsonl file (one JSON per line, timestamped). It also writes the received video track out to received_video.mkv so you can verify both were preserved.



 python sender.py 127.0.0.1 5000 '{"user":"data"}'  --video ../demo/test2sec.avi python receiver.py 5000 ../out/received.mp4