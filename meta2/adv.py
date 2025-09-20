#!/usr/bin/env python3
"""
Advanced metadata handling options for GStreamer pipelines
Demonstrates multiple approaches for metadata injection and extraction
"""

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstVideo', '1.0')
from gi.repository import Gst, GLib, GstVideo
import json
import struct
import base64

class MetadataHandler:
    """Various methods for handling metadata in GStreamer"""
    
    @staticmethod
    def method1_klv_metadata(pipeline, metadata):
        """
        Method 1: KLV (Key-Length-Value) Metadata
        Used in professional broadcast and MISB standards
        """
        # KLV encoding for metadata
        def encode_klv(key, value):
            key_bytes = key.encode('utf-8')[:16].ljust(16, b'\x00')  # 16-byte key
            value_bytes = value.encode('utf-8')
            length = len(value_bytes)
            
            # BER length encoding
            if length < 128:
                length_bytes = bytes([length])
            else:
                length_bytes = bytes([0x81, length])  # Simplified for lengths < 256
            
            return key_bytes + length_bytes + value_bytes
        
        # Create KLV metadata
        klv_data = b''
        for key, value in metadata.items():
            klv_data += encode_klv(key, str(value))
        
        # Insert KLV as auxiliary data
        structure = Gst.Structure.new_empty("meta/x-klv")
        structure.set_value("data", klv_data)
        
        return structure
    
    @staticmethod
    def method2_sei_messages(h264_encoder, metadata):
        """
        Method 2: H.264 SEI (Supplemental Enhancement Information) Messages
        Embeds metadata directly in the H.264 stream
        """
        # SEI User Data Unregistered format
        uuid = b'\x4d\x49\x53\x42\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'  # Custom UUID
        payload = json.dumps(metadata).encode('utf-8')
        
        # Create SEI NAL unit (simplified)
        sei_data = uuid + payload
        
        # Set x264enc property for SEI insertion
        if h264_encoder:
            # This would require custom x264enc properties or a custom element
            # For demonstration, we'll use a caps event
            caps = Gst.Caps.from_string("video/x-h264,sei-user-data=" + base64.b64encode(sei_data).decode())
            return caps
        
        return None
    
    @staticmethod
    def method3_id3_tags(muxer, metadata):
        """
        Method 3: ID3 Tags in MPEG-TS
        Commonly used for timed metadata in HLS streams
        """
        taglist = Gst.TagList.new_empty()
        
        # Standard ID3 tags
        if 'title' in metadata:
            taglist.add_value(Gst.TagMergeMode.REPLACE, Gst.TAG_TITLE, metadata['title'])
        if 'artist' in metadata:
            taglist.add_value(Gst.TagMergeMode.REPLACE, Gst.TAG_ARTIST, metadata['artist'])
        
        # Custom ID3 TXXX frame for arbitrary data
        custom_data = json.dumps(metadata)
        taglist.add_value(Gst.TagMergeMode.REPLACE, Gst.TAG_EXTENDED_COMMENT, f"TXXX:{custom_data}")
        
        return taglist
    
    @staticmethod
    def method4_rtp_header_extension(metadata):
        """
        Method 4: RTP Header Extensions
        For real-time streaming with metadata
        """
        # RTP header extension format (RFC 5285)
        extension_data = []
        
        for key, value in metadata.items():
            # One-byte header extension
            ext_id = hash(key) % 14 + 1  # ID 1-14 for one-byte header
            data = str(value).encode('utf-8')[:255]
            length = len(data)
            
            extension_data.append({
                'id': ext_id,
                'data': data,
                'length': length
            })
        
        return extension_data
    
    @staticmethod
    def method5_timed_metadata_track(output_file, metadata, timestamps):
        """
        Method 5: Separate Timed Metadata Track in MP4
        Creates a dedicated metadata track alongside video
        """
        # This would create a separate track in MP4 for metadata
        # Using qtmux with a subtitle or data track
        
        pipeline_str = f"""
            appsrc name=metasrc ! 
            text/x-raw,format=utf8 ! 
            qtmux.subtitle_0
        """
        
        # Generate WebVTT or TTML format metadata
        vtt_content = "WEBVTT\n\n"
        for timestamp, meta_item in zip(timestamps, metadata):
            start_time = f"{timestamp//3600:02d}:{(timestamp%3600)//60:02d}:{timestamp%60:06.3f}"
            end_time_sec = timestamp + 1
            end_time = f"{end_time_sec//3600:02d}:{(end_time_sec%3600)//60:02d}:{end_time_sec%60:06.3f}"
            vtt_content += f"{start_time} --> {end_time}\n"
            vtt_content += f"NOTE {json.dumps(meta_item)}\n\n"
        
        return vtt_content

