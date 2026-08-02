"""`rgraph review` — the completion screen and the human release decision."""

from __future__ import annotations

import json
from dataclasses import dataclass

from rgraph.commands.status import build_view
from rgraph.config import ConfigError
from rgraph.gates import evaluate_gate, now
from rgraph.hashing import document_hash
from rgraph.interactive import InteractionCancelled, choose, is_terminal
from rgraph.render import console, render_completion, render_provenance_notice
from rgraph.run import RunError

GATE_ORDER = ("H1", "E1", "H2", "H3", "T1", "H4", "T2", "V1", "M1")
OUTCOMES = ("release", "revise", "narrow", "null-result", "stop")
BOUNDARY = "Scientific correctness was not determined"


@dataclass
class CompletionView:
    headline: str
    units_complete: int
    gate_line: str
    artifact_line: str
    review_level: str
    release_state: str
    ready: bool


def register(subparsers) -> None:
    parser = subparsers.add_parser("review", help="the human release decision")
    parser.add_argument("--outcome", choices=OUTCOMES, help="skip the prompt")
    parser.set_defaults(handler=handle)


def handle(args) -> int:
    from rgraph.commands.check import load_for_run

    try:
        kit, run = load_for_run(args)
    except (ConfigError, RunError) as exc:
        print(f"error: {exc}")
        return 2

    render_provenance_notice(run)
    results = {g: evaluate_gate(run, kit, g) for g in GATE_ORDER}
    passed = sum(1 for r in results.values() if r.status == "PASS")
    caveats = [g for g, r in results.items() if r.status == "CAVEAT"]
    blocked = [g for g, r in results.items() if r.status not in ("PASS", "CAVEAT")]

    status_view = build_view(run, kit)
    valid, stale, _ = status_view.artifact_counts
    levels = {
        g: r.separation.level for g, r in results.items() if r.separation and r.separation.level
    }
    weakest = min(levels.values(), key=lambda level: ("context_only", "separate_model",
                                                      "separate_provider").index(level)) \
        if levels else "none"

    gate_line = f"{passed} PASS"
    if caveats:
        gate_line += f", {len(caveats)} PASS WITH CAVEATS"
    if blocked:
        gate_line += f", {len(blocked)} NOT PASSED"

    render_completion(CompletionView(
        headline=("RUN NOT READY" if blocked else
                  "RUN COMPLETE WITH CAVEATS" if caveats else "RUN COMPLETE — READY FOR REVIEW"),
        units_complete=status_view.units_complete,
        gate_line=gate_line,
        artifact_line=f"{valid} valid, {stale} stale",
        review_level=weakest.replace("_", " ").upper(),
        release_state="NOT APPROVED",
        ready=not blocked,
    ))

    outcome = args.outcome
    if outcome is None:
        if not is_terminal():
            console.print("No release decision was recorded.")
            console.print("Run from a terminal, or pass --outcome explicitly.")
            return 2
        try:
            outcome = choose(
                "What is your release decision?",
                (
                    ("release", "Release — approve this completed run"),
                    ("revise", "Revise — send the work back for correction"),
                    ("narrow", "Narrow — reduce the question or claims"),
                    ("null-result", "Null result — retain a supported negative outcome"),
                    ("stop", "Stop — close without release"),
                ),
                allow_cancel=True,
            )
        except InteractionCancelled:
            outcome = None
        if outcome is None:
            console.print("Stopped. No release decision has been recorded.")
            return 0
    if outcome not in OUTCOMES:
        print(f"error: outcome must be one of {', '.join(OUTCOMES)}")
        return 2
    if outcome in ("release", "null-result") and blocked:
        console.print("Decision refused: unresolved gates remain: " + ", ".join(blocked))
        console.print("Run `rgraph status` to see the next action.")
        return 1

    body = {
        "outcome": outcome,
        "decided_by": "human",
        "decided_at": now(),
        "revision_counts": {
            g: b["used"] for g, b in run.meta.get("revisions", {}).items()
        },
        "scope_changes": [],
        "separation_levels": levels,
        "caveats": [f"{g} decided at {levels.get(g, 'unknown').replace('_', ' ').upper()}"
                    for g in caveats],
        "not_established": [BOUNDARY],
    }
    document = {
        "artifact_id": "release_manifest",
        "version": 1,
        "produced_by": {"role": "human", "identity": "human/manual"},
        "produced_at": now(),
        "inputs": [
            {"artifact_id": a, "content_hash": run.get(a).content_hash}
            for a in kit.gates["FINAL"].inputs
            if run.get(a).present
        ],
        "body": body,
    }
    document["content_hash"] = document_hash(document)
    if run.refuse_write("release_manifest.json"):
        return 0
    (run.root / "release_manifest.json").write_text(
        json.dumps(document, indent=2) + "\n", encoding="utf-8"
    )
    run.write_gate_record({
        "gate_id": "FINAL",
        "outcome": outcome,
        "decided_at": now(),
        "decided_by": {"role": "human", "identity": "human/manual"},
        "producer_identity": None,
        "separation_level": None,
        "separation_caveat": bool(caveats),
        "inputs": document["inputs"],
        "checks": [{"name": "presence", "status": "PASS", "detail": "release inputs present"}],
        "reason": None,
        "findings": [],
        "revision_budget": {"max": kit.gates["FINAL"].max_revisions, "used": 0},
    })
    console.print(f"Recorded: {outcome}")
    return 0 if outcome == "release" else 1
