#!/bin/sh
# Put the chosen xcoin… onion key onto the onion server, straight from the key drive (nothing is copied to the Mac).
#   deploy/restore-onion-key.sh <folder on the drive, named after the address>
# e.g. deploy/restore-onion-key.sh "/Volumes/david/Onion Keys/xcoinid/xcoinid….onion"
set -eu
HOST=${XCOIN_ONION_HOST:-root@xcoin-onion}
src=${1:?usage: restore-onion-key.sh <key folder on the drive>}
[ -f "$src/hs_ed25519_secret_key" ] && [ -f "$src/hs_ed25519_public_key" ] || { echo "no onion key files in $src"; exit 1; }
addr=$(basename "$src")
echo "$addr" | grep -Eq '^[a-z2-7]{56}\.onion$' || { echo "folder is not named after a v3 onion address: $addr"; exit 1; }
echo "putting $addr on $HOST (the secret key travels inside SSH over Tailscale; it is never shown)"
tar -C "$src" -cf - hs_ed25519_secret_key hs_ed25519_public_key | ssh "$HOST" '
  set -e; d=/var/lib/tor/xcoin-survival
  install -d -o debian-tor -g debian-tor -m 700 "$d"
  tar -C "$d" -xf -; printf "%s\n" "'"$addr"'" > "$d/hostname"
  chown -R debian-tor:debian-tor "$d"; chmod 600 "$d"/hs_ed25519_* "$d/hostname"
  systemctl restart tor; sleep 3; echo "tor: $(systemctl is-active tor), serving $(cat "$d/hostname")"'
