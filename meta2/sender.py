#!/usr/bin/env python3
"""
sei_sender.py - Injects metadata as SEI NAL units into H.264 stream
Works with GStreamer 1.16 using intervideosink/intervideosrc bridge
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
import queue

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
        self.encode_pipeline = None
        self.send_pipeline = None
        self.loop = None
        self.sei_injected_count = 0
        self.buffer_count = 0
        self.running = True
        self.buffer_queue = queue.Queue(maxsize=100)
        
        # Initialize GStreamer
        Gst.init(None)
    
    def process_buffers_thread(self):
        """Thread to process buffers between pipelines"""
        appsrc = self.send_pipeline.get_by_name('source')
        if not appsrc:
            print("❌ Could not find appsrc")
            return
        
        # Configure appsrc
        appsrc.set_property('format', Gst.Format.TIME)
        appsrc.set_property('is-live', True)
        appsrc.set_property('block', True)
        
        while self.running:
            try:
                # Get buffer from queue (timeout to check running flag)
                buffer_data = self.buffer_queue.get(timeout=0.1)
                
                if buffer_data is None:  # EOS signal
                    print("📍 Sending EOS to output pipeline")
                    appsrc.emit("end-of-stream")
                    break
                
                # Push to appsrc
                new_buffer = Gst.Buffer.new_wrapped(buffer_data['data'])
                new_buffer.pts = buffer_data['pts']
                new_buffer.dts = buffer_data['dts']
                new_buffer.duration = buffer_data['duration']
                
                ret = appsrc.emit("push-buffer", new_buffer)
                if ret != Gst.FlowReturn.OK:
                    print(f"Warning: push-buffer returned {ret}")
                    
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in buffer thread: {e}")
                import traceback
                traceback.print_exc()
                break
        
        print("Buffer thread ended")
    
    def on_new_sample(self, sink):
        """Handle new sample from appsink"""
        sample = sink.emit("pull-sample")
        if not sample:
            return Gst.FlowReturn.OK
            
        buffer = sample.get_buffer()
        self.buffer_count += 1
        
        # Check if keyframe
        flags = buffer.get_flags()
        is_keyframe = (flags & Gst.BufferFlags.DELTA_UNIT) == 0
        
        # Get buffer data
        success, map_info = buffer.map(Gst.MapFlags.READ)
        if not success:
            return Gst.FlowReturn.OK
            
        data = bytes(map_info.data)
        buffer.unmap(map_info)
        
        # Process the buffer
        output_data = data
        
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
                output_data = data[:insert_pos] + sei_nal + data[insert_pos:]
            else:
                output_data = sei_nal + data
            
            self.sei_injected_count += 1
            print(f"💉 Injected SEI #{self.sei_injected_count} at keyframe (buffer #{self.buffer_count})")
            
            if self.sei_injected_count == 1:
                print(f"    SEI size: {len(sei_nal)} bytes")
                print(f"    Total buffer size: {len(output_data)} bytes")
        
        # Queue buffer for sending
        buffer_data = {
            'data': output_data,
            'pts': buffer.pts if buffer.pts != Gst.CLOCK_TIME_NONE else 0,
            'dts': buffer.dts if buffer.dts != Gst.CLOCK_TIME_NONE else 0,
            'duration': buffer.duration if buffer.duration != Gst.CLOCK_TIME_NONE else 0
        }
        
        try:
            self.buffer_queue.put(buffer_data, timeout=1.0)
        except queue.Full:
            print("Warning: Buffer queue full, dropping buffer")
        
        return Gst.FlowReturn.OK
    
    def create_pipelines(self):
        """Create encoding and sending pipelines"""
        if not os.path.exists(self.video_file):
            raise FileNotFoundError(f"Video file not found: {self.video_file}")
        
        # Encoding pipeline with appsink
        encode_str = f"""
            filesrc location={self.video_file} !
            decodebin !
            videoconvert !
            videoscale !
            video/x-raw,width=1280,height=720 !
            x264enc tune=zerolatency bitrate=2000 key-int-max=30 speed-preset=medium bframes=0 !
            video/x-h264,stream-format=byte-stream !
            h264parse config-interval=1 !
            appsink name=sink emit-signals=true max-buffers=10 drop=false
        """
        
        # Sending pipeline with appsrc
        send_str = f"""
            appsrc name=source format=3 is-live=true block=true !
            video/x-h264,stream-format=byte-stream,alignment=au !
            mpegtsmux !
            udpsink host={self.host} port={self.port} sync=false
        """
        
        self.encode_pipeline = Gst.parse_launch(encode_str)
        self.send_pipeline = Gst.parse_launch(send_str)
        
        # Get appsink and connect callback
        appsink = self.encode_pipeline.get_by_name('sink')
        if appsink:
            appsink.connect("new-sample", self.on_new_sample)
            print("✅ Connected to appsink for SEI injection")
        
        # Start buffer processing thread
        self.buffer_thread = threading.Thread(target=self.process_buffers_thread, daemon=True)
        self.buffer_thread.start()
        
        # Set up buses
        bus1 = self.encode_pipeline.get_bus()
        bus1.add_signal_watch()
        bus1.connect("message", self.on_encode_message)
        
        bus2 = self.send_pipeline.get_bus()
        bus2.add_signal_watch()
        bus2.connect("message", self.on_send_message)
    
    def on_encode_message(self, bus, message):
        """Handle encoding pipeline messages"""
        t = message.type
        
        if t == Gst.MessageType.EOS:
            print(f"\n✅ Encoding complete. Total SEI NAL units injected: {self.sei_injected_count}")
            # Signal EOS to buffer thread
            self.buffer_queue.put(None)
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"\n❌ Encode error: {err}, {debug}")
            self.stop()
        elif t == Gst.MessageType.STATE_CHANGED:
            if message.src == self.encode_pipeline:
                old_state, new_state, pending = message.parse_state_changed()
                if new_state == Gst.State.PLAYING:
                    print("▶️  Encoding and injecting SEI metadata...")
    
    def on_send_message(self, bus, message):
        """Handle sending pipeline messages"""
        t = message.type
        
        if t == Gst.MessageType.EOS:
            print("✅ Transmission complete")
            self.stop()
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"\n❌ Send error: {err}, {debug}")
            self.stop()
        elif t == Gst.MessageType.STATE_CHANGED:
            if message.src == self.send_pipeline:
                old_state, new_state, pending = message.parse_state_changed()
                if new_state == Gst.State.PLAYING:
                    print("📡 Transmitting stream...")
    
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
        
        self.create_pipelines()
        
        # Start send pipeline first
        ret = self.send_pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            print("Unable to set send pipeline to playing state")
            sys.exit(1)
        
        # Then start encode pipeline
        ret = self.encode_pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            print("Unable to set encode pipeline to playing state")
            sys.exit(1)
        
        self.loop = GLib.MainLoop()
        try:
            self.loop.run()
        except KeyboardInterrupt:
            print("\n⏹️  Interrupted by user")
            self.stop()
    
    def stop(self):
        """Stop the sender"""
        self.running = False
        
        if self.encode_pipeline:
            self.encode_pipeline.set_state(Gst.State.NULL)
        if self.send_pipeline:
            self.send_pipeline.set_state(Gst.State.NULL)
        
        # Wait for buffer thread
        if hasattr(self, 'buffer_thread'):
            self.buffer_thread.join(timeout=2)
        
        if self.loop:
            self.loop.quit()
        
        print("🛑 Sender stopped")

def main():
    parser = argparse.ArgumentParser(
        description='Send H.264 video with metadata in SEI NAL units',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This sender injects metadata directly into the H.264 bitstream as SEI NAL units.
Works with GStreamer 1.16 using dual pipeline approach.

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