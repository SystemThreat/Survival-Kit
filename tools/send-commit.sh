#!/bin/bash
# Put a sealed commitment on the xCoin chain from the commitment wallet (on the key drive), the manual way.
#   tools/send-commit.sh <72-hex OP_RETURN data from commit.py seal>
#
# Why manual: the node wallet's `send` refuses any output below the chain's 0.0001 XID floor, including the 0-value
# data output that consensus explicitly exempts (src/wallet/spend.cpp ~1114 vs src/consensus/tx_check.cpp). So this
# builds the transaction by hand: ONE confirmed coin of the wallet in, the data output plus change back to the wallet
# out, a fixed fee of 0.00003 XID (about 2 sat/vB for ~1,484 vB; mainnet owes no settlement levy today). Rehearsed on
# regtest: signed, testmempoolaccept allowed, mined. It checks every trap before asking you to type SEND.
set -euo pipefail
read -ra CLI <<< "${XCOIN_CLI:-$HOME/x-Coin/xCoin-xid/build/bin/nex-cli -datadir=$HOME/xcoin-mainnet -conf=$HOME/xcoin-mainnet/mainnet.conf}"
W="${XCOIN_SURVIVAL_KEYS:-/Volumes/david/Survival Keys}/commit-wallet"
FEE=0.00003
DATA=${1:?usage: tools/send-commit.sh <72-hex OP_RETURN data>}
[[ $DATA =~ ^58494443[0-9a-f]{64}$ ]] || { echo "the data must be 'XIDC' + fingerprint: 58494443 followed by 64 hex (72 in all)"; exit 1; }
[ -d "$W" ] || { echo "the key drive is not plugged in ($W)"; exit 1; }
"${CLI[@]}" listwallets | grep -qF "$W" || "${CLI[@]}" loadwallet "$W" >/dev/null
w() { "${CLI[@]}" -rpcwallet="$W" "$@"; }

# the largest confirmed coin of the wallet
read -r TXID VOUT AMOUNT < <(w listunspent 0 | python3 -c '
import json,sys; u=sorted([x for x in json.load(sys.stdin) if x.get("safe", True)], key=lambda x: -x["amount"])
print(u[0]["txid"], u[0]["vout"], format(u[0]["amount"], ".8f")) if u else print("- - 0")')
[ "$TXID" != "-" ] || { echo "no spendable coin in the commitment wallet: fund it first (see COMMITMENTS.md)"; exit 1; }
CHANGE=$(python3 -c "from decimal import Decimal as D; print(D('$AMOUNT') - D('$FEE'))")
python3 -c "from decimal import Decimal as D; import sys; sys.exit(0 if D('$CHANGE') >= D('0.0001') else 1)" \
  || { echo "the coin ($AMOUNT) is too small: change would be under the 0.0001 floor"; exit 1; }
ADDR=$(w getrawchangeaddress)

RAW=$(w createrawtransaction "[{\"txid\":\"$TXID\",\"vout\":$VOUT}]" "[{\"data\":\"$DATA\"},{\"$ADDR\":$CHANGE}]")
SIGNED=$(w signrawtransactionwithwallet "$RAW" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d["complete"], "signing incomplete"; print(d["hex"])')
CHECK=$("${CLI[@]}" testmempoolaccept "[\"$SIGNED\"]")
python3 - "$CHECK" "$DATA" "$FEE" "$SIGNED" <<'PY' || exit 1
import json, sys
from decimal import Decimal as D
r = json.loads(sys.argv[1])[0]; data, fee = sys.argv[2], D(sys.argv[3])
if not r.get("allowed"): sys.exit(f"the network would refuse it: {r.get('reject-reason')}")
if D(str(r["fees"]["base"])) != fee: sys.exit(f"fee is {r['fees']['base']}, expected {fee}: refusing")
print(f"checked: allowed by the network, fee {fee} XID, {r['vsize']} vbytes, data output 'XIDC'+{data[8:16]}…")
PY
echo "  in:     $AMOUNT XID ($TXID:$VOUT)"
echo "  out:    data $DATA"
echo "  change: $CHANGE XID back to the commitment wallet ($ADDR)"
read -r -p "Type SEND to broadcast: " ok
[ "$ok" = SEND ] || { echo "not sent"; exit 1; }
SENT=$("${CLI[@]}" sendrawtransaction "$SIGNED")
echo "sent: $SENT"
echo "$SENT" > "${XCOIN_SENT_FILE:-/dev/null}"
echo "after it confirms: ${CLI[*]} -rpcwallet=\"$W\" gettransaction $SENT | grep blockhash"
