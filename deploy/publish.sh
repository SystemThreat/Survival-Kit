#!/bin/sh
# Copy the SIGNED release to the onion server, after checking it here first. Refuses an unsigned or modified page.
set -eu
HOST=${XCOIN_ONION_HOST:-root@xcoin-onion}
here=$(cd "$(dirname "$0")/.." && pwd)
python3 "$here/checker/survival.py" verify "$here/site" "$here/allowed_signers"
cp "$here/allowed_signers" "$here/site/allowed_signers"
rsync -a --delete --chmod=D755,F644 \
  "$here/site/index.html" "$here/site/manifest.json" "$here/site/manifest.json.sig" "$here/site/allowed_signers" \
  "$HOST:/var/www/xcoin-survival/"
rm -f "$here/site/allowed_signers"
echo "published to $HOST:/var/www/xcoin-survival"
