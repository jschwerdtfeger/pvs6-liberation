> Auto-generated from offline, read-only analysis of an owner's own PVS6 firmware (right-to-repair, build 2019.8.26.249). Security-sensitive specifics are withheld from public docs pending responsible disclosure.

---

All facts now verified directly from the image. The `fwup -k NONE` signature-skip option is confirmed verbatim (`-k key ... If key is set to NONE, no signature verification`), and the `automatic_upgrade` → `checkFW` → `fwup -v <link>` flow is confirmed with `COMMISSIONING_FILE` and `interval_days=7`. I have everything needed to produce the merged document.

## PVS6 architecture (firmware build 2019.8.26.249)

### Overview

This is a read-only map of an unpacked, pre-lockdown PVS6 (PV Supervisor) rootfs image (ext4, 256 MB), build `2019.08.26.249`, built from `git@github.com:SunPower/pvs_meta-layers.git` (branch `staging-prod-adama`, timestamp `20190826113152` per `/etc/spwr_version`, `/etc/version`). The OS is a systemd-based OpenEmbedded/Yocto Linux; hostname `pvs6` (`/etc/hostname`).

The device acquires solar production data from on-roof microinverters and meters over powerline communication (PLC), aggregates it, archives it to flash, and ships it to SunPower's cloud over two parallel channels: a legacy HTTP "collector" channel (`data_logger`) and an AWS IoT MQTT channel (`communicator`). A local, unauthenticated HTTP API on `/www` (served by lighttpd, backed by the `dl_cgi` binary) is what the SunPower app and third-party Home Assistant integrations poll. Firmware updates arrive via two paths (a polled pull path and an MQTT push path) that both terminate in `/home/data_logger/bin/fwup`.

```
        on-roof PV hardware (microinverters / revenue meters)
                  │  AC powerline (PLC)
                  ▼
        ┌──────────────────────┐
        │  sidecar / eASIC PLC  │  co-processor ("scooter")
        │  modem  (UART)        │  /home/mime/plctools/e-asic/*.bin
        └──────────┬───────────┘
                   │ uart:/dev/ttyUSB3  (COBS / ARCPAC framing)
                   ▼
        ┌──────────────────────┐
        │  mime daemon          │  /home/mime/bin/mime
        │  (PLC ↔ MI/meter)     │
        └──────────┬───────────┘
                   │ local UDP IPC  (/mimecmdq queue; /tmp/mr%u, /tmp/sfacli%u)
                   ▼
        ┌──────────────────────┐         ┌───────────────────────────┐
        │  data_logger daemon   │◄───────►│  dl_cgi (local API engine) │
        │  /home/data_logger    │ cmd Q   │  /www/cgi-bin/dl_cgi        │
        │  poll→aggregate→archive│        └─────────────┬─────────────┘
        └───┬───────────────┬───┘                       │ lighttpd :80 (no auth/TLS)
            │ HTTP          │ SysV/POSIX IPC msg queues  │ wildcard CORS
            ▼               ▼                            ▼
  collector.sunpowermonitor.com   ┌──────────────────────┐   LAN / Wi-Fi-AP clients
  (Data + Command .aspx)          │  communicator daemon  │   (SunPower app, HA integration)
                                  │  /home/communicator   │
                                  └──────────┬───────────┘
                                             │ MQTT/TLS (mbedTLS, client cert)
                                             ▼
                            a1wvyyv74srg62.iot.us-west-2.amazonaws.com  (AWS IoT)

  Update path:  automatic_upgrade.timer → automatic_upgrade → /www/cgi-bin/checkFW
                → firmware-update-api.edp.sunpower.com/pvs6/ → fwup -v <url>   (pull)
                communicator EDPCommand.UpgradeFirmware (upd_spec_url)         (push)
  Identity:     cert_client.sh → register.edp.sunpower.com:3001 → /app0/secrets/mqtt/
```

---

### Subsystem: `data_logger` (telemetry engine)

`/home/data_logger` is the solar telemetry engine: a long-running C++ daemon (`bin/data_logger`, inode 778, ARM ELF, not stripped) that polls microinverters/meters, aggregates readings on fixed intervals, archives protobuf messages to flash, and uploads them to the cloud collector. Lua scripts supply all configuration and per-protocol register maps.

