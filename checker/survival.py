#!/usr/bin/env python3
"""xCoin survival sheet: the manifest, its signature, and the mirror checker. Python standard library + ssh-keygen only.

A release of the sheet is a directory (site/) plus two files next to it:
  manifest.json       {"format", "version", "created", "files": {name: sha256}}  (canonical JSON, see manifest_bytes)
  manifest.json.sig   an OpenSSH signature of manifest.json, namespace "xcoin-survival"
Anyone can check a copy with stock tools:
  ssh-keygen -Y verify -f allowed_signers -I release@xcoinproject -n xcoin-survival -s manifest.json.sig < manifest.json
  shasum -a 256 index.html      (must equal manifest.json's files["index.html"])

The trust lives in the signature, not in any server: every honest checker that fetches the same mirror reaches the same
verdict, so mirrors can check each other with or without the original. A checker reads other mirrors' lists only to learn
onion addresses; it never adopts another mirror's verdict.

  python3 survival.py manifest <site-dir>                  write <site-dir>/manifest.json (sign it with tools/sign.sh)
  python3 survival.py verify <site-dir> <allowed_signers>  check a local copy
  python3 survival.py check <url> <allowed_signers>        check one mirror (http://….onion goes through Tor)
"""
import hashlib, json, os, re, socket, subprocess, sys, tempfile, time, urllib.parse

FORMAT = "xcoin-survival/1"
NAMESPACE = "xcoin-survival"
SIGNER = "release@xcoinproject"
FILES = ("index.html",)                        # what a release signs; every mirror serves exactly these
TOR_SOCKS = ("127.0.0.1", 9050)
MAX_BYTES = 2 * 1024 * 1024                    # nothing in a release comes near this; a mirror cannot make us read more
ONION = re.compile(r"^[a-z2-7]{56}\.onion$")

# verdicts, best first
VERIFIED, OUTDATED, MODIFIED, UNREACHABLE = "verified", "outdated", "modified", "unreachable"


def sha256(b): return hashlib.sha256(b).hexdigest()


def manifest_bytes(m):
    """The one byte form of a manifest that is signed and served: sorted keys, no spaces, one trailing newline."""
    return (json.dumps(m, sort_keys=True, separators=(",", ":")) + "\n").encode()


def build_manifest(site, version, created=None):
    files = {}
    for name in FILES:
        with open(os.path.join(site, name), "rb") as f: files[name] = sha256(f.read())
    return {"format": FORMAT, "version": int(version), "created": created or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "files": files}


def verify_signature(manifest_raw, sig_raw, allowed_signers):
    """True when sig_raw is a valid signature of manifest_raw by a key in allowed_signers (OpenSSH, our namespace)."""
    with tempfile.TemporaryDirectory() as d:
        sp = os.path.join(d, "m.sig")
        with open(sp, "wb") as f: f.write(sig_raw)
        r = subprocess.run(["ssh-keygen", "-Y", "verify", "-f", allowed_signers, "-I", SIGNER, "-n", NAMESPACE, "-s", sp],
                           input=manifest_raw, capture_output=True, timeout=20)
        return r.returncode == 0


def judge(files, manifest_raw, sig_raw, allowed_signers, latest_version=None):
    """The verdict for one copy, from its bytes alone: files {name: bytes}, the manifest and its signature as served.
    Returns (verdict, detail, version)."""
    if manifest_raw is None or sig_raw is None: return MODIFIED, "no manifest or no signature", None
    if not verify_signature(manifest_raw, sig_raw, allowed_signers): return MODIFIED, "manifest signature does not verify", None
    try: m = json.loads(manifest_raw)
    except ValueError: return MODIFIED, "manifest is not JSON", None
    if manifest_bytes(m) != manifest_raw or m.get("format") != FORMAT: return MODIFIED, "manifest not in canonical form", None
    for name in FILES:
        want = (m.get("files") or {}).get(name)
        got = files.get(name)
        if got is None: return MODIFIED, f"{name} missing", m.get("version")
        if sha256(got) != want: return MODIFIED, f"{name} differs from the signed release", m.get("version")
    v = m.get("version")
    if latest_version is not None and isinstance(v, int) and v < latest_version:
        return OUTDATED, f"genuine but older: version {v}, latest {latest_version}", v
    return VERIFIED, f"identical to signed version {v}", v


