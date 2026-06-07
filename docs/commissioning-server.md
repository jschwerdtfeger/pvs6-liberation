> Auto-generated from offline, read-only analysis of an owner's own PVS6 firmware (right-to-repair, build 2019.8.26.249). Security-sensitive specifics are withheld from public docs pending responsible disclosure.

---

## Build-your-own PVS6 commissioning / cloud server — design & feasibility

*Offline reverse-engineering of OWNED PVS6 firmware (build 2019.8.26.249, pre-lockdown) to design an owner-run replacement cloud. All claims are evidence-cited or marked (inferred). Right-to-repair scope: this is the owner's own hardware.*

---

### 0. Executive summary

A PVS6 on this pre-lockdown build can be **fully attached to an owner-run cloud**, because the single hardest dependency — getting the device to trust *your* server — is already wide open in the firmware: the registration HTTP POST uses `curl -k` (TLS verification disabled, with an in-script "TODO remove the insecure flag"), and the target host is an editable config string (`network.Register.host` in `/etc/PVS.json`). Everything else (CA/PKI, MQTT broker, protobuf) is standard infrastructure plus a protocol layer that is **100% recoverable from the binary** (the compiled `FileDescriptorProto` is embedded in `communicator`).

Two honest boundaries frame the whole effort:

1. **The "happy cloud" tier is genuinely easy; full remote command/control is RE-heavy** but doable because the protobuf descriptors and `dl_cgi` are both un-stripped/recoverable.
2. **None of this fixes the owner's actual blocker.** Error **13036 "battery pack enumeration"** lives in the **Hub+/ESS subsystem — a different device whose firmware is not in this artifact.** A PVS6 cloud server replaces SunPower's *PV-monitoring* back-office; it does not commission the SunVault batteries. For the batteries, **Path B (Schneider-native local commissioning)** is the correct lane, not a fallback. See §5.

---

### 1. Architecture — owner-run cloud and how the device attaches

```
                          PVS6 device (your hardware, build 2019.8.26.249)
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │  /etc/PVS.json : network.Register.host = "https://YOURHOST:3001"   (EDITABLE)  │
  │                                                                                │
  │  cert_client.sh MQTT ──curl -s --fail -k──► POST /api/pvs/issue                │
  │      body {serial,mac,iccid,ssid,wpa_key}                                      │
  │                                                                                │
  │  communicator (daemon, mbedTLS) ──mutual-TLS MQTT 8883, ClientId=serial──►     │
  │      pub: client/<serial>/{data,event,toi}                                     │
  │      sub: client/<serial>/{command,command/update,time}                        │
  │                                                                                │
  │  dl_cgi (lighttpd, NO auth) ◄── local HTTP from your LAN orchestrator          │
  │      ?Command=StartDiscovery / GridProfileSet / SetMeterCt / ExportLimitSet …  │
  └──────────────────────────────────────────────────────────────────────────────┘
        │ (1) register over HTTPS          │ (2) MQTT/mTLS          │ (3) local HTTP
        ▼                                  ▼                        ▼
  ┌───────────────────────┐   ┌──────────────────────────┐   ┌─────────────────────┐
  │ REGISTRATION SERVER   │   │   MQTT BROKER (mosquitto/ │   │ LOCAL-API           │
  │ HTTPS :3001           │   │   EMQX/VerneMQ) :8883     │   │ ORCHESTRATOR        │
  │ POST /api/pvs/issue   │   │   mutual-TLS              │   │ (drives dl_cgi over │
  │  - parse 5 id fields  │   │   client-auth trusts      │   │  the LAN; no cloud  │
  │  - mint device cert ──┼─► │     Device CA             │   │  needed for local   │
  │    from Device CA     │   │   server cert chains to   │   │  PV operation)      │
  │  - return 11-field    │   │     Broker CA             │   └─────────────────────┘
  │    JSON (certs+topics)│   │   ACL: client/<serial>/*  │
  └───────────┬───────────┘   │   ClientId == serial      │
              │               └────────────┬─────────────┘
              ▼                             ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │ INTERNAL CA / PKI (step-ca or openssl)                                         │
  │   Device CA  → signs per-device client certs (EKU clientAuth), returned as     │
  │                response.certificate (+ privateKey); broker trusts it           │
  │   Broker CA  → signs broker server cert (EKU serverAuth, SAN=awsIotEndpoint);  │
  │                returned as response.awsIotRootCert (device verifies broker)    │
  │   (minimum viable = ONE CA signing both; return it as both CA fields)          │
  └──────────────────────────────────────────────────────────────────────────────┘
              ▲                             ▲
              │                             │
  ┌───────────┴─────────────────────────────┴────────────────────────────────────┐
  │ PROTOBUF PROTOCOL LAYER  (package EDPMessaging, file EDPMessage.proto)         │
  │   Recovered verbatim from communicator's embedded FileDescriptorProto.        │
  │   Envelopes: EDPData / EDPEvent / EDPTechnical (in)  •  EDPCommand (out)  •    │
  │              EDPAcknowledge (out, on command/update).                          │
  │   Broker-side codecs: decode telemetry; optionally encode 1 command           │
  │   (SiteOperationalSet) for "operational/green".                               │
  └────────────────────────────────────────────────────────────────────────────────┘
```

