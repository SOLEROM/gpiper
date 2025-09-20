# meta side channel

* MPEG-TS (Transport Stream) doesn't preserve GStreamer tags. 
* see 2 shells 2sideTags to see that the metadata is stripped but better the next test that shows the metadata is saved in mp4 file but not transmitted over mpeg-ts;


``` 
test.py
==========

python test.py                              
GStreamer Metadata Test
==================================================
GStreamer version: 1.16.3
✓ Plugin 'coreelements' found
✓ Plugin 'videoconvert' found
✓ Plugin 'x264' found
✓ Plugin 'typefindfunctions' found
✓ Plugin 'mpegtsdemux' found
✓ Plugin 'isomp4' found

==================================================
Testing metadata locally (no network)...
Test metadata: {'user': 'test', 'timestamp': '2024-01-01', 'session_id': '12345'}
--------------------------------------------------
Creating test pipeline...
Injecting metadata programmatically...
Injecting tags into: mp4mux0

Pipeline completed. File saved to: /tmp/tmpjp2zaq3_.mp4

==================================================
RESULTS:
❌ No metadata extracted - there may be an issue with your GStreamer installation

==================================================
Testing reading metadata from saved file...
test.py:146: Warning: g_value_get_string: assertion 'G_VALUE_HOLDS_STRING (value)' failed
  success, value = taglist.get_string(tag_name)
✅ Metadata persisted in file!
File tags: {
  "video-codec": "H.264 / AVC",
  "title": "Test Video",
  "comment": "user:test",
  "description": "metadata:{\"user\": \"test\", \"timestamp\": \"2024-01-01\", \"session_id\": \"12345\"}",
  "encoder": "x264",
  "container-format": "ISO MP4/M4A"
}
```

* MPEG-TS strips GStreamer tags during transmission.
* GStreamer tags are NOT part of MPEG-TS specification - they get stripped at the muxer
* uses a metadata side channel. This approach:

```
Video:    AVI → H.264 → MPEG-TS → UDP:5000 → MPEG-TS → H.264 → MP4
Metadata: JSON → UDP:5001 → JSON file
```

Benefits:

* 100% reliable - metadata always arrives intact
* Simple - no complex encoding/decoding
* Flexible - can update metadata during streaming
* Standard practice - many streaming protocols use separate channels (e.g., RTSP uses separate ports for control/data)

### sender.py:

Sends video on the specified port (e.g., 5000)
Sends metadata on port+1 (e.g., 5001)
Sends metadata 3 times to ensure delivery
Clear status messages and progress indicators
Proper error handling

### receiver.py:

Listens for video on the specified port
Listens for metadata on port+1
Saves video as MP4
Saves metadata as JSON file
Shows received metadata in real-time
Handles timeouts gracefully

## run

```
python3 receiver.py 5000 ../out/received.mp4


python3 sender.py 127.0.0.1 5000 '{"user":"john","timestamp":"2024-01-01","session_id":"12345"}' --video ../demo/test2sec.avi
```

## example


```
python3 receiver.py 5000 ../out/received.mp4

============================================================
VIDEO RECEIVER WITH METADATA
============================================================
📡 Video port: 5000
📋 Metadata port: 5001
💾 Output file: ../out/received.mp4
============================================================
⏳ Waiting for stream...
👂 Listening for metadata on port 5001...

📦 METADATA RECEIVED from 127.0.0.1:
   ----------------------------------------
   • user: john
   • timestamp: 2024-01-01
   • session_id: 12345
   ----------------------------------------


📦 METADATA RECEIVED from 127.0.0.1:
   ----------------------------------------
   • user: john
   • timestamp: 2024-01-01
   • session_id: 12345
   ----------------------------------------

▶️  Receiving video stream...

📦 METADATA RECEIVED from 127.0.0.1:
   ----------------------------------------
   • user: john
   • timestamp: 2024-01-01
   • session_id: 12345
   ----------------------------------------


⏱️  Video stream timeout - no data for 5 seconds

============================================================
📋 METADATA SAVED
============================================================
📁 File: ../out/received_metadata.json
📦 Content:
   • user: john
   • timestamp: 2024-01-01
   • session_id: 12345
============================================================
Stopping receiver...
Metadata listener stopped

📹 Video saved to: ../out/received.mp4
📋 Metadata saved to: ../out/received_metadata.json

```


```
python3 sender.py 127.0.0.1 5000 '{"user":"john","timestamp":"2024-01-01","session_id":"12345"}' --video ../demo/test2sec.avi

============================================================
VIDEO SENDER WITH METADATA
============================================================
📹 Source file: ../demo/test2sec.avi
🌐 Destination: 127.0.0.1
📡 Video port: 5000
📋 Metadata port: 5001
📦 Metadata content:
   • user: john
   • timestamp: 2024-01-01
   • session_id: 12345
============================================================

📨 Sending metadata to port 5001...
  Sent metadata packet 1/3
  Sent metadata packet 2/3
▶️  Streaming video...
  Sent metadata packet 3/3
✅ Metadata sent successfully


✅ Video stream ended
Stopping sender...
🛑 Sender stopped

```


```
out/received_metadata.json

{
  "user": "john",
  "timestamp": "2024-01-01",
  "session_id": "12345"
}

```