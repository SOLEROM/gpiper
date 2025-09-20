

MPEG-TS (Transport Stream) doesn't preserve GStreamer tags. 


 uses a metadata side channel. This approach:

Sends video on the main port (e.g., 5000)
Sends metadata on port+1 (e.g., 5001)
Uses a special packet format to distinguish metadata from video


## 

python3 sideChTest.py receiver 5000 ../out/received.mp4


python3 sideChTest.py sender 127.0.0.1 5000 '{"user":"john","timestamp":"2024-01-01","session_id":"12345"}' --video ../demo/test2sec.avi


## example

```
python3 sideChTest.py receiver 5000 ../out/received.mp4

Starting improved receiver...
  Video port: 5000
  Metadata port: 5001
  Output: ../out/received.mp4
Listening for metadata on port 5001...

📦 Metadata received from 127.0.0.1:
   {
  "user": "john",
  "timestamp": "2024-01-01",
  "session_id": "12345"
}


📦 Metadata received from 127.0.0.1:
   {
  "user": "john",
  "timestamp": "2024-01-01",
  "session_id": "12345"
}


📦 Metadata received from 127.0.0.1:
   {
  "user": "john",
  "timestamp": "2024-01-01",
  "session_id": "12345"
}

Receiving video stream...

⏱️  Video stream timeout - no data for 5 seconds
✅ Metadata saved to: ../out/received_metadata.json
   Content: {
  "user": "john",
  "timestamp": "2024-01-01",
  "session_id": "12345"
}
📹 Video saved to: ../out/received.mp4

```

```
python3 sideChTest.py sender 127.0.0.1 5000 '{"user":"john","timestamp":"2024-01-01","session_id":"12345"}' --video ../demo/test2sec.avi
Starting improved sender...
  Video port: 5000
  Metadata port: 5001
  Destination: 127.0.0.1
  Source: ../demo/test2sec.avi
  Metadata: {'user': 'john', 'timestamp': '2024-01-01', 'session_id': '12345'}
Sent metadata packet 1/3
Sent metadata packet 2/3
Sent metadata packet 3/3
Streaming video...
Video stream ended
Sender stopped

```

out/received_metadata.json :

```

{
  "user": "john",
  "timestamp": "2024-01-01",
  "session_id": "12345"
}
```