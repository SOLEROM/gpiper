# about


* rtp over udp
* decodebin handles whatever codec is inside the src
* re-encode to H.264 for clean RTP
* no hw encode (x264enc)

## run

* start receiver first then sender

```
 61862 ../demo/test2sec.avi
469759 ../out/received.mkv
```
