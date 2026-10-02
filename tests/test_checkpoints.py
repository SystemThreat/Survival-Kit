"""The checkpoint table on the signed page: well-formed, newest first, one per 1,000 heights down to genesis, and the
page keeps its no-script, script and print behaviour hooks. Node-free: reads site/index.html as it is."""
import importlib.util, os, re, unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
spec = importlib.util.spec_from_file_location("cp", os.path.join(ROOT, "tools", "checkpoints.py"))
CP = importlib.util.module_from_spec(spec); spec.loader.exec_module(CP)
PAGE = open(os.path.join(ROOT, "site", "index.html"), encoding="utf-8").read()


class Checkpoints(unittest.TestCase):
    def test_table_is_newest_first_every_1000_down_to_genesis(self):
        cps = CP.parse(PAGE)
        self.assertTrue(cps, "no checkpoints on the page")
        hs = [h for h, _ in cps]
        self.assertEqual(hs, list(range(hs[0], -1, -CP.STEP)))
        self.assertEqual(cps[-1], (0, CP.GENESIS))
        for _, x in cps: self.assertRegex(x, r"^[0-9a-f]{64}$")

    def test_every_row_between_the_markers_is_a_checkpoint_row(self):
        body = PAGE[PAGE.index(CP.BEGIN) + len(CP.BEGIN):PAGE.index(CP.END)]
        lines = [l for l in body.strip().splitlines() if l.strip()]
        self.assertEqual(len(lines), len(CP.parse(PAGE)), "a row the parser does not read")

    def test_rows_round_trip(self):
        cps = CP.parse(PAGE)
        self.assertEqual(CP.rows_html(cps).splitlines(), [l for l in PAGE[PAGE.index(CP.BEGIN) + len(CP.BEGIN):PAGE.index(CP.END)].strip().splitlines()])

    def test_tip_shown_matches_and_is_at_least_100_above_the_latest_checkpoint(self):
        tips = re.findall(r"<!-- cp-tip -->([\d,]+)<!-- /cp-tip -->", PAGE)
        self.assertTrue(tips); self.assertEqual(len(set(tips)), 1)
        self.assertGreaterEqual(int(tips[0].replace(",", "")) - CP.parse(PAGE)[0][0], CP.DEPTH)

    def test_behaviour_hooks(self):
        # no script: five rows and a CSS-only "show all"; script: search + pager; print: all rows, no controls
        self.assertIn(".cp tbody tr:nth-child(n+6){display:none}", PAGE)
        self.assertIn(".cp-all:checked + .cp-all-l + .wrap .cp tbody tr{display:table-row}", PAGE)
        self.assertNotIn(".cp-all:checked ~", PAGE)   # ~ reached every later table: one switch opened both lists
        for i in ('id="cp-q"', 'id="cp-prev"', 'id="cp-next"', 'id="cp-tools" hidden', 'id="cp-pager"'): self.assertIn(i, PAGE)
        self.assertIn(".cp tbody tr,.cp tbody tr[hidden]{display:table-row!important}", PAGE)
        self.assertIn("PER=5", PAGE)


if __name__ == "__main__":
    unittest.main()


class GenesisMessage(unittest.TestCase):
    def test_hex_on_the_page_decodes_to_the_message_shown(self):
        h = re.search(r'<pre class="gm-hex" id="gm-hex">([0-9a-f]+)</pre>', PAGE).group(1)
        raw = bytes.fromhex(h)
        self.assertEqual(raw[:9].hex(), "04ffff001d01044c4f")       # difficulty push, 01 04, OP_PUSHDATA1 0x4f (79 bytes)
        self.assertEqual(len(raw) - 9, 0x4f)
        text = raw[9:].decode()
        self.assertEqual(text, "Hic experimentum prosperat - 2026-09-26 - 10,000,000,000,000,000 sats, 100M XID")
        self.assertIn(f'<pre class="gm-out" id="gm-out">{text}</pre>', PAGE)
        self.assertIn(f"<b>“{text}”</b>", PAGE)
