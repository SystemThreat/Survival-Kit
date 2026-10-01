#!/bin/sh
# Make the survival sheet's release-signing key (once). ssh-keygen asks for a passphrase itself, hidden: choose a long
# one and keep it on paper with the other key passphrases. The private key never leaves ~/.xcoin-survival-keys (and the
# USB sticks); only the public line goes into allowed_signers, which is published with every release.
set -eu
dir="$HOME/.xcoin-survival-keys"; key="$dir/release"
here=$(cd "$(dirname "$0")/.." && pwd)
if [ -e "$key" ]; then echo "a key already exists at $key: not replacing it"; exit 1; fi
mkdir -p "$dir"; chmod 700 "$dir"
ssh-keygen -t ed25519 -a 200 -C release@xcoinproject -f "$key"
printf 'release@xcoinproject namespaces="xcoin-survival" %s\n' "$(cut -d' ' -f1,2 "$key.pub")" > "$here/allowed_signers"
echo
echo "public key written to $here/allowed_signers (publish it; it is not secret)"
echo "fingerprint: $(ssh-keygen -lf "$key.pub")"
echo "NOW: copy $dir to both USB sticks (see README.md, 'The key')."
