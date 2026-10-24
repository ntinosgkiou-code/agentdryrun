"""Hostile bundles: verify.py must never say VERIFIED for changed evidence, must never crash, and must not be
talked into reading unbounded data. Starts from the real example bundle. No network: python -m unittest"""
import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
import warnings
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import verify  # noqa: E402

EX = os.path.join(ROOT, "examples")
KEY = "MHY2fDusvOBeEJjZJngCGuF/NjHtLpGLcgrHgM0EhWA="
WIT = {"auditor-witness": "Mwi9ce86bGM/9ctAKQeNu+bVxN9AlGJec/bNcsRab88=", "insurer-witness": "wh8uZprcOMB/IjMVDoLD1cVQxvYRZ8jzoXIAssy5jbg="}


def load(name="bundle-valid.zip"):
    with zipfile.ZipFile(os.path.join(EX, name)) as z:
        return {i.filename: z.read(i.filename) for i in z.infolist()}


def refresh(files):
    """What an attacker does: make manifest.json agree with the changed files."""
    m = json.loads(files["manifest.json"])
    for fn in list(m.get("files", {})):
        if fn in files:
            m["files"][fn] = hashlib.sha256(files[fn]).hexdigest()
    files["manifest.json"] = json.dumps(m).encode()
    return files


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = load()
        self.lines = self.base["records.jsonl"].decode().splitlines()

    def bundle(self, files, extra=()):
        p = os.path.join(self.tmp.name, "b.zip")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)         # zipfile warns when we deliberately write a duplicate name
            with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
                for k, v in files.items():
                    z.writestr(k, v)
                for k, v in extra:
                    z.writestr(k, v)
        return p

    def check(self, files, extra=(), **kw):
        kw.setdefault("min_witnesses", 2)
        return verify.verify_bundle(self.bundle(files, extra), KEY, WIT, **kw)

    def with_records(self, lines):
        f = dict(self.base)
        f["records.jsonl"] = ("\n".join(lines) + "\n").encode()
        return refresh(f)

    def assertRejected(self, rep, msg=""):
        self.assertFalse(rep["ok"], msg or rep)
        self.assertTrue(rep["problems"], msg)


class Control(Base):
    def test_untouched_bundle_verifies(self):
        rep = self.check(dict(self.base))
        self.assertTrue(rep["ok"], rep["problems"])
        self.assertEqual(rep["warnings"], [])
        self.assertTrue(rep["info"]["complete"])

    def test_the_tampered_example_fails(self):
        self.assertRejected(verify.verify_bundle(os.path.join(EX, "bundle-tampered.zip"), KEY, WIT, min_witnesses=2))


class Malformed(Base):
    def test_missing_empty_or_garbage_files_fail_cleanly(self):
        for fn in ("manifest.json", "checkpoints.json", "records.jsonl"):
            for how, val in (("missing", None), ("empty", b""), ("garbage", b"\xff\xfe\x00 not json")):
                f = dict(self.base)
                if val is None:
                    del f[fn]
                else:
                    f[fn] = val
                for fixed in (False, True):
                    self.assertRejected(self.check(refresh(dict(f)) if fixed and fn != "manifest.json" else f), f"{how} {fn} fixed={fixed}")

    def test_wrong_json_types_fail_cleanly(self):
        values = ["[]", '"x"', "5", "null", "true", "{}", '{"main": 5}', '{"main": {}}', '{"main": {"note": 5}}']
        for fn in ("manifest.json", "checkpoints.json"):
            for v in values:
                f = dict(self.base)
                f[fn] = v.encode()
                self.assertRejected(self.check(refresh(f) if fn != "manifest.json" else f), f"{fn} = {v}")
        for v in ("5", "[]", '"x"', '{"seq": "a"}', '{"seq": true, "body": "{}", "leaf": "00", "proof": []}', '{"seq": 0, "body": 5}',
                  '{"seq": 0, "body": "{}", "leaf": 5, "proof": 5}', '{"seq": -1, "body": "{}", "leaf": "00", "proof": []}', '{"seq": 1e999}'):
            f = dict(self.base)
            f["records.jsonl"] = (v + "\n").encode()
            self.assertRejected(self.check(refresh(f)), f"records = {v}")

    def test_deep_nesting_does_not_crash(self):
        deep = "[" * 200000 + "]" * 200000
        self.assertRejected(self.check(self.with_records([deep])))

    def test_duplicate_zip_entries_and_too_many_entries(self):
        rep = self.check(dict(self.base), extra=[("records.jsonl", b"")])
        self.assertRejected(rep)
        self.assertIn("same file name twice", rep["problems"][0])
        many = dict(self.base)
        many.update({f"junk{i}": b"x" for i in range(verify.MAX_ENTRIES + 1)})
        self.assertRejected(self.check(many))

    def test_a_member_that_inflates_past_the_limit_is_refused_before_it_is_read(self):
        f = dict(self.base)
        f["records.jsonl"] = self.base["records.jsonl"] + b" " * (2 * 1024 * 1024)      # ~2 KB zipped, 2 MB inflated
        p = self.bundle(refresh(f))
        self.assertLess(os.path.getsize(p), 100_000)
        rep = verify.verify_bundle(p, KEY, WIT, min_witnesses=2, max_member_bytes=1024 * 1024)
        self.assertRejected(rep)
        self.assertIn("would inflate", rep["problems"][0])
        self.assertTrue(verify.verify_bundle(p, KEY, WIT, min_witnesses=2)["ok"])       # under the default limit it is just padding


