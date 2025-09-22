#!/usr/bin/env python3
"""
rtp_sei_receiver.py - Receives H.264 video with SEI metadata over RTP/UDP
Single port, extracts SEI NAL units
Usage: python rtp_sei_receiver.py 5000 output.mp4
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
    
    CUSTOM_UUID = b'METADATA' + b'\x00' * 8
    
    @staticmethod
    def find_and_extract_sei(data):
        """Find and extract metadata from SEI NAL units (handles both start-code and length-prefixed formats)"""
        extracted = []
        i = 0
        
        # Check if this is length-prefixed format (first 4 bytes are length)
        if len(data) > 4:
            # Try to interpret first 4 bytes as length
            first_nal_length = int.from_bytes(data[0:4], 'big')
            
            # If length seems reasonable, assume length-prefixed format
            if 0 < first_nal_length < len(data):
                # Parse length-prefixed NAL units
                while i < len(data) - 4:
                    nal_length = int.from_bytes(data[i:i+4], 'big')
                    if nal_length <= 0 or i + 4 + nal_length > len(data):
                        break
                    
                    nal_data = data[i+4:i+4+nal_length]
                    if nal_data:
                        nal_type = nal_data[0] & 0x1F
                        
                        # Check if it's SEI (type 6)
                        if nal_type == 6:
                            # Parse SEI payload (skip NAL header)
                            sei_data = nal_data[1:]
                            
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
                                        except (UnicodeDecodeError, json.JSONDecodeError) as e:
                                            pass
                                    
                                    k += payload_size
                                else:
                                    break
                    
                    i += 4 + nal_length
                
                return extracted
        
        # Fallback to start-code format parsing
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

class RTPSEIReceiver:
    def __init__(self, port, output_file):
        self.port = port
        self.output_file = output_file
        self.pipeline = None
        self.extracted_metadata = {}
        self.sei_count = 0
        self.buffer_count = 0
        self.unique_metadata = set()
        
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
            
            # Debug first few buffers
            if self.buffer_count <= 3:
                print(f"  Buffer #{self.buffer_count}: {len(data)} bytes")
                if len(data) > 40:
                    print(f"    First 40 bytes: {data[:40].hex()}")
                    
                    # Check format
                    if len(data) > 4:
                        possible_length = int.from_bytes(data[0:4], 'big')
                        if 0 < possible_length < len(data):
                            print(f"    Format: Length-prefixed (first NAL length = {possible_length})")
                            # Check first NAL type
                            if len(data) > 4:
                                first_nal_type = data[4] & 0x1F
                                print(f"    First NAL type: {first_nal_type} (6=SEI, 5=IDR, 9=AUD)")
                                
                                if first_nal_type == 6:
                                    print("    ✅ First NAL is SEI!")
                                    # Show SEI payload
                                    print(f"    SEI payload starts: {data[5:25].hex()}")
                        else:
                            print(f"    Format: Start-code delimited")
                            # Look for NAL units
                            for j in range(min(20, len(data) - 5)):
                                if data[j:j+4] == b'\x00\x00\x00\x01':
                                    nal_type = data[j+4] & 0x1F
                                    print(f"    NAL at offset {j}: type {nal_type}")
                                    break
            
            # Extract SEI metadata
            extracted_list = SEINALExtractor.find_and_extract_sei(data)
            
            for metadata in extracted_list:
                self.sei_count += 1
                metadata_str = json.dumps(metadata, sort_keys=True)
                
                if metadata_str not in self.unique_metadata:
                    self.unique_metadata.add(metadata_str)
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
        """Create pipeline to receive RTP/H.264 and extract SEI"""
        # Ensure output directory exists
        output_dir = os.path.dirname(self.output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # RTP/H.264 receiving pipeline
        pipeline_str = f"""
            udpsrc port={self.port} caps="application/x-rtp,media=video,encoding-name=H264,payload=96" !
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
        
        try:
            self.pipeline = Gst.parse_launch(pipeline_str)
        except GLib.GError as e:
            print(f"Error creating pipeline: {e}")
            sys.exit(1)
        
        # Add probe after RTP depayloader to see raw H.264
        rtpdepay = self.pipeline.get_by_name('rtph264depay0')
        if rtpdepay:
            src_pad = rtpdepay.get_static_pad('src')
            if src_pad:
                src_pad.add_probe(
                    Gst.PadProbeType.BUFFER,
                    self.on_pad_probe
                )
                print("✅ SEI extraction probe added after RTP depayload")
        
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
                    print("▶️  Receiving RTP/H.264 stream...")
    
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
                print(f"🔢 Total SEI NAL units found: {self.sei_count}")
                print(f"📦 Total buffers processed: {self.buffer_count}")
                print(f"🎯 Unique metadata sets: {len(self.unique_metadata)}")
                print("📦 Final metadata content:")
                for key, value in self.extracted_metadata.items():
                    print(f"   • {key}: {value}")
                print("=" * 60)
            except Exception as e:
                print(f"Error saving metadata: {e}")
        else:
            print(f"\n⚠️  No SEI metadata found in {self.buffer_count} buffers")
            print("   This could mean:")
            print("   1. No SEI was injected by sender")
            print("   2. SEI was stripped somewhere in the pipeline")
            print("   3. Different UUID was used")
    
    def start(self):
        """Start the receiver"""
        print("=" * 60)
        print("RTP/H.264 SEI RECEIVER (Single Port)")
        print("=" * 60)
        print(f"📡 UDP port: {self.port}")
        print(f"💾 Output file: {self.output_file}")
        print(f"🔧 Protocol: RTP/H.264 over UDP (preserves SEI)")
        print(f"🔍 Looking for UUID: {SEINALExtractor.CUSTOM_UUID[:8].hex()}...")
        print("=" * 60)
        print("⏳ Waiting for RTP stream...")
        
        self.create_pipeline()
        
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            print("Unable to set pipeline to playing state")
            sys.exit(1)
        
        self.loop = GLib.MainLoop()
        
        # Add timeout for no data
        self.timeout_id = GLib.timeout_add_seconds(10, self.check_timeout)
        
        try:
            self.loop.run()
        except KeyboardInterrupt:
            print("\n⏹️  Interrupted by user")
            self.save_metadata()
            self.stop()
        
        print(f"\n📹 Video saved to: {self.output_file}")
    
    def check_timeout(self):
        """Check if we're receiving data"""
        if self.buffer_count == 0:
            print("\n⏱️  Timeout - no data received")
            print("   Check that:")
            print("   1. Sender is running")
            print("   2. Correct IP and port")
            print("   3. No firewall blocking UDP")
            self.stop()
            return False
        elif self.sei_count == 0 and self.buffer_count > 50:
            print("\n⚠️  Receiving data but no SEI found yet...")
        return True  # Continue checking
    
    def stop(self):
        """Stop the receiver"""
        if hasattr(self, 'timeout_id'):
            GLib.source_remove(self.timeout_id)
        
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
        
        if hasattr(self, 'loop') and self.loop:
            self.loop.quit()
        
        print("🛑 Receiver stopped")

def main():
    parser = argparse.ArgumentParser(
        description='RTP/H.264 receiver with SEI metadata extraction',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Single-port metadata reception using SEI NAL units in RTP/H.264 stream.
The metadata is extracted directly from the H.264 bitstream preserved by RTP.

Example:
  python rtp_sei_receiver.py 5000 output.mp4
        """
    )
    
    parser.add_argument('port', type=int, help='UDP port to receive on')
    parser.add_argument('output', help='Output MP4 file path')
    
    args = parser.parse_args()
    
    # Validate port
    if args.port < 1024 or args.port > 65535:
        print("Error: Port must be between 1024 and 65535")
        sys.exit(1)
    
    receiver = RTPSEIReceiver(args.port, args.output)
    receiver.start()

if __name__ == '__main__':
    main()