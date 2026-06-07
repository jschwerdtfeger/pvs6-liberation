> Auto-generated from offline, read-only analysis of an owner's own PVS6 firmware (right-to-repair, build 2019.8.26.249). Security-sensitive specifics are withheld from public docs pending responsible disclosure.

---

Final confirmations:
- **`e2cp` ABSENT**, `debugfs`/`e2fsck` present under e2fsprogs ✓ (Draft 2 correct). `xz`, `tar`, `shasum`, `md5`, `sha256sum`, `md5sum` all present ✓
- **`fwup-usb.sh` does NOT exist anywhere in the image** — Draft 2's heavy reliance on `/usr/local/sbin/fwup-usb.sh` (with cited inode 6724) and the `sunpower/$MODEL/fwup.lua` USB layout is **not supported by this image**. Must be flagged as unverified/community-reported.
- **`e-asic_firmware_for_mime_v99.0.9.bin` / `duo-library` / `99.0.9` NOT found** — Draft 3's specific eASIC filename and Enphase duo-library provenance are unverified.
- **No `fwup -v ... -k NONE` invocation exists in any on-image script** — the `-k NONE` option exists in the binary's help text (confirmed) but is NOT wired into any shipped updater script here. So "the stock updater script passes/doesn't pass -k NONE" claims can't be grounded; only the binary option string is confirmed.
- `readplatform.sh model` → `PVS6` confirmed (offline-verifiable, not donor-only).

I have everything needed to produce a corrected, merged section. Here is the final markdown.

## Repointing phone-home — offline dev recipe (older build)

**Build:** `2019.8.26.249` (CDN index `staging-prod-adama/249`). Right-to-repair documentation for **owned hardware**, derived entirely from **offline, read-only** inspection of the unpacked ext image at `/tmp/pvsfw/rootfs/image` (via `debugfs`). Nothing here writes to a device. The repack/load steps are documentation for a community member who has a **donor/spare** unit; flashing a sole/production unit is out of scope and is never advised.

Every claim that cannot be confirmed from the image alone is marked **(unverified — needs donor-device testing)** and collected at the end.

---

### 1. What is actually editable, and what is not

The phone-home destinations on this build live in **plaintext config and shell scripts**, not in compiled binaries. This was verified file-by-file:

| Destination | Where it lives (confirmed) | Editable? |
|---|---|---|
| Telemetry + command channels (6 URLs) | `/home/data_logger/config.lua` and `/home/data_logger/default_config.lua`, table `param_table` | Yes — plaintext Lua |
| Registration / cert-manager reachability target | `/etc/PVS.json` → `network.Register.host` (currently `""`), read at runtime by `/usr/local/sbin/smshandler.sh` | Yes — plaintext JSON |
| Firmware-update **health-check** host `fwupgrade.sunpowermonitor.com` | `/usr/local/sbin/smshandler.sh` (plaintext shell, inode 5135), line 294: `FW_CHECK_REACH=\`check_internet fwupgrade.sunpowermonitor.com\`` | Yes — plaintext shell (it is **only a reachability probe**, see §4) |

Correction to earlier notes: the `fwupgrade.sunpowermonitor.com` string is **not** embedded in the compiled `/home/mime/bin/mime` binary. A `strings` scan of that binary (inode 711, 5,635,340 bytes) contains no occurrence of `fwupgrade` or `sunpowermonitor`. The only copy in the image is in the plaintext `smshandler.sh`. No binary patching is required or recommended for any part of this recipe.

---

### 2. Change table — the config edits

Edit **both** Lua files identically. `config.lua` is live; `default_config.lua` is the fallback, and `copy_configuration.sh` copies both forward across an A/B update (it preserves `/home/data_logger/c*.lua` and `d*.lua` — see §5), so a reset or update re-introduces the SunPower URLs if only one file is changed. Line numbers below were confirmed by `debugfs cat`; preserve the surrounding quotes and trailing commas exactly.

