#!/usr/bin/env python3
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

def on_handoff(element, buffer, pad=None):
    global FRAME_COUNTER
    FRAME_COUNTER += 1

    # Get the src pad if pad wasn't provided
    if pad is None:
        pad = element.get_static_pad("src")
    
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
    return True

def main():
    print("Starting ball tracker with video display...")
    sys.stdout.flush()
    
    pipeline = Gst.parse_launch(PIPELINE)

    identity = pipeline.get_by_name("tap")
    if not identity:
        print("ERROR: Could not find identity element", file=sys.stderr)
        sys.exit(1)

    # Connect handoff signal with wrapper to handle both 2-arg and 3-arg versions
    identity.connect("handoff", lambda e, b, *args: on_handoff(e, b, args[0] if args else None))
    print("Connected handoff signal")
    sys.stdout.flush()

    bus = pipeline.get_bus()
    bus.add_signal_watch()
    loop = GLib.MainLoop()
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