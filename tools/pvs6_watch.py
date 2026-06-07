#!/usr/bin/env python3
"""pvs6_watch.py — passively log every host your PVS6 talks to.

Wraps tcpdump, filters to the PVS6's IP, and reports the distinct endpoints it
contacts: DNS lookups (the gold — real hostnames), new outbound connections
(dst IP:port), and a best-effort category (telemetry / firmware / MQTT / etc.).
Writes a timestamped JSONL log so a commissioning-day capture is on the record.

This is passive observation of YOUR OWN device on YOUR OWN network. It changes
nothing — read-only.

VISIBILITY: tcpdump only sees the PVS6's traffic if it runs somewhere in that
traffic's path. Run it on:
  - your router / firewall (or Pi-hole box), or
  - a Pi set as the PVS6's gateway or DNS server, or
  - a Mac/laptop that can see the segment (mirror port, or temporarily inline).
On a plain switched LAN, a laptop on Wi-Fi will NOT see a wired PVS6's traffic.

USAGE:
  sudo python3 pvs6_watch.py --pvs-ip 192.168.1.50 --iface en0
  sudo python3 pvs6_watch.py --pvs-ip 192.168.1.50 --iface eth0 --duration 1800
  (Ctrl-C to stop; a summary table prints on exit.)
"""
import argparse, json, re, signal, subprocess, sys, socket
from datetime import datetime, timezone

# --- known SunPower/SunStrong + AWS endpoints -> human category ---------------
CATEGORIES = [
    ("collector.sunpowermonitor.com", "telemetry/command (legacy collector)"),
    ("fwupgrade.sunpowermonitor.com", "firmware reachability probe"),
    ("firmware-update-api", "firmware version API"),
    ("fw-assets-pvs6", "firmware image CDN"),
    ("register.edp", "registration / cert-manager"),
    ("-ats.iot.", "AWS IoT MQTT broker"),
    (".iot.", "AWS IoT MQTT broker"),
    ("s3.", "AWS S3"),
    ("amazonaws.com", "AWS (generic)"),
    ("edp.sunpower.com", "SunStrong cloud"),
    ("sunpower", "SunPower (other)"),
    ("ntp", "NTP time sync"),
    ("pool.ntp.org", "NTP time sync"),
]

def categorize(host: str) -> str:
    h = host.lower()
    for needle, label in CATEGORIES:
        if needle in h:
            return label
    return "unknown"

DNS_Q = re.compile(r"\bA{1,4}\? ([A-Za-z0-9._-]+?)\.? \(")
# matches "IP <src>.<port> > <dst>.<port>: Flags [S]," (SYN, not SYN-ACK)
SYN = re.compile(r"IP6?\s+(\S+?)\.(\d+)\s+>\s+(\S+?)\.(\d+):\s+Flags \[S\](?!\.)")

_rev_cache = {}
def rev_dns(ip: str) -> str:
    if ip not in _rev_cache:
        try:
            socket.setdefaulttimeout(1.0)
            _rev_cache[ip] = socket.gethostbyaddr(ip)[0]
        except Exception:
            _rev_cache[ip] = ""
    return _rev_cache[ip]

def main():
    ap = argparse.ArgumentParser(description="Passively log what the PVS6 talks to.")
    ap.add_argument("--pvs-ip", required=True, help="PVS6 LAN IP")
    ap.add_argument("--iface", default=None, help="capture interface (e.g. en0, eth0)")
    ap.add_argument("--duration", type=int, default=0, help="seconds to run (0 = until Ctrl-C)")
    ap.add_argument("--out", default=None, help="JSONL log path")
    args = ap.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = args.out or f"pvs6-watch-{stamp}.jsonl"
    bpf = (f"host {args.pvs_ip} and "
           f"(udp port 53 or (tcp[tcpflags] & (tcp-syn|tcp-ack) == tcp-syn))")
    cmd = ["tcpdump", "-l", "-n", "-q"]
    if args.iface:
        cmd += ["-i", args.iface]
    cmd += [bpf]

    print(f"# watching PVS6 {args.pvs_ip}  iface={args.iface or 'default'}  log={out_path}")
    print(f"# filter: {bpf}\n# (new endpoints print as they appear; Ctrl-C for summary)\n")

    seen = {}  # key -> {count, first, category, label, port}
    logf = open(out_path, "a")

    def record(kind, host, ip="", port=""):
        key = host or f"{ip}:{port}"
        cat = categorize(host or rev_dns(ip) or ip)
        now = datetime.now(timezone.utc).isoformat()
        logf.write(json.dumps({"ts": now, "kind": kind, "pvs": args.pvs_ip,
                               "endpoint": host or ip, "port": port,
                               "rdns": rev_dns(ip) if ip else "", "category": cat}) + "\n")
        logf.flush()
        if key not in seen:
            seen[key] = {"count": 0, "first": now, "category": cat, "port": port,
                         "label": rev_dns(ip) if (ip and not host) else ""}
            extra = f"  [{seen[key]['label']}]" if seen[key]["label"] else ""
            print(f"+ {kind:5} {key:42} {cat}{extra}")
        seen[key]["count"] += 1

    def summary(*_):
        print("\n=== PVS6 endpoints seen ===")
        for key, v in sorted(seen.items(), key=lambda kv: -kv[1]["count"]):
            lbl = f"  ({v['label']})" if v["label"] else ""
            print(f"  {v['count']:5}x  {key:42} {v['category']}{lbl}")
        print(f"\nlog: {out_path}")
        logf.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, summary)
    if args.duration:
        signal.signal(signal.SIGALRM, summary)
        signal.alarm(args.duration)

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except FileNotFoundError:
        sys.exit("tcpdump not found — install it or run on a box that has it.")

    for line in proc.stdout:
        m = DNS_Q.search(line)
        if m:
            record("dns", m.group(1).lower())
            continue
        s = SYN.search(line)
        if s:
            src_ip, _sp, dst_ip, dport = s.group(1), s.group(2), s.group(3), s.group(4)
            if src_ip.startswith(args.pvs_ip):  # outbound from the PVS6
                record("conn", "", dst_ip, dport)

    err = proc.stderr.read()
    if err and not seen:
        print(err, file=sys.stderr)
        if "permission" in err.lower() or "operation not permitted" in err.lower():
            print("\nHint: run with sudo (tcpdump needs packet-capture privilege).", file=sys.stderr)

if __name__ == "__main__":
    main()
