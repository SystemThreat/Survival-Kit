#!/bin/sh
# Copy the SIGNED release to the onion server, after checking it here first. Refuses an unsigned or modified page.
set -eu
HOST=${XCOIN_ONION_HOST:-root@xcoin-onion}
here=$(cd "$(dirname "$0")/.." && pwd)
python3 "$here/checker/survival.py" verify "$here/site" "$here/allowed_signers"
# tar over ssh (macOS's own rsync lacks --chmod): exactly the four release files, then world-readable for nginx
COPYFILE_DISABLE=1 tar --no-xattrs -cf - -C "$here/site" index.html manifest.json manifest.json.sig -C "$here" allowed_signers \
  | ssh "$HOST" 'set -e; d=/var/www/xcoin-survival; t=$(mktemp -d); tar -C "$t" -xf -
      install -d -m 755 "$d"; for f in index.html manifest.json manifest.json.sig allowed_signers; do install -m 644 "$t/$f" "$d/$f"; done
      rm -rf "$t"; ls -l "$d" | sed 1d'
echo "published to $HOST:/var/www/xcoin-survival"
