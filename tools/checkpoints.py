#!/usr/bin/env python3
"""Write the checkpoint table of site/index.html from a node: one row per 1,000 heights, newest first, only heights at
least DEPTH blocks deep (a checkpoint must never be reorganised away). Every hash is asked of TWO nodes and must agree,
so one node on a wrong chain cannot put a wrong checkpoint on the page. Nothing is typed by hand.

  tools/checkpoints.py                       ask this Mac's node, cross-check a second node over ssh (read-only)
  tools/checkpoints.py --check               only compare the page with the nodes; change nothing (exit 1 on any difference)

Environment: XCOIN_CLI (the local nex-cli command line), XCOIN_CHECK_SSH (ssh target of the second node, read-only;
or the one line of the private, git-ignored file deploy/check-node), XCOIN_CHECK_CLI (nex-cli command line on it).
Then sign a new release (tools/sign.sh <n>) and publish it.
"""
import os, re, shlex, subprocess, sys

STEP, DEPTH = 1000, 100
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(HERE, "site", "index.html")
LOCAL = shlex.split(os.environ.get("XCOIN_CLI", os.path.expanduser(
    "~/x-Coin/xCoin-xid/build/bin/nex-cli -datadir=~/xcoin-mainnet -conf=~/xcoin-mainnet/mainnet.conf").replace("~", os.path.expanduser("~"))))
def check_node():
    """The second node's ssh target: XCOIN_CHECK_SSH, or deploy/check-node (private, git-ignored: see check-node.example)."""
    t = os.environ.get("XCOIN_CHECK_SSH")
    f = os.path.join(HERE, "deploy", "check-node")
    if not t and os.path.exists(f):
        t = next((l.split("#")[0].strip() for l in open(f) if l.split("#")[0].strip()), None)
    if not t: raise SystemExit("no second node: set XCOIN_CHECK_SSH or write deploy/check-node (see deploy/check-node.example)")
    return t
REMOTE = os.environ.get("XCOIN_CHECK_CLI", "/opt/xcoin/mainnet/bin/nex-cli -conf=/etc/xcoin/mainnet.conf")
GENESIS = "3bc1a36df7d786a5c4584e21d248e0a3785a96aaa60a5b3959dfad50283379f2"
BEGIN, END = "<!-- checkpoints:begin (written by tools/checkpoints.py; newest first) -->", "<!-- checkpoints:end -->"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
EXPLORER = "https://superknet.com/block/"   # a convenience link only: the hash itself is what to compare


def local(*args):
    return subprocess.run(LOCAL + list(args), capture_output=True, text=True, check=True, timeout=60).stdout.strip()


def remote_hashes(heights):
    """All hashes from the second node in one SSH call (read-only RPC)."""
    cmd = "; ".join(f"{REMOTE} getblockhash {h}" for h in heights)
    out = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", check_node(), cmd],
                         capture_output=True, text=True, check=True, timeout=120).stdout.split()
    if len(out) != len(heights): raise SystemExit(f"second node returned {len(out)} hashes for {len(heights)} heights")
    return dict(zip(heights, out))


def fmt(n): return f"{n:,}"


def rows_html(cps):
    return "\n".join(f'<tr data-h="{h}"><th>{fmt(h)}</th><td class="hash"><a href="{EXPLORER}{x}">{x}</a></td></tr>' for h, x in cps)


def parse(page):
    """The checkpoints currently on the page: [(height, hash)], as written."""
    body = page[page.index(BEGIN) + len(BEGIN):page.index(END)]
    return [(int(h), x) for h, x in re.findall(r'<tr data-h="(\d+)"><th>[\d,]+</th><td class="hash"><a href="https://superknet\.com/block/([0-9a-f]{64})">\2</a></td></tr>', body)]


def collect():
    # the tip both nodes have reached: a node that is behind (or ahead on a fork) cannot raise the page's height
    tip = min(int(local("getblockcount")), int(subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", check_node(),
              f"{REMOTE} getblockcount"], capture_output=True, text=True, check=True, timeout=60).stdout.strip()))
    top = (tip - DEPTH) // STEP * STEP
    heights = list(range(0, top + 1, STEP))
    mine = {h: local("getblockhash", str(h)) for h in heights}
    theirs = remote_hashes(heights)
    bad = [h for h in heights if mine[h] != theirs[h] or not HEX64.match(mine[h])]
    if bad: raise SystemExit(f"the two nodes disagree (or a hash is malformed) at heights {bad}: not writing anything")
    if mine[0] != GENESIS: raise SystemExit("height 0 is not the xCoin genesis: wrong chain, not writing anything")
    return tip, [(h, mine[h]) for h in reversed(heights)]


def genesis_coinbase_ok(page):
    """The genesis message hex shown on the page must be block 0's coinbase, byte for byte, as the node returns it."""
    import json
    m = re.search(r'id="gm-hex">([0-9a-f]+)</pre>', page)
    if not m: return True
    blk = json.loads(local("getblock", GENESIS, "2"))
    return blk["tx"][0]["vin"][0]["coinbase"] == m.group(1)


def main(argv):
    page = open(PAGE, encoding="utf-8").read()
    if not genesis_coinbase_ok(page): raise SystemExit("the genesis message hex on the page is not block 0's coinbase: fix the page first")
    tip, cps = collect()
    if "--check" in argv:
        have = parse(page)
        want = {h: x for h, x in cps}
        wrong = [h for h, x in have if want.get(h) != x]
        missing = sorted(set(want) - {h for h, _ in have})
        print(f"page: {len(have)} checkpoints; nodes agree on {len(cps)} (tip {fmt(tip)}); wrong on the page: {wrong or 'none'}; "
              f"missing (page is stale): {missing or 'none'}")
        return 1 if wrong or missing else 0
    new = page[:page.index(BEGIN) + len(BEGIN)] + "\n" + rows_html(cps) + "\n" + page[page.index(END):]
    new = re.sub(r"<!-- cp-tip -->.*?<!-- /cp-tip -->", f"<!-- cp-tip -->{fmt(tip)}<!-- /cp-tip -->", new)
    if parse(new) != cps: raise SystemExit("internal: the written table does not read back as the nodes' checkpoints")
    open(PAGE, "w", encoding="utf-8").write(new)
    print(f"wrote {len(cps)} checkpoints (0 to {fmt(cps[0][0])}), tip {fmt(tip)}; both nodes agree. Now: tools/sign.sh <next version>")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
