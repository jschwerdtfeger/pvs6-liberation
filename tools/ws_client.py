#!/usr/bin/env python3
"""Minimal pure-stdlib WebSocket client for the PVS6 1-second power stream.

Usage: python3 ws_client.py <PVS_IP> [count]
Reads `count` live `power` frames from ws://<PVS_IP>:9002 (default 10).
No external deps. The telemetry socket is plain ws (no TLS, no auth).

The 1-second stream is gated by /sys/telemetryws/enable on the PVS. If you get
no frames, confirm it's enabled (read it via the authenticated /vars API).
"""
import socket, base64, os, struct, time, json, sys

if len(sys.argv) < 2:
    sys.exit("usage: ws_client.py <PVS_IP> [count]")
HOST = sys.argv[1]
PORT = 9002
COUNT = int(sys.argv[2]) if len(sys.argv) > 2 else 10


def main():
    key = base64.b64encode(os.urandom(16)).decode()
    s = socket.create_connection((HOST, PORT), timeout=8)
    s.sendall(
        (
            f"GET / HTTP/1.1\r\nHost: {HOST}:{PORT}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode()
    )
    s.settimeout(15)
    if b"101" not in s.recv(4096):
        sys.exit("handshake failed")

    buf = bytearray()

    def readn(n):
        while len(buf) < n:
            d = s.recv(8192)
            if not d:
                raise EOFError
            buf.extend(d)
        out = bytes(buf[:n])
        del buf[:n]
        return out

    got = 0
    while got < COUNT:
        b1, b2 = readn(2)
        op, masked, ln = b1 & 0x0F, b2 & 0x80, b2 & 0x7F
        if ln == 126:
            ln = struct.unpack(">H", readn(2))[0]
        elif ln == 127:
            ln = struct.unpack(">Q", readn(8))[0]
        mask = readn(4) if masked else b""
        payload = readn(ln)
        if masked:
            payload = bytes(c ^ mask[i % 4] for i, c in enumerate(payload))
        if op == 8:
            break
        if op in (9, 10):
            continue
        got += 1
        try:
            p = json.loads(payload)["params"]
            print(
                f"pv={p['pv_p']:6.3f}kW  house={p['site_load_p']:6.3f}kW  "
                f"grid={p['net_p']:+7.3f}kW  t={p['time']}"
            )
        except Exception:
            print("frame:", payload[:200])
    s.close()


if __name__ == "__main__":
    main()
