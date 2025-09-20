#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

Gst.init(None)

# ── Annex-B helpers ───────────────────────────────────────────────────────────
def find_nalus_annexb(data: bytes):
    n = len(data)
    def next_start(pos):
        while True:
            i = data.find(b'\x00\x00\x01', pos)
            if i == -1:
                return -1, 0
            if i > 0 and data[i-1] == 0x00:
                return i-1, 4           # 00 00 00 01
            return i, 3                 # 00 00 01
    start, sc = next_start(0)
    while start != -1:
        pos = start + sc
        if pos >= n:
            break
        nal_type = data[pos] & 0x1F
        nxt, _ = next_start(pos)
        end = nxt if nxt != -1 else n
        yield start, nal_type, pos + 1, end
        if nxt == -1:
            break
        start, sc = next_start(end)

def remove_epb(rbsp: bytes) -> bytes:
    out, zeros, i = bytearray(), 0, 0
    while i < len(rbsp):
        b = rbsp[i]
        if zeros >= 2 and b == 0x03:
            zeros = 0
            i += 1
            continue
        out.append(b)
        zeros = zeros + 1 if b == 0 else 0
        i += 1
    return bytes(out)

def parse_sei_user_data_unregistered(rbsp: bytes):
    rbsp = remove_epb(rbsp)
    out, i, n = [], 0, len(rbsp)
    while i < n:
        pt = 0
        while i < n and rbsp[i] == 0xFF:
            pt += 255; i += 1
        if i >= n: break
        pt += rbsp[i]; i += 1
        ps = 0
        while i < n and rbsp[i] == 0xFF:
            ps += 255; i += 1
        if i >= n: break
        ps += rbsp[i]; i += 1
        payload = rbsp[i:i+ps]; i += ps
        if pt == 5 and len(payload) >= 16:
            out.append((payload[:16], payload[16:]))
        # stop at rbsp_trailing_bits (not strictly needed, parser is tolerant)
    return out

# ── Pad-probe extractor ───────────────────────────────────────────────────────
class SeiExtractor:
    def cb(self, pad, info):
        buf = info.get_buffer()
        if not buf:
            return Gst.PadProbeReturn.OK
        ok, mapinfo = buf.map(Gst.MapFlags.READ)
        if not ok:
            return Gst.PadProbeReturn.OK
        try:
            data = bytes(mapinfo.data)
        finally:
            buf.unmap(mapinfo)

        for _, nal_type, p0, p1 in find_nalus_annexb(data):
            if nal_type != 6:          # SEI
                continue
            for uuid_bytes, body in parse_sei_user_data_unregistered(data[p0:p1]):
                uuid_hex = "-".join([
                    uuid_bytes[0:4].hex(),
                    uuid_bytes[4:6].hex(),
                    uuid_bytes[6:8].hex(),
                    uuid_bytes[8:10].hex(),
                    uuid_bytes[10:16].hex()
                ])
                try:
                    txt = body.decode("utf-8", errors="replace")
                except Exception:
                    txt = repr(body)
                print(f"[SEI] uuid={uuid_hex} pts={buf.pts} dts={buf.dts} payload={txt}")
        return Gst.PadProbeReturn.OK

def main():
    # usage:
    # python extract_sei_receiver.py 5000 ../out/received.mp4
    port    = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    outfile = sys.argv[2] if len(sys.argv) > 2 else "../out/received.mp4"

    # Probe Annex-B/AU branch; mp4 branch is repacked AVC for saving
    pipe_str = f"""
      tcpserversrc host=0.0.0.0 port={port} !
      matroskademux name=demux demux.video_0 !
      h264parse config-interval=-1 name=hp !
        video/x-h264,stream-format=byte-stream,alignment=au !
      tee name=t !
      queue !
        h264parse config-interval=1 !
        video/x-h264,stream-format=avc,alignment=au !
        mp4mux faststart=true ! filesink location={outfile} sync=false
      t. ! fakesink sync=false
    """

    pipeline = Gst.parse_launch(pipe_str)

    # attach extractor to Annex-B / AU pad
    h264parse_au = pipeline.get_by_name("hp")
    pad = h264parse_au.get_static_pad("src")
    pad.add_probe(Gst.PadProbeType.BUFFER, SeiExtractor().cb)

    pipeline.set_state(Gst.State.PLAYING)
    bus = pipeline.get_bus()
    while True:
        msg = bus.timed_pop_filtered(Gst.SECOND, Gst.MessageType.ERROR | Gst.MessageType.EOS)
        if msg:
            if msg.type == Gst.MessageType.ERROR:
                err, dbg = msg.parse_error()
                print("ERR:", err, "\nDBG:", dbg)
            break
    pipeline.set_state(Gst.State.NULL)

if __name__ == "__main__":
    main()
