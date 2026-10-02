# xCoin survival sheet: README

One page with everything needed to find, check and run the xCoin network if every xCoin website is gone, served
identically by many mirrors (onion, IPFS, Codeberg, the web). The trust lives in a **signature**, not in any server:
any copy can be checked against the release key, so mirrors keep checking each other even if the original is gone.

## What is here

| Path | What |
|---|---|
| `site/index.html` | The sheet. One file, no trackers, one optional print-button script. Public domain (CC0). |
| `site/manifest.json` | Version, date and the SHA-256 of every release file (written by `tools/sign.sh`). |
| `site/manifest.json.sig` | OpenSSH signature of the manifest, namespace `xcoin-survival`. |
| `allowed_signers` | The public release key. Published with every release; not secret. |
| `checker/survival.py` | Builds manifests, verifies copies, checks mirrors over Tor. Python standard library + `ssh-keygen`. |
| `tools/keygen.sh` | Makes the release-signing key (once). |
| `tools/sign.sh` | Signs a release. |
| `tools/checkpoints.py` | Writes the checkpoint table from two agreeing nodes (`--check` compares only). |
| `tools/commit.py` | Sealed commitments (commit-reveal): see [COMMITMENTS.md](COMMITMENTS.md). |
| `tools/set-release.py` | Puts the newest xCoin node release on the page (version, commit, download buttons); `--check` only asks. |
| `tools/release-watch.sh` | Daily macOS notification when a node release is newer than the page (`--install` once). |
| `mirrors/mirrord.py` | Community mirrors: the submit form and the hourly check that lists/drops them (runs on every official onion). |
| `deploy/hosts` | The official onion mirrors that `publish.sh` updates (git-ignored; start from `deploy/hosts.example`). |
| `deploy/publish.sh` | Publishes the signed release to every host in `deploy/hosts` and confirms each serves it. |
| `deploy/install-mirrord.sh` | Installs/updates the community-mirror service on one official onion. |
| `deploy/setup-onion.sh`, `restore-onion-key.sh` | A new official onion server; its address key from the key drive. |
| `tests/` | `python3 -m unittest discover -s tests` |

## Verdicts

| Verdict | Meaning |
|---|---|
| verified | Byte-identical to a release signed by the release key, and the newest one the checker knows. |
| outdated | A genuine signed release, but an older version. Not tampered with; the mirror should update. |
| modified | Anything else: a changed page, a changed manifest, a missing or wrong signature. Do not trust. |
| unreachable | Could not be fetched this time. |

## The key (do this once)

    cd ~/xcoin-sites/xcoin-survival && tools/keygen.sh

ssh-keygen asks for a passphrase (hidden). Choose a long one and keep it on paper with the other key passphrases.
The private key is made **on the key drive**, in `/Volumes/david/Survival Keys/`, never on the Mac (another location:
set `XCOIN_SURVIVAL_KEYS`). Copy that folder to the second USB stick, next to a copy of this README. Signing reads the
key from the drive, so the drive must be plugged in. Without the key file AND the passphrase, no new release can be signed. Old releases stay valid.

Later: add co-maintainers' public keys to `allowed_signers` so the sheet does not depend on one person.

## Sign a release

    cd ~/xcoin-sites/xcoin-survival && tools/sign.sh 1

Use a higher version number every time (2, 3, …). The script writes the manifest, asks for the passphrase, signs, and
verifies the result. Then `deploy/publish.sh` sends it to every official onion in `deploy/hosts` and prints OK per
mirror. GitHub/Codeberg Pages are git pushes, done by hand (squash first: see the session notes).

## A new xCoin node release

    tools/set-release.py          # finds the latest tag on GitHub, checks its commit against ~/x-Coin/xCoin-xid, edits the page
    tools/sign.sh <next> && deploy/publish.sh

`tools/release-watch.sh --install` makes the Mac tell you daily when the page is behind. It never edits or signs anything.

## Community mirrors (automatic listing)

Anyone serves the three release files on their own onion and submits the address at `/submit` on any official onion.
`mirrord.py check` runs hourly on every official onion: it fetches each candidate over Tor and lists it in
`/community.json` only while it serves the current signed release byte for byte (checker verdicts). A changed page is
dropped at once and blocked for 7 days; an older release is shown as "behind" for 7 days, then dropped; unreachable for
48 h, dropped. Official onions read each other's lists for addresses only and always check themselves, so there is no
primary: any one of them can die. The list is not signed; the page reads it only on an onion host, text-only.
Install/update on a host: `deploy/install-mirrord.sh` (and `XCOIN_ONION_HOST=root@<host> …` for the others).

## Check

    python3 checker/survival.py verify site allowed_signers                 # this copy
    python3 checker/survival.py check http://<56 chars>.onion allowed_signers   # a mirror (needs Tor on 127.0.0.1:9050)

## Still to build

4. The mirror kit: one command for anyone to run their own onion copy (setup-onion.sh minus the founder's key).

## Never

- Never copy the private key onto the Mac.
- Never put the private key or its passphrase in this repository, a note app, email or chat.
- Never sign a page you have not read in full.