**Attach sequence (verified):**
1. Owner sets `network.Register.host = "https://YOURHOST:3001"` in `/etc/PVS.json` (or `set_config_string`; default if empty is `https://register.edp.sunpower.com:3001`). Evidence: `cert_client.sh` reads `URL_HOST = get_config network.Register.host`; `get_config` = `jq -r .network.Register.host /etc/PVS.json` under `flock /var/lock/pvs_json.lock` (`/etc/config_functions.sh`).
2. `cert_client.sh MQTT` POSTs the 5 identity fields to `$URL_HOST/api/pvs/issue` with `curl -s --fail -k`. Server returns 11-field JSON; script writes 4 cert files to `/app0/secrets/mqtt/` and runs `communicator` in config-write mode to persist `communicator.cfg`.
3. The `communicator` daemon (started with `-x` by its service) loads `communicator.cfg` + the 3 pinned cert files and connects to your broker over mutual-TLS MQTT, ClientId = serial.
4. Independently, your LAN orchestrator drives `dl_cgi` over local HTTP for the actual PV commissioning operations (no cloud round-trip required — see §3/Tier 0).

---

### 2. Component-by-component build spec

#### 2.1 Registration server — **Achievable now (weekend, with certs)**

- **What it does:** Accepts one anonymous HTTPS POST and returns the device's MQTT identity (client cert/key + broker trust CA + endpoint + 6 topic names).
- **Exact contract (verified against `cert_client.sh`):**
  - `POST /api/pvs/issue`, `Content-Type: application/json`, **no auth / no API key / no client cert** on this request. Must return **HTTP 2xx** (curl `--fail`; any 4xx/5xx aborts the script with "Failed to retrieve data from certificate manager server").
  - **Request body** (built in `id_sys()`; non-pretty, tab-indented but valid JSON):

    | field | source on device | notes |
    |---|---|---|
    | `serial` | `readplatform.sh serialnum` | becomes MQTT ClientId |
    | `mac` | `sys_show lmac`, colons stripped | 12 hex chars |
    | `iccid` | `modemif -C` or `''` | **optional** — tolerate `""` |
    | `ssid` | `sys_show ssid` | onboard AP SSID |
    | `wpa_key` | `sys_show key` | onboard AP WPA key |

    `id_sys()` `fatal`s if `serial/mac/ssid/wpa_key` empty; `iccid` is the only optional field. No signature over the body — identity is asserted, not proven (an owner server can trust them or check against your own allowlist).
  - **Response body** — flat JSON, all **11 fields mandatory and case-sensitive** (each read by `jq -r ".<field>"`; a missing field becomes literal `null` and silently mis-configures the device — the script has `#TODO: Error checking?`). PEMs are `\n`-escaped JSON strings.

    ```json
    {
      "caCertificate":   "<PEM broker CA>",
      "certificate":     "<PEM device client cert, identity=serial>",
      "privateKey":      "<PEM device key>",
      "awsIotRootCert":  "<PEM CA the device trusts to verify the broker>",
      "awsIotEndpoint":  "your.broker.host",
      "awsIotTopicCommand":       "client/<serial>/command",
      "awsIotTopicCommandUpdate": "client/<serial>/command/update",
      "awsIotTopicData":          "client/<serial>/data",
      "awsIotTopicEvent":         "client/<serial>/event",
      "awsIotTopicTechnical":     "client/<serial>/toi",
      "awsIotTopicTime":          "client/<serial>/time"
    }
    ```

    Field→use map: `certificate`/`privateKey` → device mTLS client identity (`/app0/secrets/mqtt/deviceCert.pem.crt`, `private.pem`); `awsIotRootCert` → `AWSRoot.crt` = the CA the device verifies the **broker** against (this is the one `communicator` actually loads as `root_ca_filepath`); `awsIotEndpoint` → `communicator -u`; the 6 topics → `--tpclcmd/--tpcmdrsp/--tpdata/--tpevent/--tptoi/--tpsynctime`. **Note:** `caCertificate` is written to `caCert.pem.crt` but `communicator`'s pinned paths reference only `AWSRoot.crt`/`deviceCert.pem.crt`/`private.pem`, so `caCertificate` is informational on this build — populate it with the broker CA anyway.
