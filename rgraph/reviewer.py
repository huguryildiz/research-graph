"""Structured response contract shared by challenge execution and verification."""

from __future__ import annotations

import hashlib
import json

from rgraph.schemas import registry

START = "<rgraph-decision>"
END = "</rgraph-decision>"


def allowed_reasons(kit, gate_id: str) -> tuple[str, ...]:
    """Typed reasons the executable graph can actually carry from this gate."""
    reasons: list[str] = []
    for edge in kit.graph.out_edges(gate_id):
        if edge.kind != "return":
            continue
        for reason in edge.carries:
            if reason not in reasons:
                reasons.append(reason)
    return tuple(reasons)


def decision_hash(decision: dict) -> str:
    encoded = json.dumps(
        decision, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def parse_decision(output: str, kit) -> tuple[dict | None, str | None]:
    """Extract one unambiguous valid decision from a provider transcript.

    Codex CLI emits a transcript that includes the input prompt and may repeat
    the final response after its event stream.  The prompt's illustrative block
    is deliberately schema-invalid (``pass|revise|block``), while repeated real
    decisions are byte-semantically equal.  Accepting equal valid duplicates
    handles that transport without accepting two conflicting decisions.
    """
    candidates: list[dict] = []
    cursor = 0
    saw_block = False
    last_error: str | None = None
    while True:
        opening = output.find(START, cursor)
        if opening < 0:
            break
        saw_block = True
        start = opening + len(START)
        end = output.find(END, start)
        if end < 0:
            last_error = f"reviewer output has an unterminated {START} block"
            break
        cursor = end + len(END)
        try:
            decision = json.loads(output[start:end].strip())
        except json.JSONDecodeError as exc:
            last_error = f"reviewer decision is not valid JSON: {exc}"
            continue
        errors = registry(kit.root).validate("reviewer_decision", decision)
        if errors:
            first = errors[0]
            last_error = f"reviewer decision is invalid: {first.path}: {first.message}"
            continue
        candidates.append(decision)

    if not candidates:
        if not saw_block:
            return None, f"reviewer output contains no {START} ... {END} block"
        return None, last_error or "reviewer output contains no valid decision block"
    unique = {decision_hash(item) for item in candidates}
    if len(unique) != 1:
        return None, "reviewer output contains conflicting valid decision blocks"
    return candidates[-1], None
