#!/bin/sh
# Make the survival sheet's release-signing key (once). ssh-keygen asks for a passphrase itself, hidden: choose a long
# one and keep it on paper with the other key passphrases. The private key is made ON THE KEY DRIVE (david), never on
# the Mac, and copied to the second stick; only the public line goes into allowed_signers, which is published with every release.
set -eu
dir="${XCOIN_SURVIVAL_KEYS:-/Volumes/david/Survival Keys}"; key="$dir/release"
[ -d "${dir%/*}" ] || { echo "the key drive is not plugged in (${dir%/*}): plug it in first"; exit 1; }
here=$(cd "$(dirname "$0")/.." && pwd)
if [ -e "$key" ]; then echo "a key already exists at $key: not replacing it"; exit 1; fi
mkdir -p "$dir"; chmod 700 "$dir"
ssh-keygen -t ed25519 -a 200 -C release@xcoinproject -f "$key"
printf 'release@xcoinproject namespaces="xcoin-survival" %s\n' "$(cut -d' ' -f1,2 "$key.pub")" > "$here/allowed_signers"
echo
echo "public key written to $here/allowed_signers (publish it; it is not secret)"
echo "fingerprint: $(ssh-keygen -lf "$key.pub")"
echo "NOW: copy $dir to the second USB stick too (see README.md, 'The key'). Nothing was written to this Mac."
