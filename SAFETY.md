# SAFETY & LEGAL — read before doing anything

This project touches **grid-tied solar + battery hardware** and, optionally, **firmware modification**. Mistakes can damage equipment, void interconnection agreements, violate code, or be dangerous. Proceed only if you understand and accept that risk.

## Electrical / grid
- High-voltage DC (battery) and AC (grid/inverter) are present. De-energize and follow lockout/tagout before any physical work.
- **Grid-interaction settings are regulated.** Export limits, grid profiles, and anti-islanding behavior are governed by UL 1741 / IEEE 1547, your **utility interconnection agreement** (e.g., PG&E Rule 21), and your AHJ. Do not change `grid/profile`, `grid/export_limit`, or related settings without understanding the rules that apply to you. When in doubt, consult your utility / a licensed electrician.
- Battery (ESS) work — bus, BMS, comms — should not be improvised. Get qualified help.

## Firmware
- Loading modified or unsigned firmware can **brick** the device. Recovery may require UART/U-Boot/JTAG.
- **Never develop against your only/production PVS6.** Use a donor/test unit.
- Keep a known-good image and a recovery plan before flashing anything.

## Legal
- **Do not redistribute SunPower/SunStrong firmware binaries.** This project documents how to fetch your own image and what to edit — it does not host their copyrighted images. `.gitignore` blocks image files; keep it that way.
- This is owner-of-record, right-to-repair tooling for hardware you own. It is **not** affiliated with, endorsed by, or supported by SunPower, SunStrong, Schneider Electric, or any utility.
- No warranty. See [LICENSE](LICENSE). You assume all risk.

## Privacy
- Don't commit your **serial number, credentials (`ssm_owner` password = last 5 of serial), site keys, or device certs.** Treat them like passwords.
