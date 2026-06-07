#!/usr/bin/env bash
# check-fw.sh — ask SunPower's update server what firmware YOUR PVS6 is offered,
# and print only the resulting firmware URL.
#
# Why this exists: the update server only offers firmware to units that are BEHIND.
# If your PVS6 is on an older build, this returns a URL to the newer image. Sharing
# that URL (NOT your serial) lets the pvs6-liberation project document the latest build.
#
# Read-only: this changes NOTHING on your PVS6 or your account. It just asks a question.
#
# Privacy: the last 5 characters of a PVS6 serial are its local-API password, so this
# script is careful to NEVER print your serial — only the firmware URL it gets back.
#
# Usage:  ./check-fw.sh <PVS6_LAN_IP>
#   e.g.  ./check-fw.sh 192.168.1.50

set -eu

PVS_IP="${1:-}"
[ -n "$PVS_IP" ] || { echo "usage: $0 <PVS6_LAN_IP>   (e.g. $0 192.168.1.50)"; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "error: curl is required"; exit 1; }

API="https://firmware-update-api.edp.sunpower.com/pvs6/"

# 1. Read serial + build from the PVS6 (this endpoint needs no password).
INFO=$(curl -sk --max-time 15 "https://$PVS_IP/cgi-bin/dl_cgi/supervisor/info" 2>/dev/null || true)
FLAT=$(printf '%s' "$INFO" | tr -d '\n\t')
SERIAL=$(printf '%s' "$FLAT" | sed -n 's/.*"SERIAL":[^"]*"\([^"]*\)".*/\1/p')
BUILD=$(printf '%s' "$FLAT" | sed -n 's/.*"BUILD":[[:space:]]*\([0-9][0-9]*\).*/\1/p')

if [ -z "$SERIAL" ] || [ -z "$BUILD" ]; then
  echo "Couldn't read your PVS6 at $PVS_IP."
  echo "Double-check the IP and that you're on the same network. To test by hand:"
  echo "  curl -sk https://$PVS_IP/cgi-bin/dl_cgi/supervisor/info"
  exit 1
fi

echo "Your PVS6 is on build $BUILD."

# 2. Ask the update server what firmware THIS unit is offered.
Q="${API}?fwver=${BUILD}&sn=${SERIAL}&type=PVS6&ctx=auto"
RESP=$(curl -s --max-time 20 "$Q" 2>/dev/null || true)
# Some machines lack the intermediate CA for *.edp.sunpower.com; retry without verify.
[ -n "$RESP" ] || RESP=$(curl -sk --max-time 20 "$Q" 2>/dev/null || true)

# 3. Report. Only ever print the URL — never the serial.
case "$RESP" in
  http*)
    if printf '%s' "$RESP" | grep -qF "$SERIAL"; then
      echo
      echo "An update URL came back, but it CONTAINS your serial — do NOT share it as-is."
      echo "Let the maintainer know so it can be handled safely."
      exit 0
    fi
    echo
    echo "Your unit is offered a firmware update. This URL is safe to share (no serial in it):"
    echo
    echo "    $RESP"
    echo
    echo "That URL is the only thing to send. If it looks like it has a long personal token in"
    echo "it, DM it rather than posting publicly. Thanks for helping."
    ;;
  *)
    echo "No update offered — your unit is already current (or not eligible)."
    echo "Nothing to share here, but thanks for checking."
    ;;
esac