- **TLS for this endpoint:** must be `https://` (default port 3001) but the cert can be **self-signed** — the device uses `curl -k` and will not validate it. Evidence: `cert_client.sh` `-k` flag + `#TODO: Need to remove the insecure flag once we have certs in place for our domain`.
- **Tech recommendation:** a tiny HTTPS app (Flask/FastAPI + uvicorn behind a self-signed TLS cert, or Go `net/http`). On each request, shell to your PKI (step-ca `sign` or `openssl x509`) to mint the per-device cert. ~150 lines.
- **Effort:** Low (a day, once PKI exists).

#### 2.2 Internal CA / PKI — **Achievable now**

- **What it does:** Mints per-device client certs at registration time and backs the broker's server cert. The registration server and broker trust chains must be **co-designed** — this is the real architectural glue, not an RE problem.
- **Exact contract / constraints (from `communicator` mbedTLS usage):**
  - Device client certs: **EKU = clientAuth**, KU = digitalSignature, subject/identity tied to `serial` (e.g. `CN=<serial>`) to match ClientId=serial. mbedTLS checks `id-ce-keyUsage` / `id-ce-extKeyUsage` (strings in binary) → wrong EKU yields "Usage does not match" rejections.
  - Broker server cert: **EKU = serverAuth**, **SAN must match the `awsIotEndpoint` host** you return.
  - **Minimum viable = one CA** signing both, returned as both `awsIotRootCert` and `caCertificate`. Two-CA split (separate client-trust vs server chain) also works if the broker is configured for it.
- **Tech recommendation:** `step-ca` (smallstep) for a real issuing CA with an automatable `sign` API, or plain `openssl`/`cfssl` for a static lab CA. Hold the Device-CA key on the registration host.
- **Effort:** Low–Medium.

#### 2.3 MQTT broker — **Achievable now**

- **What it does:** Terminates the device's mutual-TLS MQTT 3.1.1 connection on :8883 and enforces per-serial topic ACLs. This is just "an MQTT+mTLS broker" — AWS IoT is not special here.
- **Exact contract (verified):**
  - Port 8883, mutual-TLS, **ClientId = device serial**.
  - Server cert chains to the CA returned as `awsIotRootCert`; client-auth trusts your **Device CA**.
  - Six topics, `client/<serial>/...`: device **publishes** `data`/`event`/`toi`; **subscribes** `command`/`command/update`/`time`. (`time` triggers `/usr/local/sbin/sync_time.sh -w` on the device.) ACLs must permit exactly these.
