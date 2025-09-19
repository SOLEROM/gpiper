#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, json, uuid as uuidlib
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GObject

Gst.init(None)

# ── H.264 SEI (user_data_unregistered) builder ────────────────────────────────
def _emulation_prevention(data: bytes) -> bytes:
    out, zeros = bytearray(), 0
    for b in data:
        if zeros >= 2 and b <= 3:
            out.append(0x03); zeros = 0
        out.append(b)
        zeros = zeros + 1 if b == 0 else 0
    return bytes(out)

def build_user_data_unregistered_sei(uuid_bytes: bytes, user_payload: bytes) -> bytes:
    # payloadType=5 (user_data_unregistered) with 0xFF extension coding
    body = uuid_bytes + user_payload
    size = len(body)
    size_bytes = b''
    while size >= 255:
        size_bytes += b'\xff'; size -= 255
    size_bytes += bytes([size])

    rbsp = b'\x05' + size_bytes + body + b'\x80'          # trailing_bits
    rbsp = _emulation_prevention(rbsp)
    return b'\x00\x00\x00\x01' + b'\x06' + rbsp           # startcode + NAL type 6

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

        sei = build_user_data_unregistered_sei(self.uuid, self._make_payload())

        # Make new buffer = [SEI][orig]
        orig_sz = buf.get_size()
        new_buf = Gst.Buffer.new_allocate(None, len(sei) + orig_sz, None)

        # copy flags / timestamps / metas (NOT data bytes)
        new_buf.copy_into(
            buf,
            Gst.BufferCopyFlags.FLAGS | Gst.BufferCopyFlags.TIMESTAMPS | Gst.BufferCopyFlags.META,
            0,
            0
        )

        # read original bytes once
        ok, o_map = buf.map(Gst.MapFlags.READ)
        if not ok:
            return Gst.PadProbeReturn.OK
        try:
            orig_bytes = bytes(o_map.data)
        finally:
            buf.unmap(o_map)

        # fill new buffer
        new_buf.fill(0, sei)
        new_buf.fill(len(sei), orig_bytes)

        # IMPORTANT: replace the buffer in the probe
        try:
            info.set_data(new_buf)                  # preferred API
        except AttributeError:
            # some GI builds allow direct assignment
            try:
                info.data = new_buf                # fallback
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
    meta_json= sys.argv[5] if len(sys.argv) > 5 else '{"user":"demo","note":"sei"}'
    every_n  = int(sys.argv[6]) if len(sys.argv) > 6 else 0  # 0 = IDR-only

    meta = json.loads(meta_json)

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

    # attach injector to Annex-B / AU pad (hp.src)
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
