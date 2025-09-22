# TP/H.264 Over UDP 

* Perfect for SEI + Compression
* Single UDP port - Everything in one stream
* Full H.264 compression - Same video compression as before
* SEI NAL units preserved - RTP doesn't strip them
* Standard protocol - Used by WebRTC, VoIP, IP cameras


```
[AVI File] → [H.264 Encode + SEI Injection] → [RTP Packetization] → UDP Port 5000
                                                                       ↓
[MP4 File] ← [H.264 Decode + SEI Extract] ← [RTP Depacketization] ← UDP Port 5000
```

## diffs from before

```
MPEG-TS Structure:
    [MPEG-TS Header][PES Header][H.264 Data (SEI stripped)]
RTP Structure:
    [RTP Header][H.264 Data (SEI preserved)]
```


## test

```
python receiver.py 5000 ../out/received.mp4

python sender.py 127.0.0.1 5000 '{"user":"john","timestamp":"2024-01-01","session_id":"12345"}' --video ../demo/test2sec.avi
```

## example

```
 python receiver.py 5000 ../out/received.mp4

============================================================
RTP/H.264 SEI RECEIVER (Single Port)
============================================================
📡 UDP port: 5000
💾 Output file: ../out/received.mp4
🔧 Protocol: RTP/H.264 over UDP (preserves SEI)
🔍 Looking for UUID: 4d45544144415441...
============================================================
⏳ Waiting for RTP stream...
✅ SEI extraction probe added after RTP depayload



  Buffer #1: 8332 bytes
    First 40 bytes: 000002bf0605ffffbbdc45e9bde6d948b7962cd820d923eeef78323634202d20636f726520313535
    Format: Length-prefixed (first NAL length = 703)
    First NAL type: 6 (6=SEI, 5=IDR, 9=AUD)
    ✅ First NAL is SEI!
    SEI payload starts: 05ffffbbdc45e9bde6d948b7962cd820d923eeef
▶️  Receiving RTP/H.264 stream...
  Buffer #2: 1808 bytes
    First 40 bytes: 0000000209300000002e419a3b10ebfffe8cb00006a09e241b781922d51d1100dbe042810cba4441
    Format: Length-prefixed (first NAL length = 2)
    First NAL type: 9 (6=SEI, 5=IDR, 9=AUD)
  Buffer #3: 4381 bytes
    First 40 bytes: 00000002093000000091419a4f0864ca6104affea9960000de4519ae008cde2900cb2115a4b6c4f7
    Format: Length-prefixed (first NAL length = 2)
    First NAL type: 9 (6=SEI, 5=IDR, 9=AUD)

🔍 SEI METADATA EXTRACTED (occurrence #1):
   ----------------------------------------
   • user: john
   • timestamp: 2024-01-01
   • session_id: 12345
   ----------------------------------------


```

```
 python sender.py 127.0.0.1 5000 '{"user":"john","timestamp":"2024-01-01","session_id":"12345"}' --video ../demo/test2sec.avi
============================================================
RTP/H.264 SEI SENDER (Single Port)
============================================================
📹 Source: ../demo/test2sec.avi
🌐 Destination: 127.0.0.1:5000
📦 Metadata to inject:
   • user: john
   • timestamp: 2024-01-01
   • session_id: 12345
🔧 Protocol: RTP/H.264 over UDP (preserves SEI)
============================================================
✅ Connected appsink for SEI injection
💉 Injected SEI #1 at keyframe (buffer #1)
    SEI size: 90 bytes
    First 40 bytes of output: 000000010910000000010605524d4554414441544100000000000000007b2275736572223a20226a
📡 RTP transmission started...
▶️  Encoding started...
💉 Injected SEI #2 at keyframe (buffer #31)

✅ Encoding complete. SEI injected: 2
✅ Transmission complete
🛑 Sender stopped
```