# Downgrading a locked PVS6 to a pre-lockdown build — feasibility

> From offline, read-only analysis of PVS6 firmware build 61707. Right-to-repair, owned hardware.

Newer PVS6 firmware (build **61840+**, e.g. 61846) gates the local commissioning API behind authentication. Older builds (e.g. **61707**) leave it open. So: can you downgrade a locked unit to a pre-lockdown build to regain the open API?

## What we can confirm: 61707 has no anti-rollback

Disassembly of 61707's updater (`fwup`) plus a sweep of its boot/recovery layer found **no version-floor / anti-rollback anywhere**:
- `fwup` never compares the manifest build against the running build. Its only version check is the manifest *schema* version. Installed revs are read only for a "skip identical" **equality** optimization — a *different* build, higher **or lower**, gets written.
- Signature is a single fixed RSA key (not keyed per build). `update=mandatory` is server-side urgency, not a guard.
- The bootloader env boots via **unsigned `bootz`**; `bootswitcher` is a plain A/B index; `recovery` restores byte-identical backups only. No rollback counter / min-version anywhere.

So a **correctly-signed** pre-lockdown image would install and boot **as far as 61707's own mechanism is concerned**.

> Note on signatures: an **unmodified** downgrade is genuinely signed, so it does **not** hit a signature wall. A **modified** image (e.g. repointed to your own server) breaks the signature and needs the updater's `-k NONE` option + console/root access.

## What we can't confirm (the honest unknowns)

A rollback guard, if one exists, would live where this rootfs can't reveal it:
1. **The locked build's own `fwup`/manifest** — could carry a server-injected minimum or a version gate (we don't have the 61846 image).
2. **The U-Boot binary + live env** — on the eMMC boot partitions, outside the rootfs.
3. **The i.MX6 eFUSE / HAB secure-boot state** — hardware fuse state, unreadable offline; the one thing that could hard-block *modified* (unsigned) firmware.

So: 61707 will *accept* a downgrade; whether the *locked unit you start from* lets you perform it depends entirely on logic we can't see offline.

## How to settle it cheaply

A **bare PVS6 is ~$60** used — a throwaway test bench:
- Ideally start from a unit already on the **locked** build, dry-run `fwup` (`-D`) with a signed pre-lockdown manifest, and watch for any version-refusal. That surfaces a guard in the locked build / U-Boot / eFUSE if it exists.
- **Back up the eMMC boot partitions + both rootfs slots first.** A blocked or botched flash can brick the boot env.
- **Never test on a production unit.**

## Reality check

Even if a downgrade works, it (a) does **not** fix battery/inverter topology — you still need the right inverter count ([battery-inverter-cap.md](battery-inverter-cap.md)) — and (b) is **unnecessary** if you already have a unit on a pre-lockdown build. Its real value is for the liberation tooling and for verifying the procedure on cheap hardware before risking anything real.
