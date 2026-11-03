"""End-to-end wiring: segment -> extract -> validate -> triage -> rows.

Adapters are faked; no API calls. Covers the happy path, no-crop,
bad-doc, structurally-invalid, and duplicate-collapse paths, plus the
`ptl e2e` CLI plumbing with run_e2e mocked.
"""
import copy
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from ptl.api.cli import build_parser, cmd_e2e
from ptl.api.e2e import NO_RECEIPTS, run_e2e
from ptl.pipeline.dedup import SeenStore
from ptl.pipeline.segment import Crop
from ptl.review.queue import ReviewQueue
from tests.fixtures import fresh_seed

IMG = b"\xff\xd8\xff fake jpeg bytes"


def _crop(i=0):
    return Crop(index=i, polygon=[[0, 0], [10, 0], [10, 10], [0, 10]],
                image_path="s.jpg")


class _Seg:
    def __init__(self, crops):
        self._crops = crops

    def segment(self, image_path):
        return list(self._crops)


class _Ext:
    def __init__(self, docs):
        self._docs = docs
        self.calls = 0

    def extract(self, crop):
        doc = copy.deepcopy(self._docs[min(self.calls, len(self._docs) - 1)])
        self.calls += 1
        return doc, {}


def _image_file(data=IMG):
    f = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    f.write(data)
    f.close()
    return f.name


class _RecSeg(_Seg):
    def segment(self, image_path):
        self.seen = image_path
        return super().segment(image_path)