class AdvancedSender:
    """Sender with multiple metadata injection methods"""
    
    def __init__(self, host, port, metadata, video_file, method='tags'):
        self.host = host
        self.port = port
        self.metadata = metadata
        self.video_file = video_file
        self.method = method
        self.pipeline = None
        
        Gst.init(None)
    
    def create_pipeline(self):
        """Create pipeline with selected metadata method"""
        
        if self.method == 'klv':
            # Pipeline with KLV metadata insertion
            pipeline_str = f"""
                filesrc location={self.video_file} !
                decodebin !
                videoconvert !
                x264enc tune=zerolatency bitrate=2000 key-int-max=30 name=encoder !
                video/x-h264,stream-format=byte-stream !
                h264parse !
                mpegtsmux name=mux !
                udpsink host={self.host} port={self.port}
            """
        elif self.method == 'rtp':
            # Pipeline with RTP and header extensions
            pipeline_str = f"""
                filesrc location={self.video_file} !
                decodebin !
                videoconvert !
                x264enc tune=zerolatency bitrate=2000 !
                rtph264pay name=rtppay config-interval=1 !
                udpsink host={self.host} port={self.port}
            """
        else:  # Default: tags method
            pipeline_str = f"""
                filesrc location={self.video_file} !
                decodebin !
                videoconvert !
                x264enc tune=zerolatency bitrate=2000 !
                h264parse !
                mpegtsmux name=mux !
                udpsink host={self.host} port={self.port}
            """
        
        self.pipeline = Gst.parse_launch(pipeline_str)
        self.inject_metadata_by_method()
    
    def inject_metadata_by_method(self):
        """Inject metadata using the selected method"""
        
        if self.method == 'klv':
            # KLV metadata injection
            mux = self.pipeline.get_by_name('mux')
            if mux:
                klv_struct = MetadataHandler.method1_klv_metadata(self.pipeline, self.metadata)
                event = Gst.Event.new_custom(Gst.EventType.CUSTOM_DOWNSTREAM, klv_struct)
                mux.send_event(event)
                
        elif self.method == 'rtp':
            # RTP header extension
            rtppay = self.pipeline.get_by_name('rtppay')
            if rtppay:
                extensions = MetadataHandler.method4_rtp_header_extension(self.metadata)
                # Note: Actual RTP extension would require custom payloader or properties
                print(f"RTP Extensions prepared: {extensions}")
                
        elif self.method == 'id3':
            # ID3 tags in MPEG-TS
            mux = self.pipeline.get_by_name('mux')
            if mux:
                taglist = MetadataHandler.method3_id3_tags(mux, self.metadata)
                event = Gst.Event.new_tag(taglist)
                mux.send_event(event)
                
        else:  # Default tags
            mux = self.pipeline.get_by_name('mux')
            if mux:
                taglist = Gst.TagList.new_empty()
                for key, value in self.metadata.items():
                    taglist.add_value(Gst.TagMergeMode.REPLACE, Gst.TAG_COMMENT, f"{key}:{value}")
                event = Gst.Event.new_tag(taglist)
                mux.send_event(event)

# Example usage and testing
def example_usage():
    """
    Example of how to use different metadata methods
    """
    
    # Example 1: Simple tag-based metadata
    print("Example 1: Tag-based metadata")
    print("-" * 40)
    print("python sender.py 127.0.0.1 5000 '{\"user\":\"john\",\"session\":\"12345\"}' --video test.avi")
    print()
    
    # Example 2: KLV metadata (professional broadcast)
    print("Example 2: KLV metadata for broadcast")
    print("-" * 40)
    print("python sender.py 127.0.0.1 5000 '{\"timestamp\":\"2024-01-01T12:00:00\",\"location\":\"40.7,-74.0\"}' --video test.avi --method klv")
    print()
    
    # Example 3: RTP with header extensions
    print("Example 3: RTP streaming with header extensions")
    print("-" * 40)
    print("python sender.py 127.0.0.1 5000 '{\"stream_id\":\"cam01\",\"quality\":\"HD\"}' --video test.avi --method rtp")
    print()
    
    # Example 4: ID3 tags in MPEG-TS
    print("Example 4: ID3 tags for HLS streaming")
    print("-" * 40)
    print("python sender.py 127.0.0.1 5000 '{\"title\":\"Live Stream\",\"artist\":\"Camera 1\"}' --video test.avi --method id3")
    print()
    
    # Pipeline examples for different use cases
    print("GStreamer Pipeline Examples:")
    print("=" * 40)
    
    # Simple pipeline with metadata
    print("\n1. Simple pipeline with JSON metadata:")
    print("""
    gst-launch-1.0 filesrc location=input.avi ! \\
        decodebin ! x264enc ! h264parse ! \\
        mpegtsmux ! taginject tags="comment=\\"metadata:value\\"" ! \\
        udpsink host=127.0.0.1 port=5000
    """)
    
    # Pipeline with KLV
    print("\n2. Pipeline with KLV metadata:")
    print("""
    gst-launch-1.0 filesrc location=input.avi ! \\
        decodebin ! x264enc ! \\
        mpegtsmux alignment=7 ! klvtimestamp ! \\
        udpsink host=127.0.0.1 port=5000
    """)
    
    # Pipeline with RTP
    print("\n3. RTP streaming pipeline:")
    print("""
    gst-launch-1.0 filesrc location=input.avi ! \\
        decodebin ! x264enc ! \\
        rtph264pay ! application/x-rtp-stream ! \\
        udpsink host=127.0.0.1 port=5000
    """)

if __name__ == "__main__":
    example_usage()