
#!/usr/bin/env python3
"""
rtp_sei_sender.py - Sends H.264 video with SEI metadata over RTP/UDP
Single port, preserves SEI NAL units
Usage: python rtp_sei_sender.py 127.0.0.1 5000 '{"user":"john"}' --video test.avi
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

class RTPSEISender:
    def __init__(self, host, port, metadata, video_file):
        self.host = host
        self.port = port
        self.metadata = metadata
        self.video_file = video_file
        self.encode_pipeline = None
        self.send_pipeline = None
        self.sei_injected_count = 0
        self.buffer_count = 0
        
        Gst.init(None)
    
    def on_new_sample(self, sink):
        """Handle new sample from appsink and inject SEI"""
        sample = sink.emit("pull-sample")
        if not sample:
            return Gst.FlowReturn.OK
        
        buffer = sample.get_buffer()
        self.buffer_count += 1
        
        # Get appsrc
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
        
        if is_keyframe and self.sei_injected_count < 10:  # Inject SEI at first 10 keyframes
            # Create SEI NAL
            metadata_json = json.dumps(self.metadata)
            sei_nal = SEINALInjector.create_sei_nal_unit(metadata_json)
            
            # Find insertion point (after AUD if present, otherwise at start)
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
                print(f"    First 40 bytes of output: {output_data[:40].hex()}")
        
        # Create new buffer and push to appsrc
        new_buffer = Gst.Buffer.new_wrapped(output_data)
        new_buffer.pts = buffer.pts
        new_buffer.dts = buffer.dts
        new_buffer.duration = buffer.duration
        
        ret = appsrc.emit("push-buffer", new_buffer)
        if ret != Gst.FlowReturn.OK:
            print(f"Warning: push-buffer returned {ret}")
        
        return Gst.FlowReturn.OK
    
    def create_pipelines(self):
        """Create separate encode and send pipelines connected via appsink/appsrc"""
        if not os.path.exists(self.video_file):
            raise FileNotFoundError(f"Video file not found: {self.video_file}")
        
        # Encoding pipeline - outputs to appsink
        encode_str = f"""
            filesrc location={self.video_file} !
            decodebin !
            videoconvert !
            videoscale !
            video/x-raw,width=1280,height=720,framerate=30/1 !
            x264enc tune=zerolatency bitrate=2000 key-int-max=30 speed-preset=medium bframes=0 !
            video/x-h264,stream-format=byte-stream !
            h264parse config-interval=1 !
            appsink name=sink emit-signals=true sync=false
        """
        
        # RTP sending pipeline - receives from appsrc
        send_str = f"""
            appsrc name=src format=3 is-live=true !
            video/x-h264,stream-format=byte-stream,alignment=au !
            rtph264pay config-interval=1 mtu=1400 pt=96 !
            application/x-rtp,media=video,encoding-name=H264,payload=96 !
            udpsink host={self.host} port={self.port} sync=false
        """
        
        self.encode_pipeline = Gst.parse_launch(encode_str)
        self.send_pipeline = Gst.parse_launch(send_str)
        
        # Connect appsink callback
        appsink = self.encode_pipeline.get_by_name('sink')
        if appsink:
            appsink.connect("new-sample", self.on_new_sample)
            print("✅ Connected appsink for SEI injection")
        
        # Configure appsrc
        appsrc = self.send_pipeline.get_by_name('src')
        if appsrc:
            appsrc.set_property('format', Gst.Format.TIME)
            appsrc.set_property('is-live', True)
        
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
            print(f"\n✅ Encoding complete. SEI injected: {self.sei_injected_count}")
            # Send EOS to appsrc
            appsrc = self.send_pipeline.get_by_name('src')
            if appsrc:
                appsrc.emit("end-of-stream")
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"\n❌ Encode error: {err}")
            self.stop()
        elif t == Gst.MessageType.STATE_CHANGED:
            if message.src == self.encode_pipeline:
                old_state, new_state, pending = message.parse_state_changed()
                if new_state == Gst.State.PLAYING:
                    print("▶️  Encoding started...")
    
    def on_send_message(self, bus, message):
        """Handle sending pipeline messages"""
        t = message.type
        
        if t == Gst.MessageType.EOS:
            print("✅ Transmission complete")
            self.stop()
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"\n❌ Send error: {err}")
            self.stop()
        elif t == Gst.MessageType.STATE_CHANGED:
            if message.src == self.send_pipeline:
                old_state, new_state, pending = message.parse_state_changed()
                if new_state == Gst.State.PLAYING:
                    print("📡 RTP transmission started...")
    
    def start(self):
        """Start the sender"""
        print("=" * 60)
        print("RTP/H.264 SEI SENDER (Single Port)")
        print("=" * 60)
        print(f"📹 Source: {self.video_file}")
        print(f"🌐 Destination: {self.host}:{self.port}")
        print(f"📦 Metadata to inject:")
        for key, value in self.metadata.items():
            print(f"   • {key}: {value}")
        print(f"🔧 Protocol: RTP/H.264 over UDP (preserves SEI)")
        print("=" * 60)
        
        self.create_pipelines()
        
        # Start send pipeline first, then encode pipeline
        ret = self.send_pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            print("Unable to set send pipeline to playing state")
            sys.exit(1)
        
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
        if self.encode_pipeline:
            self.encode_pipeline.set_state(Gst.State.NULL)
        if self.send_pipeline:
            self.send_pipeline.set_state(Gst.State.NULL)
        if hasattr(self, 'loop') and self.loop:
            self.loop.quit()
        print("🛑 Sender stopped")

def main():
    parser = argparse.ArgumentParser(
        description='RTP/H.264 sender with SEI metadata preservation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Single-port metadata transmission using SEI NAL units in RTP/H.264 stream.
The metadata is embedded directly in the H.264 bitstream and preserved by RTP.

Example:
  python rtp_sei_sender.py 127.0.0.1 5000 '{"user":"john","session":"123"}' --video test.avi
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
    
    sender = RTPSEISender(args.host, args.port, metadata, args.video)
    sender.start()

if __name__ == '__main__':
    main()