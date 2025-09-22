#!/usr/bin/env python3
"""
Simple test to verify metadata injection and extraction works locally
Run this first to test if metadata works without UDP
"""

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import sys
import json
import tempfile

def test_metadata_locally():
    """Test metadata injection and extraction in a simple pipeline"""
    
    metadata = {"user": "test", "timestamp": "2024-01-01", "session_id": "12345"}
    
    print("Testing metadata locally (no network)...")
    print(f"Test metadata: {metadata}")
    print("-" * 50)
    
    # Create a test video file if needed
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
        output_file = tmp.name
    
    # Simple pipeline with metadata injection
    # Properly escape the JSON for shell parsing
    escaped_metadata = json.dumps(metadata).replace('"', '\\"')
    
    pipeline_str = f"""
        videotestsrc num-buffers=100 ! 
        video/x-raw,width=320,height=240,framerate=30/1 ! 
        x264enc ! 
        h264parse ! 
        mp4mux ! 
        filesink location={output_file}
    """
    
    print(f"Creating test pipeline...")
    try:
        pipeline = Gst.parse_launch(pipeline_str)
    except Exception as e:
        print(f"Failed to create pipeline: {e}")
        print("Trying alternative method...")
        return
    
    # Now inject tags programmatically after pipeline creation
    print("Injecting metadata programmatically...")
    
    # Create taglist
    taglist = Gst.TagList.new_empty()
    taglist.add_value(Gst.TagMergeMode.REPLACE, Gst.TAG_TITLE, "Test Video")
    taglist.add_value(Gst.TagMergeMode.REPLACE, Gst.TAG_COMMENT, "user:test")
    taglist.add_value(Gst.TagMergeMode.REPLACE, Gst.TAG_DESCRIPTION, f"metadata:{json.dumps(metadata)}")
    
    # Create tag setter to inject tags
    # We'll send a tag event once pipeline starts
    
    # Set up bus monitoring
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    
    extracted_tags = {}
    
    def on_message(bus, message):
        t = message.type
        if t == Gst.MessageType.TAG:
            taglist = message.parse_tag()
            if taglist:
                print(f"\n✓ Tags detected in pipeline!")
                for i in range(taglist.n_tags()):
                    tag_name = taglist.nth_tag_name(i)
                    success, value = taglist.get_string(tag_name)
                    if success:
                        extracted_tags[tag_name] = value
                        print(f"  - {tag_name}: {value}")
        elif t == Gst.MessageType.EOS:
            print(f"\nPipeline completed. File saved to: {output_file}")
            pipeline.set_state(Gst.State.NULL)
            loop.quit()
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"Error: {err}")
            pipeline.set_state(Gst.State.NULL)
            loop.quit()
    
    bus.connect("message", on_message)
    
    # Inject tags after pipeline is created but before playing
    def inject_tags():
        # Find the muxer to inject tags
        elements = pipeline.iterate_elements()
        for element in elements:
            if 'mux' in element.get_name().lower() or element.__class__.__name__ == 'GstMp4Mux':
                print(f"Injecting tags into: {element.get_name()}")
                tag_event = Gst.Event.new_tag(taglist)
                element.send_event(tag_event)
                break
        return False  # Don't repeat
    
    # Schedule tag injection
    GLib.idle_add(inject_tags)
    
    # Run pipeline
    pipeline.set_state(Gst.State.PLAYING)
    loop = GLib.MainLoop()
    
    try:
        loop.run()
    except KeyboardInterrupt:
        pass
    
    print("\n" + "=" * 50)
    print("RESULTS:")
    if extracted_tags:
        print("✅ Metadata injection WORKS!")
        print(f"Extracted tags: {json.dumps(extracted_tags, indent=2)}")
    else:
        print("❌ No metadata extracted - there may be an issue with your GStreamer installation")
    
    # Now test reading the file
    print("\n" + "=" * 50)
    print("Testing reading metadata from saved file...")
    
    # Read metadata from the saved file
    read_pipeline_str = f"""
        filesrc location={output_file} ! 
        qtdemux name=demux ! 
        fakesink
    """
    
    read_pipeline = Gst.parse_launch(read_pipeline_str)
    read_bus = read_pipeline.get_bus()
    read_bus.add_signal_watch()
    
    file_tags = {}
    
    def on_read_message(bus, message):
        t = message.type
        if t == Gst.MessageType.TAG:
            taglist = message.parse_tag()
            if taglist:
                for i in range(taglist.n_tags()):
                    tag_name = taglist.nth_tag_name(i)
                    success, value = taglist.get_string(tag_name)
                    if success:
                        file_tags[tag_name] = value
        elif t == Gst.MessageType.EOS:
            read_pipeline.set_state(Gst.State.NULL)
            read_loop.quit()
    
    read_bus.connect("message", on_read_message)
    read_pipeline.set_state(Gst.State.PLAYING)
    
    read_loop = GLib.MainLoop()
    GLib.timeout_add_seconds(2, lambda: read_loop.quit())
    read_loop.run()
    
    if file_tags:
        print("✅ Metadata persisted in file!")
        print(f"File tags: {json.dumps(file_tags, indent=2)}")
    else:
        print("⚠️  No metadata found in saved file")
        
    print("\n" + "=" * 50)
    print("Testing UDP metadata transmission...")
    
    # Test with UDP locally
    udp_pipeline_str = f"""
        filesrc location={output_file} ! 
        qtdemux ! 
        h264parse ! 
        mpegtsmux ! 
        tee name=t ! 
        queue ! udpsink host=127.0.0.1 port=5555
        t. ! queue ! fakesink
    """
    
    # Also set up a receiver
    receive_pipeline_str = """
        udpsrc port=5555 ! 
        tsdemux ! 
        h264parse ! 
        fakesink
    """
    
    print("Note: For full UDP test, run the sender.py and receiver.py scripts")
    
    import os
    os.unlink(output_file)  # Clean up temp file
    
    return extracted_tags

if __name__ == "__main__":
    print("GStreamer Metadata Test")
    print("=" * 50)
    
    # Initialize GStreamer first
    Gst.init(None)
    
    # Check GStreamer version
    version = Gst.version()
    print(f"GStreamer version: {version[0]}.{version[1]}.{version[2]}")
    
    # Check for required plugins
    required_plugins = ['coreelements', 'videoconvert', 'x264', 'typefindfunctions', 'mpegtsdemux', 'isomp4']
    missing = []
    
    registry = Gst.Registry.get()
    for plugin_name in required_plugins:
        plugin = registry.find_plugin(plugin_name)
        if plugin:
            print(f"✓ Plugin '{plugin_name}' found")
        else:
            print(f"✗ Plugin '{plugin_name}' MISSING")
            missing.append(plugin_name)
    
    if missing:
        print(f"\n⚠️  Missing plugins: {', '.join(missing)}")
        print("Install with: sudo apt-get install gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly")
    
    print("\n" + "=" * 50)
    test_metadata_locally()