- **Tech recommendation:** **Mosquitto** (cafile=Device-CA, `require_certificate true`, `use_identity_as_username true`, per-serial ACL file) for the simplest start; **EMQX/VerneMQ** if you want `${clientid}` ACL templating closer to AWS IoT's `${iot:ClientId}` substitution (that substitution is the broker's job, not the device's).
- **Effort:** Low–Medium (mechanical; the hard part is the PKI co-design in §2.2).

#### 2.4 Protobuf protocol layer — **Schema recovery: essentially done; semantics: partial**

- **What it does:** Decodes telemetry the device publishes and (optionally) encodes commands the device subscribes to.
- **Exact contract (recovered, see §3 for fidelity):** package `EDPMessaging`, file `EDPMessage.proto`, embedded `FileDescriptorProto` at offset `0x174bd4` in the dumped binary (~20,790 bytes). 14 top-level messages, 8 enums, deps on `google/protobuf/timestamp.proto`+`descriptor.proto`. Common envelope field 1 = `EDPHeader header` = `{Timestamp msg_crt_eps=1; string sn=2; string prod_mdl_nm=3; string cmd_tkn=4}` — **`cmd_tkn` is the correlation token a server must echo in the ACK.**
- **Tech recommendation:** Extract the blob, run `protoc --decode google.protobuf.FileDescriptorProto descriptor.proto < blob` to regenerate `EDPMessage.proto` verbatim, then `protoc` it into your broker app's language. Cross-check field names against `/usr/local/sbin/net_to_edp.py` (the device's own camelCase-JSON↔snake_case-proto bridge — e.g. `msgCrtEps`→`msg_crt_eps`), which also lets you test the device's JSON-ingestion path.
- **Effort:** Low for decode (schema is exact); Medium-to-High for a full command server (semantics/state machine — see §3).

#### 2.5 Local-API orchestrator — **Achievable now**

