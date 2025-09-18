# to use tcp

receiver

```
gst-launch-1.0 -q tcpserversrc host=0.0.0.0 port=5000 ! filesink location=../out/received.mp4

```


Send

```
gst-launch-1.0 -q filesrc location=../demo/test2sec.mp4 ! tcpclientsink host=127.0.0.1 port=5000

```

results:

```
md5sum ../demo/test2sec.mp4 ../out/received.mp4
6bdb48c83318d205d6358e90c56ff8d3  ../demo/test2sec.mp4
6bdb48c83318d205d6358e90c56ff8d3  ../out/received.mp4
```
