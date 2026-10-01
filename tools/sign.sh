#!/bin/sh
# Sign a release of the sheet: writes site/manifest.json for the given version and site/manifest.json.sig, then checks
# the result with the published allowed_signers. ssh-keygen asks for the key's passphrase (hidden).
#   tools/sign.sh <version>
set -eu
here=$(cd "$(dirname "$0")/.." && pwd); dir="${XCOIN_SURVIVAL_KEYS:-/Volumes/david/Survival Keys}"; key="$dir/release"
[ -f "$key" ] || { echo "no release key at $key: plug in the key drive"; exit 1; }
[ $# -eq 1 ] || { echo "usage: tools/sign.sh <version number, higher than the last>"; exit 2; }
python3 "$here/checker/survival.py" manifest "$here/site" "$1"
rm -f "$here/site/manifest.json.sig"
ssh-keygen -Y sign -f "$key" -n xcoin-survival "$here/site/manifest.json"
python3 "$here/checker/survival.py" verify "$here/site" "$here/allowed_signers"