class TestRunE2E(unittest.TestCase):
    def test_happy_path_s1(self):
        path = _image_file()
        try:
            res = run_e2e(path, segmenter=_Seg([_crop()]),
                          extractor=_Ext([fresh_seed("S1")]))
        finally:
            os.unlink(path)
        self.assertEqual(len(res["crops"]), 1)
        self.assertEqual(len(res["rows"]), 1)
        self.assertEqual(res["rows"][0]["review_status"], "auto_accept")
        self.assertEqual(res["docs"][0]["triage"]["decision"], "auto_accept")
        self.assertIn("grand_total", res["csv"])
        self.assertEqual(res["docs"][0]["doc"]["source"]["crop_index"], 0)

    def test_e2e_scrubs_pii_at_ingestion(self):
        # 02 sec 12: PII the model leaks into free text must be
        # masked before validate/store/queue/export ever see it.
        doc = fresh_seed("S1")
        doc["issuer"]["phone"] = "081-375-6270"
        doc.setdefault("discarded_text", []).append("Tel: 02-0178899")
        path = _image_file()
        try:
            res = run_e2e(path, segmenter=_Seg([_crop()]),
                          extractor=_Ext([doc]))
        finally:
            os.unlink(path)
        out = res["docs"][0]["doc"]
        self.assertIsNone(out["issuer"]["phone"])
        self.assertNotIn("02-0178899", json.dumps(out))
        self.assertNotIn("081-375-6270", json.dumps(out))
        self.assertNotIn("02-0178899", res["csv"])
        self.assertEqual(res["rows"][0]["review_status"], "auto_accept")

    def test_two_crops_yield_two_docs(self):
        # "Several receipts in one shot" (mission statement): one doc
        # per slip, each extraction scoped to its crop. Distinct seeds
        # so in-run R10 must NOT collapse them (that path has its own
        # test with identical crops).
        path = _image_file()
        try:
            res = run_e2e(path, segmenter=_Seg([_crop(0), _crop(1)]),
                          extractor=_Ext([fresh_seed("S1"),
                                          fresh_seed("S2")]))
        finally:
            os.unlink(path)
        self.assertEqual(len(res["crops"]), 2)
        self.assertEqual(len(res["docs"]), 2)
        self.assertEqual(len(res["rows"]), 2)
        self.assertEqual(res["docs"][0]["crop_index"], 0)
        self.assertEqual(res["docs"][1]["crop_index"], 1)
        self.assertEqual(res["docs"][0]["doc"]["source"]["crop_index"], 0)
        self.assertEqual(res["docs"][1]["doc"]["source"]["crop_index"], 1)
        self.assertNotEqual(res["rows"][0]["document_number"],
                            res["rows"][1]["document_number"])

    def test_retry_recovers_transient_slip(self):
        bad = fresh_seed("S1")
        bad["line_items"][0]["line_total"] += 100  # R1 hard fail
        path = _image_file()
        try:
            ext = _Ext([bad, fresh_seed("S1")])
            res = run_e2e(path, segmenter=_Seg([_crop()]),
                          extractor=ext)
        finally:
            os.unlink(path)
        self.assertEqual(ext.calls, 2)
        self.assertEqual(res["docs"][0]["attempts"], 2)
        self.assertEqual(res["rows"][0]["review_status"], "auto_accept")

    def test_attempts_1_preserves_single_shot(self):
        bad = fresh_seed("S1")
        bad["line_items"][0]["line_total"] += 100
        path = _image_file()
        try:
            ext = _Ext([bad, fresh_seed("S1")])
            res = run_e2e(path, segmenter=_Seg([_crop()]),
                          extractor=ext, attempts=1)
        finally:
            os.unlink(path)
        self.assertEqual(ext.calls, 1)
        self.assertEqual(res["rows"][0]["review_status"], "blocked:R1")

    def test_usage_reported(self):
        # 05 sec 8 item 6: every e2e run reports its own cost
        # footprint (calls/tokens/seconds per stage + wall time).
        path = _image_file()
        try:
            res = run_e2e(path, segmenter=_Seg([_crop()]),
                          extractor=_Ext([fresh_seed("S1")]))
            empty = run_e2e(path, segmenter=_Seg([]),
                            extractor=_Ext([]))
        finally:
            os.unlink(path)
        for r in (res, empty):
            self.assertEqual(r["usage"]["segment"]["calls"], 0)
            self.assertEqual(r["usage"]["extract"]["calls"], 0)
            self.assertGreaterEqual(r["elapsed_seconds"], 0.0)

    def test_usage_surfaces_adapter_stats(self):
        path = _image_file()
        try:
            seg, ext = _Seg([_crop()]), _Ext([fresh_seed("S1")])
            seg.stats = {"calls": 1, "input_tokens": 10,
                         "output_tokens": 5, "seconds": 1.5}
            ext.stats = {"calls": 2, "input_tokens": 100,
                         "output_tokens": 50, "reasoning_tokens": 20,
                         "seconds": 3.0}
            res = run_e2e(path, segmenter=seg, extractor=ext)
        finally:
            os.unlink(path)
        self.assertEqual(res["usage"]["segment"]["calls"], 1)
        self.assertEqual(res["usage"]["segment"]["reasoning_tokens"], 0)
        self.assertEqual(res["usage"]["extract"]["output_tokens"], 50)
        self.assertEqual(res["usage"]["extract"]["reasoning_tokens"], 20)
        self.assertEqual(res["usage"]["extract"]["seconds"], 3.0)

    def test_no_crops(self):
        path = _image_file()
        try:
            res = run_e2e(path, segmenter=_Seg([]), extractor=_Ext([]))
        finally:
            os.unlink(path)
        self.assertEqual(res["note"], NO_RECEIPTS)
        self.assertEqual(res["rows"], [])
        self.assertEqual(res["docs"], [])

    def test_hard_fail_blocked_but_exported(self):
        doc = fresh_seed("S1")
        doc["line_items"][0]["line_total"] += 100  # break R1 (hard)
        path = _image_file()
        try:
            res = run_e2e(path, segmenter=_Seg([_crop()]),
                          extractor=_Ext([doc]))
        finally:
            os.unlink(path)
        entry = res["docs"][0]
        self.assertFalse(entry["validation"]["rules"]["R1"]["pass"])
        self.assertEqual(entry["triage"]["decision"], "needs_review")
        self.assertEqual(len(res["rows"]), 1)
        self.assertEqual(res["rows"][0]["review_status"], "blocked:R1")

    def test_soft_fail_needs_review(self):
        doc = fresh_seed("S1")
        doc["form"] = "unknown"  # break R14 (soft)
        path = _image_file()
        try:
            res = run_e2e(path, segmenter=_Seg([_crop()]),
                          extractor=_Ext([doc]))
        finally:
            os.unlink(path)
        entry = res["docs"][0]
        self.assertFalse(entry["validation"]["rules"]["R14"]["pass"])
        self.assertEqual(entry["triage"]["decision"], "needs_review")
        self.assertEqual(res["rows"][0]["review_status"], "needs_review")

    def test_low_confidence_triage_needs_review(self):
        doc = fresh_seed("S1")
        doc["field_confidence"] = {"issuer.legal_name": 0.3}
        path = _image_file()
        try:
            res = run_e2e(path, segmenter=_Seg([_crop()]),
                          extractor=_Ext([doc]))
        finally:
            os.unlink(path)
        entry = res["docs"][0]
        self.assertFalse(entry["validation"]["requires_human_review"])
        self.assertEqual(entry["triage"]["decision"], "needs_review")
        self.assertEqual(res["rows"][0]["review_status"], "needs_review")

    def test_review_queue_enqueues_flagged_doc(self):
        doc = fresh_seed("S1")
        doc["field_confidence"] = {"issuer.legal_name": 0.3}
        path = _image_file()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                qdir = os.path.join(tmp, "q")
                res = run_e2e(path, segmenter=_Seg([_crop()]),
                              extractor=_Ext([doc]), review_queue=qdir)
                pending = ReviewQueue(qdir).pending()
        finally:
            os.unlink(path)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["triage"]["decision"], "needs_review")
        self.assertEqual(res["review_enqueued"], [pending[0]["doc_id"]])

    def test_review_queue_skips_clean_doc(self):
        doc = fresh_seed("S1")
        path = _image_file()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                qdir = os.path.join(tmp, "q")
                res = run_e2e(path, segmenter=_Seg([_crop()]),
                              extractor=_Ext([doc]), review_queue=qdir)
                pending = ReviewQueue(qdir).pending()
        finally:
            os.unlink(path)
        self.assertEqual(pending, [])
        self.assertEqual(res["review_enqueued"], [])

    def test_partial_crop_never_auto_accepts(self):
        # 05 sec 5 stage 1: a cut-off slip is extracted for the
        # reviewer but always needs review, queued with a retake note.
        crop = _crop()
        crop.partial = True
        path = _image_file()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                qdir = os.path.join(tmp, "q")
                res = run_e2e(path, segmenter=_Seg([crop]),
                              extractor=_Ext([fresh_seed("S1")]),
                              review_queue=qdir, attempts=1)
                pending = ReviewQueue(qdir).pending()
        finally:
            os.unlink(path)
        self.assertTrue(res["crops"][0]["partial"])
        self.assertEqual(res["docs"][0]["triage"]["decision"],
                         "needs_review")
        self.assertIn("partial capture",
                      res["docs"][0]["triage"]["reason"])
        self.assertEqual(res["rows"][0]["review_status"], "needs_review")
        self.assertIn("retake", res["rows"][0]["note"])
        self.assertEqual(len(pending), 1)
        self.assertEqual(res["review_enqueued"], [pending[0]["doc_id"]])

    def test_exif_stripped_before_adapters(self):
        jpeg = (b"\xff\xd8\xff\xe1\x00\x1aExif\x00\x00GPS-1\x00\x00\x00"
                b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
                b"\xff\xda\x00\x08SCANDATA\xff\xd9")
        doc = fresh_seed("S1")
        doc["source"]["image_uri"] = "tmpEVIL.jpg"  # model echoes temp name
        path = _image_file(data=jpeg)
        try:
            seg = _RecSeg([_crop()])
            res = run_e2e(path, segmenter=seg, extractor=_Ext([doc]))
        finally:
            os.unlink(path)
        self.assertNotEqual(seg.seen, path)  # adapters got the scrubbed copy
        self.assertFalse(os.path.exists(seg.seen))  # temp cleaned up
        self.assertTrue(res["ingest"]["exif_stripped"])
        self.assertEqual(res["crops"][0]["image_path"], path)
        uri = res["docs"][0]["doc"]["source"]["image_uri"]
        self.assertEqual(uri, os.path.basename(path))

    def test_image_hash_filled_from_photo_bytes(self):
        import hashlib
        doc = fresh_seed("S1")
        self.assertEqual(doc["source"]["image_hash"], "placeholder-hash-s1")
        path = _image_file()
        try:
            with open(path, "rb") as f:
                want = hashlib.sha256(f.read()).hexdigest()
            res = run_e2e(path, segmenter=_Seg([_crop()]),
                          extractor=_Ext([doc]))
        finally:
            os.unlink(path)
        got = res["docs"][0]["doc"]["source"]["image_hash"]
        self.assertEqual(got, want)
        self.assertEqual(got, res["ingest"]["image_hash"])

    def test_repeat_photo_excluded_by_image_hash(self):
        import hashlib
        path = _image_file()
        try:
            with open(path, "rb") as f:
                digest = hashlib.sha256(f.read()).hexdigest()
            store = SeenStore()
            store.image_hashes.add(digest)  # only the image leg is armed
            res = run_e2e(path, segmenter=_Seg([_crop()]),
                          extractor=_Ext([fresh_seed("S1")]),
                          seen_store=store)
        finally:
            os.unlink(path)
        self.assertEqual(res["rows"], [])
        self.assertIn("duplicate image hash",
                      res["docs"][0]["excluded"])

    def test_no_exif_passthrough_path(self):
        doc = fresh_seed("S1")
        doc["source"]["image_uri"] = "custom.jpg"
        path = _image_file()
        try:
            seg = _RecSeg([_crop()])
            res = run_e2e(path, segmenter=seg, extractor=_Ext([doc]))
        finally:
            os.unlink(path)
        self.assertEqual(seg.seen, path)
        self.assertFalse(res["ingest"]["exif_stripped"])
        uri = res["docs"][0]["doc"]["source"]["image_uri"]
        self.assertEqual(uri, "custom.jpg")

    def test_struct_invalid_doc_excluded(self):
        doc = fresh_seed("S1")
        del doc["totals"]  # required top-level key
        path = _image_file()
        try:
            res = run_e2e(path, segmenter=_Seg([_crop()]),
                          extractor=_Ext([doc]))
        finally:
            os.unlink(path)
        self.assertTrue(res["docs"][0]["structure_errors"])
        self.assertTrue(res["docs"][0]["excluded"])
        self.assertEqual(res["rows"], [])

    def test_identical_crops_collapse_in_run(self):
        path = _image_file()
        try:
            res = run_e2e(path,
                          segmenter=_Seg([_crop(0), _crop(1)]),
                          extractor=_Ext([fresh_seed("S1")]))
        finally:
            os.unlink(path)
        self.assertEqual(len(res["rows"]), 1)
        self.assertTrue(res["docs"][1]["excluded"].startswith("duplicate"))

    def test_seen_store_flags_repeat(self):
        store = SeenStore()
        store.record(fresh_seed("S1"))
        path = _image_file()
        try:
            res = run_e2e(path, segmenter=_Seg([_crop()]),
                          extractor=_Ext([fresh_seed("S1")]),
                          seen_store=store)
        finally:
            os.unlink(path)
        self.assertEqual(res["rows"], [])
        self.assertIn("duplicate", res["docs"][0]["excluded"])


