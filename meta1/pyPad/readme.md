# pyPAD

Hook a pad probe on h264parse.src

## what is a pad probe?

a pad probe is a callback you attach to a pad (src/sink) to observe or modify data flowing through it. with it you can:

    inspect/modify buffers (compressed bytes, timestamps, flags),

    drop/duplicate data,

    peek at events/queries.


## sender side

For each buffer:

    If keyframe (GST_BUFFER_FLAG_DELTA_UNIT not set) or every-N frames:

    Build an SEI NAL (start code 00 00 00 01, nal_unit_type=6).

    Payload: user_data_unregistered: 16-byte UUID + your TLV/CBOR/JSON bytes.

    Do emulation-prevention (insert 0x03 after any 00 00 before a byte ≤ 0x03).

    Prepend the SEI NAL to the AU (safe because we’re AU-aligned).


## receiver side



    Probe after h264parse on the demux video pad.

    Scan for NAL type 6, then for payload type “user_data_unregistered” (0x05 in H.264’s SEI payload type coding), read the UUID, and parse the rest as your custom payload.


## run

python extract_sei_receiver.py 5000 ../../out/received.mp4
python inject_sei_sender.py 127.0.0.1 5000 ../../demo/test2sec.avi 12345678-1234-1234-1234-1234567890ab '{"user":"myUser","task":"gparted-pipe","note":"demo-1"}'