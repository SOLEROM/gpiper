# Single Port with SEI NAL Units

What SEI NAL Units Are:

SEI (Supplemental Enhancement Information) are special NAL units in the H.264 bitstream that carry non-video data. They're part of the H.264 standard, not GStreamer tags, so they survive muxing/demuxing.

GStreamer Tags: [Pipeline Level] → STRIPPED by muxer → Not transmitted
SEI NAL Units:  [H.264 Bitstream Level] → Part of video → Always transmitted

## sender side

1. Create custom GStreamer element or use pad probe after x264enc
2. For each video frame:
   - Intercept the H.264 buffer
   - Create SEI NAL unit with metadata (type 5 - user_data_unregistered)
   - Insert SEI before each IDR frame (keyframe)
   
Structure of SEI NAL:
- NAL header: 0x00 0x00 0x00 0x01 0x06 (type 6 = SEI)
- SEI payload type: 0x05 (unregistered user data)
- Payload size (variable length encoding)
- UUID (16 bytes) - identifies your metadata format
- JSON metadata (UTF-8 encoded)
- RBSP trailing bits

## receiver side

1. Add pad probe after h264parse element
2. For each buffer:
   - Parse NAL units looking for type 6 (SEI)
   - Extract payload type 5 (user data)
   - Match your UUID
   - Extract and parse JSON metadata

use the appsink/appsrc approach that works with GStreamer 1.16



## local test to prove extractions

```
test.py
#########
python test.py
SEI NAL INJECTION TEST FOR GSTREAMER 1.16


======================================================================
SIMPLE SEI NAL UNIT TEST
======================================================================
Created SEI NAL unit:
  • Size: 55 bytes
  • First 20 bytes: 0000000106052f4d455441444154410000000000
  • Should start with: 0000000106 (start code + SEI NAL type)

Extraction test:
  • Extracted: {'test': 'data', 'number': 123}
  • Original: {'test': 'data', 'number': 123}
  • Match: True

✅ Basic SEI NAL creation/extraction works!
======================================================================
SEI INJECTION TEST WITH APPSINK/APPSRC
======================================================================
Metadata: {'user': 'john', 'timestamp': '2024-01-01', 'session_id': '12345'}
Output: /tmp/tmpt3y_uit2.h264
----------------------------------------------------------------------

Phase 1: Injecting SEI...
----------------------------------------------------------------------
✅ Injected SEI #1 (buffer #1)
✅ Injected SEI #2 (buffer #21)
✅ Injected SEI #3 (buffer #41)
✅ Injected SEI #4 (buffer #61)
✅ Injected SEI #5 (buffer #81)

Results:
  • Buffers: 100
  • Keyframes: 5
  • SEI injected: 5

======================================================================
Phase 2: Verifying SEI in file...
----------------------------------------------------------------------
File size: 784,485 bytes

Found SEI NAL #1 at offset 0
  ✅ Extracted metadata: {'user': 'john', 'timestamp': '2024-01-01', 'session_id': '12345'}
  ✅ MATCHES ORIGINAL!

Found SEI NAL #2 at offset 143724
  ✅ Extracted metadata: {'user': 'john', 'timestamp': '2024-01-01', 'session_id': '12345'}
  ✅ MATCHES ORIGINAL!

Found SEI NAL #3 at offset 300024
  ✅ Extracted metadata: {'user': 'john', 'timestamp': '2024-01-01', 'session_id': '12345'}
  ✅ MATCHES ORIGINAL!

Found SEI NAL #4 at offset 460455
  ✅ Extracted metadata: {'user': 'john', 'timestamp': '2024-01-01', 'session_id': '12345'}
  ✅ MATCHES ORIGINAL!

Found SEI NAL #5 at offset 621321
  ✅ Extracted metadata: {'user': 'john', 'timestamp': '2024-01-01', 'session_id': '12345'}
  ✅ MATCHES ORIGINAL!

File analysis:
  • SEI NAL units found: 5
  • Metadata extracted: 5

======================================================================
TEST RESULT
======================================================================
✅ SUCCESS! SEI injection and extraction working!

✅ Full pipeline SEI injection works!


```


## run

python receiver.py 5000 ../out/received.mp4

python sender.py 127.0.0.1 5000 '{"user":"john","timestamp":"2024-01-01","session_id":"12345"}' --video ../demo/test2sec.avi



## example

