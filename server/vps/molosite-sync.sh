#!/bin/bash
# molonari.io sync, run every hour by root's cron on the VPS: follow CGS-MOLO in the Operating Space, then push the site.
# Installed as /usr/local/sbin/molosite-sync from molonari.io/server/vps/. Settings: /etc/molonari/vps.env.
# See molonari.io/server/OperatingSpaceDeploy.md.
set -uo pipefail
CONF=${MOLONARI_VPS_ENV:-/etc/molonari/vps.env}
exec 9>/run/molosite-sync.lock
flock -n 9 || { echo "$(date -Is) already running"; exit 0; }
[ -r "$CONF" ] || { echo "$(date -Is) molosite-sync: no settings file $CONF"; exit 1; }
# shellcheck source=/dev/null
source "$CONF"
: "${CGSHOME:?CGSHOME missing in $CONF}" "${CGS_FILE:?CGS_FILE missing in $CONF}" "${MOLOSITE_ENV:=/root/.molosite.env}"
export CGSHOME PATH="/root/.pixi/bin:/usr/local/bin:/usr/bin:/bin"
# shellcheck source=/dev/null
source "$MOLOSITE_ENV"
echo "== $(date -Is) $CGSHOME $CGS_FILE"
# --frozen: pixi must not rewrite pixi.lock, or the gate checkout becomes dirty and push refuses
cd "$CGSHOME" && pixi run --frozen molo update "$CGS_FILE" || { echo "update failed"; exit 1; }
cd "$CGSHOME/molonari.io" && pixi run --frozen site push
code=$?
echo "exit $code"
exit $code