Verified key files:
- `config.lua` (inode 829) and identical seed `default_config.lua` (inode 786) — define `param_table`; `devices.lua`/`default_devices.lua` are empty (`devices = {}` — no devices provisioned in this image).
- `lua_scripts/` (inode 787): `basic_param.lua` (default polled sets `iv_basic` key 130, `pm_basic` key 140, `gfm_basic` key 170), `parse_config.lua` (register address/count/format/scaler per protocol), `modbus_map.lua`, SunSpec drivers `sunspec_iv.lua`/`sunspec_ac_meter.lua` plus ~30 vendor drivers (fronius, sma, kaco, power_one, schneider_gt, etc.).
- `bin/` (inode 766): `data_logger` (778), `dl_cgi` (774), `dl_send_cmd` (776, CLI client to the daemon command queue), `fwup` (768), `read_archive` (775), `mbclient` (772), `sysmon` (767), `file_rotate` (773), `recovery` (777), `connect`/`download` (771/770), `sendversion.sh` (769).
- `util/` (inode 761): `sysstats.sh`, `reboot.sh`, and `‹redacted-key›` (inode 764, mode 0600) — **a plaintext RSA private key embedded in the image** (verified header `-----BEGIN ‹redacted›-----`, 1675 bytes).

Verified `param_table` values (from `config.lua`):
- Telemetry channel: `data_chan_url_1/2/3 = http://collector.sunpowermonitor.com/Data/SMS2DataCollector.aspx`; `data_chan_conn_int=300`s, `data_chan_fail_int=120`s.
- Command channel: `cmd_chan_url_1/2/3 = http://collector.sunpowermonitor.com/Command/SMS2DataCollector.aspx`; `cmd_chan_conn_int=1800`s, `cmd_chan_fail_int=600`s.
- Polling/aggregation: `device_scan_int=15`s, `device_aggregation_int=300`s, `dl_report_int=300`s.
- Archiving: `archive_data_quota=50e6`, `archive_metadata_quota=500e3`.
- Discovery: `sunspec_ip_range = "172.27.153.50;172.27.153.99"`; `zero_export = {}` (empty here).

How it works: `ConfigManager` loads the Lua config; `DataAcquisition`/`DeviceIf`/`Protocols` poll each device's `*_basic` set every 15 s (GFM at 1 s); `DataAccumulator` reduces readings over the 300 s window; `DataArchiver` writes protobuf to `arc_data/%08x.adf` + `arc_meta/%08x.amf` (checksummed, quota-capped); `ServerComm` uploads to `data_chan_url_*` and polls `cmd_chan_url_*`. Device data for the local API is fetched live from the running daemon over its command queue (via `Cmdif_*`), not from archives. Microinverter/meter operations go to the `mime` daemon over a separate POSIX queue `/mimecmdq` (`MIMECmd*`/`MIMERsp*` classes).

---

### Subsystem: `mime` (PLC to microinverters/meters)

`/home/mime` owns the powerline link to SunPower/SolarBridge (and, compiled-in, Enphase) microinverters and revenue meters. Two component trees, both built 2019-08-23 (`cb3402da`):

- `/home/mime/bin` — the production MIME daemon (`mime`, inode 711, 5,635,340 B) and its multi-call IPC client `MIMECommand` (inode 743) with `mc_*` symlinks (verified `mc_lease` → `MIMECommand`).
- `/home/mime/plctools` — lower-level PLC debug/mfg tools (`plc_tool`, inode 636) with ~50 `mc_*`/`sc*` symlinks, Python orchestration (`plctools.py`, `pvinfo.py`, `toi.py`), and eASIC/sidecar firmware images under `e-asic/`.

Two-hop architecture: the host CPU runs `mime`, which talks over a UART (default `uart:/dev/ttyUSB3`) to the **sidecar** — an eASIC-based PLC modem co-processor (internal codename "scooter"). Transport modules in the daemon: `scooter_uart.c`, `cobs.c` (COBS framing), `arcpac_*.c` (ARCPAC packet protocol), `enph_xaction.c`/`enphase_command.c` (Enphase variant). Clients reach MIME over local UDP datagram IPC (socket-path templates `/tmp/mr%u`, `/tmp/sfacli%u`); the IPC wire format is `MIMEMsgHdr_t {msgType, len, txnID}` + typed payload (`mimeif.h`, inode 734). `preinstall.sh` seeds the default cadence: MI poll 150 s, meter 5 s, stats 3600 s, police 86400 s, upgrade-check 30 s.

