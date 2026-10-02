#!/usr/bin/env python3
"""Community mirrors: anyone may submit an onion address; a machine lists it only while it serves the signed page.

Runs on every official onion mirror, as equals (no primary). Python standard library + ssh-keygen + Tor only.

  mirrord.py serve      the submit form, on 127.0.0.1:8081 (nginx forwards /submit to it, over Tor only)
  mirrord.py check      once an hour (systemd timer): check every candidate and write <state>/community.json

How a mirror gets listed, and stays listed (all verdicts come from checker/survival.py, from the bytes alone):
  - submitted here, or seen in another official mirror's community.json (learned as an address only; never trusted)
  - fetched over Tor; listed only when it serves EXACTLY this server's current signed release
  - re-checked every hour: a changed page (or a bad signature) drops it at once and blocks it for 7 days;
    an older signed release is shown as "behind" for up to 7 days, then dropped; unreachable for 48 hours, dropped
  - a new submission that cannot be reached is retried for 24 hours, then forgotten
community.json is NOT signed: it is a machine-checked list. The trust stays in the release key: anyone can check any
listed mirror with the two stock commands on the page.
"""
import base64, fcntl, hashlib, html, http.server, json, os, sys, time, urllib.parse
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.environ.get("XCOIN_CHECKER_DIR", os.path.dirname(os.path.abspath(__file__))))
import survival as S

WEB = os.environ.get("XCOIN_WEB", "/var/www/xcoin-survival")
STATE = os.environ.get("XCOIN_MIRRORS_STATE", "/var/lib/xcoin-mirrors")
CONF = os.environ.get("XCOIN_MIRRORS_CONF", "/etc/xcoin-mirrors.json")     # {"self": onion, "official": [onions]}
PORT = int(os.environ.get("XCOIN_MIRRORS_PORT", "8081"))

MAX_LISTED = 100              # the page shows at most this many community mirrors
MAX_PENDING = 300             # submissions waiting for their first check
MAX_PER_HOUR = 30             # accepted submissions per hour (Tor hides who submits, so the limit is global)
MAX_CHECKS = 150              # mirrors fetched per run
WORKERS = 6
HOUR, DAY = 3600, 86400
BEHIND_GRACE = 7 * DAY        # an older signed release stays listed (as "behind") this long after it was last current
DOWN_GRACE = 2 * DAY          # a listed mirror unreachable this long is dropped
PENDING_GRACE = DAY           # a new submission unreachable this long is forgotten
BLOCK = 7 * DAY               # a mirror caught serving a changed page cannot be resubmitted for this long


def now(): return int(time.time())


def readjson(path):
    with open(path) as f: return json.load(f)
def iso(t): return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def onion_ok(addr):
    """A v3 onion address with a valid checksum -> 'http://<56>.onion', else None (catches typos, not just shape)."""
    base = S.onion_base(addr or "")
    if not base: return None
    raw = base32 = base[len("http://"):-len(".onion")]
    try: raw = base64.b32decode(base32.upper())
    except ValueError: return None
    pub, check, version = raw[:32], raw[32:34], raw[34:]
    if version != b"\x03": return None
    if hashlib.sha3_256(b".onion checksum" + pub + version).digest()[:2] != check: return None
    return base


def host(base): return base[len("http://"):]


def load_conf():
    c = readjson(CONF)
    return {"self": c["self"], "official": [o for o in c.get("official", [])]}


def load_state():
    try: return readjson(os.path.join(STATE, "state.json"))
    except (OSError, ValueError): return {"listed": {}, "pending": {}, "blocked": {}}


def write_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f: f.write(data)
    os.chmod(tmp, 0o644); os.replace(tmp, path)


def our_version():
    return readjson(os.path.join(WEB, "manifest.json"))["version"]


# ── submissions: appended to a queue file by `serve`, taken in by `check` ──
QUEUE = lambda: os.path.join(STATE, "submitted.jsonl")


