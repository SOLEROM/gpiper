#!/usr/bin/env python3
"""
sei_receiver.py - Extracts metadata from SEI NAL units in H.264 stream
Works with GStreamer 1.16
Usage: python sei_receiver.py 5000 output.mp4
"""

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import sys
import json
import argparse
import os

class SEINALExtractor:
    """Helper class for extracting SEI NAL units from H.264 stream"""
    
    # Custom UUID to look for (must match sender)
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
                
                # Extract SEI data (skip start code and NAL header)
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

class SEIVideoReceiver:
    def __init__(self, port, output_file):
        self.port = port
        self.output_file = output_file
        self.pipeline = None
        self.loop = None
        self.extracted_metadata = {}
        self.sei_count = 0
        self.buffer_count = 0
        self.unique_metadata_sets = set()
        
        # Initialize GStreamer
        Gst.init(None)
    
    def on_pad_probe(self, pad, info):
        """Probe to extract SEI NAL units from H.264 stream"""
        buffer = info.get_buffer()
        if not buffer:
            return Gst.PadProbeReturn.OK
        
        self.buffer_count += 1
        
        try:
            # Get buffer data
            success, map_info = buffer.map(Gst.MapFlags.READ)
            if not success:
                return Gst.PadProbeReturn.OK
            
            data = bytes(map_info.data)
            buffer.unmap(map_info)
            
            # Debug first buffer
            if self.buffer_count == 1:
                print(f"  First buffer received, size: {len(data)} bytes")
                if len(data) > 20:
                    print(f"  First 20 bytes: {data[:20].hex()}")
            
            # Look for and extract SEI metadata
            extracted_list = SEINALExtractor.find_and_extract_sei(data)
            
            for metadata in extracted_list:
                self.sei_count += 1
                
                # Convert to string for set comparison
                metadata_str = json.dumps(metadata, sort_keys=True)
                
                if metadata_str not in self.unique_metadata_sets:
                    self.unique_metadata_sets.add(metadata_str)
                    self.extracted_metadata = metadata
                    
                    print(f"\n🔍 SEI METADATA EXTRACTED (occurrence #{self.sei_count}):")
                    print("   " + "-" * 40)
                    for key, value in metadata.items():
                        print(f"   • {key}: {value}")
                    print("   " + "-" * 40)
            
        except Exception as e:
            print(f"Error in probe: {e}")
            import traceback
            traceback.print_exc()
        
        return Gst.PadProbeReturn.OK
    
    def create_pipeline(self):
        """Create pipeline with SEI extraction probe"""
        # Ensure output directory exists
        output_dir = os.path.dirname(self.output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Build pipeline
        pipeline_str = f"""
            udpsrc port={self.port} timeout=5000000000 !
            video/mpegts !
            tsdemux !
            h264parse config-interval=-1 !
            tee name=t !
            queue !
            mp4mux !
            filesink location={self.output_file}
            
            t. !
            queue !
            fakesink
        """
        
        try:
            self.pipeline = Gst.parse_launch(pipeline_str)
        except GLib.GError as e:
            print(f"Error creating pipeline: {e}")
            sys.exit(1)
        
        # Add probe to h264parse src pad to extract SEI
        h264parse = self.pipeline.get_by_name('h264parse0')
        if h264parse:
            src_pad = h264parse.get_static_pad('src')
            if src_pad:
                src_pad.add_probe(
                    Gst.PadProbeType.BUFFER,
                    self.on_pad_probe
                )
                print("✅ SEI extraction probe added to h264parse output")
        
        # Set up bus
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_message)
    
    def on_message(self, bus, message):
        """Handle pipeline messages"""
        t = message.type
        
        if t == Gst.MessageType.EOS:
            print(f"\n✅ Stream complete. SEI NAL units found: {self.sei_count}")
            self.save_metadata()
            self.stop()
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"\n❌ Error: {err}, {debug}")
            self.stop()
        elif t == Gst.MessageType.STATE_CHANGED:
            if message.src == self.pipeline:
                old_state, new_state, pending = message.parse_state_changed()
                if new_state == Gst.State.PLAYING:
                    print("▶️  Receiving and extracting SEI metadata...")
        elif t == Gst.MessageType.ELEMENT:
            structure = message.get_structure()
            if structure and structure.get_name() == "GstUDPSrcTimeout":
                print(f"\n⏱️  Stream timeout. SEI NAL units found: {self.sei_count}")
                print(f"     Total buffers processed: {self.buffer_count}")
                self.save_metadata()
                self.stop()
    
    def save_metadata(self):
        """Save extracted metadata to JSON file"""
        if self.extracted_metadata:
            metadata_file = self.output_file.replace('.mp4', '_metadata.json')
            try:
                with open(metadata_file, 'w') as f:
                    json.dump(self.extracted_metadata, f, indent=2)
                
                print("\n" + "=" * 60)
                print("📋 SEI METADATA EXTRACTION COMPLETE")
                print("=" * 60)
                print(f"📁 Metadata file: {metadata_file}")
                print(f"🔢 Total SEI NAL units processed: {self.sei_count}")
                print(f"📦 Total buffers processed: {self.buffer_count}")
                print(f"🎯 Unique metadata sets found: {len(self.unique_metadata_sets)}")
                print("📦 Final metadata content:")
                for key, value in self.extracted_metadata.items():
                    print(f"   • {key}: {value}")
                print("=" * 60)
            except Exception as e:
                print(f"Error saving metadata: {e}")
        else:
            print(f"\n⚠️  No SEI metadata found in {self.buffer_count} buffers")
    
    def start(self):
        """Start the receiver"""
        print("=" * 60)
        print("H.264 SEI NAL METADATA EXTRACTOR (GStreamer 1.16)")
        print("=" * 60)
        print(f"📡 UDP port: {self.port}")
        print(f"💾 Output file: {self.output_file}")
        print(f"🔍 Looking for SEI UUID: {SEINALExtractor.CUSTOM_UUID[:8].hex()}...")
        print("=" * 60)
        print("⏳ Waiting for stream with SEI metadata...")
        
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
            self.save_metadata()
            self.stop()
        
        print(f"\n📹 Video saved to: {self.output_file}")
    
    def stop(self):
        """Stop the receiver"""
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
        if self.loop:
            self.loop.quit()
        print("🛑 Receiver stopped")

def main():
    parser = argparse.ArgumentParser(
        description='Receive H.264 video and extract metadata from SEI NAL units',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This receiver extracts metadata that was injected into the H.264 bitstream
as SEI (Supplemental Enhancement Information) NAL units.
Works with GStreamer 1.16.

Example:
  python sei_receiver.py 5000 output.mp4
        """
    )
    
    parser.add_argument('port', type=int, help='UDP port to receive on')
    parser.add_argument('output', help='Output MP4 file path')
    
    args = parser.parse_args()
    
    # Create and start receiver
    receiver = SEIVideoReceiver(args.port, args.output)
    receiver.start()

if __name__ == '__main__':
    main()