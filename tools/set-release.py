#!/usr/bin/env python3
"""Put the newest xCoin node release on the page: version, commit, download buttons, checkout line. Nothing typed by hand.

  tools/set-release.py            find the latest release on GitHub; update the page if it is newer than the page's
  tools/set-release.py --check    only say whether the page is current (exit 1 when a newer release exists)
  tools/set-release.py v32.0.0.1  use this tag instead of "latest"

The commit is asked of GitHub AND of this Mac's own copy of the xCoin source (after fetching tags); the two must agree,
so one compromised place cannot put a wrong commit on the page. Then sign and publish as usual:
  tools/sign.sh <next>   then   deploy/publish.sh
Environment: XCOIN_SRC (local xCoin checkout, default ~/x-Coin/xCoin-xid), XCOIN_REPO (default SystemThreat/xCoin).
"""
import json, os, re, subprocess, sys, urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(HERE, "site", "index.html")
REPO = os.environ.get("XCOIN_REPO", "SystemThreat/xCoin")
SRC = os.path.expanduser(os.environ.get("XCOIN_SRC", "~/x-Coin/xCoin-xid"))
CURRENT = re.compile(r"<tr><th>Current release</th><td>(v[0-9][0-9A-Za-z.\-]*)</td></tr>")
TAG = re.compile(r"^v[0-9][0-9A-Za-z.\-]*$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")


def gh(path):
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/{path}",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "xcoin-survival"})
    with urllib.request.urlopen(req, timeout=30) as r: return json.load(r)


def github_commit(tag):
    o = gh(f"git/ref/tags/{tag}")["object"]
    if o["type"] == "tag": o = gh(f"git/tags/{o['sha']}")["object"]       # annotated tag -> the commit it names
    if o["type"] != "commit": raise SystemExit(f"{tag} does not point at a commit on GitHub")
    return o["sha"]


def local_commit(tag):
    subprocess.run(["git", "-C", SRC, "fetch", "--quiet", "--tags", "origin"], check=True)
    r = subprocess.run(["git", "-C", SRC, "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}"],
                       capture_output=True, text=True)
    if r.returncode: raise SystemExit(f"{tag} is not in the local source {SRC} even after fetching tags")
    return r.stdout.strip()


def page_release(s):
    m = CURRENT.search(s)
    if not m: raise SystemExit("could not find the 'Current release' row on the page")
    old = m.group(1)
    commits = set(re.findall(r"\b[0-9a-f]{40}\b", s[s.index("Check you have the real release"):][:600]))
    if len(commits) != 1: raise SystemExit("could not find the one release commit on the page")
    return old, commits.pop()


def newer(a, b):
    """True when tag a is a later version than tag b (numeric parts compared in order)."""
    k = lambda t: [int(x) for x in re.findall(r"\d+", t)]
    return k(a) > k(b)


def main(argv):
    check = "--check" in argv
    args = [a for a in argv[1:] if a != "--check"]
    tag = args[0] if args else gh("releases/latest")["tag_name"]
    if not TAG.match(tag): raise SystemExit(f"unexpected tag name: {tag!r}")
    s = open(PAGE, encoding="utf-8").read()
    old, old_commit = page_release(s)
    if tag == old:
        print(f"the page already shows {old}: nothing to do"); return 0
    if not args and not newer(tag, old):
        print(f"GitHub's latest release {tag} is not newer than the page's {old}: nothing to do"); return 0
    if check:
        print(f"NEWER RELEASE: {tag} (the page shows {old}). Run tools/set-release.py, then sign and publish."); return 1
    a, b = github_commit(tag), local_commit(tag)
    if a != b or not HEX40.match(a):
        raise SystemExit(f"STOP: {tag} is {a} on GitHub but {b} in {SRC}. Nothing was changed. Find out why first.")
    n_ver, n_commit = s.count(old), s.count(old_commit)
    s = s.replace(old, tag).replace(old_commit, a)
    open(PAGE, "w", encoding="utf-8").write(s)
    print(f"page: {old} -> {tag} ({n_ver} places: buttons, links, checkout line, release row)")
    print(f"      commit {old_commit[:12]}… -> {a[:12]}… ({n_commit} place; GitHub and the local source agree)")
    print("NEXT: check the seed lists on the page still match the new release, then tools/sign.sh <next> and deploy/publish.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