Co-processor firmware (separately flashable):
- eASIC/sidecar PLC modem fw: `/home/mime/plctools/e-asic/*.bin` (e.g. `e-asic_firmware_for_mime_v1.6.0.bin`), flashed by `easic0dayfwup.sh`/`scupgrade.sh` via `scupg`+`screset`; also `sidecarupg_10.bin` (`SIDECARBUILDNO=10`) in `/home/mime/bin`.
- Microinverter/MPPT fw: `miupg-*.bin` and `mppt_upd_ee_*.{upg,bin}` staged in the **directory** `/home/mime/bin/mifwup` (inode 713 — verified a directory, **not** a binary), applied over PLC via the MIME `UPGRADE` command (`mc_upgrade <rules.json>`; `rs1eepupdate.sh`). `rules.json` gates application on hardware model + IC/OC fw versions + EEPROM signature.

Note (cross-check, system/boot draft): `/usr/local/sbin/flash_psoc.sh` (inode 5141) is a **different** co-processor path (PSoC via `psoc-hssp.ko`) and is not part of the mime/eASIC PLC chain.

---

### Subsystem: `communicator` (AWS IoT MQTT, cloud command, device identity)

`/home/communicator/bin/communicator` (inode 748, 1,822,648 B, ARM ELF, stripped) is the AWS IoT MQTT client. Internals below are from `strings` plus the launcher/provisioning scripts. It connects to AWS IoT broker `a1wvyyv74srg62.iot.us-west-2.amazonaws.com` over mutually-authenticated TLS (mbedTLS, client cert + private key); the MQTT ClientId is the device serial number. It speaks Google Protocol Buffers and store-and-forwards via a local SQLite queue.

Service unit `/etc/systemd/system/communicator.service`: `ExecStart=/home/communicator/bin/communicator -v6 -x -o -l -m -b`, `Type=forking`, `WorkingDirectory=/home/communicator`, `After=mnt-mfg.mount`.

Verified MQTT topic templates:
- `client/${iot:ClientId}/data` — outbound telemetry
- `client/${iot:ClientId}/event` — outbound events
- `client/${iot:ClientId}/toi` — outbound Technical Operational Intelligence
- `client/${iot:ClientId}/command` — **inbound commands**
- `client/${iot:ClientId}/command/update` — command acknowledgements
- `client/${iot:ClientId}/time` — time-sync

Inbound `EDPCommand` handlers (RTTI strings, per the communicator draft) include `UpgradeFirmware` (carries `upd_spec_url` — the MQTT push update path), `RebootSystem`, Wi-Fi/cellular config, `ChangeDeviceSerialNumber`, `SetEphemeralAccessCode`, and remote-support `ConnectToSSHServer`/`CloseSSHConnection` (cloud-initiated reverse SSH tunnel). On-device helpers it invokes that exist in the image: `data_logger`, `mime/bin/mc_lease`, `readplatform.sh`, `net_to_edp.py` (inode 5147).

MQTT secrets and persistent config live on the runtime partition `/app0` (`/app0/secrets/mqtt/{AWSRoot.crt,deviceCert.pem.crt,private.pem}`, `/app0/app_data/communicator/`), which is **not present in this rootfs** (`/app0` = `mmcblk1p8`, mounted at runtime).

---

### Local HTTP API (`/www`, `dl_cgi`, `checkFW`)

