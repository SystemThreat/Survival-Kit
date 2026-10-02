#!/usr/bin/env python3
"""Sealed commitments (commit-reveal): publish a fingerprint now, prove later what it hid.

  fingerprint = SHA-256( "xcoin-commit/1|" + secret text + "|" + salt )         (UTF-8; salt = 64 lowercase hex)

The salt (32 random bytes) makes the fingerprint unguessable even for someone who guesses the text. The secret text and
salt are written ONLY to the key drive; they are never printed until you reveal. The fingerprint is safe to publish
anywhere: on the page, and in an xCoin transaction (OP_RETURN) whose block time proves when it existed.

  tools/commit.py seal                 asks the secret text at a hidden prompt; writes the sealed file on the key drive;
                                       prints only the fingerprint and the OP_RETURN data (hex) to put on chain
  tools/commit.py reveal <file>        prints text, salt and fingerprint, for publishing on the day you reveal
  tools/commit.py onchain <block.json|-> <fingerprint>  find it in a block: nex-cli getblock <hash> 2 | tools/commit.py onchain - <fp>
  tools/commit.py verify <text> <salt> <fingerprint>    anyone: recompute and compare (also works with plain shasum, see README)
"""
import getpass, hashlib, json, os, re, secrets, shlex, sys, time

PREFIX = "xcoin-commit/1|"
TAG = b"XIDC"                                            # OP_RETURN data = TAG + 32-byte fingerprint (36 bytes)
DIR = os.path.join(os.environ.get("XCOIN_SURVIVAL_KEYS", "/Volumes/david/Survival Keys"), "commitments")
SALT = re.compile(r"^[0-9a-f]{64}$")


def fingerprint(text, salt):
    if not SALT.match(salt): raise ValueError("salt must be 64 lowercase hex characters")
    if not text or "|" in text or text != text.strip(): raise ValueError("text must be non-empty, no '|', no leading/trailing spaces")
    return hashlib.sha256((PREFIX + text + "|" + salt).encode("utf-8")).hexdigest()


def opreturn_hex(fp): return (TAG + bytes.fromhex(fp)).hex()


def seal(text=None, salt=None, out_dir=DIR):
    keys = os.path.dirname(out_dir)
    if not os.path.isdir(keys) or not os.path.isfile(os.path.join(keys, "release.pub")):
        raise SystemExit(f"the key drive is not plugged in (no {keys}/release.pub): nothing written")
    if text is None:
        text = getpass.getpass("Secret text to seal (not shown): ").strip()
        if getpass.getpass("Type it again: ").strip() != text: raise SystemExit("the two entries differ: nothing written")
    salt = salt or secrets.token_hex(32)
    fp = fingerprint(text, salt)
    os.makedirs(out_dir, mode=0o700, exist_ok=True)
    path = os.path.join(out_dir, f"commit-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{fp[:8]}.json")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f: json.dump({"format": "xcoin-commit/1", "text": text, "salt": salt, "fingerprint": fp}, f)
    return path, fp


def reveal(path):
    d = json.load(open(path))
    if fingerprint(d["text"], d["salt"]) != d["fingerprint"]: raise SystemExit("the sealed file does not recompute to its own fingerprint")
    return d


def onchain(block, fp):
    """Find the commitment in a block (getblock <hash> 2 JSON): exactly one output whose script is 6a24 'XIDC' <fp>.
    Returns {"txid", "height", "time"} or None. Anything else (other OP_RETURNs, wrong length, wrong tag) is ignored."""
    want = "6a24" + opreturn_hex(fp.lower())
    for tx in block.get("tx", []):
        for o in tx.get("vout", []):
            if o.get("scriptPubKey", {}).get("hex") == want:
                return {"txid": tx["txid"], "height": block["height"], "time": block["time"]}
    return None


def main(argv):
    if argv[:1] == ["seal"] and len(argv) == 1:
        path, fp = seal()
        print(f"sealed (secret text and salt are on the key drive only): {path}")
        print(f"fingerprint (publish this): {fp}")
        print(f"OP_RETURN data (hex, 36 bytes = 'XIDC' + fingerprint): {opreturn_hex(fp)}")
        print("NEXT: copy the commitments folder to the second USB stick too.")
        return 0
    if argv[:1] == ["reveal"] and len(argv) == 2:
        d = reveal(argv[1])
        print(f"text: {d['text']}\nsalt: {d['salt']}\nfingerprint: {d['fingerprint']}")
        print("anyone checks: printf '%s' " + shlex.quote(PREFIX + d['text'] + "|" + d['salt']) + " | shasum -a 256")
        return 0
    if argv[:1] == ["verify"] and len(argv) == 4:
        try: ok = fingerprint(argv[1], argv[2]) == argv[3].lower()
        except ValueError as e: print(f"NO MATCH ({e})"); return 1
        print("MATCH: this text and salt are what the fingerprint sealed" if ok else "NO MATCH")
        return 0 if ok else 1
    if argv[:1] == ["onchain"] and len(argv) == 3:
        hit = onchain(json.load(open(argv[1]) if argv[1] != "-" else sys.stdin), argv[2])
        if not hit: print("NOT in this block (looked for exactly 6a24 58494443 <fingerprint>)"); return 1
        print(f"FOUND in tx {hit['txid']} at height {hit['height']}, block time {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(hit['time']))}")
        return 0
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
