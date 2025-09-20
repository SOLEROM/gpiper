#!/usr/bin/env python3
"""
GStreamer receiver with custom metadata extraction
Receives H.264 stream over UDP and saves as MP4 with metadata
"""

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import sys
import argparse
import json
import os

class VideoReceiver:
    def __init__(self, port, output_file):
        self.port = port
        self.output_file = output_file
        self.pipeline = None
        self.loop = None
        self.extracted_metadata = {}
        self.timeout_id = None
        self.last_buffer_time = None
        
        # Initialize GStreamer
        Gst.init(None)
        
    def create_pipeline(self):
        """Create GStreamer pipeline for receiving video and extracting metadata"""
        
        # Ensure output directory exists
        output_dir = os.path.dirname(self.output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Build pipeline string for receiving and saving as MP4
        # Added timeout property to udpsrc
        pipeline_str = f"""
            udpsrc port={self.port} caps="video/mpegts" timeout=5000000000 ! 
            tsdemux name=demux ! 
            h264parse ! 
            tee name=t ! 
            queue ! 
            mp4mux name=mux ! 
            filesink location={self.output_file}
        """
        
        try:
            self.pipeline = Gst.parse_launch(pipeline_str)
        except GLib.GError as e:
            print(f"Error creating pipeline: {e}")
            sys.exit(1)
        
        # Add pad probe to monitor data and extract metadata
        self.add_metadata_probe()
        
        # Set up bus to handle messages
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_message)
        
        # Add a timeout to check for inactivity
        self.timeout_id = GLib.timeout_add_seconds(10, self.check_timeout)
        
    def add_metadata_probe(self):
        """Add probe to extract metadata from the stream"""
        # Get elements for probing
        demux = self.pipeline.get_by_name('demux')
        if demux:
            # Connect to pad-added signal for dynamic pads
            demux.connect("pad-added", self.on_pad_added)
        
        # Also probe the muxer for tags
        mux = self.pipeline.get_by_name('mux')
        if mux:
            sink_pad = mux.get_static_pad('video_0')
            if sink_pad:
                sink_pad.add_probe(
                    Gst.PadProbeType.EVENT_DOWNSTREAM,
                    self.on_pad_event
                )
    
    def on_pad_added(self, element, pad):
        """Handle dynamically added pads"""
        print(f"New pad added: {pad.get_name()}")
        
        # Add probe to the new pad for metadata extraction
        pad.add_probe(
            Gst.PadProbeType.EVENT_DOWNSTREAM | Gst.PadProbeType.EVENT_UPSTREAM,
            self.on_pad_event
        )
        
    def on_pad_event(self, pad, info):
        """Extract metadata from events"""
        event = info.get_event()
        if not event:
            return Gst.PadProbeReturn.OK
            
        event_type = event.type
        
        # Update last buffer time for timeout detection
        self.last_buffer_time = GLib.get_monotonic_time()
        
        # Extract metadata from TAG events
        if event_type == Gst.EventType.TAG:
            print("\n📨 Metadata received via pad event:")
            taglist = event.parse_tag()
            if taglist:
                self.extract_tags(taglist)
        
        # Extract custom metadata events
        elif event_type == Gst.EventType.CUSTOM_DOWNSTREAM or \
             event_type == Gst.EventType.CUSTOM_UPSTREAM:
            structure = event.get_structure()
            if structure and structure.get_name() == "custom-metadata":
                # Get data from structure
                data = structure.get_value("data")
                if data:
                    try:
                        metadata = json.loads(data)
                        self.extracted_metadata.update(metadata)
                        print(f"\n🔧 Custom metadata event received: {metadata}")
                        print(f"📦 Current metadata collection: {json.dumps(self.extracted_metadata, indent=2)}\n")
                    except (json.JSONDecodeError, TypeError):
                        pass
        
        # Detect EOS event
        elif event_type == Gst.EventType.EOS:
            print("\n📍 EOS event detected on pad")
            # Give it a moment to process remaining data
            GLib.timeout_add_seconds(1, lambda: self.on_message(None, 
                Gst.Message.new_eos(self.pipeline)))
        
        return Gst.PadProbeReturn.OK
    
    def extract_tags(self, taglist):
        """Extract metadata from GStreamer TagList"""
        if not taglist:
            print("  - Warning: Empty taglist")
            return
            
        # Debug: print all available tags
        print(f"  - Number of tags: {taglist.n_tags()}")
        
        for i in range(taglist.n_tags()):
            tag_name = taglist.nth_tag_name(i)
            print(f"  - Found tag: {tag_name}")
            
            # Try to get the value in different ways
            if tag_name:
                # Try string first
                success, value = taglist.get_string(tag_name)
                if success:
                    print(f"    Value (string): {value}")
                    
                    # Check for our custom metadata formats
                    if tag_name == Gst.TAG_COMMENT and ':' in value:
                        key, val = value.split(':', 1)
                        self.extracted_metadata[key] = val
                        print(f"    ✓ Extracted field: {key} = {val}")
                    elif tag_name == Gst.TAG_EXTENDED_COMMENT and '=' in value:
                        key, val = value.split('=', 1)
                        self.extracted_metadata[key] = val
                        print(f"    ✓ Extracted field: {key} = {val}")
                    elif tag_name == Gst.TAG_DESCRIPTION and value.startswith('metadata:'):
                        try:
                            json_str = value[9:]
                            metadata = json.loads(json_str)
                            self.extracted_metadata.update(metadata)
                            print(f"    ✓ Extracted JSON: {metadata}")
                        except json.JSONDecodeError as e:
                            print(f"    Error parsing JSON: {e}")
                    else:
                        # Store any other string tags
                        self.extracted_metadata[tag_name] = value
                else:
                    # Try other types
                    try:
                        # Try to get as uint
                        success, value = taglist.get_uint(tag_name)
                        if success:
                            print(f"    Value (uint): {value}")
                            self.extracted_metadata[tag_name] = str(value)
                    except:
                        pass
                    
                    try:
                        # Try to get value at index 0
                        value = taglist.get_value_index(tag_name, 0)
                        if value:
                            print(f"    Value (generic): {value}")
                            self.extracted_metadata[tag_name] = str(value)
                    except:
                        pass
        
        if self.extracted_metadata:
            print(f"\n📦 Current metadata collection: {json.dumps(self.extracted_metadata, indent=2)}\n")
    
    def on_message(self, bus, message):
        """Handle GStreamer bus messages"""
        t = message.type
        
        if t == Gst.MessageType.EOS:
            print("\n✅ End of stream reached")
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
                    print("▶️  Receiving stream...")
        elif t == Gst.MessageType.STREAM_START:
            print("🎬 Stream started")
            self.last_buffer_time = GLib.get_monotonic_time()
        elif t == Gst.MessageType.TAG:
            # Handle tags from bus messages
            print("\n📨 Metadata received via bus message:")
            taglist = message.parse_tag()
            if taglist:
                self.extract_tags(taglist)
        elif t == Gst.MessageType.ELEMENT:
            # Handle timeout from udpsrc
            structure = message.get_structure()
            if structure and structure.get_name() == "GstUDPSrcTimeout":
                print("\n⏱️  UDP timeout - no data received for 5 seconds")
                print("Stream might have ended. Saving current data...")
                self.save_metadata()
                self.stop()
    
    def check_timeout(self):
        """Check if we haven't received data for a while"""
        if self.last_buffer_time:
            time_since_last = (GLib.get_monotonic_time() - self.last_buffer_time) / 1000000  # Convert to seconds
            if time_since_last > 15:
                print(f"\n⏰ No data received for {time_since_last:.1f} seconds. Assuming stream ended.")
                self.save_metadata()
                self.stop()
                return False
        return True  # Continue checking
    
    def save_metadata(self):
        """Save extracted metadata to a JSON file"""
        if self.extracted_metadata:
            metadata_file = self.output_file.replace('.mp4', '_metadata.json')
            try:
                with open(metadata_file, 'w') as f:
                    json.dump(self.extracted_metadata, f, indent=2)
                print(f"Metadata saved to: {metadata_file}")
                print(f"Metadata content: {json.dumps(self.extracted_metadata, indent=2)}")
            except Exception as e:
                print(f"Error saving metadata: {e}")
    
    def start(self):
        """Start the receiver"""
        print(f"Starting receiver...")
        print(f"  Listening on port: {self.port}")
        print(f"  Output file: {self.output_file}")
        
        self.create_pipeline()
        
        # Start playing
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            print("Unable to set pipeline to playing state")
            sys.exit(1)
        
        # Create and run main loop
        self.loop = GLib.MainLoop()
        try:
            self.loop.run()
        except KeyboardInterrupt:
            print("\nInterrupted by user")
            self.stop()
    
    def stop(self):
        """Stop the receiver"""
        print(f"\n🛑 Stopping receiver...")
        
        # Cancel timeout
        if self.timeout_id:
            GLib.source_remove(self.timeout_id)
            self.timeout_id = None
            
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
        if self.loop:
            self.loop.quit()
        
        print(f"📹 Video saved to: {self.output_file}")
        
        # Print final metadata summary
        if self.extracted_metadata:
            print(f"\n📊 Final extracted metadata:")
            for key, value in self.extracted_metadata.items():
                print(f"  • {key}: {value}")

def main():
    parser = argparse.ArgumentParser(description='GStreamer video receiver with metadata extraction')
    parser.add_argument('port', type=int, help='UDP port to listen on')
    parser.add_argument('output', help='Output MP4 file path')
    
    args = parser.parse_args()
    
    # Create and start receiver
    receiver = VideoReceiver(args.port, args.output)
    receiver.start()

if __name__ == '__main__':
    main()