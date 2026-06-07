# Battery-per-inverter cap — why "6 batteries on 1 inverter" won't commission

> From offline, read-only analysis of PVS6 firmware build 61707. Right-to-repair, owned hardware.

If an installer consolidated a SunVault onto **fewer inverters than the battery count allows** — e.g. **6 batteries on a single XW Pro** — the system **cannot commission**. This is a common, non-obvious root cause of a "stuck" SunVault.

## The rule (enforced in compiled firmware)

ESS commissioning validates the inverter-to-battery layout in `ESMM::BulkSettingsImpl::preconfigureBatteryGroups()` (in `/home/data_logger/lib/libesmm.so`). The hard rule, traced to the actual compare instructions:

```
1  ≤  battery_count  ≤  4 × inverter_count
```

i.e. a hard ceiling of **4 batteries per storage inverter (XW Pro)**. Exceed it and commissioning rejects the layout, logging:

```
Unexpected XW - BMS configuration. XW count: <n>, Batt count: <m>
```

- **1 inverter + 6 batteries → 6 > 4 → REJECTED**
- **2 inverters + 6 batteries → 6 ≤ 8 → OK** (firmware even-splits to 3+3)

Notes:
- The cap is **4, not 3.** The familiar 3+3 layout is a deployment convention; the firmware only enforces ≤4 per inverter and computes group sizes by even division at runtime (no hardcoded `{3,3}`).
- There's also a **1:1 inverter↔MIO** check.

## What it means for recovery

- **Under SunStrong/PVS commissioning (Path A):** you must have enough inverters that each carries **≤4 batteries**. If your installer reduced you to one inverter for 6 batteries, restoring the second inverter (→ 3+3) is **not optional** — it's required for the firmware to commission at all.
- **6-on-1 only works via Schneider-native (Path B)**, which commissions outside the PVS6/ESMM path and isn't bound by this cap. (That's why a single-inverter, all-batteries-paralleled topology is associated with Schneider-direct setups.)

See also: [build-61707-analysis.md](build-61707-analysis.md) (full firmware analysis), [schneider-conversion.md](schneider-conversion.md) (Path B).