# ── fetching: plain HTTP, through Tor's SOCKS port for .onion hosts (no third-party SOCKS library) ──
def _socks5(host, port):
    s = socket.create_connection(TOR_SOCKS, timeout=60)
    s.sendall(b"\x05\x01\x00")
    if s.recv(2) != b"\x05\x00": raise OSError("Tor SOCKS refused")
    h = host.encode()
    s.sendall(b"\x05\x01\x00\x03" + bytes([len(h)]) + h + port.to_bytes(2, "big"))
    r = s.recv(10)
    if len(r) < 2 or r[1] != 0: raise OSError(f"Tor could not reach {host} (code {r[1] if len(r) > 1 else '?'})")
    return s


def http_get(url, timeout=60):
    """GET url -> bytes, or None on 404. Onion hosts go through Tor; at most MAX_BYTES; no redirects followed."""
    u = urllib.parse.urlsplit(url)
    if u.scheme != "http": raise ValueError("only http:// (onion services are already end-to-end encrypted)")
    host, port = u.hostname, u.port or 80
    s = _socks5(host, port) if host.endswith(".onion") else socket.create_connection((host, port), timeout=timeout)
    s.settimeout(timeout)
    try:
        s.sendall(f"GET {u.path or '/'} HTTP/1.0\r\nHost: {host}\r\nUser-Agent: xcoin-survival-check/1\r\nConnection: close\r\n\r\n".encode())
        buf = b""
        while len(buf) <= MAX_BYTES + 65536:
            chunk = s.recv(65536)
            if not chunk: break
            buf += chunk
    finally:
        s.close()
    head, _, body = buf.partition(b"\r\n\r\n")
    status = int(head.split(b" ", 2)[1]) if head.startswith(b"HTTP/") else 0
    if status == 404: return None
    if status != 200: raise OSError(f"HTTP {status}")
    if len(body) > MAX_BYTES: raise OSError("response too large")
    return body


def check_mirror(base, allowed_signers, latest_version=None, get=http_get):
    """Fetch one mirror's release files and judge them. base: 'http://<56 chars>.onion' (or any http URL in tests)."""
    base = base.rstrip("/")
    try:
        manifest_raw = get(base + "/manifest.json")
        sig_raw = get(base + "/manifest.json.sig")
        files = {name: get(base + "/" + name) for name in FILES}
    except (OSError, ValueError) as e:
        return {"url": base, "verdict": UNREACHABLE, "detail": str(e), "version": None, "checked": int(time.time())}
    files = {k: v for k, v in files.items() if v is not None}
    verdict, detail, version = judge(files, manifest_raw, sig_raw, allowed_signers, latest_version)
    return {"url": base, "verdict": verdict, "detail": detail, "version": version, "checked": int(time.time())}


def onion_base(addr):
    """Normalise a submitted address to http://<56>.onion, or None if it is not a v3 onion address."""
    a = addr.strip().lower()
    a = re.sub(r"^https?://", "", a).split("/")[0]
    return "http://" + a if ONION.match(a) else None


def main(argv):
    if len(argv) >= 3 and argv[1] == "manifest":
        site = argv[2]; version = int(argv[3]) if len(argv) > 3 else 1
        m = build_manifest(site, version)
        with open(os.path.join(site, "manifest.json"), "wb") as f: f.write(manifest_bytes(m))
        print(f"wrote {site}/manifest.json: version {m['version']}, index.html {m['files']['index.html'][:16]}…")
        return 0
    if len(argv) == 4 and argv[1] == "verify":
        site, signers = argv[2], argv[3]
        rd = lambda n: open(os.path.join(site, n), "rb").read() if os.path.exists(os.path.join(site, n)) else None
        v, d, _ = judge({n: rd(n) for n in FILES if rd(n) is not None}, rd("manifest.json"), rd("manifest.json.sig"), signers)
        print(f"{v}: {d}"); return 0 if v == VERIFIED else 1
    if len(argv) == 4 and argv[1] == "check":
        r = check_mirror(argv[2], argv[3]); print(json.dumps(r, indent=2)); return 0 if r["verdict"] == VERIFIED else 1
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
