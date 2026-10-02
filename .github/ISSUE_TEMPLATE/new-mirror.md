---
name: New mirror
about: Submit your own onion (or web) mirror of the xCoin survival sheet
title: "New mirror: <your address>"
labels: mirror
---

**Address** (one only; a 56-character v3 `.onion`, or an `https://` web address):

**Serving the signed release version** (from your `manifest.json`):

Before submitting, check your mirror yourself; it must say `verified`:

    python3 checker/survival.py check http://<your-address>.onion allowed_signers

A mirror is listed only after an independent check finds it byte-for-byte identical to a signed release.
Do not put anything else here: no names, emails or IP addresses.
