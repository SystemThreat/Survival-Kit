#!/bin/sh
# Publish the SIGNED release to every official onion mirror (deploy/hosts), then check each one serves it.
#   deploy/publish.sh                                     all mirrors in deploy/hosts
#   XCOIN_ONION_HOST=root@<host> deploy/publish.sh        one mirror only
# Refuses an unsigned or modified page. After each copy it starts that host's community-mirror check (if installed), so
# /community.json reflects the new release at once instead of at the next hourly run. GitHub/Codeberg Pages are git pushes (never automatic: see README).
set -eu
here=$(cd "$(dirname "$0")/.." && pwd)
python3 "$here/checker/survival.py" verify "$here/site" "$here/allowed_signers"
want=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$here/site/manifest.json")
sum=$(shasum -a 256 "$here/site/index.html" | cut -c1-64)
if [ -n "${XCOIN_ONION_HOST:-}" ]; then hosts=$XCOIN_ONION_HOST
else
  [ -f "$here/deploy/hosts" ] || { echo "deploy/hosts is missing: copy deploy/hosts.example to deploy/hosts and list the official onions"; exit 1; }
  hosts=$(sed 's/#.*//' "$here/deploy/hosts" | tr -s ' \n' '\n' | grep .)
fi
ok=0; bad=0
for HOST in $hosts; do
  # tar over ssh (macOS's own rsync lacks --chmod): exactly the four release files, then world-readable for nginx
  if COPYFILE_DISABLE=1 tar --no-xattrs -cf - -C "$here/site" index.html manifest.json manifest.json.sig -C "$here" allowed_signers \
     | ssh -o ConnectTimeout=15 "$HOST" 'set -e; d=/var/www/xcoin-survival; t=$(mktemp -d); tar -C "$t" -xf -
         install -d -m 755 "$d"; for f in index.html manifest.json manifest.json.sig allowed_signers; do install -m 644 "$t/$f" "$d/$f"; done
         rm -rf "$t"; systemctl start --no-block xcoin-mirrors-check.service 2>/dev/null || true' \
   && got=$(ssh -o ConnectTimeout=15 "$HOST" 'curl -s http://127.0.0.1:8080/ | sha256sum | cut -c1-64') \
   && [ "$got" = "$sum" ]; then
    echo "OK    $HOST serves release $want"; ok=$((ok+1))
  else
    echo "FAIL  $HOST (not updated or not serving release $want: run again, or check the server)"; bad=$((bad+1))
  fi
done
echo "release $want: $ok mirror(s) updated, $bad failed"
[ "$bad" = 0 ]
