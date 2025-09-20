#!/usr/bin/env python3
"""
sei_sender.py - Injects metadata as SEI NAL units into H.264 stream
Works with GStreamer 1.16 using appsink/appsrc approach
Usage: python sei_sender.py 127.0.0.1 5000 '{"user":"john"}' --video test.avi
"""

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstApp', '1.0')
from gi.repository import Gst, GstApp, GLib
import sys
import json
import argparse
import os
import threading

class SEINALInjector:
    """Helper class for creating SEI NAL units"""
    
    # Custom UUID for our metadata (16 bytes)
    CUSTOM_UUID = b'METADATA' + b'\x00' * 8
    
    @staticmethod
    def create_sei_nal_unit(metadata_json):
        """Create a SEI NAL unit with user_data_unregistered payload"""
        json_bytes = metadata_json.encode('utf-8')
        payload_size = 16 + len(json_bytes)
        
        sei_payload = bytearray()
        sei_payload.append(0x05)  # user_data_unregistered
        
        # Add payload size
        if payload_size < 255:
            sei_payload.append(payload_size)
        else:
            size_remaining = payload_size
            while size_remaining >= 255:
                sei_payload.append(0xFF)
                size_remaining -= 255
            sei_payload.append(size_remaining)
        
        # Add UUID and JSON data
        sei_payload.extend(SEINALInjector.CUSTOM_UUID)
        sei_payload.extend(json_bytes)
        sei_payload.append(0x80)  # RBSP stop bit
        
        # Complete SEI NAL with start code
        return b'\x00\x00\x00\x01\x06' + bytes(sei_payload)