| File | Key (line) | Current value | New value |
|---|---|---|---|
| `/home/data_logger/config.lua` | `param_table.data_chan_url_1` (5) | `http://collector.sunpowermonitor.com/Data/SMS2DataCollector.aspx` | `http://YOUR-SERVER/Data/SMS2DataCollector.aspx` |
| `/home/data_logger/config.lua` | `data_chan_url_2` (6) | same | `http://YOUR-SERVER/Data/SMS2DataCollector.aspx` |
| `/home/data_logger/config.lua` | `data_chan_url_3` (7) | same | `http://YOUR-SERVER/Data/SMS2DataCollector.aspx` |
| `/home/data_logger/config.lua` | `cmd_chan_url_1` (11) | `http://collector.sunpowermonitor.com/Command/SMS2DataCollector.aspx` | `http://YOUR-SERVER/Command/SMS2DataCollector.aspx` |
| `/home/data_logger/config.lua` | `cmd_chan_url_2` (12) | same | `http://YOUR-SERVER/Command/SMS2DataCollector.aspx` |
| `/home/data_logger/config.lua` | `cmd_chan_url_3` (13) | same | `http://YOUR-SERVER/Command/SMS2DataCollector.aspx` |
| `/home/data_logger/default_config.lua` | same six keys, same lines | same | mirror the six values above |
| `/etc/PVS.json` | `network.Register.host` | `""` | `"https://YOUR-SERVER:3001"` (only if you intend to take over registration/cert-manager — see §3) |

---

### 3. `network.Register.host` behaviour (confirmed in `smshandler.sh`)

`smshandler.sh` reads this value at runtime:

```
CERT_MAN_REACH_CONFIG_URL=`get_config network.Register.host`
if [ -z ${CERT_MAN_REACH_CONFIG_URL} ]; then
    CERT_MAN_REACH_CONFIG_URL="https://register.edp.sunpower.com:3001"
fi
CERT_MAN_REACH=`check_internet_no_ping ${CERT_MAN_REACH_CONFIG_URL}`
```

So when `Register.host` is empty (its current state), the script falls back to `https://register.edp.sunpower.com:3001` for a **reachability check** that is reported in the status string. Setting `Register.host` to your own `https://YOUR-SERVER:3001` repoints that reachability target. Note this is a `check_internet_no_ping` reachability probe in `smshandler.sh`; whether populating this field also redirects the actual cert-provisioning transaction performed by `cert_client.sh` is **not** established from the script alone **(unverified — needs donor-device testing)**. If you point it at an HTTPS endpoint, your host must speak TLS on :3001 (see §6).

---

### 4. The firmware-update host is a health probe, not the download URL

In `smshandler.sh`, `fwupgrade.sunpowermonitor.com` is used only as `check_internet fwupgrade.sunpowermonitor.com`, and the result (`FW_CHECK_REACH`) is appended to the device status string. It is a reachability/health indicator, not the firmware download source.

The actual update download URL is the `url=` field inside the **server-delivered, signed `fwup.lua` manifest** — it is not a device-side setting. Practical consequence: repointing the six telemetry/command URLs already stops the collector from handing the device an update manifest, so the firmware path is neutralized by config edits alone, with no binary or script change required. If you also want the health LED/status string to reflect your own host, edit the plaintext `fwupgrade.sunpowermonitor.com` literal in `smshandler.sh` (it is editable shell, not a binary) — optional and not required.

---

### 5. Persistence across A/B updates (confirmed from `copy_configuration.sh`)

The post-install script `copy_configuration.sh` (verbatim in the image) mounts the inactive rootfs and copies config forward. Confirmed details:

- A/B mapping is derived from the U-Boot `bootswitcher` env var: active `bootswitcher=0` → inactive partition `/dev/mmcblk1p6`; active `=1` → inactive `/dev/mmcblk1p5`.
- Files preserved include: `/etc/PVS.json`, `/home/data_logger/c*.lua` and `d*.lua` (your edited `config.lua`/`default_config.lua`), `/home/commapp_state.txt`, `/etc/ssh/ssh_host_*_key*`, `communicator.cfg`, `mime.cfg`, connman state, and others.

So your repointed config is "sticky" across a rootfs swap on a donor unit. These edits are plaintext runtime config and do **not** touch the rootfs image, so they have no interaction with the manifest RSA signature.

---

### 6. HTTP vs HTTPS/MQTT and the trust store

Active comms on this build are plain **HTTP** to the collector (the six Lua URLs are `http://`). So `http://YOUR-SERVER` needs **no certificate work** — your endpoint just answers the `/Data/...aspx` and `/Command/...aspx` POSTs. This is the simplest first-stage local-capture setup and is the recommended path.

If you instead repoint to **HTTPS or MQTT/mTLS** (the form `Register.host` expects on :3001):
- The build ships standard Mozilla `ca-certificates` under `/etc/ssl`, so a self-signed `YOUR-SERVER` cert will fail validation; you would need to add your own CA to the device trust store. The exact trust-store layout and whether `update-ca-certificates` is present and used **(unverified — needs donor-device testing)**.
- `/usr/local/sbin/cert_client.sh` (inode 5168, present) provisions a device client cert from the cert manager. Taking over that path requires your `:3001` host to act as the cert-manager/CA `cert_client.sh` expects. The request/response protocol is **not characterized from this image (unverified — needs donor-device testing)**.

