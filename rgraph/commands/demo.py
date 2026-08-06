"""`rgraph demo` — a short tour or one detailed fixture scenario."""

from __future__ import annotations

import json
import pathlib
import shutil
import tempfile

from rgraph.config import ConfigError
from rgraph.gates import evaluate_gate
from rgraph.hashing import document_hash
from rgraph.provenance import hash_mismatch, invalidated_gates
from rgraph.render import (
    BODY_STYLE, STATUS_STYLE, body_text, console, marked, muted, render_error,
    render_gate_result, render_next_action, render_provenance_notice,
    render_stale_chain, rule, section, table_row,
)
from rgraph.run import load_run

SCENARIOS = ("1", "2", "3")
ALL_GATES = ("H1", "E1", "H2", "H3", "T1", "H4", "T2", "V1", "M1")


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "demo",
        help="take a 30-second tour of what the verifier catches",
        description=(
            "Show a short tour of what the verifier catches, or inspect one "
            "fixture scenario in detail."
        ),
        epilog=(
            "Examples:\n"
            "  rgraph demo\n"
            "  rgraph demo --scenario 1\n"
            "  rgraph demo --all\n\n"
            "The short tour exits 0 when the clean handoff passes and both staged "
            "defects are caught. --all preserves the detailed failure screens and "
            "therefore exits 1."
        ),
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--scenario", choices=SCENARIOS, help="inspect one scenario in detail"
    )
    selection.add_argument(
        "--all", action="store_true",
        help="show all detailed scenarios; staged failures make the command exit 1",
    )
    parser.set_defaults(handler=handle)


def _break_doi(run_dir: pathlib.Path) -> None:
    """Fabricate a citation as if retrieval had done so from the start.

    The hash chain is re-linked, so the only thing left to catch is the missing
    source identity itself. Scenario 3 is where a broken chain gets its own screen.
    """
    path = run_dir / "corpus_snapshot.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["body"]["sources"][0]["doi"] = None
    document["content_hash"] = document_hash(document)
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    _relink(run_dir, "corpus_snapshot", document["content_hash"])


def _relink(run_dir: pathlib.Path, artifact_id: str, digest: str) -> None:
    for path in sorted(run_dir.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document.get("inputs"), list):
            continue
        touched = False
        for reference in document["inputs"]:
            if reference.get("artifact_id") == artifact_id:
                reference["content_hash"] = digest
                touched = True
        if touched:
            document["content_hash"] = document_hash(document)
            path.write_text(json.dumps(document, indent=2), encoding="utf-8")
            _relink(run_dir, document["artifact_id"], document["content_hash"])


def _change_data_after_freeze(run_dir: pathlib.Path) -> None:
    path = run_dir / "data_manifest.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["body"]["datasets"][0]["bytes"] += 1
    document["content_hash"] = document_hash(document)
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")


def _gate_line(run, kit, gate_id: str) -> str:
    result = evaluate_gate(run, kit, gate_id)
    table_row(
        f"{gate_id}  {kit.gates[gate_id].title}", result.status, width=43,
        value_style=STATUS_STYLE.get(result.status, BODY_STYLE),
    )
    return result.status


def _scenario_one(kit, run_dir, *, detail: bool = True) -> int:
    if detail:
        rule("SCENARIO 1 / CLEAN EVIDENCE", None, 58)
        body_text("Expected: all nine checkpoints accept the handoff.")
        console.print()
    run = load_run(run_dir, kit)
    states = [
        _gate_line(run, kit, gate_id) if detail
        else evaluate_gate(run, kit, gate_id).status
        for gate_id in ALL_GATES
    ]
    clean = all(s in ("PASS", "CAVEAT") for s in states)
    if not detail:
        return 0 if clean else 1
    console.print()
    if clean:
        body_text("Nine gates, no missing artifact, no broken hash chain.")
        console.print()
        section("What this demo verified")
        console.print(marked("PASS", "Artifact presence and JSON Schema"))
        console.print(marked("PASS", "SHA-256 provenance and stale-input detection"))
        console.print(marked("PASS", "Recorded producer/reviewer separation"))
        console.print(marked("PASS", "Gate prerequisites and revision budgets"))
        console.print(marked("----", "Scientific correctness was not determined"))
    else:
        failed = [g for g, s in zip(ALL_GATES, states) if s not in ("PASS", "CAVEAT")]
        body_text(f"Expected nine green gates; {', '.join(failed)} did not pass.")
        muted("This is not part of the demo — please report it.")
    console.print()
    return 0 if clean else 1


def _scenario_two(kit, run_dir, *, detail: bool = True) -> int:
    if detail:
        rule("SCENARIO 2 / SOURCE IDENTITY MISSING", None, 58)
        body_text("Expected: stop at evidence review and name the repair.")
        console.print()
    _break_doi(run_dir)
    shutil.rmtree(run_dir / "gates", ignore_errors=True)  # the gate runs for the first time
    run = load_run(run_dir, kit)
    result = evaluate_gate(run, kit, "E1")
    # This is a throwaway copy, so a real-run revision command would be unsafe
    # and misleading here. The demo's only next command is printed at the end.
    if detail:
        render_gate_result(result, kit.gates["E1"], show_next=False)
        console.print()
        if result.status not in ("PASS", "CAVEAT"):
            console.print(marked(
                "PASS", "Demo result: the untraceable source was caught before release."
            ))
            console.print()
    return 0 if result.status in ("PASS", "CAVEAT") else 1


