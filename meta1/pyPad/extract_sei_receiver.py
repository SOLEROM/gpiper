#!/usr/bin/env python3
import sys, struct
from gi.repository import Gst, GObject

Gst.init(None)

def find_nalus_annexb(data: bytes):
    """Yield (offset, nal_type, payload_start, payload_end) for Annex-B NALs."""
    i, n = 0, len(data)
    def next_start(pos):
        while True:
            pos = data.find(b"\x00\x00\x01", pos)
            if pos == -1:
                return -1, 0
            # check 4-byte start code too
            if pos > 0 and data[pos-1] == 0x00:
                return pos-1, 4
            return pos, 3

    start, sc = next_start(0)
    while start != -1:
        pos = start + sc
        if pos >= n: break
        nal_hdr = data[pos]
        nal_type = nal_hdr & 0x1F
        # find next start
        nxt, _ = next_start(pos)
        end = nxt if nxt != -1 else n
        yield start, nal_type, pos+1, end  # payload excludes nal header
        if nxt == -1: break
        start, sc = next_start(end)

def remove_epb(rbsp: bytes) -> bytes:
    """Remove emulation prevention bytes 0x03 after 00 00."""
    out = bytearray()
    zeros = 0
    i = 0
    while i < len(rbsp):
        b = rbsp[i]
        if zeros >= 2 and b == 0x03:
            # skip this EPB, reset zeros but don't append
            zeros = 0
            i += 1
            continue
        out.append(b)
        zeros = zeros + 1 if b == 0 else 0
        i += 1
    return bytes(out)

def parse_sei_user_data_unregistered(rbsp: bytes):
    """Return list of (uuid_bytes, payload_bytes)."""
    # undo EPBs first
    rbsp = remove_epb(rbsp)
    out = []
    i = 0
    n = len(rbsp)
    while i < n:
        # payloadType
        pt = 0
        while i < n and rbsp[i] == 0xFF:
            pt += 255; i += 1
        if i >= n: break
        pt += rbsp[i]; i += 1
        # payloadSize
        ps = 0
        while i < n and rbsp[i] == 0xFF:
            ps += 255; i += 1
        if i >= n: break
        ps += rbsp[i]; i += 1
        payload = rbsp[i:i+ps]
        i += ps
        # trailing bits may follow at the very end; ignore here
        if pt == 5 and len(payload) >= 16:  # user_data_unregistered
            uuid = payload[:16]
            body = payload[16:]
            out.append((uuid, body))
        # continue to next SEI message
    return out

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
            if nal_type != 6:
                continue
            sei_payload = data[p0:p1]
            msgs = parse_sei_user_data_unregistered(sei_payload)
            for uuid_bytes, body in msgs:
                # pretty-print
                uuid_hex = "-".join([
                    uuid_bytes[0:4].hex(),
                    uuid_bytes[4:6].hex(),
                    uuid_bytes[6:8].hex(),
                    uuid_bytes[8:10].hex(),
                    uuid_bytes[10:16].hex()
                ])
                try:
                    txt = body.decode("utf-8", errors="replace")
                except:
                    txt = repr(body)
                print(f"[SEI] uuid={uuid_hex} pts={buf.pts} dts={buf.dts} payload={txt}")
        return Gst.PadProbeReturn.OK

def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    outfile = sys.argv[2] if len(sys.argv) > 2 else "../out/received.mp4"

    pipe_str = f"""
    tcpserversrc host=0.0.0.0 port={port} !
    matroskademux name=demux demux.video_0 !
    h264parse config-interval=-1 name=hp ! video/x-h264,stream-format=byte-stream,alignment=au !
    tee name=t !
    queue ! mp4mux faststart=true ! filesink location={outfile} sync=false
    t. ! fakesink sync=false
    """
    pipeline = Gst.parse_launch(pipe_str)
    h264parse = pipeline.get_by_name("hp")
    pad = h264parse.get_static_pad("src")
    pad.add_probe(Gst.PadProbeType.BUFFER, SeiExtractor().cb)

    pipeline.set_state(Gst.State.PLAYING)
    bus = pipeline.get_bus()
    while True:
        msg = bus.timed_pop_filtered(Gst.SECOND, Gst.MessageType.ERROR | Gst.MessageType.EOS)
        if msg:
            break
    pipeline.set_state(Gst.State.NULL)

if __name__ == "__main__":
    GObject.threads_init()
    main()
