"""Persistent duplicate-detection store backing R10.

`validate()` only checks the `seen` mapping the caller passes, so without
persistence every run starts empty and duplicates are never caught. SeenStore
keeps the R10 key sets (doc keys, fuzzy keys, image hashes) as JSON on disk
between CLI invocations.

Recording policy (enforced by callers): record a doc only once it is
accepted as a ledger row, never a failed validation — otherwise a corrected
re-submission would false-positive as a duplicate of its own broken draft.
Per the document model, a duplicate already in the books is fixed with a
credit/debit note, not a re-export.
"""
import json
import os

from .validate_rules import dup_keys


class SeenStore:
    def __init__(self):
        self.doc_keys = set()
        self.fuzzy_keys = set()
        self.image_hashes = set()

    @classmethod
    def load(cls, path):
        """Load a store; a missing path yields an empty store."""
        store = cls()
        if not path or not os.path.exists(path):
            return store
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        store.doc_keys = {tuple(k) for k in data.get("doc_keys", [])}
        store.fuzzy_keys = {tuple(k) for k in data.get("fuzzy_keys", [])}
        store.image_hashes = set(data.get("image_hashes", []))
        return store

    def save(self, path):
        data = {"doc_keys": sorted(self.doc_keys),
                "fuzzy_keys": sorted(self.fuzzy_keys),
                "image_hashes": sorted(self.image_hashes)}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        return path

    def to_seen(self):
        """Return the `seen` mapping shape `validate()` expects."""
        return {"doc_keys": set(self.doc_keys),
                "fuzzy_keys": set(self.fuzzy_keys),
                "image_hashes": set(self.image_hashes)}

    def record(self, doc):
        """Add a doc's usable R10 keys; return the recorded key dict."""
        keys = dup_keys(doc)
        if keys["doc_key"] is not None:
            self.doc_keys.add(keys["doc_key"])
        if keys["fuzzy_key"] is not None:
            self.fuzzy_keys.add(keys["fuzzy_key"])
        if keys["image_hash"] is not None:
            self.image_hashes.add(keys["image_hash"])
        return keys
