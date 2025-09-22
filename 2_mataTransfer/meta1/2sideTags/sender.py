#!/usr/bin/env python3
"""
GStreamer sender with custom metadata injection
Sends AVI file as H.264 encoded stream over UDP with metadata
"""

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstVideo', '1.0')
from gi.repository import Gst, GLib, GstVideo
import sys
import json
import argparse
import os

class VideoSender:
    def __init__(self, host, port, metadata, video_file):
        self.host = host
        self.port = port
        self.metadata = metadata
        self.video_file = video_file
        self.pipeline = None
        self.loop = None
        
        # Initialize GStreamer
        Gst.init(None)
        
    def create_pipeline(self):
        """Create GStreamer pipeline for sending video with metadata"""
        
        # Check if input file exists
        if not os.path.exists(self.video_file):
            raise FileNotFoundError(f"Video file not found: {self.video_file}")
        
        # Build pipeline string - using taginject for metadata
        # Create tags string for taginject element
        tags_str = ""
        for key, value in self.metadata.items():
            tags_str += f"comment=\"{key}:{value}\","
        
        # Add the full JSON as description
        tags_str += f"description=\"metadata:{json.dumps(self.metadata)}\""
        
        pipeline_str = f"""
            filesrc location={self.video_file} ! 
            decodebin name=decoder ! 
            videoconvert ! 
            videoscale ! 
            video/x-raw,width=1280,height=720 ! 
            taginject tags="{tags_str}" !
            x264enc tune=zerolatency bitrate=2000 key-int-max=30 ! 
            video/x-h264,stream-format=byte-stream ! 
            h264parse ! 
            mpegtsmux name=mux ! 
            udpsink host={self.host} port={self.port} sync=true async=false
        """
        
        try:
            self.pipeline = Gst.parse_launch(pipeline_str)
            print(f"Pipeline created with inline tags: {tags_str[:100]}...")
        except GLib.GError as e:
            # If taginject fails, try without it
            print(f"Note: taginject not available or failed, using alternative method")
            pipeline_str = f"""
                filesrc location={self.video_file} ! 
                decodebin name=decoder ! 
                videoconvert ! 
                videoscale ! 
                video/x-raw,width=1280,height=720 ! 
                x264enc tune=zerolatency bitrate=2000 key-int-max=30 name=encoder ! 
                video/x-h264,stream-format=byte-stream ! 
                h264parse name=parser ! 
                mpegtsmux name=mux ! 
                udpsink host={self.host} port={self.port} sync=true async=false
            """
            self.pipeline = Gst.parse_launch(pipeline_str)
            
            # Get multiple elements to inject metadata at different points
            encoder = self.pipeline.get_by_name('encoder')
            parser = self.pipeline.get_by_name('parser') 
            mux = self.pipeline.get_by_name('mux')
            
            # Inject at multiple points
            if encoder:
                self.inject_metadata(encoder)
            if parser:
                self.inject_metadata(parser)
            if mux:
                self.inject_metadata(mux)
            
        # Set up bus to handle messages
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_message)
        
    def inject_metadata(self, element):
        """Inject custom metadata into the stream"""
        print(f"Injecting metadata into element: {element.get_name()}")
        
        # Method 1: Using tags (will be preserved in the stream)
        taglist = Gst.TagList.new_empty()
        
        # Add custom metadata as comment tags
        for key, value in self.metadata.items():
            if isinstance(value, str):
                # Use comment tag which accepts strings
                taglist.add_value(Gst.TagMergeMode.REPLACE, 
                                 Gst.TAG_COMMENT, 
                                 f"{key}:{value}")
                print(f"  Added TAG_COMMENT: {key}:{value}")
                
                # Also add as extended comment
                taglist.add_value(Gst.TagMergeMode.REPLACE,
                                 Gst.TAG_EXTENDED_COMMENT,
                                 f"{key}={value}")
                print(f"  Added TAG_EXTENDED_COMMENT: {key}={value}")
        
        # Add entire metadata as a single comment
        metadata_json = json.dumps(self.metadata)
        taglist.add_value(Gst.TagMergeMode.REPLACE, 
                         Gst.TAG_DESCRIPTION,
                         f"metadata:{metadata_json}")
        print(f"  Added TAG_DESCRIPTION: metadata:{metadata_json}")
        
        # Also add a title tag for testing
        taglist.add_value(Gst.TagMergeMode.REPLACE, 
                         Gst.TAG_TITLE,
                         "Test Video with Metadata")
        
        # Create a tag event and send it downstream
        tag_event = Gst.Event.new_tag(taglist)
        
        # Send to the element's sink pad
        sinkpad = element.get_static_pad("sink")
        if sinkpad:
            result = sinkpad.send_event(tag_event)
            print(f"  Tag event sent to sink pad: {result}")
        else:
            # Try sending to the element directly
            result = element.send_event(tag_event)
            print(f"  Tag event sent to element: {result}")
        
        # Method 2: Using custom events (for real-time metadata)
        # Create structure with properly formatted string
        structure = Gst.Structure.new_empty("custom-metadata")
        structure.set_value("data", metadata_json)
        
        custom_event = Gst.Event.new_custom(Gst.EventType.CUSTOM_DOWNSTREAM, structure)
        if sinkpad:
            sinkpad.send_event(custom_event)
        else:
            element.send_event(custom_event)
        
        print(f"Metadata injection completed\n")
    
    def on_message(self, bus, message):
        """Handle GStreamer bus messages"""
        t = message.type
        
        if t == Gst.MessageType.EOS:
            print("End of stream reached")
            self.stop()
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"Error: {err}, {debug}")
            self.stop()
        elif t == Gst.MessageType.STATE_CHANGED:
            if message.src == self.pipeline:
                old_state, new_state, pending = message.parse_state_changed()
                print(f"Pipeline state changed: {old_state.value_nick} -> {new_state.value_nick}")
        elif t == Gst.MessageType.STREAM_START:
            print("Stream started")
            
    def start(self):
        """Start the pipeline"""
        print(f"Starting sender...")
        print(f"  Source: {self.video_file}")
        print(f"  Destination: {self.host}:{self.port}")
        print(f"  Metadata: {self.metadata}")
        
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
        """Stop the pipeline"""
        print("Stopping sender...")
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
        if self.loop:
            self.loop.quit()

def main():
    parser = argparse.ArgumentParser(description='GStreamer video sender with metadata')
    parser.add_argument('host', help='Destination IP address')
    parser.add_argument('port', type=int, help='Destination port')
    parser.add_argument('metadata', help='JSON metadata string')
    parser.add_argument('--video', required=True, help='Input video file (AVI)')
    
    args = parser.parse_args()
    
    # Parse metadata JSON
    try:
        metadata = json.loads(args.metadata)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON metadata: {e}")
        sys.exit(1)
    
    # Create and start sender
    sender = VideoSender(args.host, args.port, metadata, args.video)
    sender.start()

if __name__ == '__main__':
    main()