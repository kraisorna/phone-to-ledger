"""Shared cloud-adapter transport: POST JSON with transient retry (mocked).

Live Spark batches showed transient read timeouts failing whole
documents (6/20 first-pass failures, every one succeeding on manual
retry); post_json retries those inside the adapter with backoff
instead of failing the document.
"""
import http.client
import io
import json
import unittest
import urllib.error
from unittest import mock

from ptl.adapters.base import new_stats, post_json, record_call, response_usage

URL = "https://x.test/v1/responses"


def _resp(payload):
    resp = mock.MagicMock()
    resp.__enter__.return_value = io.StringIO(json.dumps(payload))
    resp.__exit__.return_value = False
    return resp


def _http_error(code):
    return urllib.error.HTTPError(URL, code, "x", {}, None)


def _run(opener, **kw):
    kw.setdefault("attempts", 3)
    with mock.patch("ptl.adapters.base.urllib.request.urlopen",
                    opener), \
            mock.patch("ptl.adapters.base.sleep") as slp:
        return post_json(URL, {"model": "m"}, "k", 300, **kw), slp


class TestPostJson(unittest.TestCase):
    def test_success_first_try_no_sleep(self):
        out, slp = _run(mock.MagicMock(return_value=_resp({"ok": True})))
        self.assertEqual(out, {"ok": True})
        slp.assert_not_called()

    def test_timeout_then_success(self):
        opener = mock.MagicMock(
            side_effect=[TimeoutError("timed out"), _resp({"ok": True})])
        out, slp = _run(opener)
        self.assertEqual(out, {"ok": True})
        self.assertEqual(opener.call_count, 2)
        slp.assert_called_once_with(2)

    def test_url_error_then_success(self):
        opener = mock.MagicMock(
            side_effect=[urllib.error.URLError("conn reset"),
                         _resp({"ok": True})])
        out, slp = _run(opener)
        self.assertEqual(out, {"ok": True})
        slp.assert_called_once_with(2)

    def test_remote_disconnect_then_success(self):
        opener = mock.MagicMock(
            side_effect=[http.client.RemoteDisconnected("closed"),
                         _resp({"ok": True})])
        out, slp = _run(opener)
        self.assertEqual(out, {"ok": True})
        slp.assert_called_once_with(2)

    def test_read_side_timeout_retried(self):
        bad = mock.MagicMock()
        bad.__enter__.return_value.read.side_effect = TimeoutError(
            "The read operation timed out")
        opener = mock.MagicMock(side_effect=[bad, _resp({"ok": True})])
        out, slp = _run(opener)
        self.assertEqual(out, {"ok": True})
        self.assertEqual(opener.call_count, 2)

    def test_retryable_http_then_success(self):
        for code in (429, 500, 502, 503, 504):
            opener = mock.MagicMock(
                side_effect=[_http_error(code), _resp({"ok": True})])
            out, slp = _run(opener)
            self.assertEqual(out, {"ok": True})
            self.assertEqual(opener.call_count, 2)
            slp.assert_called_once_with(2)

    def test_fatal_http_no_retry(self):
        for code in (400, 401, 403, 404):
            opener = mock.MagicMock(side_effect=_http_error(code))
            with mock.patch("ptl.adapters.base.urllib.request.urlopen",
                            opener), \
                    mock.patch("ptl.adapters.base.sleep") as slp:
                with self.assertRaises(urllib.error.HTTPError):
                    post_json(URL, {"model": "m"}, "k", 300, attempts=3)
            self.assertEqual(opener.call_count, 1)
            slp.assert_not_called()

    def test_exhaust_attempts_raises_last(self):
        opener = mock.MagicMock(side_effect=TimeoutError("t"))
        with mock.patch("ptl.adapters.base.urllib.request.urlopen",
                        opener), \
                mock.patch("ptl.adapters.base.sleep") as slp:
            with self.assertRaises(TimeoutError):
                post_json(URL, {"model": "m"}, "k", 300, attempts=3)
        self.assertEqual(opener.call_count, 3)
        slp.assert_has_calls([mock.call(2), mock.call(4)])

    def test_attempts_one_disables_retry(self):
        opener = mock.MagicMock(side_effect=TimeoutError("t"))
        with mock.patch("ptl.adapters.base.urllib.request.urlopen",
                        opener), \
                mock.patch("ptl.adapters.base.sleep") as slp:
            with self.assertRaises(TimeoutError):
                post_json(URL, {"model": "m"}, "k", 300, attempts=1)
        self.assertEqual(opener.call_count, 1)
        slp.assert_not_called()

    def test_response_usage_shapes(self):
        self.assertEqual(response_usage({"usage": {"input_tokens": 10,
                                                 "output_tokens": 3}}),
                         (10, 3))
        self.assertEqual(response_usage({"usage": {"prompt_tokens": 7,
                                                 "completion_tokens": 2}}),
                         (7, 2))
        self.assertEqual(response_usage({"output": []}), (0, 0))
        self.assertEqual(response_usage({}), (0, 0))
        self.assertEqual(response_usage(None), (0, 0))
        self.assertEqual(response_usage({"usage": {"input_tokens": "x"}}),
                         (0, 0))

    def test_record_call_accumulates(self):
        stats = new_stats()
        record_call(stats, {"usage": {"input_tokens": 10,
                                     "output_tokens": 3}}, 1.5)
        record_call(stats, {"output": []}, 0.5)
        self.assertEqual(stats, {"calls": 2, "input_tokens": 10,
                                 "output_tokens": 3, "seconds": 2.0})

    def test_on_response_fires_per_success(self):
        seen = []
        opener = mock.MagicMock(
            side_effect=[TimeoutError("t"), _resp({"ok": True})])
        with mock.patch("ptl.adapters.base.urllib.request.urlopen",
                        opener), \
                mock.patch("ptl.adapters.base.sleep"):
            post_json(URL, {"model": "m"}, "k", 300, attempts=3,
                      on_response=lambda b, s: seen.append((b, s)))
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][0], {"ok": True})
        self.assertGreaterEqual(seen[0][1], 0)

    def test_on_response_silent_on_total_failure(self):
        seen = []
        opener = mock.MagicMock(side_effect=TimeoutError("t"))
        with mock.patch("ptl.adapters.base.urllib.request.urlopen",
                        opener), \
                mock.patch("ptl.adapters.base.sleep"):
            with self.assertRaises(TimeoutError):
                post_json(URL, {"model": "m"}, "k", 300, attempts=2,
                          on_response=lambda b, s: seen.append((b, s)))
        self.assertEqual(seen, [])


if __name__ == "__main__":
    unittest.main()
