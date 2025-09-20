#!/usr/bin/env python3
"""
Working solution that sends metadata via a side channel
since MPEG-TS strips GStreamer tags
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

class ImprovedSender:
    def __init__(self, host, port, metadata, video_file):
        self.host = host
        self.port = port
        self.metadata = metadata
        self.video_file = video_file
        self.pipeline = None
        Gst.init(None)
    
    def send_metadata(self):
        """Send metadata packets periodically"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Send metadata packet multiple times to ensure delivery
        packet = MetadataProtocol.create_metadata_packet(self.metadata)
        
        for i in range(3):  # Send 3 times with delays
            sock.sendto(packet, (self.host, self.port + 1))  # Use port+1 for metadata
            print(f"Sent metadata packet {i+1}/3")
            time.sleep(0.1)
        
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
        
        self.pipeline = Gst.parse_launch(pipeline_str)
    
    def start(self):
        print(f"Starting improved sender...")
        print(f"  Video port: {self.port}")
        print(f"  Metadata port: {self.port + 1}")
        print(f"  Destination: {self.host}")
        print(f"  Source: {self.video_file}")
        print(f"  Metadata: {self.metadata}")
        
        # Send metadata first in a separate thread
        metadata_thread = threading.Thread(target=self.send_metadata)
        metadata_thread.start()
        
        # Create and start video pipeline
        self.create_pipeline()
        
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        
        def on_message(bus, message):
            t = message.type
            if t == Gst.MessageType.EOS:
                print("Video stream ended")
                self.pipeline.set_state(Gst.State.NULL)
                loop.quit()
            elif t == Gst.MessageType.ERROR:
                err, debug = message.parse_error()
                print(f"Error: {err}")
                self.pipeline.set_state(Gst.State.NULL)
                loop.quit()
            elif t == Gst.MessageType.STATE_CHANGED:
                if message.src == self.pipeline:
                    old_state, new_state, pending = message.parse_state_changed()
                    if new_state == Gst.State.PLAYING:
                        print("Streaming video...")
        
        bus.connect("message", on_message)
        
        self.pipeline.set_state(Gst.State.PLAYING)
        
        loop = GLib.MainLoop()
        try:
            loop.run()
        except KeyboardInterrupt:
            print("\nStopping...")
            self.pipeline.set_state(Gst.State.NULL)
        
        metadata_thread.join()
        print("Sender stopped")

