"""Adapter interfaces shared by cloud and offline backends."""
import http.client
import json
import os
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod

sleep = time.sleep  # indirection so tests patch this, not time

RETRYABLE_HTTP = frozenset({429, 500, 502, 503, 504})
ATTEMPTS = 3
BACKOFF = 2


def _num(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def response_usage(body):
    """Return (input_tokens, output_tokens) from an API response body.

    Reads Responses-style (input/output_tokens) or chat-style
    (prompt/completion_tokens) usage blocks; zeros when absent or odd.
    """
    use = body.get("usage") if isinstance(body, dict) else None
    if not isinstance(use, dict):
        return (0, 0)
    return (_num(use.get("input_tokens", use.get("prompt_tokens"))),
            _num(use.get("output_tokens", use.get("completion_tokens"))))


def new_stats():
    """Return a zeroed per-extractor usage accumulator."""
    return {"calls": 0, "input_tokens": 0, "output_tokens": 0, "seconds": 0.0}


def record_call(stats, body, seconds):
    """Accumulate one successful API response into a stats dict."""
    used_in, used_out = response_usage(body)
    stats["calls"] += 1
    stats["input_tokens"] += used_in
    stats["output_tokens"] += used_out
    stats["seconds"] += seconds


def post_json(url, payload, api_key, timeout, attempts=ATTEMPTS,
              backoff=BACKOFF, on_response=None):
    """POST payload as JSON; return the decoded response body.

    Retries transient transport failures (timeouts incl. read-side,
    connection errors, HTTP 429/5xx), sleeping backoff * 2**n seconds
    after attempt n. Fatal HTTP statuses raise immediately; the last
    error raises once attempts run out. on_response(body, seconds) fires
    once per successful response (attempt latency, backoff excluded);
    failed attempts never fire it.
    """
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"})
    tries = max(1, attempts)
    for n in range(tries):
        start = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = json.load(r)
            if on_response is not None:
                on_response(body, time.monotonic() - start)
            return body
        except urllib.error.HTTPError as e:
            if e.code not in RETRYABLE_HTTP or n + 1 >= tries:
                raise
        except (TimeoutError, urllib.error.URLError,
                http.client.HTTPException):
            if n + 1 >= tries:
                raise
        sleep(backoff * 2 ** n)


def source_name(source):
    """Basename for path-like extraction sources; None for raw bytes.

    Duck-typed (no Crop import): objects carrying image_path resolve
    through it, plain paths stringify, empty values yield None.
    """
    if isinstance(source, (bytes, bytearray)):
        return None
    path = getattr(source, "image_path", source)
    if not path:
        return None
    return os.path.basename(str(path))


def stamp_source(doc, source):
    """Set doc source.image_uri to the true filename when known.

    Overwrites model-emitted values: the adapter knows the real file
    (ledger audit trail). Raw-bytes input leaves the block untouched.
    Returns doc.
    """
    name = source_name(source)
    if name is not None and isinstance(doc.get("source"), dict):
        doc["source"]["image_uri"] = name
    return doc


class Segmenter(ABC):
    @abstractmethod
    def segment(self, image_path):
        """Return list of Crop records."""


class Extractor(ABC):
    @abstractmethod
    def extract(self, crop):
        """Return (schema doc dict, per-field confidence dict)."""


class Reviewer(ABC):
    @abstractmethod
    def review(self, doc, validation):
        """Return triage decision dict."""
