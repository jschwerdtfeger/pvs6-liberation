# PVS6 Local API

The PVS6 exposes a documented HTTP(S) API on your LAN. On firmware build ≥ 61840 (≈2025.x) requests must be
authenticated; older builds were open. The auth scheme below is **official** — published by SunStrong in their
own [`pypvs`](https://github.com/SunStrong-Management/pypvs) repo (`doc/LocalAPI.md`).

> Replace `<PVS_IP>` with your PVS6's LAN IP and `<LAST5>` with the last 5 chars of your serial.
> Never commit your real serial/credentials.

## Auth

- Username: `ssm_owner`
- Password: last 5 characters of the PVS6 serial number
- Self-signed HTTPS — use `curl -k`.

```bash
auth=$(printf 'ssm_owner:<LAST5>' | base64)
curl -sk -c cookies.txt -H "Authorization: basic $auth" "https://<PVS_IP>/auth?login"
# -> {"session":"..."} plus a `session` cookie. Pass -b cookies.txt on every call.
# The session expires; re-run /auth?login to refresh.
```

## Reading data (`/vars` — varserver)

```bash
curl -sk -b cookies.txt "https://<PVS_IP>/vars?name=/sys/livedata/site_load_p"   # one leaf (house load, kW)
curl -sk -b cookies.txt "https://<PVS_IP>/vars?match=livedata&fmt=obj"            # live power/energy subtree
curl -sk -b cookies.txt "https://<PVS_IP>/vars?match=/net&fmt=obj"                # network/interface state
```

Key livedata leaves (kW / lifetime kWh): `pv_p`, `site_load_p`, `net_p` (negative = exporting), `pv_en`,
`site_load_en`, `net_en`, plus `ess_p`/`soc` (battery, `nan` if no ESS / ESS off).

Notes: `/vars` is whitelist-ish per-leaf; parent nodes may 400. `match=/` dumps the whole tree but is heavy —
prefer targeted subtrees for polling. Data via `/vars` refreshes ~every 5 min; use the WebSocket for real-time.

## Device inventory

```bash
curl -sk -b cookies.txt "https://<PVS_IP>/cgi-bin/dl_cgi/devices/list"
```
Returns PVS + power meters + PV microinverters with per-device `STATE`. (Battery/XW Pro ESS devices live behind
the Hub+/ESS subsystem, not in this list.) Note: legacy `dl_cgi?Command=DeviceList` was removed — use the
path-style `dl_cgi/devices/list`.

## Real-time (1-second) WebSocket

`ws://<PVS_IP>:9002` — plain ws, no TLS, no auth. Emits a `power` notification every second. Gated by
`/sys/telemetryws/enable`. See [`tools/ws_client.py`](../tools/ws_client.py):
```bash
python3 tools/ws_client.py <PVS_IP> 20
```

## Full API spec

The box serves its own OpenAPI spec at `GET /cgi-bin/swagger.json` (authenticated) — "DL_CGI Interface Spec".
It documents ~90 operations: device discovery/replace, commissioning, grid profile/export limit, network
config, firmware upgrade, ESS status, etc. **Regenerate it from your own unit** rather than relying on a copy
(it's the authoritative, version-matched reference). ⚠️ Most non-GET operations change hardware/grid state —
see [SAFETY.md](../SAFETY.md).

## Going cloud-free (Track A)

A *commissioned* system keeps operating with no internet. To cut the cloud for monitoring:
1. Firewall-block the PVS6's outbound at your router (it publishes telemetry to AWS IoT).
2. Optionally `DELETE /cgi-bin/dl_cgi/network/tunnel` to drop the remote SSH tunnel, and tighten
   `network/firewallSettings` / `network/whitelist`.
3. Read everything locally via the API + WebSocket into Home Assistant / Grafana.
