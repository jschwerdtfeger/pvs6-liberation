# pvs6-liberation

**Local-first tooling and documentation for SunPower PVS6 owners stranded by the SunPower bankruptcy / SunStrong transition.**

If you own a SunPower system outright and want to monitor, control, and eventually run it **without depending on any third-party cloud**, this project is for you. Everything here works against the PVS6 on your own LAN.

> ⚠️ **Read [SAFETY.md](SAFETY.md) first.** This involves grid-tied power equipment and (optionally) firmware modification. You are responsible for your own system, your utility interconnection agreement, and your local code. No warranty — see [LICENSE](LICENSE).

---

## Who this helps

Two populations, two tracks:

| Track | You are… | What this gives you | Maturity |
|---|---|---|---|
| **A — Liberate** | Already commissioned & working, but worried the cloud dies | Local monitoring + control, cut the cloud, no app dependency | ✅ Works today |
| **B — Recover/Convert** | Stuck at commissioning / system non-operational | Path to local commissioning (firmware route, or Schneider-native conversion) | 🚧 In progress |

Most owners are Track A and can get fully local **without touching firmware** — just the local API below.

---

## Quick start (Track A — no firmware needed)

The PVS6 exposes a documented local API over your LAN. Auth is an **official** SunStrong scheme (published in their own `pypvs` repo):

- Username: `ssm_owner`
- Password: **last 5 characters of your PVS6 serial number**

```bash
# 1. Log in -> session cookie
auth=$(printf 'ssm_owner:<LAST5>' | base64)
curl -sk -c cookies.txt -H "Authorization: basic $auth" "https://<PVS_IP>/auth?login"

# 2. Read live data
curl -sk -b cookies.txt "https://<PVS_IP>/vars?match=livedata&fmt=obj"
curl -sk -b cookies.txt "https://<PVS_IP>/cgi-bin/dl_cgi/devices/list"
```

Then point Home Assistant / Grafana at it, and **firewall-block the PVS6's outbound** to go cloud-free. See [docs/local-api.md](docs/local-api.md).

**Live 1-second stream:** `python3 tools/ws_client.py <PVS_IP>` — see [tools/ws_client.py](tools/ws_client.py).

---

## Track B — recovery / full independence

Two sub-paths, documented honestly with their tradeoffs:

1. **Firmware route** — repoint phone-home to your own host by editing plaintext config in the firmware image. Recon shows this is viable (images are public + unencrypted; phone-home URLs are editable text). The hard kernel remains **local commissioning**. See [docs/firmware-recon.md](docs/firmware-recon.md).
2. **Schneider-native conversion** — remove PVS6/Hub+, run the batteries on their native Schneider Conext brains (XW Pro + Insight Facility + MIO), which commission **locally by design**. Often the more robust answer for stranded systems. *(Conversion guide: TODO.)*

---

## Key findings (so far)

Distilled from offline analysis of the firmware (build 61707) and the live API. Detail in the linked docs.

- **The local API is owner-accessible; the auth lockdown is recent.** Pre-lockdown builds (< 61840) leave the `dl_cgi` commissioning endpoints open; 61840+ (e.g. 61846) gate them behind a cloud-issued installer JWT that **can't be forged offline**. Owner creds (`ssm_owner`) still read live data + ESS state via the varserver on any build. → [build-61707-analysis.md](docs/build-61707-analysis.md)
- **"6 batteries on 1 inverter" can't commission.** The firmware hard-caps at **4 batteries per inverter** — a common, non-obvious reason a SunVault is stuck after an installer consolidated inverters. → [battery-inverter-cap.md](docs/battery-inverter-cap.md)
- **Stuck-system errors split cleanly.** A phantom-inverter "can't connect" (30008-class) is PVS-side and fixable by correcting the owned-set; a battery-pack enumeration shortfall (13036-class) is **BMS-internal** (CAN bus) and is *not* a PVS edit. → [build-61707-analysis.md](docs/build-61707-analysis.md)
- **Downgrades aren't blocked by the old firmware itself.** 61707 has no anti-rollback; any blocker would live in the locked build / U-Boot / eFUSE, cheaply testable on a ~$60 donor. → [downgrade-feasibility.md](docs/downgrade-feasibility.md)
- **Phone-home is repointable / blockable.** Firmware images are public + unencrypted; cloud endpoints are plaintext config; firmware auto-update can be blocked at the network (don't forget cellular). → [firmware-recon.md](docs/firmware-recon.md), [commissioning-server.md](docs/commissioning-server.md)

---

## Status

- [x] Local API auth + endpoint map
- [x] 1-second WebSocket telemetry client
- [x] Firmware recon: distribution, format, phone-home config locations
- [x] Modern build (2024 / 61707) pulled + analyzed — auth tiers, topology storage, ESS, recovery path ([docs/build-61707-analysis.md](docs/build-61707-analysis.md))
- [x] Topology rule: 4-batteries-per-inverter cap ([docs/battery-inverter-cap.md](docs/battery-inverter-cap.md))
- [x] Downgrade feasibility: no anti-rollback in 61707 ([docs/downgrade-feasibility.md](docs/downgrade-feasibility.md))
- [ ] Verified `-k NONE` modified-image load on a donor unit (~$60 bare PVS6)
- [ ] Local recovery (correct owned-set / re-commission) validated on a live system
- [ ] Home Assistant package / dashboard
- [ ] Schneider-native conversion guide

## Prior art / credits

- [SunStrong-Management/pypvs](https://github.com/SunStrong-Management/pypvs) — official local API + auth docs
- [krbaker/hass-sunpower](https://github.com/krbaker/hass-sunpower), [smcneece/ha-esunpower](https://github.com/smcneece/ha-esunpower) — HA integrations
- [koleson PVS6 notes](https://gist.github.com/koleson/5c719620039e0282976a8263c068e85c)
- [MrStrabo/PVS5-6_Reverse_Proxy_Guide](https://github.com/MrStrabo/PVS5-6_Reverse_Proxy_Guide)
- Dolf Starreveld — PVS6 Access and API (PDF)

## Contributing

Stranded owners, RE folks, and Schneider/Conext experts all welcome. The highest-leverage open problems are marked 🚧 above. Please don't commit firmware binaries, serials, or credentials.
