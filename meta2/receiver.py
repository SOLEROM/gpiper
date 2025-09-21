#!/usr/bin/env python3
"""
sei_direct_receiver.py - Receives H.264 with SEI directly (no MPEG-TS)
Extracts SEI metadata from RTP/H.264 stream
"""

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import sys
import json
import argparse
import os

class SEINALExtractor:
    """Helper class for extracting SEI NAL units"""
    
    CUSTOM_UUID = b'METADATA' + b'\x00' * 8
    
    @staticmethod
    def find_and_extract_sei(data):
        """Find and extract all metadata from SEI NAL units in buffer"""
        extracted = []
        i = 0
        
        while i < len(data) - 20:
            # Look for SEI NAL start code
            if data[i:i+5] == b'\x00\x00\x00\x01\x06':
                # Find end of this NAL unit
                end = len(data)
                for j in range(i+5, min(i+500, len(data)-3)):
                    if data[j:j+3] == b'\x00\x00\x01' or data[j:j+4] == b'\x00\x00\x00\x01':
                        end = j
                        break
                
                # Extract SEI data
                sei_data = data[i+5:end]
                
                # Parse SEI payload
                k = 0
                while k < len(sei_data) - 1:
                    # Read payload type
                    payload_type = 0
                    while k < len(sei_data) and sei_data[k] == 0xFF:
                        payload_type += 255
                        k += 1
                    if k < len(sei_data):
                        payload_type += sei_data[k]
                        k += 1
                    
                    # Read payload size
                    payload_size = 0
                    while k < len(sei_data) and sei_data[k] == 0xFF:
                        payload_size += 255
                        k += 1
                    if k < len(sei_data):
                        payload_size += sei_data[k]
                        k += 1
                    
                    # Check for user_data_unregistered (type 5)
                    if payload_type == 5 and k + payload_size <= len(sei_data):
                        payload = sei_data[k:k+payload_size]
                        
                        # Check for our UUID
                        if len(payload) >= 16 and payload[:16] == SEINALExtractor.CUSTOM_UUID:
                            try:
                                json_str = payload[16:].rstrip(b'\x00\x80').decode('utf-8')
                                metadata = json.loads(json_str)
                                extracted.append(metadata)
                            except (UnicodeDecodeError, json.JSONDecodeError):
                                pass
                        
                        k += payload_size
                    else:
                        break
                
                i = end
            else:
                i += 1
        
        return extracted