def _root_causes(run) -> list[str]:
    """The artifacts that actually changed, not the ones that merely went stale."""
    causes: set[str] = set()
    for artifact in run.artifacts.values():
        if artifact.present:
            causes.update(name for name, _, _ in hash_mismatch(run, artifact))
    return sorted(causes)


def _scenario_three(kit, run_dir, *, detail: bool = True) -> int:
    if detail:
        rule("SCENARIO 3 / DATA CHANGED AFTER FREEZE", None, 58)
        body_text("Expected: invalidate approvals that depended on the old data.")
        console.print()
    _change_data_after_freeze(run_dir)
    run = load_run(run_dir, kit)
    invalidated = invalidated_gates(run, kit)
    if detail:
        render_stale_chain([
            f"run/{name}.json changed after the H4 protocol freeze"
            for name in _root_causes(run)
        ])
        if invalidated:
            body_text(
                f"Invalidated: {', '.join(sorted(invalidated))} "
                "(must re-run before they can pass)."
            )
        console.print()
    states = [
        _gate_line(run, kit, gate_id) if detail
        else evaluate_gate(run, kit, gate_id).status
        for gate_id in ("T2", "V1", "M1")
    ]
    if detail:
        console.print()
        if not all(s in ("PASS", "CAVEAT") for s in states):
            console.print(marked(
                "PASS", "Demo result: changed data retired the old approvals."
            ))
            console.print()
    return 0 if all(s in ("PASS", "CAVEAT") for s in states) else 1


RUNNERS = {"1": _scenario_one, "2": _scenario_two, "3": _scenario_three}


def _overview(kit) -> int:
    """Run the real fixture checks, then explain their meaning without a log dump."""
    rule("DEMO / WHAT RESEARCH-GRAPH CATCHES", None, 58)
    body_text(
        "This 30-second tour uses bundled teaching data. It calls no model and "
        "changes no study files."
    )
    muted(
        "The fixture's provider identities are illustrative; this is not evidence "
        "from a real multi-agent study."
    )
    console.print()

    outcomes: dict[str, int] = {}
    for scenario in SCENARIOS:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = pathlib.Path(tmp) / "run"
            shutil.copytree(kit.root / "example-run", run_dir)
            outcomes[scenario] = RUNNERS[scenario](kit, run_dir, detail=False)

    expected = {"1": 0, "2": 1, "3": 1}
    rows = (
        ("1", "Clean evidence", "all nine checkpoints accepted it"),
        ("2", "Source identity missing", "evidence review stopped it"),
        ("3", "Data changed after freeze", "later approvals were retired"),
    )
    section("Three handoffs")
    for scenario, title, consequence in rows:
        status = "PASS" if outcomes[scenario] == expected[scenario] else "FAIL"
        console.print(marked(status, f"{scenario}. {title} — {consequence}."))

    worked = outcomes == expected
    console.print()
    section("The point")
    if worked:
        body_text(
            "Good evidence moves forward. A source that cannot be traced stops at "
            "review. Data changed after a freeze cannot reuse the old approvals."
        )
        console.print(marked("----", "Scientific correctness was not determined."))
    else:
        body_text("The bundled demo did not behave as expected. Please report this run.")

    console.print()
    section("Inspect one case")
    table_row("clean", "rgraph demo --scenario 1", width=10)
    table_row("source", "rgraph demo --scenario 2", width=10)
    table_row("changed", "rgraph demo --scenario 3", width=10)
    muted("Detailed failure scenarios exit 1 because the selected gate fails on purpose.")
    console.print()
    return 0 if worked else 1


def handle(args) -> int:
    from rgraph.commands.check import load

    try:
        # Pinned to the example assignment on purpose. The fixture's recorded
        # identities were authored against it, so reading the user's own
        # assignment.yaml here would fail gates that describe nobody's run.
        kit = load(args, assignment="assignment.example.yaml")
    except ConfigError as exc:
        render_error(str(exc))
        return 2
    if not (kit.root / "example-run" / "meta.json").exists():
        render_error("example-run/ is missing from this checkout")
        return 2

    if args.scenario is None and not args.all:
        result = _overview(kit)
        muted("The committed example-run/ was not modified.")
        console.print()
        render_next_action("rgraph setup" if result == 0 else "rgraph demo --scenario 1")
        return result

    scenarios = [args.scenario] if args.scenario else list(SCENARIOS)
    render_provenance_notice(load_run(kit.root / "example-run", kit))

    worst = 0
    for scenario in scenarios:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = pathlib.Path(tmp) / "run"
            shutil.copytree(kit.root / "example-run", run_dir)
            worst = max(worst, RUNNERS[scenario](kit, run_dir))
    muted("The committed example-run/ was not modified.")
    if worst:
        console.print()
        if args.scenario:
            muted(
                f"Exit code 1 is expected for scenario {args.scenario}: this failure is "
                "staged on purpose."
            )
        elif args.all:
            muted(
                "Exit code 1 is the expected result: scenarios 2 and 3 are failures\n"
                "staged on purpose. Your installation is fine."
            )
        console.print()
        render_next_action("rgraph demo --scenario 1")
    elif args.scenario == "1":
        console.print()
        render_next_action("rgraph setup")
    return worst
