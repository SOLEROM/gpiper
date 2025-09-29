# meta side channel

* MPEG-TS (Transport Stream) doesn't preserve GStreamer tags. 
* see 2 shells 2sideTags to see that the metadata is stripped 
* use the test that shows the metadata is saved in mp4 file but not transmitted over mpeg-ts;


``` #!/usr/bin/env python3
import sys
import gi
gi.require_version("Gst", "1.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gst, GLib

Gst.init(None)

FRAME_COUNTER = 0

PIPELINE = """
videotestsrc pattern=ball is-live=true !
video/x-raw,format=RGB,width=320,height=240,framerate=30/1 !
identity name=tap signal-handoffs=true !
videoconvert !
autovideosink sync=false
"""

def find_brightest_spot(data, width, height):
    """Find the coordinate of the brightest spot (the ball)"""
    stride = width * 3
    max_brightness = 0
    ball_x, ball_y = 0, 0
    
    # Sample every 4th pixel for speed
    for y in range(0, height, 4):
        for x in range(0, width, 4):
            offset = y * stride + x * 3
            r = data[offset]
            g = data[offset + 1]
            b = data[offset + 2]
            brightness = r + g + b
            
            if brightness > max_brightness:
                max_brightness = brightness
                ball_x = x
                ball_y = y
    
    return ball_x, ball_y

def on_handoff(element, buffer, pad):
    global FRAME_COUNTER
    FRAME_COUNTER += 1

    # Get video dimensions from caps
    caps = pad.get_current_caps()
    if not caps:
        print("No caps available")
        return

    struct = caps.get_structure(0)
    success, width = struct.get_int("width")
    if not success:
        print("Could not get width")
        return
    success, height = struct.get_int("height")
    if not success:
        print("Could not get height")
        return
    
    # Map buffer for reading
    success, map_info = buffer.map(Gst.MapFlags.READ)
    if not success:
        print("Could not map buffer")
        return

    try:
        ball_x, ball_y = find_brightest_spot(map_info.data, width, height)
        print(f"Frame {FRAME_COUNTER:04d}: Ball center at ({ball_x:3d}, {ball_y:3d})")
        sys.stdout.flush()  # Force print to appear immediately
            
    finally:
        buffer.unmap(map_info)

def on_bus(bus, msg, loop, pipeline):
    if msg.type == Gst.MessageType.ERROR:
        err, debug = msg.parse_error()
        print(f"\nERROR: {err}")
        if debug:
            print(f"DEBUG: {debug}")
        pipeline.set_state(Gst.State.NULL)
        loop.quit()
    elif msg.type == Gst.MessageType.EOS:
        print("\nEnd of stream")
        pipeline.set_state(Gst.State.NULL)
        loop.quit()
    elif msg.type == Gst.MessageType.WARNING:
        warn, debug = msg.parse_warning()
        print(f"WARNING: {warn}")
    return True

def main():
    print("Starting ball tracker with video display...")
    sys.stdout.flush()
    
    pipeline = Gst.parse_launch(PIPELINE)

    identity = pipeline.get_by_name("tap")
    if not identity:
        print("ERROR: Could not find identity element", file=sys.stderr)
        sys.exit(1)

    # Connect handoff signal
    identity.connect("handoff", on_handoff)
    print("Connected handoff signal")
    sys.stdout.flush()

    bus = pipeline.get_bus()
    bus.add_signal_watch()
    loop = GLib.MainLoop()  # Fixed: use GLib.MainLoop instead of GObject.MainLoop
    bus.connect("message", on_bus, loop, pipeline)

    ret = pipeline.set_state(Gst.State.PLAYING)
    if ret == Gst.StateChangeReturn.FAILURE:
        print("ERROR: Failed to start pipeline", file=sys.stderr)
        sys.exit(1)
    
    print("Pipeline started, waiting for frames...\n")
    sys.stdout.flush()

    try:
        loop.run()
    except KeyboardInterrupt:
        print("\n\nStopped by user")
    finally:
        pipeline.set_state(Gst.State.NULL)
        print("Pipeline stopped")

if __name__ == "__main__":
    main()
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

* Sends video on the specified port (e.g., 5000)
* Sends metadata on port+1 (e.g., 5001)
* Sends metadata 3 times to ensure delivery
* Clear status messages and progress indicators
* Proper error handling

### receiver.py:

* Listens for video on the specified port
* Listens for metadata on port+1
* Saves video as MP4
* Saves metadata as JSON file
* Shows received metadata in real-time
* Handles timeouts gracefully

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