- **What it does:** Drives the actual PV commissioning operations over the LAN against the un-authenticated `dl_cgi`. This is the workhorse for local operation and needs **no cloud and no protobuf**.
- **Exact surface (this build's `dl_cgi`, `/www/cgi-bin/dl_cgi`, un-stripped):** legacy `?Command=` tokens — `DeviceList`, `StartDiscovery`, `GetDiscoveryProgress`, `GetSupervisorInformation`, `GridProfileGet/Set/List/Refresh`, `SetMeterCt`, `ExportLimitGet/Set`, `ChangeSerialNumber`, `Get_AP_List`/`SetAP`, `StartFWUpgrade` — plus REST `/network/*`, `/devices`, `/grid/voltage`. **Verified absent on this build:** every `/commission/*`, `site_key`, `datastore`, `decommission`, `energy-storage-system/*` route (those exist only in the newer swagger — see §3/§6).
- **Tech recommendation:** a small script/service (Python `requests`) that sequences `StartDiscovery → poll GetDiscoveryProgress → GridProfileSet → SetMeterCt → ExportLimitSet` and reads `/network/powerProduction`. Self-host `GridProfileRefresh`'s source (public S3 `s3-us-west-2.amazonaws.com/2oduso0/gridprofiles…`, fetched via `curl -k`, no auth) by mirroring `toc.json`. Repoint `StartFWUpgrade`/`checkFW` via `/www/cloudConfig.json`.
- **Effort:** Low.

---

### 3. The protobuf reality — recoverable now vs needs more RE, and the minimal-viable path

**Recoverable now (no disassembly, no captured traffic):** the **entire wire schema.** `communicator` was built with Protobuf 3.4.x, which embeds the serialized `FileDescriptorProto` in rodata. Decoding it yields **exact field names, field numbers, wire types, labels, nested types, and all enum values** — deterministic, not guesswork. A `strings`-only pass recovers ~80% of *names* but **misses field numbers and wire types** (not printable); the descriptor approach recovers 100%. Estimated ~95% faithful as reconstructed; residual risk is (i) a handful of names protobuf 3.4 *could* strip (none observed stripped here) and (ii) descriptor-length bounding done heuristically — both removed entirely by a single `protoc --decode` round-trip. Known-exact highlights:

- **Inbound `EDPCommand`** — 33 sub-messages at fields 2–34, e.g. `UpgradeFirmware=5 {string upd_spec_url=1}`, `RebootSystem=6`, `ConnectToSSHServer=7`, `TriggerDeviceDiscovery=9`, `GetDeviceDiscovery=10`, `ChangeDeviceSerialNumber=11`, `SetEphemeralAccessCode=12`, `WiFiSetCredentials=13 {ssid;bssid;pwd}`, `METStationCalibrationSet=19`, `SiteOperationalSet=21 {bool site_op_st_fl=1}`, `CTScalingFactorSet=24`, `AdhocCommand=26` (ShellCmd), `DeviceDisassociate=27`, `CellPrimarySet=28`, `Dcm*=29–34`.
- **Outbound `EDPData`/`EDPEvent`/`EDPTechnical`** — full inverter/meter/MET/ground-current/ESS/Dcm/datalogger parameter sets; `EDPTechnical.PVSCore` carries `System.Startup`/`Heartbeat`/`Networking`.
- **`EDPAcknowledge`** (on `command/update`) — `{EDPHeader header=1; ACK ack=2; NAK nak=3}`, `ACK={bool cmplt_fl=1}`, `NAK={NAKReason nak_rsn_enum=1}` (21-value enum).
- **Enums** — `DeviceType{…,ESS=5,DCM_CONTROLLER=6}`, Cell/WiFi statuses, `Dcm*` enums, `DataLoggerParameter.Name`.

**Needs more RE (and mostly out of scope):** the **semantics** — the *sequence/state machine* a real commissioning flow expects and any server-side business logic. The wire format tells you how to send `TriggerDeviceDiscovery`, not the orchestration order or back-office rules. That needs captured traffic from a real commissioning session or behavioral testing on the device.

**Minimal-viable path — the "happy cloud" + local-API-driving hypothesis (CONFIRMED by evidence):**

A PVS6 on this build can reach **local PV operation with NO cloud at all.** Nothing in `dl_cgi`/`data_logger` gates discovery, metering, or grid-profile ops on any "operational"/"site" state (no such gate string exists; `config_state:"factory"` in `/etc/PVS.json` is informational and is never advanced to "commissioned" by any script). `data_logger` scans devices and buffers/reports on a timer **independent of MQTT/EDP** (legacy plain-HTTP `collector.sunpowermonitor.com` in `/home/data_logger/config.lua`, with a `DataArchiver` circular buffer). So:

- **Tier 0 — fully local, zero cloud:** drive `StartDiscovery → GridProfileSet → SetMeterCt → ExportLimitSet` via `dl_cgi`; let `data_logger` scan/report (or point `config.lua`'s `data_chan_url_*` at your own collector). Achieves local PV-supervisor operation with **no protobuf and no broker**.
- **Tier 1 — minimal "happy cloud" (device shows connected/green):** stand up only (a) the registration server (§2.1) and (b) an MQTT broker (§2.3) that **just ACKs** on `data/event/toi/time`. Optionally publish a single `EDPCommand{SiteOperationalSet: site_op_st_fl=true}` on `client/<serial>/command` so the device records itself operational — that's the **only** protobuf *encode* you need. UpgradeFirmware, AdhocCommand, discovery-over-MQTT, etc. stay unimplemented / NAK'd.

**vs. full reimplementation:** implementing the inbound `EDPCommand` set (remote discovery, firmware, Dcm/ESS dispatch, access codes, telemetry decode + storage + dashboard) is the multi-week-to-multi-month track. Doable because descriptors survive and both `dl_cgi` and `data_logger` are **not stripped** — but it is the heavy lane, and it is only needed for *remote* control or to satisfy the real EDP back-office, neither of which is required to reach local operation.

What even Tier 1 does **not** give you: a real SunPower-app/EDP account binding. On this build there is **no on-device notion of a site/account at all** — `site_key` appears nowhere in `dl_cgi`/`data_logger`; the association lives entirely server-side in EDP and the device never learns it. Replicating the app experience means replacing the whole back-office, not just the broker.

---

### 4. Phased plan

| Phase | Goal | Build | Proves | Effort |
|---|---|---|---|---|
| **P0** | Local operation, zero cloud | Local-API orchestrator (§2.5) driving `dl_cgi`; optional self-collector via `config.lua` | The PV array discovers, sets grid profile/CTs, and produces/reports **without any cloud** | Low |
| **P1** | Device attaches to your cloud | Registration server (§2.1) + one-CA PKI (§2.2) + Mosquitto mTLS broker (§2.3), ACK-only | Device registers against `YOURHOST:3001`, connects MQTT with ClientId=serial, stays connected | Low–Med |
| **P2** | "Operational/green" + telemetry decode | `protoc` the recovered `EDPMessage.proto`; broker decodes `data/event/toi`; optionally encode one `SiteOperationalSet(true)` | You can read live telemetry and (inferred) flip the operational indicator | Med |
| **P3** | Telemetry storage + dashboard | Ingest → TSDB → web UI | Owner-run monitoring replacing SunPower's | Med |
| **P4** *(optional, RE-heavy)* | Inbound command server | Implement selected `EDPCommand`s (discovery, Dcm/ESS dispatch, WiFi). **Defer/avoid** `AdhocCommand`/`ConnectToSSHServer`/`UpgradeFirmware` (root reach + brick risk) | Remote control of an already-healthy system | High / risky |

Build P0 first — it delivers the owner's PV-monitoring independence with the least work and the least risk, and it does not depend on any of the RE-heavy pieces.

---

### 5. Scope boundary — does this help the owner? (honest section)

**No — not for the stated blocker.** The owner's real problem is the **SunVault non-operational, topology corruption (2 inverters→1), error 13036 "battery pack enumeration."** That handshake lives in the **Hub+/ESS commissioning subsystem — a different device, different firmware that is not in this artifact.** Verified in *this* PVS6 build:

1. **No commissioning/enumeration logic exists.** Grepping `communicator` for `enumerat|componentmap|commission|decommission|hubplus|gateway|provision|onboard` returns nothing. "Energy Storage System" in `dl_cgi` is a device-type *label*, not a route.
2. **The modern ESS commissioning API is in the swagger but NOT compiled into this firmware.** Swagger 2.3.1 lists `/energy-storage-system/{status,pre-discover,component-mapping,firmware}`, `/commissioning/{start,stop}`, `/commission/{config,datastore,decommission}`, `/discovery` with `Device:"storage"` — **none of these handlers are in this 2019.8.26.249 `dl_cgi`.** The swagger describes a *later* firmware than the artifact.
3. **What the PVS6 *can* do for the battery is operational, not commissioning:** `DcmEssOpMode/Type/ChargeConstraint`, `EDPData.EssParameters` (soc/soh/charge limits), `EDPEvent.EssAlert`, `ZigBeeSEP*` — runtime dispatch/telemetry/control for an **already-enumerated, operational** ESS. There is no "enumerate battery packs" or "map components" command anywhere in this set.
4. **The SEP/ZigBee provisioning path is vestigial here.** `cert_client.sh SEP` hits `/api/sep/provide` → `sep_bundle.txt`, but **nothing in this rootfs consumes the bundle** (no `sep_bundle`/`link_key`/`installation_code`/SmartEnergy reader). It is a stub on this build.

**Therefore:** a PVS6 cloud server buys the owner (a) independence from SunPower's cloud for PV monitoring/control, (b) the ability to re-register an orphaned PVS6, and (c) a path to *issue Dcm/ESS dispatch commands to an already-working battery*. It does **not** re-enumerate or re-map battery components, and so does not clear 13036.

**Where Path B (Schneider) is the better route — for the batteries specifically:** the SunVault is Schneider-built; the 13036 enumeration/topology state machine is **ESS-internal**, owned by the Schneider ESS gateway / power-conversion system, which Schneider's native local commissioning tools talk to directly. Both Path A (recommission existing topology) and Path B (Schneider conversion / native local commissioning) operate **below** the PVS6 layer; the PVS6 server, at best, sits on top once the ESS is healthy. Pursue Path B for the battery fault — the PVS6 cloud project is **orthogonal** to it (worth doing for monitoring independence, but not a battery fix).

---

### 6. Consolidated open RE questions (need a donor device, captured traffic, or disassembly)

**Need captured traffic (real commissioning session) or behavioral testing on a live device:**
1. The **commissioning state machine / sequence** — what order the back-office issues `TriggerDeviceDiscovery`/`SiteOperationalSet`/CT/grid-profile, and any handshake timing. Wire format is known; orchestration is not.
2. Whether publishing `SiteOperationalSet(site_op_st_fl=true)` from an owner broker actually yields a "green/operational" device state (inferred from absence of any operational gate; **no runtime observation performed**).
3. Whether `caCertificate` (vs `awsIotRootCert`) is ever used by a later daemon build, or remains informational.
4. The MQTT keepalive/QoS/reconnect and time-sync expectations the daemon enforces at runtime.

**Need `protoc` round-trip (have the blob; just confirm):**
5. Airtight regeneration of `EDPMessage.proto` via `protoc --decode google.protobuf.FileDescriptorProto` (removes the two residual fidelity caveats in §3).

**Need a donor device / different firmware artifact (this rootfs is insufficient):**
6. The **Hub+/ESS firmware itself** — the actual home of error 13036 battery-pack enumeration and component-mapping. Not in this artifact; this is the long pole for the owner's real problem.
7. The **newer PVS6 firmware** that implements the swagger-2.3.1 `/commission/*` + `energy-storage-system/*` routes — to study the device-side ESS commissioning glue (still PV-supervisor glue, not the Hub+ enumeration logic).
8. The **SEP/ZigBee bundle consumer** — `/api/sep/provide` exists but no consumer is present here; a build that actually uses `sep_bundle.txt` (`dvc_cert`/`dvc_eui64`/`instl_cd`/`pub_ca_key`) is needed to understand the Smart Energy provisioning path.
9. **OTA update verification** — `UpgradeFirmware(upd_spec_url)` is owner-controllable but the update package's **signature/verification story is unverified** here (brick risk); needs the update-agent disassembly before any owner-OTA is attempted.

**Runtime-only artifacts not in this read-only system image (exist only on a live unit):**
10. `/app0/secrets/mqtt/*`, `/app0/app_data/communicator/communicator.cfg`, `/app0/access_codes.db`, and the manufacturing-data partition (`sys atsh` source of serial/mac/ssid/key/iccid) — needed to bench-replicate identity sourcing off-device.

---

*Evidence base (all absolute, in-image unless noted): `/usr/local/sbin/cert_client.sh`, `/etc/config_functions.sh`, `/etc/PVS.json`, `/home/communicator/bin/communicator` (dumped; `FileDescriptorProto` @ `0x174bd4`), `/usr/local/sbin/net_to_edp.py`, `/usr/local/sbin/readplatform.sh`, `/usr/local/sbin/modemif`, `/www/cgi-bin/dl_cgi` (un-stripped), `/home/data_logger/bin/data_logger` (un-stripped), `/home/data_logger/config.lua`, `/app0/etc/gridprofiles/toc.json`, `/www/cgi-bin/checkFW`, `/www/cloudConfig.json`; newer-than-firmware swagger `/tmp/pvs_swagger.json` and `/Users/jschwerdtfeger/Desktop/Git/HighCamp/pvs6/pvs6_swagger.json`.*