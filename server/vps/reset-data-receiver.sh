#!/bin/bash
# Put the receiver's database in place for the askdb page of molonari.io (plugin sqlite-molonaviz).
# Installed as /usr/local/sbin/reset-data-receiver from molonari.io/server/vps/. Settings: /etc/molonari/vps.env.
#   reset-data-receiver           check RECEIVER_DB, copy it (SQLite backup API), check the copy, then replace SITE_DB;
#                                 the previous file is kept as SITE_DB.prev
#   reset-data-receiver --check   check and print what would be done; write nothing
# See molonari.io/server/reset-data-receiver.md.
set -euo pipefail
CONF=${MOLONARI_VPS_ENV:-/etc/molonari/vps.env}
[ -r "$CONF" ] || { echo "reset-data-receiver: no settings file $CONF"; exit 1; }
# shellcheck source=/dev/null
source "$CONF"
: "${CGSHOME:?CGSHOME missing in $CONF}" "${RECEIVER_DIR:?RECEIVER_DIR missing in $CONF}" "${RECEIVER_DB:?RECEIVER_DB missing in $CONF}"
: "${SITE_DB:=/var/lib/molonari/Molonari.sqlite}"
SRC="$CGSHOME/$RECEIVER_DIR/$RECEIVER_DB"
PY="$CGSHOME/.pixi/envs/default/bin/python"
[ -f "$SRC" ] || { echo "reset-data-receiver: $SRC not found (check RECEIVER_DIR and RECEIVER_DB in $CONF)"; exit 1; }
[ -x "$PY" ] || { echo "reset-data-receiver: no $PY (run pixi install in $CGSHOME)"; exit 1; }
if [ -e "$SITE_DB" ] && [ "$(readlink -f "$SRC")" = "$(readlink -f "$SITE_DB")" ]; then
    echo "reset-data-receiver: $SRC is $SITE_DB itself (a live receiver writes it?): nothing to copy"; exit 1
fi
case "${1:-}" in
    "") MODE=copy ;;
    --check) MODE=check ;;
    *) echo "reset-data-receiver: unknown option '$1' (only --check); nothing written"; exit 2 ;;
esac
[ "$MODE" = copy ] && install -d -m 755 "$(dirname "$SITE_DB")"
# The plugin reads table RawMeasuresTemp, ordered by Date: refuse a file it could not show. The copy goes through the
# SQLite backup API, so a database being written is copied consistently, and it is checked again before it replaces SITE_DB.
summary=$("$PY" -I - "$SRC" "$MODE" "$SITE_DB.new" <<'PY'
import os, sqlite3, sys
src_path, mode, new_path = sys.argv[1:4]

def summary(db):
    if "Date" not in [r[1] for r in db.execute("pragma table_info(RawMeasuresTemp)")]:
        sys.exit("no table RawMeasuresTemp with a Date column: the askdb page could not show it")
    rows, last = db.execute("select count(*), max(Date) from RawMeasuresTemp").fetchone()
    return f"{rows} rows in RawMeasuresTemp, newest {last}"

src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
text = summary(src)
if mode == "copy":
    if os.path.exists(new_path):
        os.remove(new_path)
    dst = sqlite3.connect(new_path)
    src.backup(dst)
    dst.close()
    copy = sqlite3.connect(f"file:{new_path}?mode=ro", uri=True)
    if copy.execute("pragma integrity_check").fetchone()[0] != "ok" or summary(copy) != text:
        os.remove(new_path)
        sys.exit("the copy does not match its source")
print(text)
PY
) || { echo "reset-data-receiver: $SRC refused; $SITE_DB unchanged"; rm -f "$SITE_DB.new"; exit 1; }
echo "source: $SRC ($summary)"
echo "target: $SITE_DB"
[ "$MODE" = check ] && { echo "--check: nothing written"; exit 0; }
chmod 644 "$SITE_DB.new"
[ -f "$SITE_DB" ] && cp -p "$SITE_DB" "$SITE_DB.prev"
mv -f "$SITE_DB.new" "$SITE_DB"
echo "done; the previous file is $SITE_DB.prev"
