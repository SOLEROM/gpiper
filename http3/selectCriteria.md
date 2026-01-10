# selecte criteria

**HTTP/3 (QUIC) is best for video when the video is treated as *secure, chunked data over unreliable networks*, not as a real-time media stream.**

If your problem is **delivery robustness, mobility, and Internet traversal**, HTTP/3 shines.
If your problem is **real-time latency, sync, or LAN efficiency**, it does not.

---

## The “Right Shape” of Video for HTTP/3

HTTP/3 works best when video traffic has **these properties**:

| Property                   | Why it matters                              |
| -------------------------- | ------------------------------------------- |
| WAN / Internet path        | QUIC solves TCP loss and handshake problems |
| Client mobility            | Connection migration (Wi-Fi ↔ LTE)          |
| Encryption required        | Built-in TLS 1.3                            |
| Chunked or segmented video | Matches QUIC stream semantics               |
| Many parallel transfers    | Independent streams avoid HOL blocking      |
| Client-driven fetch        | HTTP request/response fits                  |

This naturally leads to **file-like or segment-based video**, not live pipes.

---

## Cases Where HTTP/3 Is Actually the Best Choice

### 1. Adaptive Streaming (HLS / DASH over HTTP/3)

![Image](https://teyuto-documentation-production.up.railway.app/img/assets/637f6184284e4378e89b895a_LL-HLS_20vs_20LL-DASH_20_1__20_2_.webp)

![Image](https://blog.eleven-labs.com/imgs/articles/2017-07-12-video-live-dash-hls/diagram_HLS.png)

![Image](https://www.cdnetworks.com/wos/static-resource/9e836fbe17c141689830b64157c0ba9d/QUIC-PICTURE-05-1024x560.jpg?t=1740733716166)

**Best use case overall**

* Video split into small segments (2s, 1s, or LL-HLS chunks)
* Clients fetch segments independently
* QUIC prevents TCP HOL blocking between segments
* Excellent for:

  * CDNs
  * Mobile clients
  * Congested networks

**Why HTTP/3 wins**

* Loss in one segment does not stall others
* Faster recovery than TCP
* Better QoE on mobile

**This is where major CDNs use HTTP/3 today**

---

### 2. Video Upload / Ingest (Camera → Cloud)

**Example**

* Cameras uploading recordings
* Edge devices sending clips or bursts
* Cloud VMS ingestion

**Why HTTP/3 wins**

* Upload resilience on lossy links
* No TCP slow-start penalties per reconnect
* Encryption by default
* NAT friendly

This is **not live viewing**, but **reliable delivery**.

---

### 3. Large Video File Transfer (VOD, Archival, Sync)

**Example**

* Copying recorded footage
* Syncing datasets between sites
* Background transfer

**Why HTTP/3 wins**

* Better throughput stability under loss
* Stream-level recovery
* No TCP head-of-line stalls

---

### 4. Browser-First Video Delivery (Non-Ultra-Low-Latency)

If:

* Clients are browsers
* You don’t control the transport stack
* Latency tolerance is **≥ 1–2 seconds**

Then HTTP/3 is often the **best available transport**, simply because:

* Browsers support it natively
* No plugins or custom stacks
* Works everywhere HTTPS works

---

### 5. Multi-Path / Roaming Scenarios

**Example**

* Body cams
* Vehicle cameras
* Drones landing/taking off near APs

**Why HTTP/3 wins**

* Connection migration without reconnect
* Survives IP/port changes
* TCP would reset the stream

---

## Where HTTP/3 Is *Not* the Best Choice (Video)

| Scenario                    | Better choice |
| --------------------------- | ------------- |
| Live camera preview (LAN)   | RTP/UDP       |
| Robotics / vision pipelines | RTP/UDP       |
| Multicast distribution      | RTP multicast |
| Sub-100 ms latency          | RTP / WebRTC  |
| Deterministic timing        | RTP           |
| Embedded low-CPU devices    | RTP           |

HTTP/3 **cannot multicast**, has **no media clock**, and adds **encryption + user-space overhead**.

---

## Key Mental Model (Very Important)

Think in terms of **video semantics**:

### HTTP/3 video = **data transfer**

* “Here is a segment / chunk / file”
* Pull-based
* Resilient
* Encrypted
* WAN-friendly

### RTP / WebRTC video = **media transport**

* “Here is a frame at time T”
* Push-based
* Clocked
* Low-latency
* Real-time

When people struggle with HTTP/3 for video, it is almost always because they try to use it as a **media transport**.

---

## One-Line Rule of Thumb

> If your video can be **paused, retried, reordered, or buffered**, HTTP/3 is excellent.
> If your video must be **shown *now***, HTTP/3 is the wrong tool.

---

## Practical Recommendation Summary

| Video use case      | Best transport       |
| ------------------- | -------------------- |
| Live LAN camera     | RTP/UDP              |
| Multi-viewer LAN    | RTP multicast        |
| Browser streaming   | HLS/DASH over HTTP/3 |
| Cloud ingest        | HTTP/3               |
| Mobile WAN delivery | HTTP/3               |
| Ultra-low latency   | WebRTC / RTP         |

---