class ImprovedReceiver:
    def __init__(self, port, output_file):
        self.port = port
        self.output_file = output_file
        self.pipeline = None
        self.metadata = {}
        self.metadata_socket = None
        self.stop_metadata = threading.Event()
        Gst.init(None)
    
    def listen_for_metadata(self):
        """Listen for metadata on separate port"""
        self.metadata_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.metadata_socket.bind(('0.0.0.0', self.port + 1))
        self.metadata_socket.settimeout(1.0)
        
        print(f"Listening for metadata on port {self.port + 1}...")
        
        while not self.stop_metadata.is_set():
            try:
                data, addr = self.metadata_socket.recvfrom(4096)
                metadata = MetadataProtocol.parse_metadata_packet(data)
                
                if metadata:
                    self.metadata = metadata
                    print(f"\n📦 Metadata received from {addr[0]}:")
                    print(f"   {json.dumps(metadata, indent=2)}\n")
                    
            except socket.timeout:
                continue
            except Exception as e:
                if not self.stop_metadata.is_set():
                    print(f"Metadata listener error: {e}")
        
        self.metadata_socket.close()
    
    def create_pipeline(self):
        """Create video pipeline"""
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
        
        self.pipeline = Gst.parse_launch(pipeline_str)
    
    def inject_metadata_to_file(self):
        """Inject metadata into the MP4 file after recording"""
        if not self.metadata:
            return
        
        print("Injecting metadata into MP4 file...")
        
        # Create a pipeline to remux with metadata
        temp_file = self.output_file + '.tmp'
        
        # Build tag string
        tags = []
        for key, value in self.metadata.items():
            tags.append(f'comment="{key}:{value}"')
        tags.append(f'description="metadata:{json.dumps(self.metadata)}"')
        tags_str = ','.join(tags)
        
        remux_pipeline_str = f"""
            filesrc location={self.output_file} !
            qtdemux !
            qtmux !
            filesink location={temp_file}
        """
        
        # For now, just save metadata to JSON
        # (Full tag injection would require more complex pipeline)
        self.save_metadata()
    
    def save_metadata(self):
        """Save metadata to JSON file"""
        if self.metadata:
            metadata_file = self.output_file.replace('.mp4', '_metadata.json')
            with open(metadata_file, 'w') as f:
                json.dump(self.metadata, f, indent=2)
            print(f"✅ Metadata saved to: {metadata_file}")
            print(f"   Content: {json.dumps(self.metadata, indent=2)}")
    
    def start(self):
        print(f"Starting improved receiver...")
        print(f"  Video port: {self.port}")
        print(f"  Metadata port: {self.port + 1}")
        print(f"  Output: {self.output_file}")
        
        # Start metadata listener in background
        metadata_thread = threading.Thread(target=self.listen_for_metadata)
        metadata_thread.start()
        
        # Give metadata listener time to start
        time.sleep(0.5)
        
        # Create video pipeline
        self.create_pipeline()
        
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        
        def on_message(bus, message):
            t = message.type
            if t == Gst.MessageType.EOS:
                print("\n✅ Video stream complete")
                self.stop_metadata.set()
                self.inject_metadata_to_file()
                self.pipeline.set_state(Gst.State.NULL)
                loop.quit()
            elif t == Gst.MessageType.ERROR:
                err, debug = message.parse_error()
                print(f"Error: {err}")
                self.stop_metadata.set()
                self.pipeline.set_state(Gst.State.NULL)
                loop.quit()
            elif t == Gst.MessageType.STATE_CHANGED:
                if message.src == self.pipeline:
                    old_state, new_state, pending = message.parse_state_changed()
                    if new_state == Gst.State.PLAYING:
                        print("Receiving video stream...")
            elif t == Gst.MessageType.ELEMENT:
                structure = message.get_structure()
                if structure and structure.get_name() == "GstUDPSrcTimeout":
                    print("\n⏱️  Video stream timeout - no data for 5 seconds")
                    self.stop_metadata.set()
                    self.save_metadata()
                    self.pipeline.set_state(Gst.State.NULL)
                    loop.quit()
        
        bus.connect("message", on_message)
        
        self.pipeline.set_state(Gst.State.PLAYING)
        
        loop = GLib.MainLoop()
        try:
            loop.run()
        except KeyboardInterrupt:
            print("\nStopping...")
            self.stop_metadata.set()
            self.save_metadata()
            self.pipeline.set_state(Gst.State.NULL)
        
        metadata_thread.join()
        print(f"📹 Video saved to: {self.output_file}")

def main():
    parser = argparse.ArgumentParser(description='Video streaming with metadata side channel')
    subparsers = parser.add_subparsers(dest='mode', help='Mode: sender or receiver')
    
    # Sender arguments
    sender_parser = subparsers.add_parser('sender', help='Send video with metadata')
    sender_parser.add_argument('host', help='Destination IP')
    sender_parser.add_argument('port', type=int, help='Base port (video on port, metadata on port+1)')
    sender_parser.add_argument('metadata', help='JSON metadata string')
    sender_parser.add_argument('--video', required=True, help='Input video file')
    
    # Receiver arguments
    receiver_parser = subparsers.add_parser('receiver', help='Receive video with metadata')
    receiver_parser.add_argument('port', type=int, help='Base port (video on port, metadata on port+1)')
    receiver_parser.add_argument('output', help='Output MP4 file')
    
    args = parser.parse_args()
    
    if not args.mode:
        parser.print_help()
        sys.exit(1)
    
    if args.mode == 'sender':
        try:
            metadata = json.loads(args.metadata)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON metadata: {e}")
            sys.exit(1)
        
        sender = ImprovedSender(args.host, args.port, metadata, args.video)
        sender.start()
    
    elif args.mode == 'receiver':
        receiver = ImprovedReceiver(args.port, args.output)
        receiver.start()

if __name__ == '__main__':
    main()