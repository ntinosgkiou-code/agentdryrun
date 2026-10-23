"""Runs the reference verifier against the example bundles. No platform, no network: python -m unittest"""
import contextlib
import io
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import verify  # noqa: E402

EX = os.path.join(ROOT, "examples")


def keys():
    out = {}
    with open(os.path.join(EX, "KEYS.txt"), encoding="utf-8") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                out[k.split(" ")[0]] = v
    return out


def run(*args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = verify.main(list(args) + ["--json"])
    return code, json.loads(buf.getvalue())


class ExampleBundles(unittest.TestCase):
    def setUp(self):
        self.k = keys()
        self.valid = os.path.join(EX, "bundle-valid.zip")
        self.tampered = os.path.join(EX, "bundle-tampered.zip")
        self.w = ["--witness", "auditor-witness=" + self.k["auditor-witness"], "--witness", "insurer-witness=" + self.k["insurer-witness"]]

    def test_valid_bundle_is_verified_with_pinned_key_and_two_witnesses(self):
        code, rep = run(self.valid, "--log-key", self.k["log-key"], *self.w, "--min-witnesses", "2")
        self.assertEqual(code, 0, rep["problems"])
        self.assertTrue(rep["ok"])
        self.assertTrue(rep["pinned"])
        self.assertEqual(rep["info"]["observed"]["total"], 45)

    def test_a_tampered_record_is_caught(self):
        code, rep = run(self.tampered, "--log-key", self.k["log-key"], *self.w, "--min-witnesses", "2")
        self.assertEqual(code, 2)
        self.assertFalse(rep["ok"])
        self.assertTrue(any("does not hash to its leaf" in p for p in rep["problems"]), rep["problems"])

    def test_the_wrong_pinned_key_fails(self):
        code, rep = run(self.valid, "--log-key", self.k["auditor-witness"])
        self.assertEqual(code, 2)
        self.assertTrue(any("different log key" in p for p in rep["problems"]))

    def test_without_a_pinned_key_it_runs_but_says_so(self):
        code, rep = run(self.valid)
        self.assertEqual(code, 0)
        self.assertTrue(any("UNPINNED" in w for w in rep["warnings"]))

    def test_three_witnesses_required_but_only_two_exist(self):
        code, rep = run(self.valid, "--log-key", self.k["log-key"], *self.w, "--min-witnesses", "3")
        self.assertEqual(code, 2)
        self.assertTrue(any("witness policy" in p.lower() for p in rep["problems"]), rep["problems"])

    def test_an_untrusted_witness_does_not_count(self):
        code, rep = run(self.valid, "--log-key", self.k["log-key"], "--witness", "auditor-witness=" + self.k["auditor-witness"], "--min-witnesses", "2")
        self.assertEqual(code, 2)

    def test_unreadable_input_exits_3(self):
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf), contextlib.redirect_stdout(io.StringIO()):
            code = verify.main([os.path.join(EX, "KEYS.txt")])
        self.assertEqual(code, 3)


class Witness(unittest.TestCase):
    def test_a_witness_can_be_created(self):
        import tempfile
        from omnios import witnessd
        with tempfile.TemporaryDirectory() as d:
            info = witnessd.init_witness(d, "w-test")
            self.assertEqual(info["name"], "w-test")
            self.assertEqual(len(info["public_key"]), 44)
            self.assertTrue(os.path.exists(info["config_path"]))


if __name__ == "__main__":
    unittest.main()
