# Schneider-Native Conversion (Track B)

> **Status: skeleton / work in progress.** This is the most promising path for *stranded* systems (stuck at
> commissioning) because Schneider Conext hardware **commissions and runs locally by design** — no cloud, no
> SunStrong. Contributions from people who've done a real conversion are especially wanted.

> ⚠️ Read [SAFETY.md](../SAFETY.md). This involves high-voltage DC/AC and battery work. Several steps should be
> done by, or with, a qualified installer. Grid-interaction settings are regulated by your utility/AHJ.

## The idea

Many SunVault systems are built on **Schneider Conext** hardware wearing SunPower clothing:
- **XW Pro** hybrid inverter(s)
- **Insight Facility** (monitoring/gateway)
- **MIO / MID** (insight + interconnect devices)
- SunVault battery modules

The SunStrong-specific, cloud-dependent parts are the **PVS6** and **Hub+**. Convert by **removing those** and
running the batteries/inverter on their native Schneider brains, with a local controller for automation.

```
Remove:  PVS6, Hub+, SunStrong dependency
Keep:    SunVault batteries, XW Pro inverter(s), MIO, Insight Facility, battery comms wiring
Add:     Schneider BCS, Raspberry Pi (Node-RED), CT clamps (2 grid + 1 solar)
Result:  Schneider-native, local-first control + monitoring, self-consumption + backup, no cloud
```

Keepalive note: on these systems, keepalive/control signaling is provided by **MIO + Insight Facility** — no
separate keepalive hardware is required.

## High-level migration steps (verify per system)

> These are a starting outline, not a validated procedure. Do not run blind — confirm against Schneider Conext
> documentation and your specific hardware/firmware.

1. **Document everything first.** Photograph all wiring, label breakers, record model/serial/firmware of each
   device, and trace your GridSense / ESS breakers (e.g., the 125A ESS and 20A grid-reference feeds) before
   changing anything.
2. Replace **Hub+ with the Schneider BCS** (battery control).
3. Add a **Raspberry Pi** running Node-RED as the local control/automation host.
4. Remove **BTS cables** between the inverter and MIO (per conversion guidance).
5. **Factory reset Insight Facility.**
6. **Factory reset the XW Pro.**
7. **Reprogram as a Schneider system** (Conext config tool / Insight — local).
8. **Verify CTs** (2 grid import/export + 1 solar production) read correctly.
9. **Bring online**; validate charge/discharge, self-consumption, and backup transfer.

## Battery topology

Leaving **both battery cabinets paralleled** onto a shared DC bus to a single XW Pro is reported to give less
SOC drift and better balancing than split topologies. Confirm against your inverter's DC input ratings.

## CT configuration

- 2× CT — grid import/export
- 1× CT — solar production

## Open questions / help wanted

- A validated, step-by-step conversion checklist with photos.
- Conext config templates / screenshots for a SunVault-derived system.
- Node-RED flows for self-consumption + backup logic.
- Mapping of common SunPower breaker/GridSense layouts to Schneider expectations.
- Known firmware-version gotchas on XW Pro / Insight Facility.

## Credits

Conversion methodology pioneered in the community by Christopher Beene (Beene Brothers) and others on the
DIY solar forums. This doc aims to turn that tribal knowledge into a repeatable, open guide.
