"""Tests for checker/survival.py: real ssh-keygen signatures with throwaway keys, and real HTTP mirrors on localhost."""
import http.server, json, os, shutil, subprocess, sys, tempfile, threading, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "checker"))
import survival as S

PAGE = b"<!doctype html><title>xCoin survival</title><p>genesis 3bc1a36d...</p>\n"


def keypair(d, name):
    k = os.path.join(d, name)
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", k], check=True)
    return k


def signers_file(d, *keys):
    p = os.path.join(d, "allowed_signers")
    with open(p, "w") as f:
        for k in keys:
            pub = open(k + ".pub").read().split()
            f.write(f'{S.SIGNER} namespaces="{S.NAMESPACE}" {pub[0]} {pub[1]}\n')
    return p


def release(d, key, page=PAGE, version=1):
    """A signed site directory: index.html, manifest.json, manifest.json.sig."""
    site = os.path.join(d, f"site-v{version}-{os.path.basename(key)}-{len(os.listdir(d))}")
    os.makedirs(site)
    open(os.path.join(site, "index.html"), "wb").write(page)
    m = S.build_manifest(site, version, created="2026-10-01T00:00:00Z")
    open(os.path.join(site, "manifest.json"), "wb").write(S.manifest_bytes(m))
    subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-f", key, "-n", S.NAMESPACE, os.path.join(site, "manifest.json")], check=True)
    return site


def read(site, n):
    p = os.path.join(site, n)
    return open(p, "rb").read() if os.path.exists(p) else None


def serve(site):
    h = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=site, **k)
    http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


class Survival(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.key = keypair(self.d, "release"); self.other = keypair(self.d, "impostor")
        self.signers = signers_file(self.d, self.key)

    def tearDown(self): shutil.rmtree(self.d)

    def judge(self, site, latest=None):
        return S.judge({"index.html": read(site, "index.html")}, read(site, "manifest.json"), read(site, "manifest.json.sig"),
                       self.signers, latest)

    def test_genuine_copy_verifies(self):
        v, detail, ver = self.judge(release(self.d, self.key))
        self.assertEqual((v, ver), (S.VERIFIED, 1), detail)

    def test_one_changed_character_is_modified(self):
        site = release(self.d, self.key)
        open(os.path.join(site, "index.html"), "wb").write(PAGE.replace(b"3bc1", b"3bc2"))   # a mirror swaps a hash
        self.assertEqual(self.judge(site)[0], S.MODIFIED)

    def test_edited_manifest_breaks_the_signature(self):
        site = release(self.d, self.key)
        bad = PAGE + b"<p>addnode=6.6.6.6:9333</p>"                                          # new page AND a matching manifest
        open(os.path.join(site, "index.html"), "wb").write(bad)
        m = json.loads(read(site, "manifest.json")); m["files"]["index.html"] = S.sha256(bad)
        open(os.path.join(site, "manifest.json"), "wb").write(S.manifest_bytes(m))
        v, detail, _ = self.judge(site)
        self.assertEqual((v, detail), (S.MODIFIED, "manifest signature does not verify"))

    def test_a_release_signed_by_another_key_is_modified(self):
        v, detail, _ = self.judge(release(self.d, self.other))
        self.assertEqual((v, detail), (S.MODIFIED, "manifest signature does not verify"))

    def test_missing_signature_or_manifest_is_modified(self):
        site = release(self.d, self.key); os.remove(os.path.join(site, "manifest.json.sig"))
        self.assertEqual(self.judge(site)[0], S.MODIFIED)

    def test_older_genuine_version_is_outdated_not_modified(self):
        v, detail, ver = self.judge(release(self.d, self.key, version=3), latest=4)
        self.assertEqual((v, ver), (S.OUTDATED, 3), detail)

    def test_over_http_a_genuine_mirror_verifies_and_a_tampered_one_does_not(self):
        good = release(self.d, self.key); bad = release(self.d, self.key)
        open(os.path.join(bad, "index.html"), "ab").write(b"<!-- injected -->")
        s1, u1 = serve(good); s2, u2 = serve(bad)
        try:
            self.assertEqual(S.check_mirror(u1, self.signers)["verdict"], S.VERIFIED)
            self.assertEqual(S.check_mirror(u2, self.signers)["verdict"], S.MODIFIED)
        finally:
            s1.shutdown(); s2.shutdown()

    def test_a_dead_mirror_is_unreachable(self):
        self.assertEqual(S.check_mirror("http://127.0.0.1:9", self.signers)["verdict"], S.UNREACHABLE)

    def test_submitted_addresses_are_normalised_or_refused(self):
        a = "a" * 56 + ".onion"
        self.assertEqual(S.onion_base(f" HTTP://{a.upper()}/index.html "), "http://" + a)
        for bad in ("example.com", "a" * 16 + ".onion", "http://" + "a" * 55 + "1.onion", ""):
            self.assertIsNone(S.onion_base(bad), bad)

    def test_the_command_line_verifies_a_local_copy(self):
        site = release(self.d, self.key)
        r = subprocess.run([sys.executable, S.__file__, "verify", site, self.signers], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr); self.assertIn("verified", r.stdout)


if __name__ == "__main__":
    unittest.main()