The on-box management API and AngularJS console, served by lighttpd over plain HTTP. `/etc/lighttpd.conf` (inode 7049): `server.document-root = "/www/"`, `alias.url = ( "/cgi-bin/" => "/www/cgi-bin/" )`, and a catch-all `cgi.assign = ( "" => "/www/cgi-bin/dl_cgi" )` so **every** path under `/cgi-bin` maps to `dl_cgi` (the script name is ignored). Loaded modules are only `mod_alias, mod_setenv, mod_cgi` — **no `mod_auth`, no `ssl.*`** (per the local-API draft's grep).

- `/www/cgi-bin/dl_cgi` (inode 7247, mode 0755, 151768 B, ARM ELF, not stripped) is the entire REST + `?Command=` API engine; it is byte-identical to `/home/data_logger/bin/dl_cgi` (inode 774, different inode, same content). It emits `Content-Type: application/json` with `Access-Control-Allow-Origin: *` and `Access-Control-Allow-Methods: GET,POST,DELETE,PUT`.
- `/www/cgi-bin/checkFW` (inode 7246, mode 0755, 781 B, `#!/bin/sh`) — firmware-check script (see Cloud & update model).

Request mechanism: `dl_cgi` reaches the PV Supervisor / `data_logger` over the SysV/POSIX message queue `/mimecmdq` using the `MIMECmd*`/`MIMERsp*` class hierarchy (`executeMimeCommand(...)`); failures log "Unable to connect to PV Supervisor process, the system may still be booting up." Representative `?Command=` tokens: `DeviceList`, `DeviceDetails`, `StartDiscovery`, `GetDiscoveryProgress`, `GetSupervisorInformation`, `StartFWUpgrade`, `GetFWUpgradeStatus`, `GridProfileGet/Set/List/Refresh`, `ExportLimitGet/Set`, `Get_AP_List`, `SetAP`. (`DeviceList` is the command the SunPower app / HA integration polls for per-device production.) REST routes include `/network/*`, `/devices`, `/grid/voltage`, `/configFile`. Network/system actions shell out to `pvsnetwork.py`, `readplatform.sh`, `getserial.sh`, `uci`/`dnsmasq`, `iptables`.

Security posture (pre-lockdown): no authentication of any kind on `dl_cgi`, plain HTTP, wildcard CORS, and state-changing verbs (`POST/DELETE/PUT`) exposed — any client that can reach the box can drive discovery, grid-profile/voltage changes, firewall/DHCP changes, serial-number change, and firmware upgrade.

---

### System / init / identity / boot

systemd-based; `/sbin/init` → `/lib/systemd/systemd`. No SysV init and no cron — periodic work is done by systemd timers. Default target `default.target` → `pvs6.target`; `multi-user.target.wants/` enables `communicator.service`, `datalogger.service` (alias `data_logger.service`), `mime.service`, `connman.service`, `systemd-networkd.service`, `dnsmasq.service`, `lighttpd.service`, `ofono.service`, `iptables.service`, `smshandler.service`, `bootack.service`, plus the timers.

Scheduling (timers, no cron): `automatic_upgrade.timer` (`OnBootSec=1h`, `OnUnitActiveSec=1h`), `watchdog.timer`, `toggle-cell.timer`, `edp-watchdog.timer`, `sysstats.timer`, `coredump-uploader.timer`, etc.

Identity:
- `/etc/PVS.json` (inode 7192): `network.Register.host=""`, `network.WAN.mode="WAN"`, `network.CELL.primary=false`, `system.config_state="factory"`, `system.environment="prod"`.
- `/usr/local/bin/readplatform.sh` (inode 5177) is the canonical identity accessor: `serialnum`→`sys_show sn`, `model`→hard-coded `"PVS6"`, etc. **Path note (cross-check):** it is under `/usr/local/bin`, **not** `/usr/local/sbin` (verified: `/usr/local/sbin/readplatform.sh` returns "File not found"). The shared-context line putting it under `/usr/local/sbin` is incorrect; thin wrappers `getserial.sh`/`getmodel.sh` do live in `/usr/local/sbin`.
- Underlying tool `/usr/bin/sys` → `/usr/bin/sys.te-cmd` (`sys atsh <field>`). Manufacturing data on `mmcblk1p1` (ro, `/mnt/mfg`); MACs read from a UBI `caldata` volume via `getmac.sh`.

Networking: a split between systemd-networkd (internal LAN/AP — `lan0` static `172.27.153.1/24`, `ap0` static `172.27.152.1/24`) and connman (uplink WAN/Wi-Fi-station/cellular only — `/etc/connman/main.conf` blacklists internal ifaces, manages `wan0`/`sta0`). `dnsmasq` serves DHCP on the LAN side; `ofono`/`lte.service`/`smshandler.service` handle cellular.

Boot / A/B / firmware env:
- Bootloader U-Boot with a writable env in eMMC boot partition `mmcblk1boot1` (`/etc/fw_env.config`: `/dev/mmcblk1boot1 0x0000 0x2000`). `writable-fw-env.service` runs `fw_env_access rw` to make it writable at boot.
- `/sbin/bootswitcher` (inode 613) wraps `fw_setenv`/`fw_printenv` on env var `bootswitcher`: `get-active`/`switch1st`(set 0)/`switch2nd`(set 1), selecting the dual A/B rootfs slots.
- Verified mount sources: `/app0` = `mmcblk1p8` (ext4, persistent app/config/secrets — holds `boot_scripts/`, `secrets/mqtt/AWSRoot.crt`); `/mnt/mfg` = `mmcblk1p1` (ro). **Cross-check:** the A/B rootfs slots `mmcblk1p5`/`mmcblk1p6` come from shared established facts and are a *separate* pair from `/app0` (`p8`) — the drafts do not conflict here, but the distinction is called out to avoid conflation.
- `bootack.service` runs `watchdog.sh clr_bootcnt` + `set_recovery_state 0` to acknowledge a successful boot (prevents A/B rollback).

TLS trust store: `/etc/ssl/certs/` is the OpenSSL hashed store (symlinks into `/usr/share/ca-certificates/mozilla/`), a stock Mozilla root set; `/etc/ca-certificates.conf` is the manifest. Device/MQTT client certs are provisioned separately at runtime to `/app0/secrets/mqtt/`. (The communicator draft counted the store informally; the system/boot draft reports 299 entries — not independently re-counted here.)

---

### Cloud & update model

Two independent cloud channels run concurrently:

1. **Legacy HTTP collector** (`data_logger` → `ServerComm`): telemetry POSTed to `http://collector.sunpowermonitor.com/Data/SMS2DataCollector.aspx` and commands polled from `.../Command/SMS2DataCollector.aspx` (plaintext HTTP, verified in `config.lua`).
2. **AWS IoT MQTT** (`communicator`): mutually-authenticated TLS to `a1wvyyv74srg62.iot.us-west-2.amazonaws.com`; telemetry/events/TOI out, commands in (topics above).

Device identity / cert provisioning (`/usr/local/sbin/cert_client.sh`, inode 5168): reads `network.Register.host` (default `https://register.edp.sunpower.com:3001`; a `register.dev-edp.sunpower.com:3001` variant also exists in the image), gathers `{serial, mac, iccid, ssid, wpa_key}`, and POSTs to `.../api/pvs/issue`. The response (`caCertificate`, `certificate`, `privateKey`, `awsIotRootCert`, `awsIotEndpoint`, topic names) is written to `/app0/secrets/mqtt/`, then the communicator binary is run in config-write mode to persist endpoint + topics. (`smshandler.sh` independently falls back to `register.edp.sunpower.com:3001` per established facts.)

Firmware update — two paths, one terminus:
- **Pull** (`/usr/local/sbin/automatic_upgrade`, inode 5153, driven by `automatic_upgrade.timer`): constants verified — `CHECK_FW='/www/cgi-bin/checkFW'`, `FWUP='/home/data_logger/bin/fwup'`, `COMMISSIONING_FILE='/app0/secrets/mqtt/AWSRoot.crt'`, default `interval_days=7` (keyed off the commissioning file's mtime). It calls `readplatform.sh`, then `checkFW`, then `subprocess.call([FWUP, '-v', link])`.
- **`checkFW`** (verified script body): picks `ENV` from `/www/cloudConfig.json` (`.config`, default `prod`), selects `https://firmware-update-api.edp.sunpower.com/pvs6/` (prod/uat/`*`) or `https://firmware-update-api.dev-edp.sunpower.com/pvs6/` (dev/test), and `curl`s `${SERVER}?fwver=${1}&sn=${2}&type=${3}&ctx=${4}`. **Cross-check / correction:** the shared-context note that checkFW takes `buildnum, serialnum, model=PVS6, ctx=auto` describes the *callers'* intent, but the actual query parameters are `fwver`, `sn`, `type`, `ctx` (verified verbatim in the script). The reply (the firmware URL when it starts with `http`) is passed to `fwup`.
- **Push** (`communicator`): cloud `EDPCommand.UpgradeFirmware` carries `upd_spec_url`; the handler ultimately applies the update via the data_logger/fwup path (the literal fwup command line is inside the stripped binary — see inferred list).
- **`fwup`** (inode 768): parses a signed "FW update spec," verifies images and the new UBI volume, and writes the inactive A/B root partition. The signature check is real (`EVP_DigestVerifyInit/Final`, "Signature verification of %s failed") and is **bypassable**: verified help text — `-k key  Use this public key file to verify the FW update spec. The default is %s. If key is set to NONE, no signature verification`. The local-API `StartFWUpgrade` command surfaces the same flow (progress in `/tmp/fwup.progress`).

Out-of-band telemetry: the mime `plctools/toi.py` uploads PV diagnostics to a Splunk HTTP Event Collector. **Cross-check:** the mime draft cited `https://splunk.p2e.io:8088/services/collector/event`, but the image contains two distinct strings — `https://splunk.p2e.io/services/collector/event` (no port) and `https://splunk.pvs5.p2e.io:8088/services/collector/event`. The exact host:port used at runtime is not resolved here; flagged below.

---

### Cross-check summary (disagreements / corrections)

- **`readplatform.sh` location:** Resolved — it is `/usr/local/bin/readplatform.sh` (inode 5177). The shared-context `/usr/local/sbin` reference is wrong (verified absent). Both the system/boot and communicator drafts use the correct `/usr/local/bin` path.
- **checkFW query params:** Resolved — actual params are `fwver/sn/type/ctx`, not `buildnum/serialnum/model/ctx` as the shared context phrased it (script verified).
- **`/app0` partition vs A/B rootfs:** Resolved — `/app0` = `mmcblk1p8`; the A/B rootfs slots are `mmcblk1p5`/`mmcblk1p6` (separate, from established facts). No draft conflict, but the two were at risk of conflation.
- **Splunk HEC endpoint (mime):** Unresolved — two different strings exist in the image (`splunk.p2e.io` no-port vs `splunk.pvs5.p2e.io:8088`); the mime draft's single `splunk.p2e.io:8088` value is not exactly present. Flagged.
- **`mifwup`:** Resolved — it is a directory (inode 713), not a binary; the MI-update command is `mc_upgrade` (symlink → `MIMECommand`).
- **flash_psoc.sh vs eASIC:** Resolved — `/usr/local/sbin/flash_psoc.sh` (inode 5141, PSoC) is a different co-processor from the mime sidecar/eASIC PLC fw path.

---

### Inferred / needs further verification

- **fwup invocation from the MQTT push path:** the communicator binary is stripped; the exact `fwup`/`data_logger` command line behind `EDPCommand.UpgradeFirmware` is not exposed as a plaintext string. That the push path ends at `/home/data_logger/bin/fwup` is inferred from the shared `upd_spec_url`/fwup facts. (unverified)
- **Splunk HEC host:port** actually used by `toi.py` at runtime (two candidate strings present). (unverified)
- **`/app0` runtime contents** (MQTT secrets, `communicator.cfg`/`.db`, `access_codes.db`, grid-profile metadata `/app0/etc/gridprofiles/*.meta`, `toc.json`) are referenced by binaries but absent from this rootfs (runtime partition). (verified-absent here)
- **MIME UDP IPC sockaddr family** (`AF_UNIX SOCK_DGRAM` on `/tmp/mr%u`/`/tmp/sfacli%u` vs `AF_INET` loopback) — inferred from imported symbols, not disassembled. (inferred)
- **data_logger ↔ mime client relationship:** that data_logger is the normal MIME IPC client is inferred from `mimeif.h` comments and `pvinfo.py`; no direct socket call traced. (inferred)
- **data_logger command-queue key** (`DlKeyGenerator`/ftok) and runtime location of `arc_data/`/`arc_meta/` — directories absent in this unprovisioned image; only the relative `%08x.adf`/`.amf` format strings are verified. (inferred)
- **`‹redacted-key›` RSA private key** (`/home/data_logger/util/‹redacted-key›`, inode 764, mode 0600) — confirmed present and plaintext, but its role (likely legacy PVS5 device/SSH auth) is not traced. (unverified) — Security note: a private key shipped in firmware.
- **SSH-tunnel mechanics** in communicator (`ConnectToSSHServer`/`srvr_id`, reverse-port template, target host) — not present as plaintext. (unverified)
- **lighttpd listen port/bind** — not set in config; compiled default `:80` on all interfaces assumed. Whether the runtime iptables ruleset restricts the management interface is not determinable from static files. (inferred/unverified)
- **`/etc/ssl/certs` exhaustive contents** — sampled, not fully enumerated; presence/absence of a SunPower-private root CA not confirmed (the 299-entry count is from one draft, not re-verified here). (unverified)
- **U-Boot script that consumes `bootswitcher`** and the `bootswitcher`→slot 0/1→`mmcblk1p5`/`p6` mapping live in the bootloader, outside this rootfs. (unverified here)
- **`sys.te-cmd` `atsh` field semantics** and **DSA switch port topology** (`wan0`/`sta0`/`br0`/`lan0`) are defined outside the rootfs (binary/device-tree). (unverified)