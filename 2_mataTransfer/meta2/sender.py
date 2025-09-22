#!/usr/bin/env python3
"""
sei_direct_sender.py - Sends H.264 with SEI directly over UDP (no MPEG-TS)
This avoids MPEG-TS stripping the SEI NAL units
"""

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstApp', '1.0')
from gi.repository import Gst, GstApp, GLib
import sys
import json
import argparse
import os

class SEINALInjector:
    """Helper class for creating SEI NAL units"""
    
    CUSTOM_UUID = b'METADATA' + b'\x00' * 8
    
    @staticmethod
    def create_sei_nal_unit(metadata_json):
        """Create a SEI NAL unit with user_data_unregistered payload"""
        json_bytes = metadata_json.encode('utf-8')
        payload_size = 16 + len(json_bytes)
        
        sei_payload = bytearray()
        sei_payload.append(0x05)  # user_data_unregistered
        
        if payload_size < 255:
            sei_payload.append(payload_size)
        else:
            size_remaining = payload_size
            while size_remaining >= 255:
                sei_payload.append(0xFF)
                size_remaining -= 255
            sei_payload.append(size_remaining)
        
        sei_payload.extend(SEINALInjector.CUSTOM_UUID)
        sei_payload.extend(json_bytes)
        sei_payload.append(0x80)  # RBSP stop bit
        
        return b'\x00\x00\x00\x01\x06' + bytes(sei_payload)

class DirectSEISender:
    def __init__(self, host, port, metadata, video_file):
        self.host = host
        self.port = port
        self.metadata = metadata
        self.video_file = video_file
        self.pipeline = None
        self.send_pipeline = None
        self.sei_injected_count = 0
        self.buffer_count = 0
        
        Gst.init(None)
    
    def on_new_sample(self, sink):
        """Handle new sample from appsink"""
        sample = sink.emit("pull-sample")
        if not sample:
            return Gst.FlowReturn.OK
            
        buffer = sample.get_buffer()
        self.buffer_count += 1
        
        # Get appsrc in send pipeline
        appsrc = self.send_pipeline.get_by_name('src')
        if not appsrc:
            return Gst.FlowReturn.ERROR
        
        # Check if keyframe
        flags = buffer.get_flags()
        is_keyframe = (flags & Gst.BufferFlags.DELTA_UNIT) == 0
        
        # Get buffer data
        success, map_info = buffer.map(Gst.MapFlags.READ)
        if not success:
            return Gst.FlowReturn.OK
            
        data = bytes(map_info.data)
        buffer.unmap(map_info)
        
        # Process buffer
        output_data = data
        
        if is_keyframe:
            # Create SEI NAL
            metadata_json = json.dumps(self.metadata)
            sei_nal = SEINALInjector.create_sei_nal_unit(metadata_json)
            
            # Find insertion point
            insert_pos = 0
            if len(data) > 5 and data[:5] == b'\x00\x00\x00\x01\x09':
                # After AUD
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
                print(f"    Output starts with: {output_data[:20].hex()}")
        
        # Create new buffer with modified data
        new_buffer = Gst.Buffer.new_wrapped(output_data)
        new_buffer.pts = buffer.pts
        new_buffer.dts = buffer.dts
        new_buffer.duration = buffer.duration
        
        # Push to appsrc
        ret = appsrc.emit("push-buffer", new_buffer)
        
        return Gst.FlowReturn.OK
    
    def create_pipelines(self):
        """Create encode and send pipelines"""
        if not os.path.exists(self.video_file):
            raise FileNotFoundError(f"Video file not found: {self.video_file}")
        
        # Encoding pipeline
        encode_str = f"""
            filesrc location={self.video_file} !
            decodebin !
            videoconvert !
            videoscale !
            video/x-raw,width=1280,height=720 !
            x264enc tune=zerolatency bitrate=2000 key-int-max=30 speed-preset=medium bframes=0 !
            video/x-h264,stream-format=byte-stream !
            h264parse config-interval=1 !
            appsink name=sink emit-signals=true
        """
        
        # Direct UDP sending pipeline (no MPEG-TS!)
        send_str = f"""
            appsrc name=src !
            video/x-h264,stream-format=byte-stream,alignment=au !
            rtph264pay config-interval=1 pt=96 !
            udpsink host={self.host} port={self.port}
        """
        
        self.pipeline = Gst.parse_launch(encode_str)
        self.send_pipeline = Gst.parse_launch(send_str)
        
        # Connect appsink
        appsink = self.pipeline.get_by_name('sink')
        appsink.connect("new-sample", self.on_new_sample)
        print("✅ Connected pipelines for direct H.264 transmission")
        
        # Set up buses
        bus1 = self.pipeline.get_bus()
        bus1.add_signal_watch()
        bus1.connect("message", self.on_encode_message)
        
        bus2 = self.send_pipeline.get_bus()
        bus2.add_signal_watch()
        bus2.connect("message", self.on_send_message)
    
    def on_encode_message(self, bus, message):
        t = message.type
        if t == Gst.MessageType.EOS:
            print(f"✅ Encoding complete. SEI injected: {self.sei_injected_count}")
            appsrc = self.send_pipeline.get_by_name('src')
            if appsrc:
                appsrc.emit("end-of-stream")
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"❌ Encode error: {err}")
            self.stop()
    
    def on_send_message(self, bus, message):
        t = message.type
        if t == Gst.MessageType.EOS:
            print("✅ Transmission complete")
            self.stop()
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"❌ Send error: {err}")
            self.stop()
    
    def start(self):
        print("=" * 60)
        print("DIRECT H.264 SEI SENDER (No MPEG-TS)")
        print("=" * 60)
        print(f"📹 Source: {self.video_file}")
        print(f"🌐 Destination: {self.host}:{self.port}")
        print(f"📦 Metadata: {self.metadata}")
        print(f"🔧 Transport: RTP/H.264 (preserves SEI)")
        print("=" * 60)
        
        self.create_pipelines()
        
        # Start both pipelines
        self.send_pipeline.set_state(Gst.State.PLAYING)
        self.pipeline.set_state(Gst.State.PLAYING)
        
        self.loop = GLib.MainLoop()
        try:
            self.loop.run()
        except KeyboardInterrupt:
            print("\n⏹️ Interrupted")
            self.stop()
    
    def stop(self):
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
        if self.send_pipeline:
            self.send_pipeline.set_state(Gst.State.NULL)
        if hasattr(self, 'loop') and self.loop:
            self.loop.quit()
        print("🛑 Stopped")

def main():
    parser = argparse.ArgumentParser(description='Direct H.264 SEI sender')
    parser.add_argument('host', help='Destination IP')
    parser.add_argument('port', type=int, help='UDP port')
    parser.add_argument('metadata', help='JSON metadata')
    parser.add_argument('--video', required=True, help='Input video file')
    
    args = parser.parse_args()
    
    try:
        metadata = json.loads(args.metadata)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}")
        sys.exit(1)
    
    sender = DirectSEISender(args.host, args.port, metadata, args.video)
    sender.start()

if __name__ == '__main__':
    main()