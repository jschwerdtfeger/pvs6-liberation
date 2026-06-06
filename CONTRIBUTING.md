# Contributing

Thanks for helping SunPower/SunVault owners get off a dead cloud. This project is built by and for owners,
reverse-engineers, and Schneider/Conext folks. Contributions of all sizes are welcome — a confirmed firmware
path, a Home Assistant dashboard, or just "this worked on my build, this didn't."

## Ground rules (please read)

**Safety first.** Read [SAFETY.md](SAFETY.md). This is grid-tied power equipment. Don't post procedures you
haven't reasoned through, and flag anything that touches grid profiles, export limits, or battery comms.

**Never commit:**
- **Firmware binaries or extracted images** — copyright. Document how to fetch one's *own* image; don't host
  SunPower's. (`.gitignore` blocks the common file types — keep it that way.)
- **Serials, credentials, site keys, or device certs.** The local-API password is the last 5 of the serial —
  treat it like a password. Use placeholders (`<PVS_IP>`, `<LAST5>`) in all examples.
- **Anyone's personal data** — addresses, account info, support-ticket contents.

**Test on a donor unit.** Anything that flashes or reconfigures firmware must be developed on a spare/test
PVS6, never the contributor's only/production unit. Say so in the PR.

## How to contribute

1. Open an issue describing what you're adding/fixing (or pick an open one — see the status board in the README).
2. For findings, include your **firmware build number** (`GET /cgi-bin/dl_cgi/supervisor/info`) — behavior
   differs a lot across builds, so version-stamping is essential.
3. Keep PRs focused. Docs and tooling are equally valued.
4. Note what you actually verified vs. what's inferred. Honest "unverified" is better than confident-and-wrong.

## Good first contributions

- "Works-on-my-build" reports (build number + what worked) — these build the compatibility matrix.
- Home Assistant / Grafana configs against the local API.
- Cleaning up or extending the docs for clarity.
- Schneider-native conversion notes from real installs.

## Project values

- **Honesty over hype.** We mark what's proven, what's experimental, and what's a dead end.
- **Owner autonomy.** The goal is local-first control with no third-party dependency — including ours.
- **Don't make things worse.** A bricked gateway helps no one; conservative defaults, loud warnings.
