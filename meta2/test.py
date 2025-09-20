#!/usr/bin/env python3
"""
sei_working_test.py - Working SEI injection test for GStreamer 1.16
Uses appsink/appsrc approach to modify buffers
"""

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstApp', '1.0')
from gi.repository import Gst, GstApp, GLib
import json
import tempfile
import os
import threading

class SEIInjector:
    """SEI NAL injection helper"""
    
    CUSTOM_UUID = b'METADATA' + b'\x00' * 8
    
    @staticmethod
    def create_sei_nal(metadata_dict):
        """Create SEI NAL unit with metadata"""
        json_bytes = json.dumps(metadata_dict).encode('utf-8')
        payload_size = 16 + len(json_bytes)
        
        sei_payload = bytearray()
        sei_payload.append(0x05)  # user_data_unregistered
        
        # Add size
        if payload_size < 255:
            sei_payload.append(payload_size)
        else:
            size_remaining = payload_size
            while size_remaining >= 255:
                sei_payload.append(0xFF)
                size_remaining -= 255
            sei_payload.append(size_remaining)
        
        # Add UUID and data
        sei_payload.extend(SEIInjector.CUSTOM_UUID)
        sei_payload.extend(json_bytes)
        sei_payload.append(0x80)  # RBSP stop bit
        
        # Complete SEI NAL
        return b'\x00\x00\x00\x01\x06' + bytes(sei_payload)
    
    @staticmethod
    def find_and_extract_sei(data):
        """Find and extract metadata from SEI in data"""
        i = 0
        while i < len(data) - 20:
            # Look for SEI NAL
            if data[i:i+5] == b'\x00\x00\x00\x01\x06':
                # Find end
                end = len(data)
                for j in range(i+5, min(i+500, len(data)-3)):
                    if data[j:j+3] == b'\x00\x00\x01' or data[j:j+4] == b'\x00\x00\x00\x01':
                        end = j
                        break
                
                sei_data = data[i+5:end]
                
                # Parse SEI
                k = 0
                while k < len(sei_data) - 1:
                    # Payload type
                    payload_type = 0
                    while k < len(sei_data) and sei_data[k] == 0xFF:
                        payload_type += 255
                        k += 1
                    if k < len(sei_data):
                        payload_type += sei_data[k]
                        k += 1
                    
                    # Payload size
                    payload_size = 0
                    while k < len(sei_data) and sei_data[k] == 0xFF:
                        payload_size += 255
                        k += 1
                    if k < len(sei_data):
                        payload_size += sei_data[k]
                        k += 1
                    
                    # Check for our UUID
                    if payload_type == 5 and k + payload_size <= len(sei_data):
                        payload = sei_data[k:k+payload_size]
                        if len(payload) >= 16 and payload[:16] == SEIInjector.CUSTOM_UUID:
                            try:
                                json_str = payload[16:].rstrip(b'\x00\x80').decode('utf-8')
                                return json.loads(json_str)
                            except:
                                pass
                        k += payload_size
                    else:
                        break
                
                i = end
            else:
                i += 1
        return None

