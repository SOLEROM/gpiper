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

def draw_crosshair(buffer, x, y, width, height, stride, size=10, color=(0, 255, 0)):
    """Draw a crosshair at the given position"""
    bpp = 3
    r, g, b = color
    
    # Draw horizontal line
    for dx in range(-size, size + 1):
        px = x + dx
        if 0 <= px < width and 0 <= y < height:
            offset = y * stride + px * bpp
            seg = bytearray([r, g, b])
            buffer.fill(offset, bytes(seg))
    
    # Draw vertical line
    for dy in range(-size, size + 1):
        py = y + dy
        if 0 <= x < width and 0 <= py < height:
            offset = py * stride + x * bpp
            seg = bytearray([r, g, b])
            buffer.fill(offset, bytes(seg))

def draw_circle(buffer, cx, cy, width, height, stride, radius=5, color=(255, 0, 0)):
    """Draw a circle outline at the given position"""
    bpp = 3
    r, g, b = color
    
    # Draw circle using midpoint circle algorithm (just the outline)
    for angle in range(0, 360, 5):  # Sample every 5 degrees
        import math
        rad = math.radians(angle)
        dx = int(radius * math.cos(rad))
        dy = int(radius * math.sin(rad))
        px, py = cx + dx, cy + dy
        
        if 0 <= px < width and 0 <= py < height:
            offset = py * stride + px * bpp
            seg = bytearray([r, g, b])
            buffer.fill(offset, bytes(seg))

def draw_box(buffer, x, y, w, h, width, height, stride, color=(255, 255, 0)):
    """Draw a filled rectangle"""
    bpp = 3
    r, g, b = color
    
    for dy in range(h):
        for dx in range(w):
            px, py = x + dx, y + dy
            if 0 <= px < width and 0 <= py < height:
                offset = py * stride + px * bpp
                seg = bytearray([r, g, b])
                buffer.fill(offset, bytes(seg))

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

    # Map buffer for reading to find ball
    ok, info = buffer.map(Gst.MapFlags.READ)
    if not ok:
        return
    
    try:
        data = info.data
        ball_x, ball_y = find_brightest_spot(data, width, height, stride)
    finally:
        buffer.unmap(info)

    # Draw visual overlays on the video
    if args.draw_position:
        # Draw green crosshair at ball position
        draw_crosshair(buffer, ball_x, ball_y, width, height, stride, size=15, color=(0, 255, 0))
        
        # Draw red circle around ball
        draw_circle(buffer, ball_x, ball_y, width, height, stride, radius=12, color=(255, 0, 0))
        
        # Draw yellow info box in top-left corner showing coordinates
        draw_box(buffer, 5, 5, 80, 12, width, height, stride, color=(0, 0, 0))  # Black background
        
        # Draw coordinate digits as colored boxes (simple visualization)
        # Each "digit" is represented by a small colored square
        x_pos = 10
        # Show ball_x in hundreds, tens, ones
        for digit_val in [ball_x // 100, (ball_x // 10) % 10, ball_x % 10]:
            brightness = int(digit_val * 25.5)  # Scale 0-9 to 0-255
            draw_box(buffer, x_pos, 7, 6, 8, width, height, stride, color=(brightness, 255, brightness))
            x_pos += 8
        
        x_pos += 5  # Space
        # Show ball_y in hundreds, tens, ones
        for digit_val in [ball_y // 100, (ball_y // 10) % 10, ball_y % 10]:
            brightness = int(digit_val * 25.5)
            draw_box(buffer, x_pos, 7, 6, 8, width, height, stride, color=(255, brightness, brightness))
            x_pos += 8

    # Optional: mutate box (inverted colors)
    if args.mutate:
        bx0, by0 = width - 70, 10  # Move to top-right so it doesn't overlap
        bx1, by1 = min(width, bx0 + 60), min(height, by0 + 60)
        bpp = 3
        
        for y in range(by0, by1):
            offset = y * stride + bx0 * bpp
            row_len = (bx1 - bx0) * bpp
            row_data = buffer.extract_dup(offset, row_len)
            seg = bytearray(row_data)
            for i in range(0, len(seg), 3):
                seg[i] = 255 - seg[i]
                seg[i+1] = 255 - seg[i+1]
                seg[i+2] = 255 - seg[i+2]
            buffer.fill(offset, bytes(seg))

    if FRAME_COUNTER % 15 == 0:
        print(f"[{FRAME_COUNTER:05d}] PTS={ms:8.2f}ms Ball:({ball_x:3d},{ball_y:3d})")
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
    ap = argparse.ArgumentParser(description="UDP sender with visual ball tracking overlay")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--width", type=int, default=320)
    ap.add_argument("--height", type=int, default=240)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--mutate", action="store_true", help="invert a small box (top-right)")
    ap.add_argument("--draw-position", action="store_true", help="draw crosshair + circle at ball position")
    args = ap.parse_args()

    pipe_desc = build_pipeline(args.host, args.port, args.width, args.height, args.fps)
    pipeline = Gst.parse_launch(pipe_desc)

    tap = pipeline.get_by_name("tap")
    if not tap:
        print("identity 'tap' not found", file=sys.stderr)
        sys.exit(1)

    tap.connect("handoff", lambda e, b, *extra: on_handoff(e, b, extra[0] if extra else None, args))

    bus = pipeline.get_bus()
    bus.add_signal_watch()
    loop = GLib.MainLoop()
    bus.connect("message", on_bus, loop, pipeline)

    print(f"Sending RTP/H.264 to {args.host}:{args.port}")
    print(f"Resolution: {args.width}x{args.height} @ {args.fps}fps")
    print(f"Visual overlay: {args.draw_position}, Mutate box: {args.mutate}")
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