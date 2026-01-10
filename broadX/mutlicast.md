# multicast

Definition : Sender transmits one stream, receivers explicitly join a multicast group.

IPv4 Multicast
* Range: 224.0.0.0 – 239.255.255.255 
* Common:   224.0.0.x → local control (not routed)  // 239.0.0.0/8 → administrative / private multicast

Transport
* UDP only
* No built-in reliability

Advantages
* Constant bandwidth regardless of receivers
* Very low latency
* Perfect for live video / telemetry
* Network handles replication

Disadvantages
* No reliability or retransmission
* Complex debugging
* Often blocked across routers
* Requires IGMP / MLD / PIM support

Typical Use
* IPTV
* Market data feeds
* Sensor data fan-out
* Real-time video on controlled LANs


## example: RTP OVER UDP MULTICAST

* One send stream, many receivers: sender bandwidth stays essentially constant as you add receivers.
* Low latency: no per-client retransmission behavior.
* Native fit for GStreamer: RTP/RTCP tooling and jitter buffering are mature.

Advantages
* Scales to many receivers without multiplying sender load
* Minimal infrastructure
* Works well for “trusted LAN” broadcast-style distribution

Disadvantages
* Requires multicast support in the LAN (IGMP snooping on switches helps; misconfig can cause flooding)
* Not reliable (packet loss shows as artifacts). On a good LAN this is usually acceptable.
* Crossing subnets/VLANs needs router multicast configuration (IGMP/PIM), otherwise keep it within one subnet.

### sender

```
gst-launch-1.0 -v \
  videotestsrc is-live=true ! videoconvert ! x264enc tune=zerolatency speed-preset=ultrafast key-int-max=30 ! \
  rtph264pay pt=96 config-interval=1 ! \
  udpsink host=239.10.10.10 port=5004 auto-multicast=true ttl=1

```

### receiver
* each client joins the multicast group
```
gst-launch-1.0 -v \
  udpsrc address=239.10.10.10 port=5004 auto-multicast=true caps="application/x-rtp, media=video, encoding-name=H264, payload=96" ! \
  rtph264depay ! avdec_h264 ! videoconvert ! autovideosink sync=false

```

