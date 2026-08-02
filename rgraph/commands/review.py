"""`rgraph review` — the completion screen and the human release decision."""

from __future__ import annotations

import json
from dataclasses import dataclass

from rgraph.commands.decide import git_user_name
from rgraph.commands.status import build_view
from rgraph.config import ConfigError
from rgraph.gates import evaluate_gate, now
from rgraph.hashing import document_hash
from rgraph.interactive import InteractionCancelled, ask_text, choose, is_terminal
from rgraph.render import (
    MAIN_STYLE, body_text, console, key_value, muted, render_completion,
    render_error, render_next_action, render_provenance_notice, section,
)
from rgraph.run import RunError

GATE_ORDER = ("H1", "E1", "H2", "H3", "T1", "H4", "T2", "V1", "M1")
OUTCOMES = ("release", "revise", "narrow", "null-result", "stop")
TERMINAL_OUTCOMES = frozenset({"release", "null-result", "stop"})
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
    parser = subparsers.add_parser(
        "review",
        help="the human release decision",
        description=(
            "Summarize release readiness and record the final attributable human "
            "decision. Passing gates do not approve publication by themselves."
        ),
        epilog=(
            "Examples:\n"
            "  rgraph review\n"
            "  rgraph review --as \"Your Name\"\n"
            "  rgraph review --outcome revise --as \"Your Name\"  # still requires a TTY"
        ),
    )
    parser.add_argument(
        "--outcome", choices=OUTCOMES,
        help="preselect an outcome at a terminal; never enables scripted approval",
    )
    parser.add_argument("--as", dest="identity", help="who is deciding; default is git user.name")
    parser.set_defaults(handler=handle)


def handle(args) -> int:
    from rgraph.commands.check import load_for_run

    try:
        kit, run = load_for_run(args)
    except (ConfigError, RunError) as exc:
        render_error(str(exc))
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

    # Refuse ordinary scripts and pipes. This is deliberately only a workflow
    # control: isatty cannot authenticate a person or detect software that was
    # explicitly given a pseudo-terminal. `--outcome` is never an escape from
    # the terminal requirement.
    if not is_terminal():
        body_text("No release decision was recorded.")
        muted("Run `rgraph review` from a terminal where the named person can read the summary.")
        return 2

    outcome = args.outcome
    if outcome is None:
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
            muted("Stopped. No release decision has been recorded.")
            return 0
    if outcome not in OUTCOMES:
        render_error(f"outcome must be one of {', '.join(OUTCOMES)}")
        return 2
    if outcome in ("release", "null-result") and blocked:
        section("Decision refused", "bold red")
        body_text("Unresolved gates remain: " + ", ".join(blocked))
        muted("Run `rgraph status` to see the next action.")
        return 1

    identity = args.identity or git_user_name()
    if not args.identity:
        try:
            identity = ask_text("Decided by", default=identity or None, required=True)
        except InteractionCancelled:
            muted("Stopped. No release decision has been recorded.")
            return 0
    if not identity:
        render_error("no identity given, and git has no user.name to fall back on")
        muted("Re-run with --as 'Your Name'.")
        return 2

    decided_at = now()
    actor = f"human/{identity}"
    inputs = [
        {"artifact_id": a, "content_hash": run.get(a).content_hash}
        for a in kit.gates["FINAL"].inputs
        if run.get(a).present
    ]
    final_result = evaluate_gate(run, kit, "FINAL")
    checks = [
        {"name": check.name, "status": check.status, "detail": check.detail}
        for check in final_result.checks
    ]

    if outcome in ("revise", "narrow"):
        gate = kit.gates["FINAL"]
        budget = run.meta.setdefault("revisions", {}).setdefault(
            "FINAL", {"max": gate.max_revisions, "used": 0}
        )
        if budget["used"] >= budget["max"]:
            section("Blocked", "bold red")
            body_text(
                f"FINAL has spent its revision budget "
                f"({budget['used']} of {budget['max']})."
            )
            console.print()
            render_next_action("rgraph review")
            return 1
        route = gate.routes[outcome]
        target = route.get("default") if isinstance(route, dict) else route
        budget["used"] += 1
        run.meta.setdefault("history", []).append({
            "at": decided_at, "gate": "FINAL", "outcome": outcome, "to": target,
        })
        run.save_meta()
        path = run.write_gate_record({
            "gate_id": "FINAL",
            "outcome": outcome,
            "decided_at": decided_at,
            "decided_by": {"role": "human", "identity": actor},
            "producer_identity": None,
            "separation_level": None,
            "separation_caveat": bool(caveats),
            "inputs": inputs,
            "checks": checks,
            "attestation": {
                "identity": actor,
                "answers": [{
                    "claim": "Human release decision recorded", "answered": "yes",
                }],
            },
            "reason": None,
            "findings": [],
            "revision_budget": budget,
        })
        section("Decision recorded")
        key_value("Outcome", outcome, value_style=MAIN_STYLE)
        key_value("Decided by", actor)
        key_value("Record", path)
        muted("No release manifest was written; this decision returns work.")
        console.print()
        render_next_action(f"rgraph next --unit {target}")
        return 1

    body = {
        "outcome": outcome,
        "decided_by": actor,
        "decided_at": decided_at,
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
        "produced_by": {"role": "human", "identity": actor},
        "produced_at": decided_at,
        "inputs": inputs,
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
        "decided_at": decided_at,
        "decided_by": {"role": "human", "identity": actor},
        "producer_identity": None,
        "separation_level": None,
        "separation_caveat": bool(caveats),
        "inputs": document["inputs"],
        "checks": checks,
        "attestation": {
            "identity": actor,
            "answers": [{
                "claim": "Human release decision recorded", "answered": "yes",
            }],
        },
        "reason": None,
        "findings": [],
        "revision_budget": {"max": kit.gates["FINAL"].max_revisions, "used": 0},
    })
    section("Decision recorded")
    key_value("Outcome", outcome, value_style=MAIN_STYLE)
    key_value("Decided by", actor)
    muted("Run complete. No further command is required.")
    return 0 if outcome == "release" else 1
