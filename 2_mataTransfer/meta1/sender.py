#!/usr/bin/env python3
"""
sender.py - Sends video with metadata using side channel
Usage: python sender.py 127.0.0.1 5000 '{"user":"john"}' --video test.avi
"""

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import sys
import json
import argparse
import os
import socket
import threading
import time
import struct

class MetadataProtocol:
    """Protocol for sending metadata alongside video"""
    
    MAGIC = b'META'
    
    @staticmethod
    def create_metadata_packet(metadata):
        """Create a metadata packet with header"""
        json_data = json.dumps(metadata).encode('utf-8')
        # Format: MAGIC (4 bytes) + length (4 bytes) + JSON data
        packet = MetadataProtocol.MAGIC + struct.pack('!I', len(json_data)) + json_data
        return packet

class VideoSender:
    def __init__(self, host, port, metadata, video_file):
        self.host = host
        self.port = port
        self.metadata = metadata
        self.video_file = video_file
        self.pipeline = None
        self.loop = None
        
        # Initialize GStreamer
        Gst.init(None)
    
    def send_metadata(self):
        """Send metadata packets periodically"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Send metadata packet multiple times to ensure delivery
        packet = MetadataProtocol.create_metadata_packet(self.metadata)
        
        print(f"\n📨 Sending metadata to port {self.port + 1}...")
        for i in range(3):  # Send 3 times with delays
            sock.sendto(packet, (self.host, self.port + 1))  # Use port+1 for metadata
            print(f"  Sent metadata packet {i+1}/3")
            time.sleep(0.1)
        
        print(f"✅ Metadata sent successfully\n")
        sock.close()
    
    def create_pipeline(self):
        """Create video pipeline"""
        if not os.path.exists(self.video_file):
            raise FileNotFoundError(f"Video file not found: {self.video_file}")
        
        # Standard MPEG-TS pipeline for video
        pipeline_str = f"""
            filesrc location={self.video_file} !
            decodebin !
            videoconvert !
            videoscale !
            video/x-raw,width=1280,height=720 !
            x264enc tune=zerolatency bitrate=2000 key-int-max=30 !
            video/x-h264,stream-format=byte-stream !
            h264parse !
            mpegtsmux !
            udpsink host={self.host} port={self.port} sync=true
        """
        
        try:
            self.pipeline = Gst.parse_launch(pipeline_str)
        except GLib.GError as e:
            print(f"Error creating pipeline: {e}")
            sys.exit(1)
        
        # Set up bus to handle messages
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_message)
    
    def on_message(self, bus, message):
        """Handle GStreamer bus messages"""
        t = message.type
        
        if t == Gst.MessageType.EOS:
            print("\n✅ Video stream ended")
            self.stop()
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"\n❌ Error: {err}, {debug}")
            self.stop()
        elif t == Gst.MessageType.STATE_CHANGED:
            if message.src == self.pipeline:
                old_state, new_state, pending = message.parse_state_changed()
                if new_state == Gst.State.PLAYING:
                    print("▶️  Streaming video...")
    
    def start(self):
        """Start the sender"""
        print("=" * 60)
        print("VIDEO SENDER WITH METADATA")
        print("=" * 60)
        print(f"📹 Source file: {self.video_file}")
        print(f"🌐 Destination: {self.host}")
        print(f"📡 Video port: {self.port}")
        print(f"📋 Metadata port: {self.port + 1}")
        print(f"📦 Metadata content:")
        for key, value in self.metadata.items():
            print(f"   • {key}: {value}")
        print("=" * 60)
        
        # Send metadata first in a separate thread
        metadata_thread = threading.Thread(target=self.send_metadata)
        metadata_thread.start()
        
        # Create and start video pipeline
        self.create_pipeline()
        
        # Start pipeline
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            print("Unable to set pipeline to playing state")
            sys.exit(1)
        
        # Create and run main loop
        self.loop = GLib.MainLoop()
        try:
            self.loop.run()
        except KeyboardInterrupt:
            print("\n⏹️  Interrupted by user")
            self.stop()
        
        # Wait for metadata thread
        metadata_thread.join()
        print("🛑 Sender stopped")
    
    def stop(self):
        """Stop the sender"""
        print("Stopping sender...")
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
        if self.loop:
            self.loop.quit()

def main():
    parser = argparse.ArgumentParser(
        description='Send video with metadata over UDP',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python sender.py 127.0.0.1 5000 '{"user":"john"}' --video test.avi
  python sender.py 192.168.1.100 5000 '{"session":"123","timestamp":"2024-01-01"}' --video demo.mp4
        """
    )
    
    parser.add_argument('host', help='Destination IP address')
    parser.add_argument('port', type=int, help='Base UDP port (video on port, metadata on port+1)')
    parser.add_argument('metadata', help='JSON metadata string')
    parser.add_argument('--video', required=True, help='Input video file (AVI, MP4, etc.)')
    
    args = parser.parse_args()
    
    # Parse and validate metadata
    try:
        metadata = json.loads(args.metadata)
        if not isinstance(metadata, dict):
            print("Error: Metadata must be a JSON object")
            sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON metadata: {e}")
        print("Example: '{\"user\":\"john\",\"session\":\"12345\"}'")
        sys.exit(1)
    
    # Validate port
    if args.port < 1024 or args.port > 65534:
        print("Error: Port must be between 1024 and 65534")
        sys.exit(1)
    
    # Create and start sender
    sender = VideoSender(args.host, args.port, metadata, args.video)
    sender.start()

if __name__ == '__main__':
    main()