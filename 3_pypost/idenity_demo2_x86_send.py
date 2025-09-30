#!/usr/bin/env python3
import argparse, sys
import gi
gi.require_version("Gst", "1.0")
gi.require_version("GstVideo", "1.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gst, GLib, GstVideo

Gst.init(None)

FRAME_COUNTER = 0

def build_pipeline(host, port, width, height, fps):
    """
    Topology:
      videotestsrc (RGB) → identity(tap) → tee
                                  ├─ branch A: (local preview)
                                  │    videoconvert → autovideosink
                                  └─ branch B: (UDP)
                                       videoconvert → I420 → x264enc → rtph264pay → udpsink
    Place identity BEFORE tee so any pixel edits affect BOTH branches.
    """
    pipe = f"""
videotestsrc pattern=ball is-live=true !
video/x-raw,format=RGB,width={width},height={height},framerate={fps}/1 !
identity name=tap signal-handoffs=true !
tee name=t

t. ! queue max-size-buffers=5 leaky=downstream ! videoconvert ! autovideosink sync=false

t. ! queue max-size-buffers=5 leaky=downstream !
videoconvert !
video/x-raw,format=I420 !
x264enc tune=zerolatency speed-preset=ultrafast bitrate=1500 key-int-max=30 !
rtph264pay config-interval=1 pt=96 !
udpsink host={host} port={port} sync=false async=false
"""
    return pipe

def find_brightest_spot(data, width, height, stride):
    """Find the coordinate of the brightest spot (the ball)"""
    bpp = 3  # RGB
    max_brightness = 0
    ball_x, ball_y = 0, 0
    
    # Sample every 4th pixel for speed
    for y in range(0, height, 4):
        for x in range(0, width, 4):
            offset = y * stride + x * bpp
            r = data[offset]
            g = data[offset + 1]
            b = data[offset + 2]
            brightness = r + g + b
            
            if brightness > max_brightness:
                max_brightness = brightness
                ball_x = x
                ball_y = y
    
    return ball_x, ball_y

def on_handoff(element, buffer, pad, args):
    """Per-frame callback on the SENDING side."""
    global FRAME_COUNTER
    FRAME_COUNTER += 1

    # Get the pad if not provided
    if pad is None:
        pad = element.get_static_pad("src")

    # Timestamp (ns → ms)
    pts = buffer.pts
    ms = -1 if pts == Gst.CLOCK_TIME_NONE else pts / Gst.MSECOND

    # Get video meta to know geometry/stride
    vmeta = GstVideo.buffer_get_video_meta(buffer)
    if vmeta is None:
        # Try getting dimensions from caps
        caps = pad.get_current_caps() if pad else None
        if not caps:
            return
        struct = caps.get_structure(0)
        success, width = struct.get_int("width")
        if not success:
            return
        success, height = struct.get_int("height")
        if not success:
            return
        stride = width * 3  # RGB
    else:
        width, height = vmeta.width, vmeta.height
        stride = vmeta.stride[0] if vmeta.n_planes > 0 else width * 3

    # Map buffer for reading
    ok, info = buffer.map(Gst.MapFlags.READ)
    if not ok:
        return
    
    try:
        data = info.data
        
        # Find ball position
        ball_x, ball_y = find_brightest_spot(data, width, height, stride)
        
        # Calculate mean brightness in center region
        cx, cy = width // 2, height // 2
        rw, rh = 80, 60
        x0, y0 = max(0, cx - rw // 2), max(0, cy - rh // 2)
        x1, y1 = min(width, x0 + rw), min(height, y0 + rh)

        s = 0
        n = 0
        bpp = 3
        for y in range(y0, y1, 2):
            row = y * stride
            for x in range(x0, x1, 2):
                p = row + x * bpp
                r, g, b = data[p], data[p+1], data[p+2]
                s += (r*3 + g*6 + b*1)
                n += 10
        mean_luma = (s / n) if n else 0.0
        
    finally:
        buffer.unmap(info)

    # Optional: mutate pixels IN THE LIVE BUFFER so both branches see it
    if args.mutate:
        # Invert a small 60x60 box at (10,10) using buffer.extract/fill
        bx0, by0 = 10, 10
        bx1, by1 = min(width, bx0 + 60), min(height, by0 + 60)
        bpp = 3
        
        for y in range(by0, by1):
            offset = y * stride + bx0 * bpp
            row_len = (bx1 - bx0) * bpp
            
            # Extract the row segment
            row_data = buffer.extract_dup(offset, row_len)
            
            # Convert to bytearray, invert colors
            seg = bytearray(row_data)
            for i in range(0, len(seg), 3):
                seg[i] = 255 - seg[i]       # R
                seg[i+1] = 255 - seg[i+1]   # G
                seg[i+2] = 255 - seg[i+2]   # B
            
            # Write back to buffer
            buffer.fill(offset, bytes(seg))

    if FRAME_COUNTER % 15 == 0:
        print(f"[{FRAME_COUNTER:05d}] PTS={ms:8.2f}ms Ball:({ball_x:3d},{ball_y:3d}) brightness≈{mean_luma:6.1f} mutate={args.mutate}")
        sys.stdout.flush()

def on_bus(bus, msg, loop, pipeline):
    t = msg.type
    if t == Gst.MessageType.ERROR:
        err, dbg = msg.parse_error()
        print(f"\n[GSTREAMER ERROR] {err}")
        if dbg: 
            print(f"[DEBUG] {dbg}")
        pipeline.set_state(Gst.State.NULL)
        loop.quit()
    elif t == Gst.MessageType.EOS:
        print("\n[GSTREAMER] EOS")
        pipeline.set_state(Gst.State.NULL)
        loop.quit()
    return True

def main():
    ap = argparse.ArgumentParser(description="UDP sender with identity handoff - tracks ball position")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--width", type=int, default=320)
    ap.add_argument("--height", type=int, default=240)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--mutate", action="store_true", help="invert a small box so edits are visible")
    args = ap.parse_args()

    pipe_desc = build_pipeline(args.host, args.port, args.width, args.height, args.fps)
    pipeline = Gst.parse_launch(pipe_desc)

    tap = pipeline.get_by_name("tap")
    if not tap:
        print("identity 'tap' not found", file=sys.stderr)
        sys.exit(1)

    # Handle both 2-arg and 3-arg handoff signal versions
    tap.connect("handoff", lambda e, b, *extra: on_handoff(e, b, extra[0] if extra else None, args))

    bus = pipeline.get_bus()
    bus.add_signal_watch()
    loop = GLib.MainLoop()
    bus.connect("message", on_bus, loop, pipeline)

    print(f"Sending RTP/H.264 to {args.host}:{args.port} (mutate={args.mutate})")
    print(f"Resolution: {args.width}x{args.height} @ {args.fps}fps")
    print("Tracking ball position...\n")
    sys.stdout.flush()
    
    if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
        print("Failed to start pipeline", file=sys.stderr)
        sys.exit(1)

    try:
        loop.run()
    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        pipeline.set_state(Gst.State.NULL)
        print("Stopped.")

if __name__ == "__main__":
    main()