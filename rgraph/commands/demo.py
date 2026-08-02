"""`rgraph demo` — three scenarios on a throwaway copy of example-run.

The exit code is the worst outcome shown: scenario 1 is clean, scenarios 2 and 3
are supposed to fail, so a full `rgraph demo` exits 1 by design.
"""

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
        help="run a clean or staged-failure scenario, no setup required",
        description="Run the clean verified fixture or the staged failure examples.",
        epilog=(
            "Examples:\n"
            "  rgraph demo --scenario 1\n"
            "  rgraph demo\n\n"
            "Without --scenario, scenarios 2 and 3 fail on purpose and exit 1."
        ),
    )
    parser.add_argument("--scenario", choices=SCENARIOS, help="run one scenario only")
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
        gate_id, result.status, width=10,
        value_style=STATUS_STYLE.get(result.status, BODY_STYLE),
    )
    return result.status


def _scenario_one(kit, run_dir) -> int:
    rule("SCENARIO 1 / A CLEAN RUN", None, 49)
    console.print()
    run = load_run(run_dir, kit)
    states = [_gate_line(run, kit, gate_id) for gate_id in ALL_GATES]
    clean = all(s in ("PASS", "CAVEAT") for s in states)
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


def _scenario_two(kit, run_dir) -> int:
    rule("SCENARIO 2 / A FABRICATED CITATION", None, 49)
    console.print()
    _break_doi(run_dir)
    shutil.rmtree(run_dir / "gates", ignore_errors=True)  # the gate runs for the first time
    run = load_run(run_dir, kit)
    result = evaluate_gate(run, kit, "E1")
    # This is a throwaway copy, so a real-run revision command would be unsafe
    # and misleading here. The demo's only next command is printed at the end.
    render_gate_result(result, kit.gates["E1"], show_next=False)
    console.print()
    return 0 if result.status in ("PASS", "CAVEAT") else 1


def _root_causes(run) -> list[str]:
    """The artifacts that actually changed, not the ones that merely went stale."""
    causes: set[str] = set()
    for artifact in run.artifacts.values():
        if artifact.present:
            causes.update(name for name, _, _ in hash_mismatch(run, artifact))
    return sorted(causes)


def _scenario_three(kit, run_dir) -> int:
    rule("SCENARIO 3 / DATA CHANGED AFTER THE FREEZE", None, 49)
    console.print()
    _change_data_after_freeze(run_dir)
    run = load_run(run_dir, kit)
    invalidated = invalidated_gates(run, kit)
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
    states = [_gate_line(run, kit, gate_id) for gate_id in ("T2", "V1", "M1")]
    console.print()
    return 0 if all(s in ("PASS", "CAVEAT") for s in states) else 1


RUNNERS = {"1": _scenario_one, "2": _scenario_two, "3": _scenario_three}


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
        else:
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
