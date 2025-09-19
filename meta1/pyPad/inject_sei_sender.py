#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, json, uuid as uuidlib
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

Gst.init(None)

# ── H.264 SEI (user_data_unregistered) builder ────────────────────────────────
def _emulation_prevention(data: bytes) -> bytes:
    out, zeros = bytearray(), 0
    for b in data:
        if zeros >= 2 and b <= 3:
            out.append(0x03)
            zeros = 0
        out.append(b)
        zeros = zeros + 1 if b == 0 else 0
    return bytes(out)

def build_user_data_unregistered_sei(uuid_bytes: bytes, user_payload: bytes) -> bytes:
    # payloadType=5 (user_data_unregistered), size coded with 0xFF extension
    body = uuid_bytes + user_payload
    size = len(body)
    size_bytes = b''
    while size >= 255:
        size_bytes += b'\xff'
        size -= 255
    size_bytes += bytes([size])

    rbsp = b'\x05' + size_bytes + body + b'\x80'  # PT=5 + size + body + trailing_bits
    rbsp = _emulation_prevention(rbsp)
    # startcode + NAL header(type=6 SEI) + rbsp
    return b'\x00\x00\x00\x01' + b'\x06' + rbsp

# ── Annex-B helpers ───────────────────────────────────────────────────────────
def annexb_iter_nalus(data: bytes):
    """
    Yield tuples: (start, end, startcode_len, nal_type) over an Annex-B access unit (AU).
    """
    n = len(data); i = 0
    while True:
        j = data.find(b'\x00\x00\x01', i); sc = 3
        if j == -1:
            break
        if j > 0 and data[j-1] == 0x00:
            j -= 1; sc = 4
        k = data.find(b'\x00\x00\x01', j + sc)
        if k > 0 and k > j + sc and data[k-1] == 0x00:
            k -= 1
        end = k if k != -1 else n
        if j + sc < n:
            nalh = data[j + sc]
            nal_type = nalh & 0x1F
            yield j, end, sc, nal_type
        if k == -1:
            break
        i = end

def insertion_pos_for_sei(au_bytes: bytes) -> int:
    """
    Choose a safe insertion point for a new SEI:
    - After any leading AUD(9)/SEI(6)/SPS(7)/PPS(8)
    - Before first VCL slice (IDR=5 or non-IDR=1)
    """
    insert_at = 0
    for start, end, _sc, nal_type in annexb_iter_nalus(au_bytes):
        if nal_type in (9, 6, 7, 8):
            insert_at = end
            continue
        if nal_type in (1, 5):  # first slice
            insert_at = start
            break
        insert_at = end
    return insert_at

# ── Pad-probe injector ────────────────────────────────────────────────────────
class SeiInjector:
    def __init__(self, uuid_str: str, meta_dict: dict, every_n: int = 0):
        self.uuid = uuidlib.UUID(uuid_str).bytes
        self.meta = dict(meta_dict)
        self.every_n = int(every_n)
        self.frame_idx = 0

    def _make_payload(self) -> bytes:
        self.meta["frame"] = self.frame_idx
        return json.dumps(self.meta, separators=(",", ":")).encode("utf-8")

    def cb(self, pad, info):
        buf = info.get_buffer()
        if not buf:
            return Gst.PadProbeReturn.OK

        self.frame_idx += 1
        is_key = not buf.has_flags(Gst.BufferFlags.DELTA_UNIT)

        # Inject on IDR; or every N if requested
        if not is_key and (self.every_n <= 0 or (self.frame_idx % self.every_n) != 0):
            return Gst.PadProbeReturn.OK

        ok, o_map = buf.map(Gst.MapFlags.READ)
        if not ok:
            return Gst.PadProbeReturn.OK
        try:
            au_bytes = bytes(o_map.data)
        finally:
            buf.unmap(o_map)

        # Build our SEI and compute insertion point
        payload = self._make_payload()
        sei = build_user_data_unregistered_sei(self.uuid, payload)
        ins = insertion_pos_for_sei(au_bytes)

        # Compose new AU
        new_bytes = au_bytes[:ins] + sei + au_bytes[ins:]

        # Allocate new buffer and copy timing/meta/flags
        new_buf = Gst.Buffer.new_allocate(None, len(new_bytes), None)
        new_buf.copy_into(
            buf,
            Gst.BufferCopyFlags.FLAGS | Gst.BufferCopyFlags.TIMESTAMPS | Gst.BufferCopyFlags.META,
            0, 0
        )
        new_buf.fill(0, new_bytes)

        # DEBUG
        if is_key or (self.every_n and (self.frame_idx % self.every_n) == 0):
            nal_types = [nt for *_t, nt in annexb_iter_nalus(new_bytes)]
            print(f"[INJECT] frame={self.frame_idx} key={is_key} inserted_at={ins} nals={nal_types}")
            try:
                print(f"[INJECT] payload={payload.decode('utf-8', 'replace')}")
            except Exception:
                pass

        # Replace the buffer in the probe
        try:
            info.set_data(new_buf)  # preferred GI API
        except AttributeError:
            try:
                info.data = new_buf   # fallback
            except Exception:
                return Gst.PadProbeReturn.OK
        return Gst.PadProbeReturn.REPLACE

def main():
    # usage:
    # python inject_sei_sender.py 127.0.0.1 5000 ../demo/test2sec.avi <uuid> '{"user":"vladi"}' [every_n]
    host     = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port     = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
    infile   = sys.argv[3] if len(sys.argv) > 3 else "../demo/test2sec.avi"
    uuid_str = sys.argv[4] if len(sys.argv) > 4 else "12345678-1234-1234-1234-1234567890ab"
    meta_json= sys.argv[5] if len(sys.argv) > 5 else '{"user":"demo","task":"gparted-pipe","note":"sei"}'
    every_n  = int(sys.argv[6]) if len(sys.argv) > 6 else 0  # 0 = IDR-only

    meta = json.loads(meta_json)

    # 1) Produce Annex-B/AU (for injection on hp.src)
    # 2) Repack to AVC for matroskamux (which doesn't accept byte-stream caps)
    pipe_str = f"""
      filesrc location={infile} !
      decodebin ! videoconvert !
      x264enc tune=zerolatency speed-preset=ultrafast bitrate=2000 key-int-max=30 !
      h264parse config-interval=-1 name=hp !
        video/x-h264,stream-format=byte-stream,alignment=au !
      h264parse config-interval=1 !
        video/x-h264,stream-format=avc,alignment=au !
      matroskamux streamable=true !
      tcpclientsink host={host} port={port}
    """

    pipeline = Gst.parse_launch(pipe_str)

    # Attach injector to Annex-B/AU pad (hp.src)
    h264parse_au = pipeline.get_by_name("hp")
    pad = h264parse_au.get_static_pad("src")
    pad.add_probe(Gst.PadProbeType.BUFFER, SeiInjector(uuid_str, meta, every_n).cb)

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
