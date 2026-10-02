#!/bin/bash
# One command for a sealed commitment: seal it, put it on the xCoin chain, wait for the block, prove it is there.
#   ~/xcoin-sites/xcoin-survival/tools/seal-and-send.sh
# You type the secret twice (hidden) and SEND once. Run it in the macOS Terminal app, key drive plugged in.
# The secret text and salt go only to the key drive; this prints only public things (fingerprint, txid, block).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
read -ra CLI <<< "${XCOIN_CLI:-$HOME/x-Coin/xCoin-xid/build/bin/nex-cli -datadir=$HOME/xcoin-mainnet -conf=$HOME/xcoin-mainnet/mainnet.conf}"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

echo "== 1/3 seal (type the secret twice; nothing shows)"
python3 "$HERE/commit.py" seal | tee "$TMP/seal.txt"
DATA=$(sed -n 's/^OP_RETURN data.*: \(58494443[0-9a-f]\{64\}\)$/\1/p' "$TMP/seal.txt")
FP=${DATA:8}
[ ${#FP} = 64 ] || { echo "could not read the fingerprint from the seal: stopping (nothing was sent)"; exit 1; }

echo; echo "== 2/3 put it on the chain"
XCOIN_SENT_FILE="$TMP/txid" "$HERE/send-commit.sh" "$DATA"
TXID=$(cat "$TMP/txid")

echo; echo "== 3/3 waiting for the block (about 4 minutes; Ctrl+C is safe, it is already sent)"
# ask the commitment wallet (the node keeps no full transaction index, so getrawtransaction stops finding it once mined)
W="${XCOIN_SURVIVAL_KEYS:-/Volumes/david/Survival Keys}/commit-wallet"
until BH=$("${CLI[@]}" -rpcwallet="$W" gettransaction "$TXID" 2>/dev/null | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("blockhash",""))
except ValueError: print("")') && [ -n "$BH" ]; do
  printf '.'; sleep 20
done
echo
"${CLI[@]}" getblock "$BH" 2 | python3 "$HERE/commit.py" onchain - "$FP"
echo
echo "DONE. Public record of this commitment (safe to share):"
echo "  fingerprint: $FP"
echo "  txid:        $TXID"
echo "Copy '/Volumes/david/Survival Keys' (commitments + commit-wallet) to the second USB stick."
