"""Duplicate detection: SeenStore persistence + CLI --seen wiring.

R10 is only as good as the `seen` mapping it gets. These tests prove the
store round-trips through JSON, that each key class fires on re-ingest,
and that `export --seen` records while `validate --seen` stays pure.
"""
import argparse
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from ptl.api.cli import cmd_export, cmd_validate
from ptl.pipeline.dedup import SeenStore
from ptl.pipeline.validate_rules import validate
from tests.fixtures import fresh, fresh_seed


def _write(path, doc):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f)


class TestSeenStore(unittest.TestCase):
    def test_missing_file_loads_empty(self):
        store = SeenStore.load("/no/such/seen.json")
        self.assertEqual(store.to_seen(),
                         {"doc_keys": set(), "fuzzy_keys": set(),
                          "image_hashes": set()})

    def test_roundtrip(self):
        store = SeenStore()
        store.record(fresh())
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "seen.json")
            store.save(path)
            back = SeenStore.load(path)
        self.assertEqual(back.to_seen(), store.to_seen())
        self.assertIn(("1234567890121", "ABB-0001"), back.doc_keys)

    def test_recorded_doc_key_fires_r10(self):
        store = SeenStore()
        store.record(fresh())
        v = validate(fresh(), store.to_seen())
        self.assertFalse(v["rules"]["R10"]["pass"])
        self.assertIn("tax_id, document_number", v["rules"]["R10"]["detail"])

    def test_fuzzy_key_fires_without_document_number(self):
        # S2 has no document_number: the (tax_id, date, total, pos) key must catch it.
        store = SeenStore()
        store.record(fresh_seed("S2"))
        v = validate(fresh_seed("S2"), store.to_seen())
        self.assertFalse(v["rules"]["R10"]["pass"])
        self.assertIn("tax_id, date, total, pos",
                      v["rules"]["R10"]["detail"])

    def test_image_hash_fires_when_keys_differ(self):
        store = SeenStore()
        store.record(fresh())
        other = fresh()
        other["document_number"] = "ABB-9999"
        other["pos_identifier"] = "E999999999999"
        v = validate(other, store.to_seen())
        self.assertFalse(v["rules"]["R10"]["pass"])
        self.assertEqual(v["rules"]["R10"]["detail"], "duplicate image hash")

    def test_different_doc_passes(self):
        store = SeenStore()
        store.record(fresh())
        v = validate(fresh_seed("S6"), store.to_seen())
        self.assertTrue(v["rules"]["R10"]["pass"])


class TestSeenCli(unittest.TestCase):
    def _doc(self, tmp, doc=None):
        path = os.path.join(tmp, "doc.json")
        _write(path, fresh() if doc is None else doc)
        return path

    def test_validate_is_pure(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = self._doc(tmp)
            seen = os.path.join(tmp, "seen.json")
            args = argparse.Namespace(doc=doc, force=False, seen=seen)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cmd_validate(args), 0)
                self.assertEqual(cmd_validate(args), 0)
            # Validating never records: no store file, no self-dup.
            self.assertFalse(os.path.exists(seen))

    def test_export_records_then_validate_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = self._doc(tmp)
            seen = os.path.join(tmp, "seen.json")
            out = os.path.join(tmp, "ledger.csv")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cmd_export(argparse.Namespace(
                    doc=doc, out=out, seen=seen)), 0)
            self.assertTrue(os.path.exists(seen))
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(cmd_validate(argparse.Namespace(
                    doc=doc, force=False, seen=seen)), 2)
            self.assertIn("R10", buf.getvalue())

    def test_reexport_excluded_with_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = self._doc(tmp)
            seen = os.path.join(tmp, "seen.json")
            first = os.path.join(tmp, "first.csv")
            second = os.path.join(tmp, "second.csv")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cmd_export(argparse.Namespace(
                    doc=doc, out=first, seen=seen)), 0)
            with open(first, encoding="utf-8") as f:
                self.assertNotIn("duplicate", f.read())
            err = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(err):
                self.assertEqual(cmd_export(argparse.Namespace(
                    doc=doc, out=second, seen=seen)), 3)
            self.assertIn("duplicate (tax_id, document_number)", err.getvalue())
            self.assertFalse(os.path.exists(second))
            # Escape hatch: without --seen the export is forced.
            forced = os.path.join(tmp, "forced.csv")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cmd_export(argparse.Namespace(
                    doc=doc, out=forced, seen="")), 0)
            self.assertTrue(os.path.exists(forced))

    def test_blocked_export_records_nothing(self):
        bad = fresh()
        bad["line_items"][0]["line_total"] = 1  # fail hard rule R1
        with tempfile.TemporaryDirectory() as tmp:
            doc = self._doc(tmp, bad)
            seen = os.path.join(tmp, "seen.json")
            with redirect_stdout(io.StringIO()):
                cmd_export(argparse.Namespace(
                    doc=doc, out=os.path.join(tmp, "o.csv"), seen=seen))
            self.assertFalse(os.path.exists(seen))


if __name__ == "__main__":
    unittest.main()
