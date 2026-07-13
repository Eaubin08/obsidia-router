"""Canonical receipt producer for Track 3 ExecutionEnvelope.

SHA-256 is computed over the deterministic JSON serialisation of the envelope
WITHOUT the receipt_hash field. The same payload always produces the same hash
(sort_keys=True, ASCII-only, compact separators).

No secrets, no private paths, no API keys, no internal reasoning chains are
included in the canonical payload.
"""
from __future__ import annotations

import hashlib
import json


def _scrub(envelope: dict) -> dict:
    """Return a copy safe to hash and store: no secrets, no private paths."""
    scrubbed = {}
    for k, v in envelope.items():
        if k == "receipt_hash":
            continue
        scrubbed[k] = v
    return scrubbed


def compute_hash(envelope: dict) -> str:
    """Deterministic SHA-256 over the canonical envelope payload."""
    payload = _scrub(envelope)
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_hash(envelope: dict) -> bool:
    """Return True if the stored receipt_hash matches the recomputed value."""
    stored = envelope.get("receipt_hash", "")
    expected = compute_hash(envelope)
    return stored == expected


def to_json(envelope: dict, *, indent: int | None = 2) -> str:
    """Serialise the complete envelope (including receipt_hash) as JSON."""
    return json.dumps(envelope, indent=indent, ensure_ascii=False, default=str)
