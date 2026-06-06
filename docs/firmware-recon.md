# PVS6 Firmware Recon

Goal: determine whether a PVS6 can be made to phone home to an owner-controlled host (and ultimately operate
fully locally) by modifying its firmware. **Yes, the mechanism is open.** Details below.

> ⚠️ See [SAFETY.md](../SAFETY.md). Firmware modification can brick the device. Develop on a donor unit, never
> your production PVS6. Do not redistribute SunPower firmware binaries — fetch your own.

## 1. Firmware distribution survived the bankruptcy
- Images are served from an AWS CloudFront CDN (`fw-assets-pvs6-*.*-edp.sunpower.com`).
- Files are **publicly fetchable, no auth** (directory listing 403, but file GETs return 200), `Accept-Ranges: bytes`.

## 2. The update format is simple and self-documenting
The update entry point is a signed **Lua manifest** (`fwup.lua`):
```lua
{ version=1, hardware='PVS6', clone_overlay=0,
  { type='rootfs', update='mandatory', dlsize=<bytes>, version='<ver>',
    url='<.../rootfs.tgz>', hash='<sha256 of tgz>',
    image='rootfs/image', imsize=268435456, image_md5='<md5>',
    postinst='rootfs/copy_configuration.sh' } }
-- followed by a base64 RSA signature over the manifest
```
- The manifest is **signed**, but the on-device USB updater can reportedly run with **`-k NONE` to disable the
  signature check** (community-reported; verify on your target build). This is the path for custom images.

## 3. The image is unencrypted
- `rootfs.tgz` is **XZ-compressed tar** (despite the `.tgz` name), containing `rootfs/copy_configuration.sh` and
  `rootfs/image` (a ~256 MB **ext4** filesystem). No decryption needed.

### Unpack (Linux, or macOS with Homebrew)
```bash
brew install e2fsprogs binwalk p7zip xz      # macOS; on Linux use your package manager
curl -sk -o rootfs.tgz "<rootfs.tgz url>"
sha256sum rootfs.tgz                          # compare to manifest `hash`
tar xf rootfs.tgz                             # -> rootfs/image (ext4) + copy_configuration.sh
debugfs -R "cat /etc/PVS.json" rootfs/image
debugfs -R "cat /home/data_logger/config.lua" rootfs/image
```
(`debugfs` ships with e2fsprogs; on macOS it's at `/opt/homebrew/opt/e2fsprogs/sbin/debugfs`.)

## 4. Phone-home is plaintext, editable config
`copy_configuration.sh` (the postinst) preserves these across updates — i.e. they're the per-site config:
`/etc/PVS.json`, `/home/data_logger/{config.lua,default_config.lua,devices.lua}`, `/home/commapp_state.txt`,
ssh host keys.

**`/home/data_logger/config.lua` → `param_table`** holds the upstream URLs as plain strings:
```lua
data_chan_url_1/2/3 = "<telemetry endpoint>"   -- 3 failover URLs
cmd_chan_url_1/2/3  = "<command/control endpoint>"
data_chan_conn_int, cmd_chan_conn_int          -- poll intervals (s)
zero_export = { ... }                          -- do-not-export config
```
**`/etc/PVS.json` → `network.Register.host`** is the registration endpoint; `system.environment` selects prod/dev.

➡️ Repointing phone-home = editing these strings, repacking the ext image, rebuilding the manifest, and loading
it (signature-bypassed). No binary patching required for the endpoint change.

## Build-era caveat (important)
Recon to date was performed on an **older, pre-lockdown build** that used a **legacy HTTP collector** for
`data_chan_url_*`. Current (~2025.x) firmware moved upstream comms to **AWS IoT MQTT + mutual TLS** (see the
swagger `cert/mqtt` endpoint and `cert_client.sh`). The *editable-config mechanism and file locations are
proven*, but the **current-build config format** (MQTT broker host + CA/trust + client-cert paths) must be
confirmed against a current image. Because you control the rootfs, you also control the trust store — which is
what makes repointing to your own broker possible where DNS-spoofing fails (mTLS).

## Open problems
- [ ] Locate current-build (2025.x) image URLs / manifest path scheme.
- [ ] Map the modern MQTT broker + cert/trust config in a current image.
- [ ] Verify `-k NONE` modified-image load on a current build (donor unit).
- [ ] Reference local broker/server, or pivot commissioning to Schneider-native.

**Liberation** (cut cloud / repoint / local monitoring) is clearly achievable. **Local commissioning** of the
ESS remains the hard kernel and may be better solved via Schneider-native conversion than by re-implementing a
proprietary cloud.