def test_with_appsink_appsrc():
    """Test using appsink/appsrc for buffer modification"""
    
    Gst.init(None)
    
    print("=" * 70)
    print("SEI INJECTION TEST WITH APPSINK/APPSRC")
    print("=" * 70)
    
    metadata = {"user": "john", "timestamp": "2024-01-01", "session_id": "12345"}
    
    with tempfile.NamedTemporaryFile(suffix='.h264', delete=False) as tmp:
        output_file = tmp.name
    
    print(f"Metadata: {metadata}")
    print(f"Output: {output_file}")
    print("-" * 70)
    
    # Statistics
    stats = {
        'keyframes': 0,
        'sei_injected': 0,
        'buffers': 0
    }
    
    # Create pipelines
    # Pipeline 1: Generate H.264 and send to appsink
    gen_pipeline = Gst.parse_launch("""
        videotestsrc num-buffers=100 !
        video/x-raw,width=320,height=240,framerate=30/1 !
        x264enc key-int-max=20 tune=zerolatency speed-preset=ultrafast bframes=0 !
        h264parse !
        appsink name=sink emit-signals=true
    """)
    
    # Pipeline 2: Receive from appsrc and save
    save_pipeline = Gst.parse_launch(f"""
        appsrc name=src !
        video/x-h264,stream-format=byte-stream !
        filesink location={output_file}
    """)
    
    appsink = gen_pipeline.get_by_name('sink')
    appsrc = save_pipeline.get_by_name('src')
    
    def on_new_sample(sink):
        """Handle new sample from appsink"""
        sample = sink.emit("pull-sample")
        if sample:
            buffer = sample.get_buffer()
            stats['buffers'] += 1
            
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
                    stats['keyframes'] += 1
                    
                    # Create SEI NAL
                    sei_nal = SEIInjector.create_sei_nal(metadata)
                    
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
                        new_data = data[:insert_pos] + sei_nal + data[insert_pos:]
                    else:
                        new_data = sei_nal + data
                    
                    # Create new buffer
                    new_buffer = Gst.Buffer.new_wrapped(new_data)
                    new_buffer.pts = buffer.pts
                    new_buffer.dts = buffer.dts
                    new_buffer.duration = buffer.duration
                    
                    # Push modified buffer
                    appsrc.emit("push-buffer", new_buffer)
                    
                    stats['sei_injected'] += 1
                    print(f"✅ Injected SEI #{stats['sei_injected']} (buffer #{stats['buffers']})")
                else:
                    # Push original buffer
                    appsrc.emit("push-buffer", buffer)
            
        return Gst.FlowReturn.OK
    
    # Connect callback
    appsink.connect("new-sample", on_new_sample)
    
    # Start pipelines
    print("\nPhase 1: Injecting SEI...")
    print("-" * 70)
    
    save_pipeline.set_state(Gst.State.PLAYING)
    gen_pipeline.set_state(Gst.State.PLAYING)
    
    # Wait for completion
    bus = gen_pipeline.get_bus()
    msg = bus.timed_pop_filtered(10 * Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
    
    # Send EOS to appsrc
    appsrc.emit("end-of-stream")
    
    # Wait for save pipeline
    bus2 = save_pipeline.get_bus()
    msg2 = bus2.timed_pop_filtered(5 * Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
    
    # Cleanup
    gen_pipeline.set_state(Gst.State.NULL)
    save_pipeline.set_state(Gst.State.NULL)
    
    print(f"\nResults:")
    print(f"  • Buffers: {stats['buffers']}")
    print(f"  • Keyframes: {stats['keyframes']}")
    print(f"  • SEI injected: {stats['sei_injected']}")
    
    # Phase 2: Verify SEI in file
    print("\n" + "=" * 70)
    print("Phase 2: Verifying SEI in file...")
    print("-" * 70)
    
    with open(output_file, 'rb') as f:
        file_data = f.read()
    
    print(f"File size: {len(file_data):,} bytes")
    
    # Find SEI NAL units
    sei_count = 0
    extracted_count = 0
    i = 0
    
    while i < len(file_data) - 5:
        if file_data[i:i+5] == b'\x00\x00\x00\x01\x06':
            sei_count += 1
            print(f"\nFound SEI NAL #{sei_count} at offset {i}")
            
            # Try to extract metadata
            extracted = SEIInjector.find_and_extract_sei(file_data[i:i+500])
            if extracted:
                extracted_count += 1
                print(f"  ✅ Extracted metadata: {extracted}")
                if extracted == metadata:
                    print(f"  ✅ MATCHES ORIGINAL!")
            
            i += 5
        else:
            i += 1
    
    print(f"\nFile analysis:")
    print(f"  • SEI NAL units found: {sei_count}")
    print(f"  • Metadata extracted: {extracted_count}")
    
    # Cleanup
    os.unlink(output_file)
    
    # Final result
    print("\n" + "=" * 70)
    print("TEST RESULT")
    print("=" * 70)
    
    if stats['sei_injected'] > 0 and extracted_count > 0:
        print("✅ SUCCESS! SEI injection and extraction working!")
        return True
    else:
        print("❌ FAILURE! SEI not working properly")
        return False

def test_simple_approach():
    """Even simpler test - just create and verify SEI NAL"""
    
    print("\n" + "=" * 70)
    print("SIMPLE SEI NAL UNIT TEST")
    print("=" * 70)
    
    metadata = {"test": "data", "number": 123}
    
    # Create SEI NAL
    sei_nal = SEIInjector.create_sei_nal(metadata)
    
    print(f"Created SEI NAL unit:")
    print(f"  • Size: {len(sei_nal)} bytes")
    print(f"  • First 20 bytes: {sei_nal[:20].hex()}")
    print(f"  • Should start with: 0000000106 (start code + SEI NAL type)")
    
    # Test extraction
    extracted = SEIInjector.find_and_extract_sei(sei_nal)
    
    print(f"\nExtraction test:")
    print(f"  • Extracted: {extracted}")
    print(f"  • Original: {metadata}")
    print(f"  • Match: {extracted == metadata}")
    
    return extracted == metadata

if __name__ == "__main__":
    print("SEI NAL INJECTION TEST FOR GSTREAMER 1.16")
    print()
    
    # Test 1: Simple SEI creation/extraction
    if test_simple_approach():
        print("\n✅ Basic SEI NAL creation/extraction works!")
        
        # Test 2: Full pipeline test
        if test_with_appsink_appsrc():
            print("\n✅ Full pipeline SEI injection works!")
        else:
            print("\n❌ Pipeline injection failed")
    else:
        print("\n❌ Basic SEI test failed")