class DirectSEIReceiver:
    def __init__(self, port, output_file):
        self.port = port
        self.output_file = output_file
        self.pipeline = None
        self.extracted_metadata = {}
        self.sei_count = 0
        self.buffer_count = 0
        
        Gst.init(None)
    
    def on_pad_probe(self, pad, info):
        """Probe to extract SEI NAL units"""
        buffer = info.get_buffer()
        if not buffer:
            return Gst.PadProbeReturn.OK
        
        self.buffer_count += 1
        
        try:
            success, map_info = buffer.map(Gst.MapFlags.READ)
            if not success:
                return Gst.PadProbeReturn.OK
            
            data = bytes(map_info.data)
            buffer.unmap(map_info)
            
            # Debug first buffer
            if self.buffer_count == 1:
                print(f"  First buffer: {len(data)} bytes")
                print(f"  Starts with: {data[:20].hex()}")
                # Check if SEI is at the start
                if data[:5] == b'\x00\x00\x00\x01\x06':
                    print("  ✅ SEI NAL detected at start!")
            
            # Extract SEI metadata
            extracted_list = SEINALExtractor.find_and_extract_sei(data)
            
            for metadata in extracted_list:
                self.sei_count += 1
                self.extracted_metadata = metadata
                
                print(f"\n🔍 SEI METADATA EXTRACTED (#{self.sei_count}):")
                print("   " + "-" * 40)
                for key, value in metadata.items():
                    print(f"   • {key}: {value}")
                print("   " + "-" * 40)
        
        except Exception as e:
            print(f"Error in probe: {e}")
        
        return Gst.PadProbeReturn.OK
    
    def create_pipeline(self):
        """Create pipeline for RTP/H.264 reception"""
        output_dir = os.path.dirname(self.output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # RTP/H.264 receiving pipeline
        pipeline_str = f"""
            udpsrc port={self.port} !
            application/x-rtp,encoding-name=H264,payload=96 !
            rtph264depay !
            h264parse config-interval=-1 !
            tee name=t !
            queue !
            mp4mux !
            filesink location={self.output_file}
            
            t. !
            queue !
            fakesink
        """
        
        self.pipeline = Gst.parse_launch(pipeline_str)
        
        # Add probe after rtph264depay (before h264parse)
        depay = self.pipeline.get_by_name('rtph264depay0')
        if depay:
            src_pad = depay.get_static_pad('src')
            if src_pad:
                src_pad.add_probe(Gst.PadProbeType.BUFFER, self.on_pad_probe)
                print("✅ SEI extraction probe added after RTP depayload")
        
        # Set up bus
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_message)
    
    def on_message(self, bus, message):
        t = message.type
        
        if t == Gst.MessageType.EOS:
            print(f"\n✅ Stream complete. SEI found: {self.sei_count}")
            self.save_metadata()
            self.stop()
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"\n❌ Error: {err}")
            self.stop()
        elif t == Gst.MessageType.STATE_CHANGED:
            if message.src == self.pipeline:
                old_state, new_state, pending = message.parse_state_changed()
                if new_state == Gst.State.PLAYING:
                    print("▶️  Receiving RTP/H.264 stream...")
    
    def save_metadata(self):
        if self.extracted_metadata:
            metadata_file = self.output_file.replace('.mp4', '_metadata.json')
            try:
                with open(metadata_file, 'w') as f:
                    json.dump(self.extracted_metadata, f, indent=2)
                
                print("\n" + "=" * 60)
                print("📋 METADATA EXTRACTION COMPLETE")
                print("=" * 60)
                print(f"📁 Metadata file: {metadata_file}")
                print(f"🔢 SEI NAL units found: {self.sei_count}")
                print(f"📦 Buffers processed: {self.buffer_count}")
                print("📦 Final metadata:")
                for key, value in self.extracted_metadata.items():
                    print(f"   • {key}: {value}")
                print("=" * 60)
            except Exception as e:
                print(f"Error saving metadata: {e}")
        else:
            print(f"\n⚠️  No SEI metadata found in {self.buffer_count} buffers")
    
    def start(self):
        print("=" * 60)
        print("DIRECT H.264 SEI RECEIVER (No MPEG-TS)")
        print("=" * 60)
        print(f"📡 UDP port: {self.port}")
        print(f"💾 Output: {self.output_file}")
        print(f"🔧 Transport: RTP/H.264 (preserves SEI)")
        print("=" * 60)
        print("⏳ Waiting for stream...")
        
        self.create_pipeline()
        
        self.pipeline.set_state(Gst.State.PLAYING)
        
        self.loop = GLib.MainLoop()
        
        # Add timeout
        GLib.timeout_add_seconds(10, self.check_timeout)
        
        try:
            self.loop.run()
        except KeyboardInterrupt:
            print("\n⏹️ Interrupted")
            self.save_metadata()
            self.stop()
        
        print(f"\n📹 Video saved to: {self.output_file}")
    
    def check_timeout(self):
        if self.buffer_count == 0:
            print("\n⏱️ Timeout - no data received")
            self.stop()
            return False
        return True
    
    def stop(self):
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
        if hasattr(self, 'loop') and self.loop:
            self.loop.quit()
        print("🛑 Stopped")

def main():
    parser = argparse.ArgumentParser(description='Direct H.264 SEI receiver')
    parser.add_argument('port', type=int, help='UDP port')
    parser.add_argument('output', help='Output MP4 file')
    
    args = parser.parse_args()
    
    receiver = DirectSEIReceiver(args.port, args.output)
    receiver.start()

if __name__ == '__main__':
    main()