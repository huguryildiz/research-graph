"""Canonical JSON hashing. The whole staleness story rests on this file."""

from __future__ import annotations

import hashlib
import json
import pathlib
import re

HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_CHUNK = 1 << 20


def canonical_bytes(obj) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def content_hash(obj) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(obj)).hexdigest()


def document_hash(document: dict) -> str:
    """The digest of everything an artifact declares except the digest itself.

    Covering the body alone left the envelope unsigned: `produced_by`,
    `inputs[]` and `produced_at` could all be rewritten with every recorded hash
    still agreeing. Separation rests on the first and the chain on the second,
    so both belong under the seal.
    """
    return content_hash({k: v for k, v in document.items() if k != "content_hash"})


def file_hash(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()
