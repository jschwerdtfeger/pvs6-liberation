#!/usr/bin/env bash
# pvs6.sh — tiny helper for the PVS6 local API (handles login + session cookie).
#
# Setup:
#   export PVS_IP=192.168.x.x          # your PVS6 LAN IP
#   export PVS_PW=xxxxx                # last 5 chars of the PVS6 serial
#
# Usage:
#   ./pvs6.sh login                    # authenticate, cache the session cookie
#   ./pvs6.sh info                     # supervisor/info (model, build, serial)
#   ./pvs6.sh live                     # live power/energy (5-min varserver)
#   ./pvs6.sh devices                  # device inventory
#   ./pvs6.sh var /sys/livedata/site_load_p   # read one var by name
#   ./pvs6.sh match livedata           # read a subtree by substring
#   ./pvs6.sh swagger > pvs6.json      # dump the OpenAPI spec
#   ./pvs6.sh raw /cgi-bin/dl_cgi/grid/profile   # arbitrary GET
#
# Read-only by design: it only performs GETs. State-changing POSTs are intentionally
# omitted — see SAFETY.md before sending any write.

set -euo pipefail

: "${PVS_IP:?set PVS_IP to your PVS6 LAN IP}"
: "${PVS_PW:?set PVS_PW to the last 5 chars of your PVS6 serial}"

BASE="https://${PVS_IP}"
CJ="${PVS6_COOKIE:-/tmp/pvs6.cookies}"
C() { curl -sk --max-time 15 "$@"; }

login() {
  local auth; auth=$(printf 'ssm_owner:%s' "$PVS_PW" | base64)
  C -c "$CJ" -H "Authorization: basic $auth" "$BASE/auth?login"
  echo
}

# auto-login if no cookie yet
ensure() { [ -s "$CJ" ] || login >/dev/null; }

get() { ensure; C -b "$CJ" "$BASE$1"; }

cmd="${1:-}"; shift || true
case "$cmd" in
  login)    login ;;
  info)     get "/cgi-bin/dl_cgi/supervisor/info" ;;
  live)     get "/vars?match=livedata&fmt=obj" ;;
  devices)  get "/cgi-bin/dl_cgi/devices/list" ;;
  var)      get "/vars?name=${1:?usage: var /path/to/leaf}" ;;
  match)    get "/vars?match=${1:?usage: match <substring>}&fmt=obj" ;;
  swagger)  get "/cgi-bin/swagger.json" ;;
  raw)      get "${1:?usage: raw /path}" ;;
  *) sed -n '2,30p' "$0"; exit 1 ;;
esac
echo
