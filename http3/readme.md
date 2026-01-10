# http3 in stream cases

* [when to use](./selectCriteria.md)


A good hybrid architecture (common in real systems)
* Inside LAN / near cameras: RTP/UDP (or RTSP) from cameras to an aggregation node
* At the edge/server: transcode/package to LL-HLS/DASH over HTTP/3 for broad distribution
    This gives you both:
	* real-time efficiency internally
	*  scalable distribution externally

