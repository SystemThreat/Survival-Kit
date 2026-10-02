"""Sealed commitments: seal / reveal / verify / onchain, and the refusals the regtest simulation asked for."""
import json, os, subprocess, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import commit as C


class Commit(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); os.makedirs(os.path.join(self.d, "keys")); open(os.path.join(self.d, "keys", "release.pub"), "w").write("x")
        self.out = os.path.join(self.d, "keys", "commitments")

    def test_seal_reveal_and_plain_shasum_agree(self):
        p, fp = C.seal(text="example.org", out_dir=self.out)
        d = C.reveal(p)
        r = subprocess.run(f"printf '%s' '{C.PREFIX}{d['text']}|{d['salt']}' | shasum -a 256", shell=True, capture_output=True, text=True)
        self.assertEqual(r.stdout.split()[0], fp)
        self.assertEqual(oct(os.stat(p).st_mode & 0o777), "0o600")

    def test_seal_refuses_without_the_key_drive(self):
        with self.assertRaises(SystemExit): C.seal(text="example.org", out_dir=os.path.join(self.d, "nokeys", "commitments"))

    def test_variants_do_not_match(self):
        s = "a" * 64; fp = C.fingerprint("example.org", s)
        for t, salt in (("example.com", s), ("Example.org", s), ("example.org.", s), ("example.org", "b" + s[1:])):
            self.assertNotEqual(C.fingerprint(t, salt), fp)
        for bad in ((" example.org", s), ("example.org", s.upper()), ("a|b", s), ("", s)):
            with self.assertRaises(ValueError): C.fingerprint(*bad)

    def test_verify_cli_says_no_match_instead_of_crashing(self):
        r = subprocess.run([sys.executable, C.__file__, "verify", "x y ", "zz", "00"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1); self.assertIn("NO MATCH", r.stdout); self.assertNotIn("Traceback", r.stderr)

    def test_onchain_finds_only_the_exact_script(self):
        fp = C.fingerprint("example.org", "c" * 64)
        good = {"txid": "t1", "vout": [{"scriptPubKey": {"hex": "6a24" + C.opreturn_hex(fp)}}]}
        decoys = [{"txid": "cb", "vout": [{"scriptPubKey": {"hex": "6a24aa21a9ed" + "00" * 32}}]},                  # witness commitment
                  {"txid": "t0", "vout": [{"scriptPubKey": {"hex": "6a25" + C.opreturn_hex(fp) + "00"}}]}]           # wrong length
        blk = {"height": 1102, "time": 1790903353, "tx": decoys + [good]}
        self.assertEqual(C.onchain(blk, fp), {"txid": "t1", "height": 1102, "time": 1790903353})
        self.assertIsNone(C.onchain({"height": 1, "time": 0, "tx": decoys}, fp))


if __name__ == "__main__":
    unittest.main()