---

### 7. Optional repack of a full firmware bundle (donor-only; not executed here)

This is needed only if a community member wants to load edited config as a *rootfs bundle* on a **donor** unit rather than editing files on a running device. It produces artifacts only; **no device is written to here**.

**Ground-truth values (measured from `/tmp/pvsfw/rootfs.tgz` and the unpacked image — confirm your tooling reproduces these before changing anything):**

| field | value |
|---|---|
| `rootfs.tgz` size (`dlsize`) | `41439476` |
| `rootfs.tgz` sha256 (`hash`) | `8c7f6bbdbb8b2fc711c5be02c63c7c9e92129ecec8b8ddc768a1c4896283086f` |
| ext `image` md5 (`image_md5`) | `d7dd68eab9f8fb67dc93b266d4a26e7b` |
| ext `image` size (`imsize`) | `268435456` (fixed) |
| `rootfs.tgz` real format | XZ compressed, CRC64 (`.tgz` is a misnomer) — confirmed `file` + `xz -t` |
| members (confirmed) | `rootfs/image` (mode 0644), `rootfs/copy_configuration.sh` (mode 0755), both owned `pvs6:pvs6` |

After edits, `dlsize`, `hash`, and `image_md5` all change; `imsize` stays `268435456`.

**Host tool status (this Mac, confirmed):** `xz`, `tar`, `shasum`, `md5`, `sha256sum`, `md5sum`, and e2fsprogs `debugfs`/`e2fsck` are present. **`e2cp`/`e2tools` are NOT installed** — in-place ext writes must use `debugfs` (present) or a Linux loop-mount.

**a. Modify config inside a copy of the ext image.** macOS has no native ext4 write. Two paths:
- **`debugfs -w` (present):** work on a copy, `rm` then `write` each file, restore mode/uid/gid with `sif` (`debugfs write` does not preserve perms/owner/mtime), then `e2fsck -fy`. Whether data_logger starts cleanly with debugfs-reconstructed inodes is **(unverified — needs donor-device testing)**.
- **Linux loop-mount (recommended if available):** `mount -o loop`, `install -o 0 -g 0 -m 0644 ...`, `umount`, `e2fsck -fy`. Preserves perms/owner/timestamps naturally.

**b. Repack `rootfs.tgz`.** Tar the two members under a `rootfs/` prefix (`rootfs/image`, `rootfs/copy_configuration.sh`), then XZ-compress. The exact byte count will differ from the original (xz preset/tar implementation differ); that is fine — the manifest hashes you recompute describe *your* file and stay self-consistent.

**c. Recompute manifest fields:** `dlsize` = byte length of your `rootfs.tgz`; `hash` = sha256 of `rootfs.tgz`; `image_md5` = md5 of the inner ext **image** (not the tgz); `imsize` = `268435456`. These mappings are confirmed by symbols in the `fwup` binary: `Downloader::verifySha256` sha256-checks the download, and `image_md5` is a literal field name in the binary.

**d. Regenerate `fwup.lua`** from the documented template (`version=1`, `hardware='PVS6'`, `clone_overlay=0`, inner block `type='rootfs'`, `update='mandatory'`, `image='rootfs/image'`, `imsize=268435456`, `postinst='rootfs/copy_configuration.sh'`), substituting your recomputed `dlsize`/`hash`/`image_md5` and your own `url` and `version` string.

---

### 8. Signature reality — no re-signing

The manifest is covered by a trailing base64 RSA signature over the manifest text. We do **not** have the private key, so any edit invalidates the signature and it **cannot be regenerated**. This is a hard cryptographic wall; the recipe does not work around it.

The on-device updater binary `/home/data_logger/bin/fwup` (inode 768, 215,264 bytes) contains, in its own help text (read verbatim from the binary):

```
-k key  Use this public key file to verify the FW update spec.
        The default is %s. If key is set to NONE, no signature verification
```