class Tampering(Base):
    """Every change below is made with manifest.json repaired, as a real attacker would. None may verify."""

    def test_editing_any_part_of_a_record(self):
        for i in (0, 10, 30, 66):
            for field in ("body", "leaf", "proof"):
                o = json.loads(self.lines[i])
                if field == "body":
                    o["body"] = o["body"][:-2] + "X}"
                elif field == "leaf":
                    o["leaf"] = "00" * 32
                else:
                    o["proof"] = o["proof"][:-1] if o["proof"] else ["00" * 32]
                lines = self.lines[:]
                lines[i] = json.dumps(o)
                self.assertRejected(self.check(self.with_records(lines)), f"record {i} {field}")

    def test_removing_reordering_or_repeating_records(self):
        L = self.lines
        for name, lines in (("delete a middle record", L[:5] + L[6:]), ("drop the last record", L[:-1]),
                            ("swap two records", L[:3] + [L[4], L[3]] + L[5:]), ("repeat the last record", L + [L[-1]])):
            self.assertRejected(self.check(self.with_records(lines)), name)

    def test_checkpoint_changes(self):
        cps = json.loads(self.base["checkpoints.json"])
        stale = json.loads(json.dumps(cps))
        stale["main"]["note"] = stale["main"]["note"].replace("\n67\n", "\n66\n", 1)
        nosig = json.loads(json.dumps(cps))
        sig = nosig["main"]["note"].rstrip("\n").split("\n")
        sig[-1] = sig[-1][:-6] + "AAAAA="
        nosig["main"]["note"] = "\n".join(sig) + "\n"
        for name, c in (("size changed, signature stale", stale), ("log signature corrupted", nosig)):
            f = dict(self.base)
            f["checkpoints.json"] = json.dumps(c).encode()
            self.assertRejected(self.check(refresh(f)), name)

    def test_wrong_pinned_key_fails(self):
        wrong = "wh8uZprcOMB/IjMVDoLD1cVQxvYRZ8jzoXIAssy5jbg="
        self.assertRejected(verify.verify_bundle(self.bundle(dict(self.base)), wrong, WIT, min_witnesses=2))

    def test_removing_one_witness_signature_breaks_a_two_witness_policy(self):
        c = json.loads(self.base["checkpoints.json"])
        for w in c["witnessed"]:
            w["note"] = "\n".join(l for l in w["note"].split("\n") if not l.startswith("— insurer-witness"))
        f = dict(self.base)
        f["checkpoints.json"] = json.dumps(c).encode()
        self.assertRejected(self.check(refresh(f), min_witnesses=2))
        self.assertTrue(self.check(refresh(dict(f)), min_witnesses=1)["ok"])

    def test_files_that_are_not_evidence_may_change(self):
        """README.txt and the verify.py copied into a bundle are not checked as evidence; that is why you never run the copy."""
        f = dict(self.base)
        f["verify.py"] = b"print('RESULT: VERIFIED')\n"
        self.assertTrue(self.check(refresh(f))["ok"])


class Completeness(Base):
    """manifest.json is not signed, so its scope label cannot be trusted: only the record count can."""

    def omitted(self, kind):
        f = dict(self.base)
        m = json.loads(f["manifest.json"])
        m["scope"] = {"kind": kind}
        f["manifest.json"] = json.dumps(m).encode()
        f["records.jsonl"] = ("\n".join(self.lines[:30]) + "\n").encode()
        return refresh(f)

    def test_omitted_records_under_a_relabelled_scope_are_warned_about(self):
        rep = self.check(self.omitted("partial"))
        self.assertTrue(rep["ok"])                                  # the 30 records shown are genuine
        self.assertFalse(rep["info"]["complete"])
        self.assertTrue(any(w.startswith("INCOMPLETE: 30 verified records of the 67") for w in rep["warnings"]), rep["warnings"])

    def test_require_all_turns_the_warning_into_a_failure(self):
        rep = self.check(self.omitted("partial"), require_all=True)
        self.assertRejected(rep)
        self.assertTrue(any("INCOMPLETE" in p for p in rep["problems"]))

    def test_scope_all_with_missing_records_fails(self):
        self.assertRejected(self.check(self.omitted("all")))

    def test_complete_bundle_passes_require_all(self):
        self.assertTrue(self.check(dict(self.base), require_all=True)["ok"])


class CommandLine(Base):
    def run_cli(self, bundle, *extra):
        args = [bundle, "--log-key", KEY, "--min-witnesses", "2"]
        for n, k in WIT.items():
            args += ["--witness", f"{n}={k}"]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = verify.main(args + list(extra))
        return rc, out.getvalue(), err.getvalue()

    def test_exit_codes(self):
        self.assertEqual(self.run_cli(self.bundle(dict(self.base)))[0], 0)
        self.assertEqual(self.run_cli(os.path.join(EX, "bundle-tampered.zip"))[0], 2)
        junk = dict(self.base)
        junk["records.jsonl"] = b"\xff\xfe"
        rc, _, err = self.run_cli(self.bundle(refresh(junk)))
        self.assertEqual(rc, 3)
        self.assertIn("malformed bundle", err)
        self.assertNotIn("Traceback", err)

    def test_require_all_flag_and_bad_keys(self):
        self.assertEqual(self.run_cli(self.bundle(Completeness.omitted(self, "partial")), "--require-all")[0], 2)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = verify.main([self.bundle(dict(self.base)), "--log-key", "not base64!!"])
        self.assertEqual(rc, 3)
        self.assertIn("32 bytes", err.getvalue())


if __name__ == "__main__":
    unittest.main()
