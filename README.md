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
verifies the result. Publish `site/` (all three files) and `allowed_signers` to every mirror.

## Check

    python3 checker/survival.py verify site allowed_signers                 # this copy
    python3 checker/survival.py check http://<56 chars>.onion allowed_signers   # a mirror (needs Tor on 127.0.0.1:9050)

## Still to build

3. The founder's onion mirror on its own AWS server, running the checker and the "submit a mirror" form.
4. The mirror kit: one command for anyone to run their own onion copy.
5. Mirror-to-mirror discovery: each mirror publishes the onions it checked; checkers learn addresses from each other
   but always re-check themselves.

## Never

- Never copy the private key onto the Mac.
- Never put the private key or its passphrase in this repository, a note app, email or chat.
- Never sign a page you have not read in full.