Stated neutrally: `-k NONE` is a documented option of the manufacturer's own updater that skips signature verification of the update spec. **Important caveats from inspection:**
- No shipped script in this image invokes `fwup` (a full-image grep for `fwup ... -k`, `fwup -v`, or `file:///` matched nothing), and **no `fwup-usb.sh` exists anywhere in this image** — earlier references to `/usr/local/sbin/fwup-usb.sh` and a `sunpower/$MODEL/fwup.lua` USB layout are **not supported by this build** and are community/other-build reports **(unverified — needs donor-device testing)**.
- `readplatform.sh model` returns `PVS6` (confirmed in `/usr/local/bin/readplatform.sh`), so any model-keyed path would use `PVS6`.
- Whether `-k NONE` is honored at runtime, and how `fwup` is meant to be invoked against a local bundle on this build, is **(unverified — needs donor-device testing)**.

**This recipe does not flash anything.** Loading a rebuilt bundle is donor-unit-only and must never be run against a sole/production PVS6.

---

### 9. Risk and scope

- **Production-unit rule:** with no donor and a production-only system, do not flash the unit you depend on — under any circumstances. All work here is offline read-only inspection and document authoring. The `-k NONE` option is recorded as a neutral fact about the tooling; skipping signature verification removes the guard against a bad image and raises brick risk, so it is donor-only.
- **Vintage-mismatch / brick risk:** putting a 2019 build onto hardware running modern firmware risks bootloader/anti-rollback refusal, co-processor firmware mismatch, and connected-device support gaps. No explicit anti-rollback string was found in this image (only unrelated MQTT "downgrade" text), but absence here does not prove later bootloaders lack such a guard **(unverified — needs donor-device testing)**.
- **A/B recovery net:** the dual-rootfs design (`/sbin/bootswitcher`, a 334-byte wrapper over the U-Boot `bootswitcher` env var via `fw_setenv`/`fw_printenv`; partition mapping per `copy_configuration.sh`) means a donor can develop against the inactive slot and keep one known-good slot. The specific `mmcblk1p5`=root0 / `mmcblk1p6`=root1 partition numbers are corroborated by `copy_configuration.sh`; the `set_pvs_led r` on-boot-failure behaviour and U-Boot `bootcmd`/`preinit` details are **not** in `/sbin/bootswitcher` and are **(unverified — needs donor-device testing)**.
- **Co-processor firmware:** `/home/mime/bin/mifwup/` contains separately-flashable microinverter/MPPT images (`miupg-*.bin`, `mppt_upd_ee_reg_sub_1.upg`, etc.) and `/usr/local/sbin/flash_psoc.sh` flashes PSoC firmware. The previously-cited eASIC filename `e-asic_firmware_for_mime_v99.0.9.bin` and an Enphase `duo-library` provenance were **not found** in this image **(unverified — needs donor-device testing)**. Rootfs-249 ↔ co-processor version compatibility is not derivable from the image.
- **Grid/regulatory:** keep work scoped to monitoring/data-logging. Do not alter grid-profile, export-limit (`zero_export`), or interconnection settings as a side effect; those are governed by your interconnection agreement and local code and are out of scope for this recipe.

---

### Needs device verification

- Whether populating `network.Register.host` redirects the actual `cert_client.sh` cert-provisioning transaction (vs. only the `smshandler.sh` reachability probe).
- Device trust-store layout under `/etc/ssl` and whether `update-ca-certificates` is present/used for adding a private CA.
- The `cert_client.sh` cert-manager request/response protocol (needed for any MQTT/mTLS takeover).
- That `data_logger` starts cleanly with `debugfs`-reconstructed inodes (perms/owner/xattr) — Path A only.
- That the device `fwup` downloader accepts your `xz` preset on the streaming decompress path.
- That `-k NONE` is honored at runtime on this build, and the correct local-bundle invocation of `fwup` (no shipped script invokes it; no `fwup-usb.sh` exists in this image; the `sunpower/$MODEL/fwup.lua` USB layout is unconfirmed here).
- End-to-end apply on a donor: `hash`/`image_md5`/`imsize` checks pass, `copy_configuration.sh` runs as `postinst` and migrates config to the inactive slot, and the `bootswitcher` env flips and boots the new rootfs.
- Whether current/newer PVS6 bootloaders enforce anti-rollback against a 2019 image (none found in this image, but not provable from it).
- The rootfs-249 ↔ eASIC/MPPT/PSoC version compatibility matrix, and the actual eASIC firmware filename/provenance (the previously-cited `e-asic_firmware_for_mime_v99.0.9.bin` / `duo-library` were not found in this image).
- The `set_pvs_led r` boot-failure behaviour and U-Boot `bootcmd`/`preinit` details (not present in `/sbin/bootswitcher`).