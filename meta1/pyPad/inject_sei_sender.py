#!/usr/bin/env python3
import sys, json, uuid as uuidlib
from gi.repository import Gst, GObject

Gst.init(None)

# ---------- minimal H.264 SEI builder (user_data_unregistered) ----------
def _emulation_prevention(data: bytes) -> bytes:
    out = bytearray()
    zeros = 0
    for b in data:
        if zeros >= 2 and b <= 3:
            out.append(0x03)  # emulation prevention byte
            zeros = 0
        out.append(b)
        if b == 0:
            zeros += 1
        else:
            zeros = 0
    return bytes(out)

def build_user_data_unregistered_sei(uuid_bytes: bytes, user_payload: bytes) -> bytes:
    # SEI payloadType coding (0x05 = user_data_unregistered)
    payload_type = b'\x05'
    # payload = 16B UUID + your payload
    body = uuid_bytes + user_payload
    # payloadSize coding with 0xFF extensions if needed
    size = len(body)
    size_bytes = b''
    while size >= 255:
        size_bytes += b'\xff'
        size -= 255
    size_bytes += bytes([size])
    # rbsp: payloadType + payloadSize + body + rbsp_trailing_bits (1000 0000)
    rbsp = payload_type + size_bytes + body + b'\x80'
    rbsp = _emulation_prevention(rbsp)
    # NAL start code + NAL header (type=6)
    return b'\x00\x00\x00\x01' + b'\x06' + rbsp

# ---------- pad probe: prepend SEI on IDR (key) frames ----------
class SeiInjector:
    def __init__(self, uuid_str: str, meta_dict: dict, every_n: int = 0):
        self.uuid = uuidlib.UUID(uuid_str).bytes
        self.meta = meta_dict
        self.every_n = every_n
        self.frame_idx = 0

    def _make_payload(self):
        # keep it tiny; JSON is fine for demo
        self.meta["frame"] = self.frame_idx
        return json.dumps(self.meta, separators=(",", ":")).encode("utf-8")

    def cb(self, pad, info):
        buf = info.get_buffer()
        if not buf:
            return Gst.PadProbeReturn.OK
        self.frame_idx += 1

        # keyframe check: DELTA_UNIT unset => keyframe
        is_key = not buf.has_flags(Gst.BufferFlags.DELTA_UNIT)
        if not is_key and self.every_n > 0 and (self.frame_idx % self.every_n != 0):
            return Gst.PadProbeReturn.OK
        if not is_key and self.every_n <= 0:
            return Gst.PadProbeReturn.OK

        payload = self._make_payload()
        sei = build_user_data_unregistered_sei(self.uuid, payload)

        # stitch: new = [sei][orig]
        orig_sz = buf.get_size()
        new_buf = Gst.Buffer.new_allocate(None, len(sei) + orig_sz, None)
        # copy timing/flags/meta
        new_buf.copy_into(buf, Gst.BufferCopyFlags.FLAGS | Gst.BufferCopyFlags.TIMESTAMPS | Gst.BufferCopyFlags.META, 0, -1)

        # write bytes
        success, mapinfo = new_buf.map(Gst.MapFlags.WRITE)
        if not success:
            return Gst.PadProbeReturn.OK
        try:
            mapinfo.data[0:len(sei)] = sei
            # extract original payload
            o_success, o_map = buf.map(Gst.MapFlags.READ)
            if not o_success:
                return Gst.PadProbeReturn.OK
            try:
                mapinfo.data[len(sei):len(sei)+orig_sz] = o_map.data[:orig_sz]
            finally:
                buf.unmap(o_map)
        finally:
            new_buf.unmap(mapinfo)

        info.set_buffer(new_buf)
        return Gst.PadProbeReturn.OK

def main():
    # usage:
    # python inject_sei_sender.py 127.0.0.1 5000 ../demo/test2sec.avi <uuid> '{"user":"vladi","task":"demo"}'
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
    infile = sys.argv[3] if len(sys.argv) > 3 else "../demo/test2sec.avi"
    uuid_str = sys.argv[4] if len(sys.argv) > 4 else "12345678-1234-1234-1234-1234567890ab"
    meta_json = sys.argv[5] if len(sys.argv) > 5 else '{"user":"demo","note":"sei"}'

    meta = json.loads(meta_json)

    pipe_str = f"""
    filesrc location={infile} !
    decodebin ! videoconvert !
    x264enc tune=zerolatency speed-preset=ultrafast bitrate=2000 key-int-max=30 !
    h264parse config-interval=-1 name=hp ! video/x-h264,stream-format=byte-stream,alignment=au !
    matroskamux streamable=true !
    tcpclientsink host={host} port={port}
    """
    pipeline = Gst.parse_launch(pipe_str)
    h264parse = pipeline.get_by_name("hp")
    injector = SeiInjector(uuid_str, meta, every_n=0)  # set every_n>0 to inject regularly
    pad = h264parse.get_static_pad("src")
    pad.add_probe(Gst.PadProbeType.BUFFER, injector.cb)

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
