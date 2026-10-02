"""Tests for mirrors/mirrord.py: submissions, the hourly check and its rules, with real signatures and a fake Tor."""
import base64, hashlib, json, os, shutil, sys, tempfile, unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "checker"))
sys.path.insert(0, os.path.join(HERE, "..", "mirrors"))
sys.path.insert(0, HERE)
from test_survival import keypair, signers_file, release, read, PAGE
import survival as S


def onion(seed):
    """A valid v3 onion address (real checksum) from any seed."""
    pub = hashlib.sha256(seed.encode()).digest()
    chk = hashlib.sha3_256(b".onion checksum" + pub + b"\x03").digest()[:2]
    return base64.b32encode(pub + chk + b"\x03").decode().lower() + ".onion"


SELF, PEER = onion("self"), onion("peer")


class Mirrord(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.web, self.state = os.path.join(self.d, "web"), os.path.join(self.d, "state")
        os.makedirs(self.web); os.makedirs(self.state)
        conf = os.path.join(self.d, "conf.json")
        json.dump({"self": SELF, "official": [SELF, PEER]}, open(conf, "w"))
        os.environ.update(XCOIN_WEB=self.web, XCOIN_MIRRORS_STATE=self.state, XCOIN_MIRRORS_CONF=conf)
        sys.modules.pop("mirrord", None)
        import mirrord; self.M = mirrord
        self.key = keypair(self.d, "release"); self.signers = signers_file(self.d, self.key)
        self.v1 = release(self.d, self.key, PAGE, 1)
        self.v2 = release(self.d, self.key, PAGE + b"<p>v2</p>\n", 2)
        self.publish(self.v2)
        self.net = {}                                   # onion -> site dir served there (missing = unreachable)
        self.t = 1_800_000_000

    def tearDown(self): shutil.rmtree(self.d)

    def publish(self, site):
        for n in ("index.html", "manifest.json", "manifest.json.sig"): shutil.copy(os.path.join(site, n), self.web)

    def get(self, url):
        h = url[len("http://"):].split("/")[0]; path = url.split(".onion", 1)[1].lstrip("/")
        if h == PEER and path == "community.json":
            if "peer_list" in self.__dict__: return json.dumps(self.peer_list).encode()
            raise OSError("peer down")
        if h not in self.net: raise OSError("Tor could not reach it")
        data = read(self.net[h], path)
        return data

    def check(self, hours=0):
        self.t += int(hours * 3600)
        return self.M.run_check(t=self.t, get=self.get, signers=self.signers)

    def listed(self, out): return {m["onion"]: m["status"] for m in out["mirrors"]}

    # ── submissions ──
    def test_rejects_bad_addresses_and_typos(self):
        good = onion("a")
        self.assertTrue(self.M.onion_ok(good)); self.assertTrue(self.M.onion_ok("http://" + good.upper() + "/"))
        typo = good[:10] + ("a" if good[10] != "a" else "b") + good[11:]
        for bad in ["", "example.com", good[:-7], typo, "x" * 56 + ".onion"]:
            self.assertFalse(self.M.submit(bad, self.t)[0], bad)

    def test_official_mirrors_are_not_submissions(self):
        self.assertFalse(self.M.submit(PEER, self.t)[0])

    def test_rate_limit(self):
        for i in range(self.M.MAX_PER_HOUR): self.assertTrue(self.M.submit(onion(f"r{i}"), self.t)[0])
        self.assertFalse(self.M.submit(onion("one-too-many"), self.t)[0])
        self.assertTrue(self.M.submit(onion("later"), self.t + 3601)[0])

    def test_duplicate_submission_is_fine(self):
        a = onion("dup")
        self.assertTrue(self.M.submit(a, self.t)[0]); self.assertIn("already waiting", self.M.submit(a, self.t)[1])

    # ── the hourly check ──
    def test_exact_copy_is_listed(self):
        a = onion("good"); self.net[a] = self.v2
        self.M.submit(a, self.t)
        out = self.check()
        self.assertEqual(self.listed(out), {a: "current"})
        self.assertFalse(out["signed"]); self.assertEqual(out["latest_version"], 2)
        self.assertEqual(json.load(open(os.path.join(self.state, "community.json")))["mirrors"][0]["onion"], a)

    def test_changed_page_is_never_listed_and_blocked(self):
        a = onion("evil"); fake = release(self.d, keypair(self.d, "impostor"), PAGE + b"<p>send coins here</p>", 2)
        self.net[a] = fake; self.M.submit(a, self.t)
        self.assertEqual(self.listed(self.check()), {})
        self.assertFalse(self.M.submit(a, self.t + 60)[0])                       # blocked for 7 days

    def test_listed_mirror_that_changes_is_dropped_at_once(self):
        a = onion("turns"); self.net[a] = self.v2; self.M.submit(a, self.t); self.check()
        tampered = os.path.join(self.d, "tampered"); shutil.copytree(self.v2, tampered)
        open(os.path.join(tampered, "index.html"), "ab").write(b"<p>new seeds: 6.6.6.6</p>")
        self.net[a] = tampered
        self.assertEqual(self.listed(self.check(1)), {})

    def test_new_mirror_must_be_current(self):
        a = onion("old"); self.net[a] = self.v1; self.M.submit(a, self.t)
        self.assertEqual(self.listed(self.check()), {})

    def test_listed_mirror_behind_is_kept_7_days(self):
        a = onion("slow"); self.net[a] = self.v2; self.M.submit(a, self.t); self.check()
        v3 = release(self.d, self.key, PAGE + b"<p>v3</p>\n", 3); self.publish(v3)
        self.assertEqual(self.listed(self.check(1)), {a: "behind"})
        self.assertEqual(self.listed(self.check(24 * 7)), {})

    def test_unreachable_listed_mirror_kept_48h(self):
        a = onion("flaky"); self.net[a] = self.v2; self.M.submit(a, self.t); self.check()
        del self.net[a]
        self.assertEqual(self.listed(self.check(1)), {a: "unreachable"})
        self.assertEqual(self.listed(self.check(47)), {a: "unreachable"})
        self.assertEqual(self.listed(self.check(2)), {})

    def test_unreachable_submission_retried_then_forgotten(self):
        a = onion("late"); self.M.submit(a, self.t)
        self.assertEqual(self.listed(self.check()), {})
        self.net[a] = self.v2
        self.assertEqual(self.listed(self.check(2)), {a: "current"})            # came up within a day: listed
        b = onion("never"); self.M.submit(b, self.t); self.check(1)
        self.check(25); self.net[b] = self.v2
        self.assertEqual(set(self.listed(self.check(1))), {a})                  # forgotten after 24 h

    def test_peer_list_is_only_a_source_of_addresses(self):
        good, bad = onion("from-peer-good"), onion("from-peer-bad")
        self.net[good] = self.v2
        self.net[bad] = release(self.d, keypair(self.d, "x"), PAGE + b"!", 2)
        self.peer_list = {"mirrors": [{"onion": good, "status": "current"}, {"onion": bad, "status": "current"},
                                      {"onion": "not-an-onion"}]}
        self.assertEqual(self.listed(self.check()), {good: "current"})          # the bad one is checked here, rejected

    def test_peer_down_changes_nothing(self):
        a = onion("p"); self.net[a] = self.v2; self.M.submit(a, self.t)
        self.assertEqual(self.listed(self.check()), {a: "current"})

    def test_list_is_capped(self):
        self.M.MAX_LISTED = 3
        for i in range(5):
            a = onion(f"c{i}"); self.net[a] = self.v2; self.M.submit(a, self.t)
        self.assertEqual(len(self.check()["mirrors"]), 3)


class Deploy(unittest.TestCase):
    def test_setup_onion_carries_the_same_nginx_config(self):
        d = os.path.join(HERE, "..", "deploy")
        conf = open(os.path.join(d, "nginx-xcoin-survival.conf")).read()
        self.assertIn(conf, open(os.path.join(d, "setup-onion.sh")).read())

    def test_official_onions_are_valid(self):
        sys.modules.pop("mirrord", None); import mirrord
        for o in open(os.path.join(HERE, "..", "deploy", "official-onions.txt")).read().split():
            self.assertTrue(mirrord.onion_ok(o), o)


if __name__ == "__main__":
    unittest.main()