def submit(addr, t=None):
    """Queue one address. Returns (ok, message for the person who submitted it)."""
    t = t or now()
    base = onion_ok(addr)
    if not base: return False, "That is not a valid onion address (v3: 56 characters, then .onion). Check for a typo."
    conf = load_conf()
    if host(base) in [conf["self"]] + conf["official"]: return False, "That is an official mirror: it is already listed."
    st = load_state()
    if host(base) in st["listed"]: return True, "That mirror is already listed. It is re-checked every hour."
    if st["blocked"].get(host(base), 0) > t:
        return False, "That address served a changed page and is blocked for 7 days. Serve the signed release unchanged."
    with open(QUEUE(), "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        lines = [json.loads(l) for l in f.read().splitlines() if l.strip()]
        if any(x["onion"] == host(base) for x in lines) or host(base) in st["pending"]:
            return True, "That address is already waiting for its check (within the hour)."
        if sum(1 for x in lines if x["t"] > t - HOUR) >= MAX_PER_HOUR or len(lines) + len(st["pending"]) >= MAX_PENDING:
            return False, "Too many submissions right now. Please try again in an hour."
        f.write(json.dumps({"onion": host(base), "t": t}) + "\n")
    return True, "Received. It is checked within the hour and listed only if it serves the signed page exactly."


def take_queue():
    try:
        with open(QUEUE(), "r+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            lines = [json.loads(l) for l in f.read().splitlines() if l.strip()]
            f.seek(0); f.truncate()
        return lines
    except FileNotFoundError:
        return []


# ── the hourly check ──
def peer_addresses(conf, get):
    """Onion addresses listed by the other official mirrors. Only the addresses are used; every one is checked here."""
    found = set()
    for o in conf["official"]:
        if o == conf["self"]: continue
        try:
            raw = get(f"http://{o}/community.json")
            for m in (json.loads(raw).get("mirrors") or [])[:MAX_LISTED]:
                b = onion_ok(m.get("onion", ""))
                if b: found.add(host(b))
        except (OSError, ValueError, AttributeError, TypeError):
            pass                                                   # a peer that is down only means fewer suggestions
    return found


def run_check(t=None, get=S.http_get, signers=None):
    t = t or now()
    conf = load_conf()
    signers = signers or os.path.join(WEB, "allowed_signers")
    latest = our_version()
    official = set([conf["self"]] + conf["official"])
    st = load_state()
    st["blocked"] = {k: v for k, v in st["blocked"].items() if v > t}
    for x in take_queue():
        if x["onion"] not in st["listed"] and x["onion"] not in st["blocked"]:
            st["pending"].setdefault(x["onion"], {"first": x["t"]})
    for o in peer_addresses(conf, get) - official:
        if o not in st["listed"] and o not in st["blocked"]:
            st["pending"].setdefault(o, {"first": t, "via": "peer"})

    todo = (list(st["listed"]) + sorted(st["pending"], key=lambda o: st["pending"][o]["first"]))[:MAX_CHECKS]
    todo = [o for o in dict.fromkeys(todo) if o not in official]
    with ThreadPoolExecutor(WORKERS) as ex:
        results = dict(zip(todo, ex.map(lambda o: S.check_mirror("http://" + o, signers, latest, get), todo)))

    for o, r in results.items():
        v = r["verdict"]
        cur = st["listed"].get(o)
        if v == S.MODIFIED:
            st["listed"].pop(o, None); st["pending"].pop(o, None); st["blocked"][o] = t + BLOCK
        elif v == S.VERIFIED:
            st["pending"].pop(o, None)
            if cur is None and len(st["listed"]) >= MAX_LISTED: continue
            st["listed"][o] = {"since": (cur or {}).get("since", t), "current": t, "seen": t, "version": r["version"]}
        elif v == S.OUTDATED:
            if cur is None: st["pending"].pop(o, None); continue    # a new mirror must serve the current release
            cur.update(seen=t, version=r["version"])
            if t - cur["current"] > BEHIND_GRACE: st["listed"].pop(o)
        else:                                                       # unreachable
            if cur is not None:
                if t - cur["seen"] > DOWN_GRACE: st["listed"].pop(o)
            elif t - st["pending"].get(o, {"first": t})["first"] > PENDING_GRACE:
                st["pending"].pop(o, None)

    os.makedirs(STATE, exist_ok=True)
    write_atomic(os.path.join(STATE, "state.json"), json.dumps(st, indent=1, sort_keys=True))
    shown = []
    for o, m in sorted(st["listed"].items(), key=lambda kv: kv[1]["since"]):
        r = results.get(o, {})
        if r.get("verdict") == S.UNREACHABLE: status = "unreachable"
        elif m["version"] == latest: status = "current"
        else: status = "behind"
        shown.append({"onion": o, "status": status, "version": m["version"],
                      "listed_since": iso(m["since"]), "last_verified": iso(m["current"])})
    out = {"format": "xcoin-survival-community/1", "checked": iso(t), "by": conf["self"], "latest_version": latest,
           "signed": False, "mirrors": shown}
    write_atomic(os.path.join(STATE, "community.json"), json.dumps(out, indent=1) + "\n")   # nginx serves it as /community.json
    return out


# ── the submit form ──
FORM = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Add a mirror · xCoin survival sheet</title>
<style>body{{font:16px/1.5 ui-monospace,Menlo,monospace;max-width:640px;margin:40px auto;padding:0 16px;background:#fbfcf6;color:#0a0a0a}}
@media (prefers-color-scheme:dark){{body{{background:#0c0e0a;color:#e9eee0}}input{{background:#171c11;color:#e9eee0}}}}
h1{{font-size:22px}}input{{font:inherit;width:100%;box-sizing:border-box;padding:10px;border:3px solid currentColor}}
button{{font:inherit;font-weight:700;margin-top:12px;padding:10px 18px;border:3px solid currentColor;background:#c7ff2e;color:#0a0a0a;cursor:pointer}}
.msg{{border:3px solid currentColor;padding:10px 14px;margin:18px 0}}.ok{{background:#c7ff2e;color:#0a0a0a}}.bad{{color:#b3261e}}
a{{color:inherit}}</style>
<h1>Add your mirror</h1>
{msg}
<p>Serve the signed survival sheet unchanged on your own onion address: <code>index.html</code>, <code>manifest.json</code>,
<code>manifest.json.sig</code>, at the root. Then enter the address. It is checked over Tor within the hour and listed
automatically while it serves the current signed release exactly. A changed page is dropped at once.</p>
<form method="post" action="/submit">
<label for="o">Onion address</label>
<input id="o" name="onion" required maxlength="80" autocomplete="off" spellcheck="false" placeholder="xxxxxxxx….onion">
<button type="submit">Submit mirror</button>
</form>
<p><a href="/">Back to the survival sheet</a> · <a href="/community.json">the current list (community.json)</a></p>
</html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "xcoin-mirrors"; sys_version = ""

    def page(self, code, msg=""):
        body = FORM.format(msg=msg).encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        if urllib.parse.urlsplit(self.path).path != "/submit": return self.page(404, '<p class="msg bad">Not found.</p>')
        self.page(200)

    def do_POST(self):
        if urllib.parse.urlsplit(self.path).path != "/submit": return self.page(404, '<p class="msg bad">Not found.</p>')
        n = int(self.headers.get("Content-Length") or 0)
        if n > 1024: return self.page(413, '<p class="msg bad">Too long.</p>')
        addr = (urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8", "replace")).get("onion") or [""])[0]
        ok, msg = submit(addr)
        self.page(200 if ok else 400, f'<p class="msg {"ok" if ok else "bad"}">{html.escape(msg)}</p>')

    def log_message(self, *a): pass                                 # keep no record of who submitted what


def main(argv):
    if argv[1:] == ["serve"]:
        os.makedirs(STATE, exist_ok=True)
        http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    elif argv[1:] == ["check"]:
        out = run_check()
        print(f"{out['checked']}: {len(out['mirrors'])} community mirror(s) listed, latest release {out['latest_version']}")
    else:
        print(__doc__); return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