class TestCmdE2E(unittest.TestCase):
    def _args(self, **kw):
        base = {"image": "s.jpg", "out": "", "csv": "", "append": False,
                "seen": "", "concept": "receipt", "api_key": ""}
        base.update(kw)
        return mock.Mock(**base)

    def _result(self, **kw):
        res = {"image": "s.jpg", "ingest": {}, "crops": [{}],
               "docs": [{"triage": {"decision": "auto_accept"},
                         "excluded": ""}],
               "rows": [{"grand_total": "45.00"}], "csv": "h\nr\n",
               "note": ""}
        res.update(kw)
        return res

    def test_exit_0_and_csv_file(self):
        args = self._args(csv=os.path.join(tempfile.mkdtemp(), "l.csv"))
        with mock.patch("ptl.api.cli.run_e2e",
                         return_value=self._result()) as m:
            with mock.patch("sys.stdout", new_callable=io.StringIO):
                rc = cmd_e2e(args)
        self.assertEqual(rc, 0)
        m.assert_called_once()
        with open(args.csv, encoding="utf-8") as f:
            self.assertEqual(f.read(), "h\nr\n")

    def test_csv_xlsx_extension_writes_workbook(self):
        import zipfile
        args = self._args(csv=os.path.join(tempfile.mkdtemp(), "l.xlsx"))
        with mock.patch("ptl.api.cli.run_e2e",
                         return_value=self._result()):
            with mock.patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(cmd_e2e(args), 0)
        with zipfile.ZipFile(args.csv) as z:
            self.assertIn("xl/worksheets/sheet1.xml", z.namelist())

    def test_exit_2_needs_review(self):
        res = self._result(
            docs=[{"triage": {"decision": "needs_review"}, "excluded": ""}])
        args = self._args()
        with mock.patch("ptl.api.cli.run_e2e", return_value=res):
            with mock.patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(cmd_e2e(args), 2)

    def test_exit_3_no_rows(self):
        res = self._result(rows=[], csv="h\n", docs=[])
        args = self._args()
        with mock.patch("ptl.api.cli.run_e2e", return_value=res):
            with mock.patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(cmd_e2e(args), 3)

    def test_exit_4_no_receipts(self):
        res = self._result(rows=[], csv="h\n", docs=[], note=NO_RECEIPTS)
        args = self._args()
        with mock.patch("ptl.api.cli.run_e2e", return_value=res):
            with mock.patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(cmd_e2e(args), 4)

    def test_parser_wires_e2e(self):
        args = build_parser().parse_args(["e2e", "s.jpg"])
        self.assertEqual(args.func, cmd_e2e)
        self.assertEqual(args.concept, "receipt")
        self.assertEqual(args.attempts, 2)
        args = build_parser().parse_args(["e2e", "s.jpg", "--attempts", "1"])
        self.assertEqual(args.attempts, 1)

    def test_cmd_passes_attempts_through(self):
        args = self._args(attempts=1)
        with mock.patch("ptl.api.cli.run_e2e",
                        return_value=self._result()) as m:
            with mock.patch("sys.stdout", new_callable=io.StringIO):
                cmd_e2e(args)
        self.assertEqual(m.call_args.kwargs["attempts"], 1)


if __name__ == "__main__":
    unittest.main()
