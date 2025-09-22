# metadata transfer with GStreamer

## summary and learned lessons
* SEI (Supplemental Enhancement Information) NAL units can carry custom metadata
* SEI injection works locally 
* Network reality: MPEG-TS muxer removes SEI during transmission
* MPEG-TS spec only preserves specific NAL types (SPS, PPS, AUD, slices) - SEI is considered "supplemental" and stripped

* GStreamer 1.16.3 doesn't support info.set_buffer() method
    * Required workarounds: appsink/appsrc pattern or drop/push approach

* RTP/H.264 with SEI was successfully tested
    * RTP preserves raw H.264 stream including SEI
    * Required handling AVCC format from RTP depayloader
    * Metadata successfully embedded and extracted

* paid solution to inject sei - [ridgerun](https://developer.ridgerun.com/wiki/index.php/GstSEIMetadata/Examples/Using_gst-launch)

### The Working Architecture

```
SENDER:
        [AVI] → [Decode] → [H.264 Encode] → [Inject SEI] → [RTP Payload] → UDP:5000
                                                  ↑
                                             [Metadata JSON]

RECEIVER:
        UDP:5000 → [RTP Depay] → [Extract SEI] → [H.264] → [MP4]
                                      ↓
                                 [Metadata JSON]

```

## work demos
* [meta0](./meta0/readme.md) : 
    * draw over video with textoverlay
* [meta1](./meta1/readme.md)
    * show MPEG-TS Tags - stream strips tags 
    * show how to use out-of-band metadata channel 
* [meta2](./meta2/readme.md) : 
    * try with sei over single port 
    * works locally but not over network
* [meta3](./meta3/readme.md) : 
    * sei over RTP - works ;
    