class SEIVideoSender:
    def __init__(self, host, port, metadata, video_file):
        self.host = host
        self.port = port
        self.metadata = metadata
        self.video_file = video_file
        self.pipeline = None
        self.loop = None
        self.sei_injected_count = 0
        self.buffer_count = 0
        
        # Initialize GStreamer
        Gst.init(None)
    
    def on_new_sample(self, sink):
        """Handle new sample from appsink"""
        sample = sink.emit("pull-sample")
        if sample:
            buffer = sample.get_buffer()
            self.buffer_count += 1
            
            # Get the appsrc
            appsrc = self.pipeline.get_by_name('appsrc')
            if not appsrc:
                return Gst.FlowReturn.ERROR
            
            # Check if keyframe
            flags = buffer.get_flags()
            is_keyframe = (flags & Gst.BufferFlags.DELTA_UNIT) == 0
            
            # Get buffer data
            success, map_info = buffer.map(Gst.MapFlags.READ)
            if success:
                data = bytes(map_info.data)
                buffer.unmap(map_info)
                
                # Inject SEI if keyframe
                if is_keyframe:
                    # Create SEI NAL
                    metadata_json = json.dumps(self.metadata)
                    sei_nal = SEINALInjector.create_sei_nal_unit(metadata_json)
                    
                    # Find insertion point (after AUD if present)
                    insert_pos = 0
                    if len(data) > 5 and data[:5] == b'\x00\x00\x00\x01\x09':
                        # Find next start code after AUD
                        for i in range(5, min(50, len(data)-3)):
                            if data[i:i+3] == b'\x00\x00\x01' or data[i:i+4] == b'\x00\x00\x00\x01':
                                insert_pos = i
                                break
                    
                    # Insert SEI
                    if insert_pos > 0:
                        new_data = data[:insert_pos] + sei_nal + data[insert_pos:]
                    else:
                        new_data = sei_nal + data
                    
                    # Create new buffer
                    new_buffer = Gst.Buffer.new_wrapped(new_data)
                    new_buffer.pts = buffer.pts
                    new_buffer.dts = buffer.dts
                    new_buffer.duration = buffer.duration
                    
                    # Push modified buffer
                    ret = appsrc.emit("push-buffer", new_buffer)
                    
                    self.sei_injected_count += 1
                    print(f"💉 Injected SEI #{self.sei_injected_count} at keyframe (buffer #{self.buffer_count})")
                    
                    if self.sei_injected_count == 1:
                        print(f"    SEI size: {len(sei_nal)} bytes")
                        print(f"    Total buffer size: {len(new_data)} bytes")
                else:
                    # Push original buffer
                    ret = appsrc.emit("push-buffer", buffer)
            else:
                # Push original buffer if mapping failed
                ret = appsrc.emit("push-buffer", buffer)
                
        return Gst.FlowReturn.OK
    
    def create_pipeline(self):
        """Create pipeline with appsink/appsrc for SEI injection"""
        if not os.path.exists(self.video_file):
            raise FileNotFoundError(f"Video file not found: {self.video_file}")
        
        # Build pipeline with appsink and appsrc
        pipeline_str = f"""
            filesrc location={self.video_file} !
            decodebin !
            videoconvert !
            videoscale !
            video/x-raw,width=1280,height=720 !
            x264enc tune=zerolatency bitrate=2000 key-int-max=30 speed-preset=medium bframes=0 !
            h264parse !
            appsink name=appsink emit-signals=true sync=false
            
            appsrc name=appsrc !
            video/x-h264,stream-format=byte-stream !
            mpegtsmux !
            udpsink host={self.host} port={self.port} sync=true
        """
        
        self.pipeline = Gst.parse_launch(pipeline_str)
        
        # Get appsink and connect callback
        appsink = self.pipeline.get_by_name('appsink')
        if appsink:
            appsink.connect("new-sample", self.on_new_sample)
            print("✅ Connected to appsink for SEI injection")
        
        # Set up bus
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_message)
    
    def on_message(self, bus, message):
        """Handle pipeline messages"""
        t = message.type
        
        if t == Gst.MessageType.EOS:
            print(f"\n✅ Stream ended. Total SEI NAL units injected: {self.sei_injected_count}")
            # Send EOS to appsrc
            appsrc = self.pipeline.get_by_name('appsrc')
            if appsrc:
                appsrc.emit("end-of-stream")
            # Wait a bit for final data
            GLib.timeout_add_seconds(1, self.stop)
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"\n❌ Error: {err}, {debug}")
            self.stop()
        elif t == Gst.MessageType.STATE_CHANGED:
            if message.src == self.pipeline:
                old_state, new_state, pending = message.parse_state_changed()
                if new_state == Gst.State.PLAYING:
                    print("▶️  Streaming with SEI metadata injection...")
    
    def start(self):
        """Start the sender"""
        print("=" * 60)
        print("H.264 SEI NAL METADATA INJECTOR (GStreamer 1.16)")
        print("=" * 60)
        print(f"📹 Source: {self.video_file}")
        print(f"🌐 Destination: {self.host}:{self.port}")
        print(f"📦 Metadata to inject in SEI NAL:")
        for key, value in self.metadata.items():
            print(f"   • {key}: {value}")
        print(f"🔧 SEI UUID: {SEINALInjector.CUSTOM_UUID[:8].hex()}...")
        print("=" * 60)
        
        self.create_pipeline()
        
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            print("Unable to set pipeline to playing state")
            sys.exit(1)
        
        self.loop = GLib.MainLoop()
        try:
            self.loop.run()
        except KeyboardInterrupt:
            print("\n⏹️  Interrupted by user")
            self.stop()
    
    def stop(self):
        """Stop the sender"""
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
        if self.loop:
            self.loop.quit()
        print("🛑 Sender stopped")
        return False  # Don't repeat timeout

def main():
    parser = argparse.ArgumentParser(
        description='Send H.264 video with metadata in SEI NAL units',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This sender injects metadata directly into the H.264 bitstream as SEI NAL units.
Works with GStreamer 1.16 using appsink/appsrc approach.

Example:
  python sei_sender.py 127.0.0.1 5000 '{"user":"john","session":"123"}' --video test.avi
        """
    )
    
    parser.add_argument('host', help='Destination IP address')
    parser.add_argument('port', type=int, help='UDP port')
    parser.add_argument('metadata', help='JSON metadata to inject')
    parser.add_argument('--video', required=True, help='Input video file')
    
    args = parser.parse_args()
    
    # Parse metadata
    try:
        metadata = json.loads(args.metadata)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON metadata: {e}")
        sys.exit(1)
    
    sender = SEIVideoSender(args.host, args.port, metadata, args.video)
    sender.start()

if __name__ == '__main__':
    main()