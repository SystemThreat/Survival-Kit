# Sealed commitments: README

Prove later that you knew something **now**, without saying what it is until you choose: a name, a plan, a decision,
a document. Until the reveal nobody can learn it, act on it first, or claim it was decided later. The examples below
use `example.com`; a sealed text can be anything without spaces.

Tool: `tools/commit.py`. Simulated end to end on a private regtest chain (seal, on chain, read back, reveal, tamper
attempts) and covered by `tests/test_commit.py`.

## Quick start: one command

Once the commitment wallet is set up and funded (one time, already done), a whole commitment is one command, in the
macOS Terminal app with the key drive plugged in:

    ~/xcoin-sites/xcoin-survival/tools/seal-and-send.sh

Type the secret twice (hidden) and `SEND` once. It seals, puts the fingerprint on the chain, waits for the block and
prints `FOUND in tx … at height …, block time …` with the fingerprint and txid (both public). Steps 1 and 2 below are
what it does; step 3 onwards stays manual.

## How it works, in one paragraph

A random 32-byte **salt** is joined to the secret text and hashed:

    fingerprint = SHA-256( "xcoin-commit/1|" + text + "|" + salt )

The fingerprint reveals nothing: without the salt, not even someone who guesses the text can match it. The fingerprint
is put into an **xCoin transaction** (an OP_RETURN output), so the **block's time proves** it existed on that date,
and nobody, including you, can change it afterwards. On the day you reveal, you publish the text and the salt; anyone
recomputes the fingerprint with one `shasum` command and finds it already in the chain.

## Where things live

| Thing | Where | Secret? |
|---|---|---|
| Text + salt (the sealed file) | `/Volumes/david/Survival Keys/commitments/commit-<date>-<8 chars>.json` | **Yes, until the reveal** |
| A copy of the sealed file | the second USB stick, same folder | **Yes** |
| Fingerprint | anywhere: the chain, the survival page, chat | No |
| OP_RETURN data | the chain | No |

The sealed file is never on the Mac, never in this repository, never in chat. Lose it before the reveal and the seal
can never be opened (only the proof is gone; the thing itself is not affected).

## Step 1: seal (once per secret)

With the key drive plugged in (the tool refuses otherwise):

    python3 ~/xcoin-sites/xcoin-survival/tools/commit.py seal

Type the text at the hidden prompt, twice: lowercase, no spaces, exactly as you will reveal it (`example.com`, not
`EXAMPLE.COM` or `example.com.`). It prints:

    sealed (secret text and salt are on the key drive only): /Volumes/david/Survival Keys/commitments/commit-…json
    fingerprint (publish this): 64 hex characters
    OP_RETURN data (hex, 36 bytes = 'XIDC' + fingerprint): 72 hex characters, starting 58494443

Then copy `/Volumes/david/Survival Keys/commitments` to the second USB stick.

## Step 2: put the fingerprint on the chain

One transaction with one data output: `"data": "<OP_RETURN data>"` (36 bytes; the relay limit is 80, so every node
accepts it). It sends no coins anywhere: only the fee is spent, about 0.000015 XID at 1 sat/vB (the transaction is
larger than Bitcoin's because of the post-quantum signature).

From the commitment wallet on the key drive (the founder sends it; nobody else):

    ~/xcoin-sites/xcoin-survival/tools/send-commit.sh <OP_RETURN data>

It builds the transaction by hand, because the node wallet's plain `send` refuses the 0-value data output (its
0.0001 XID output floor forgets the exemption that consensus gives data outputs; wallet bug, fix pending). It uses one
confirmed coin, a fixed fee of 0.00003 XID, change back to the wallet, checks the network would accept it and the fee is
exactly that, shows you everything, and broadcasts only after you type SEND.

It prints a **txid**. Wait for one confirmation (about 4 minutes), then find the block and check the commitment is in it:

    nex-cli gettransaction <txid>                                     # shows "blockhash" once confirmed
    nex-cli getblock <blockhash> 2 | python3 tools/commit.py onchain - <fingerprint>

It must say `FOUND in tx … at height …, block time …`. Write down the **txid, height and block time**.

## Step 3: show it on the survival page

Add a "Sealed commitment #1" line (fingerprint, txid, height, date) to the page, then sign and publish a new release
(`tools/sign.sh <n>`, `deploy/publish.sh`). The page shows only the fingerprint; it never shows the text.

## Step 4: reveal (when you choose)

    python3 ~/xcoin-sites/xcoin-survival/tools/commit.py reveal "/Volumes/david/Survival Keys/commitments/commit-….json"

It prints the text, the salt, the fingerprint and the one-line check. Publish all three (on the page, in a signed
release, in the forum). If the text names something you control, show that too:

1. For a domain name, a DNS TXT record on it: `xcoin-commit=<fingerprint>`.
2. A signed statement with the release key, e.g. "example.com is the xCoin project's; commitment <fingerprint>,
   tx <txid>":

       printf '%s\n' "example.com is the xCoin project's; commitment <fp>, tx <txid>" > statement.txt
       ssh-keygen -Y sign -f "/Volumes/david/Survival Keys/release" -n xcoin-survival statement.txt

## How anyone checks the reveal (no xCoin software needed for the first two)

    printf '%s' 'xcoin-commit/1|example.com|<salt>' | shasum -a 256          # must equal the fingerprint
    python3 tools/commit.py verify example.com <salt> <fingerprint>            # same, says MATCH / NO MATCH
    nex-cli getblock <blockhash> 2 | python3 tools/commit.py onchain - <fingerprint>   # it is in the chain, at that date
    dig +short TXT example.com                                                # if it is a domain: it carries the fingerprint too

## Never

- Never type the secret into any website, app or search box before the reveal (searches are logged and sometimes acted on).
- Never put the sealed file, the text or the salt on the Mac, in a repository, in a note app, email or chat before the reveal.
- Never seal a text with leading or trailing spaces or capitals you will not reveal exactly (the tool refuses spaces and `|`).
- Never reuse a salt: one seal, one fresh salt (the tool makes a new one every time).
