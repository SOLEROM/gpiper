#!/usr/bin/env python3
import argparse
import gi
gi.require_version("Gst", "1.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gst, GLib

Gst.init(None)

def build_receiver_pipeline(port):
    """
    Simple RTP/H.264 receiver
    """
    pipe = f"""
udpsrc port={port} caps="application/x-rtp, media=(string)video, clock-rate=(int)90000, encoding-name=(string)H264, payload=(int)96" !
rtph264depay !
h264parse !
avdec_h264 !
videoconvert !
autovideosink sync=false
"""
    return pipe

def on_bus(bus, msg, loop, pipeline):
    t = msg.type
    if t == Gst.MessageType.ERROR:
        err, dbg = msg.parse_error()
        print(f"\n[ERROR] {err}")
        if dbg:
            print(f"[DEBUG] {dbg}")
        pipeline.set_state(Gst.State.NULL)
        loop.quit()
    elif t == Gst.MessageType.EOS:
        print("\n[EOS] End of stream")
        pipeline.set_state(Gst.State.NULL)
        loop.quit()
    elif t == Gst.MessageType.STATE_CHANGED:
        if msg.src == pipeline:
            old, new, pending = msg.parse_state_changed()
            print(f"Pipeline state: {old.value_nick} -> {new.value_nick}")
    return True

def main():
    ap = argparse.ArgumentParser(description="UDP RTP/H.264 receiver")
    ap.add_argument("--port", type=int, default=5000, help="UDP port to listen on")
    args = ap.parse_args()

    pipe_desc = build_receiver_pipeline(args.port)
    print(f"Listening for RTP/H.264 on port {args.port}...")
    print("Waiting for stream...\n")
    
    pipeline = Gst.parse_launch(pipe_desc)

    bus = pipeline.get_bus()
    bus.add_signal_watch()
    loop = GLib.MainLoop()
    bus.connect("message", on_bus, loop, pipeline)

    if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
        print("Failed to start pipeline")
        return

    try:
        loop.run()
    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        pipeline.set_state(Gst.State.NULL)
        print("Stopped.")

if __name__ == "__main__":
    main()