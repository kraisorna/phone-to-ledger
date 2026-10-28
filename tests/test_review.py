"""Review queue: pending lifecycle + corrections exported as eval labels."""
import argparse
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from eval.run_eval import run_eval
from ptl.api.cli import cmd_review
from ptl.review.queue import ReviewQueue
from tests.fixtures import fresh


def _enqueue(queue, doc_id, doc):
    return queue.enqueue(doc_id, doc, {"requires_human_review": True},
                         {"decision": "needs_review"})


class TestReviewQueue(unittest.TestCase):
    def test_pending_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            q = ReviewQueue(os.path.join(tmp, "q"))
            self.assertEqual(q.pending(), [])
            _enqueue(q, "a", fresh())
            _enqueue(q, "b", fresh())
            self.assertEqual([r["doc_id"] for r in q.pending()], ["a", "b"])
            q.resolve("a", fresh())
            self.assertEqual([r["doc_id"] for r in q.pending()], ["b"])

    def test_export_skips_pending_and_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            q = ReviewQueue(os.path.join(tmp, "q"))
            _enqueue(q, "good", fresh())
            q.resolve("good", fresh())
            _enqueue(q, "waiting", fresh())  # still pending
            _enqueue(q, "broken", fresh())
            q.resolve("broken", {"schema_version": "1.0"})  # invalid
            with open(os.path.join(tmp, "q", "junk.json"), "w") as f:
                f.write("{not json")
            with open(os.path.join(tmp, "q", "note.txt"), "w") as f:
                f.write("ignored")
            summary = q.export_labels(os.path.join(tmp, "labels"))
            self.assertEqual(summary["exported"], ["good"])
            self.assertEqual(summary["skipped"]["waiting"], "pending")
            self.assertTrue(
                summary["skipped"]["broken"].startswith("invalid: "))
            self.assertEqual(summary["skipped"]["junk.json"], "unreadable")
            self.assertTrue(os.path.exists(
                os.path.join(tmp, "labels", "good.json")))
            self.assertFalse(os.path.exists(
                os.path.join(tmp, "labels", "broken.json")))

    def test_exported_label_scores_in_run_eval(self):
        wrong = fresh()
        wrong["totals"]["grand_total"] = 1
        fixed = fresh()
        with tempfile.TemporaryDirectory() as tmp:
            q = ReviewQueue(os.path.join(tmp, "q"))
            labels = os.path.join(tmp, "labels")
            _enqueue(q, "r1", wrong)
            q.resolve("r1", fixed)
            self.assertEqual(q.export_labels(labels)["exported"], ["r1"])
            preds = os.path.join(tmp, "preds.json")
            with open(preds, "w", encoding="utf-8") as f:
                json.dump({"r1": fixed}, f)
            report = run_eval(preds, labels)
            self.assertEqual(report["overall"]["doc_all_correct"], 1)
            # The label captures the fix: the original error now scores 0.
            with open(preds, "w", encoding="utf-8") as f:
                json.dump({"r1": wrong}, f)
            report = run_eval(preds, labels)
            self.assertEqual(report["overall"]["doc_all_correct"], 0)

    def test_reexport_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            q = ReviewQueue(os.path.join(tmp, "q"))
            labels = os.path.join(tmp, "labels")
            _enqueue(q, "r1", fresh())
            first = fresh()
            q.resolve("r1", first)
            q.export_labels(labels)
            second = fresh()
            second["totals"]["grand_total"] = 2
            q.resolve("r1", second)
            q.export_labels(labels)
            with open(os.path.join(labels, "r1.json"), encoding="utf-8") as f:
                self.assertEqual(json.load(f)["totals"]["grand_total"], 2)


class TestReviewCli(unittest.TestCase):
    def _args(self, queue, **kw):
        base = {"queue": queue, "pending": False, "show": "",
                "resolve": "", "correction": "", "export_labels": ""}
        base.update(kw)
        return argparse.Namespace(**base)

    def _seed(self, queue, doc_id="r1"):
        q = ReviewQueue(queue)
        q.enqueue(doc_id, fresh(), {"requires_human_review": True,
                                    "review_reasons": ["R11: placeholder"]},
                  {"decision": "needs_review"})
        return q

    def test_pending_lists_compact(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = os.path.join(tmp, "q")
            self._seed(queue)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cmd_review(self._args(queue, pending=True))
            self.assertEqual(rc, 0)
            (rec,) = json.loads(buf.getvalue())
            self.assertEqual(rec["doc_id"], "r1")
            self.assertEqual(rec["decision"], "needs_review")
            self.assertEqual(rec["reasons"], ["R11: placeholder"])

    def test_show_and_resolve_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = os.path.join(tmp, "q")
            self._seed(queue)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cmd_review(self._args(queue, show="r1"))
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(buf.getvalue())["doc_id"], "r1")
            fix = os.path.join(tmp, "fix.json")
            with open(fix, "w", encoding="utf-8") as f:
                json.dump(fresh(), f)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cmd_review(self._args(queue, resolve="r1",
                                           correction=fix))
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(buf.getvalue()),
                             {"doc_id": "r1", "status": "resolved"})
            self.assertEqual(ReviewQueue(queue).pending(), [])

    def test_export_labels_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = os.path.join(tmp, "q")
            self._seed(queue)
            ReviewQueue(queue).resolve("r1", fresh())
            labels = os.path.join(tmp, "labels")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cmd_review(self._args(queue, export_labels=labels))
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(buf.getvalue()),
                             {"exported": ["r1"], "skipped": {}})
            self.assertTrue(os.path.exists(
                os.path.join(labels, "r1.json")))

    def test_errors_return_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = os.path.join(tmp, "q")
            self._seed(queue)
            err = io.StringIO()
            with redirect_stderr(err):
                self.assertEqual(
                    cmd_review(self._args(queue, show="missing")), 1)
                self.assertEqual(
                    cmd_review(self._args(queue, resolve="r1")), 1)
                self.assertEqual(cmd_review(self._args(queue)), 1)
            self.assertIn("cannot show missing", err.getvalue())
            self.assertIn("needs --correction", err.getvalue())


if __name__ == "__main__":
    unittest.main()
