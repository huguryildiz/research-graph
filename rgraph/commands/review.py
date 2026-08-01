"""`rgraph review` — the completion screen and the human release decision."""

from __future__ import annotations

import json
from dataclasses import dataclass

from rgraph.commands.status import build_view
from rgraph.config import ConfigError
from rgraph.gates import evaluate_gate, now
from rgraph.hashing import content_hash
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
        headline="RUN COMPLETE WITH CAVEATS" if caveats or blocked else "RUN COMPLETE",
        units_complete=status_view.units_complete,
        gate_line=gate_line,
        artifact_line=f"{valid} valid, {stale} stale",
        review_level=weakest.replace("_", " ").upper(),
        release_state="NOT APPROVED",
    ))

    outcome = args.outcome
    if outcome is None:
        console.print("Decide: " + " · ".join(OUTCOMES))
        try:
            outcome = input("> ").strip().lower()
        except EOFError:
            outcome = "stop"
    if outcome not in OUTCOMES:
        print(f"error: outcome must be one of {', '.join(OUTCOMES)}")
        return 2

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
        "content_hash": content_hash(body),
        "body": body,
    }
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
