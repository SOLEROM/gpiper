#!/usr/bin/env python3
"""
receiver.py - Receives video with metadata using side channel
Usage: python receiver.py 5000 ../out/received.mp4
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
    """Protocol for parsing metadata packets"""
    
    MAGIC = b'META'
    
    @staticmethod
    def parse_metadata_packet(data):
        """Parse metadata packet, return None if not metadata"""
        if len(data) < 8:
            return None
        
        if data[:4] != MetadataProtocol.MAGIC:
            return None
        
        length = struct.unpack('!I', data[4:8])[0]
        if len(data) < 8 + length:
            return None
        
        try:
            json_data = data[8:8+length].decode('utf-8')
            return json.loads(json_data)
        except:
            return None

class VideoReceiver:
    def __init__(self, port, output_file):
        self.port = port
        self.output_file = output_file
        self.pipeline = None
        self.loop = None
        self.metadata = {}
        self.metadata_socket = None
        self.stop_metadata = threading.Event()
        
        # Initialize GStreamer
        Gst.init(None)
    
    def listen_for_metadata(self):
        """Listen for metadata on separate port"""
        self.metadata_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.metadata_socket.bind(('0.0.0.0', self.port + 1))
        self.metadata_socket.settimeout(1.0)
        
        print(f"👂 Listening for metadata on port {self.port + 1}...")
        
        while not self.stop_metadata.is_set():
            try:
                data, addr = self.metadata_socket.recvfrom(4096)
                metadata = MetadataProtocol.parse_metadata_packet(data)
                
                if metadata:
                    self.metadata = metadata
                    print(f"\n📦 METADATA RECEIVED from {addr[0]}:")
                    print("   " + "-" * 40)
                    for key, value in metadata.items():
                        print(f"   • {key}: {value}")
                    print("   " + "-" * 40 + "\n")
                    
            except socket.timeout:
                continue
            except Exception as e:
                if not self.stop_metadata.is_set():
                    print(f"Metadata listener error: {e}")
        
        self.metadata_socket.close()
        print("Metadata listener stopped")
    
    def create_pipeline(self):
        """Create video pipeline"""
        # Ensure output directory exists
        output_dir = os.path.dirname(self.output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Add timeout to detect end of stream
        pipeline_str = f"""
            udpsrc port={self.port} timeout=5000000000 !
            video/mpegts !
            tsdemux !
            h264parse !
            mp4mux !
            filesink location={self.output_file}
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
            print("\n✅ Video stream complete")
            self.stop_metadata.set()
            self.save_metadata()
            self.stop()
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"\n❌ Error: {err}, {debug}")
            self.stop_metadata.set()
            self.stop()
        elif t == Gst.MessageType.STATE_CHANGED:
            if message.src == self.pipeline:
                old_state, new_state, pending = message.parse_state_changed()
                if new_state == Gst.State.PLAYING:
                    print("▶️  Receiving video stream...")
        elif t == Gst.MessageType.ELEMENT:
            structure = message.get_structure()
            if structure and structure.get_name() == "GstUDPSrcTimeout":
                print("\n⏱️  Video stream timeout - no data for 5 seconds")
                self.stop_metadata.set()
                self.save_metadata()
                self.stop()
    
    def save_metadata(self):
        """Save metadata to JSON file"""
        if self.metadata:
            metadata_file = self.output_file.replace('.mp4', '_metadata.json')
            try:
                with open(metadata_file, 'w') as f:
                    json.dump(self.metadata, f, indent=2)
                
                print("\n" + "=" * 60)
                print("📋 METADATA SAVED")
                print("=" * 60)
                print(f"📁 File: {metadata_file}")
                print("📦 Content:")
                for key, value in self.metadata.items():
                    print(f"   • {key}: {value}")
                print("=" * 60)
            except Exception as e:
                print(f"Error saving metadata: {e}")
        else:
            print("\n⚠️  No metadata received")
    
    def start(self):
        """Start the receiver"""
        print("=" * 60)
        print("VIDEO RECEIVER WITH METADATA")
        print("=" * 60)
        print(f"📡 Video port: {self.port}")
        print(f"📋 Metadata port: {self.port + 1}")
        print(f"💾 Output file: {self.output_file}")
        print("=" * 60)
        print("⏳ Waiting for stream...")
        
        # Start metadata listener in background
        metadata_thread = threading.Thread(target=self.listen_for_metadata)
        metadata_thread.daemon = True
        metadata_thread.start()
        
        # Give metadata listener time to start
        time.sleep(0.5)
        
        # Create video pipeline
        self.create_pipeline()
        
        # Start pipeline
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            print("Unable to set pipeline to playing state")
            self.stop_metadata.set()
            sys.exit(1)
        
        # Create and run main loop
        self.loop = GLib.MainLoop()
        try:
            self.loop.run()
        except KeyboardInterrupt:
            print("\n⏹️  Interrupted by user")
            self.stop_metadata.set()
            self.save_metadata()
            self.stop()
        
        # Wait for metadata thread to finish
        metadata_thread.join(timeout=2)
        
        print(f"\n📹 Video saved to: {self.output_file}")
        
        # Show summary
        if self.metadata:
            metadata_file = self.output_file.replace('.mp4', '_metadata.json')
            print(f"📋 Metadata saved to: {metadata_file}")
    
    def stop(self):
        """Stop the receiver"""
        print("Stopping receiver...")
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
        if self.loop:
            self.loop.quit()

def main():
    parser = argparse.ArgumentParser(
        description='Receive video with metadata over UDP',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python receiver.py 5000 output.mp4
  python receiver.py 5000 ../recordings/stream.mp4
        """
    )
    
    parser.add_argument('port', type=int, help='Base UDP port (video on port, metadata on port+1)')
    parser.add_argument('output', help='Output MP4 file path')
    
    args = parser.parse_args()
    
    # Validate port
    if args.port < 1024 or args.port > 65534:
        print("Error: Port must be between 1024 and 65534")
        sys.exit(1)
    
    # Validate output path
    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
            print(f"Created output directory: {output_dir}")
        except Exception as e:
            print(f"Error creating output directory: {e}")
            sys.exit(1)
    
    # Create and start receiver
    receiver = VideoReceiver(args.port, args.output)
    receiver.start()

if __name__ == '__main__':
    main()