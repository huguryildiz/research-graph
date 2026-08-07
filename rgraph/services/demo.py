"""The three teaching scenarios, as data rather than as a screen.

`rgraph demo` prints these; the browser draws them. Both run the real checks
over a throwaway copy of the bundled fixture, so neither can show a result the
verifier did not actually produce, and the committed `example-run/` is never
touched.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import tempfile

from rgraph.config import Kit
from rgraph.gates import evaluate_gate
from rgraph.hashing import document_hash
from rgraph.provenance import hash_mismatch, invalidated_gates
from rgraph.run import load_run

ALL_GATES = ("H1", "E1", "H2", "H3", "T1", "H4", "T2", "V1", "M1")

SYNTHETIC_NOTE = (
    "This uses bundled teaching data. The provider and reviewer identities in it "
    "are illustrative, not evidence from a real multi-agent study. No model is "
    "called and no study file is changed."
)


def copy_fixture(kit: Kit, destination: pathlib.Path) -> pathlib.Path:
    shutil.copytree(kit.root / "example-run", destination)
    return destination


def break_doi(run_dir: pathlib.Path) -> None:
    """Fabricate a citation as if retrieval had done so from the start.

    The hash chain is re-linked, so the only thing left to catch is the missing
    source identity itself. Scenario 3 is where a broken chain gets its own screen.
    """
    path = run_dir / "corpus_snapshot.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["body"]["sources"][0]["doi"] = None
    document["content_hash"] = document_hash(document)
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    relink(run_dir, "corpus_snapshot", document["content_hash"])


def relink(run_dir: pathlib.Path, artifact_id: str, digest: str) -> None:
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
            relink(run_dir, document["artifact_id"], document["content_hash"])


def change_data_after_freeze(run_dir: pathlib.Path) -> None:
    path = run_dir / "data_manifest.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["body"]["datasets"][0]["bytes"] += 1
    document["content_hash"] = document_hash(document)
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")


def root_causes(run) -> list[str]:
    """The artifacts that actually changed, not the ones that merely went stale."""
    causes: set[str] = set()
    for artifact in run.artifacts.values():
        if artifact.present:
            causes.update(name for name, _, _ in hash_mismatch(run, artifact))
    return sorted(causes)


def _gate_rows(run, kit: Kit, gate_ids) -> list[dict]:
    rows = []
    for gate_id in gate_ids:
        result = evaluate_gate(run, kit, gate_id)
        rows.append({
            "id": gate_id,
            "title": kit.gates[gate_id].title,
            "status": result.status,
            "passed": result.status in ("PASS", "CAVEAT"),
        })
    return rows


def _scenario_one(kit: Kit, run_dir: pathlib.Path) -> dict:
    run = load_run(run_dir, kit)
    gates = _gate_rows(run, kit, ALL_GATES)
    clean = all(row["passed"] for row in gates)
    return {
        "id": "1",
        "title": "Clean evidence advances",
        "expectation": "All nine checkpoints accept the handoff.",
        "consequence": (
            "Every artifact is present, matches its schema, and its recorded input "
            "digests still match the files on disk."
        ),
        "behaved_as_documented": clean,
        "gates": gates,
        "detail": [
            "Artifact presence and JSON Schema",
            "SHA-256 provenance and stale-input detection",
            "Recorded producer/reviewer separation",
            "Gate prerequisites and revision budgets",
        ],
    }


def _scenario_two(kit: Kit, run_dir: pathlib.Path) -> dict:
    break_doi(run_dir)
    shutil.rmtree(run_dir / "gates", ignore_errors=True)  # the gate runs for the first time
    run = load_run(run_dir, kit)
    result = evaluate_gate(run, kit, "E1")
    stopped = result.status not in ("PASS", "CAVEAT")
    return {
        "id": "2",
        "title": "An untraceable source stops at evidence review",
        "expectation": "Evidence review stops it and names the repair.",
        "consequence": (
            "One cited source lost its identifier. The chain still adds up, so only "
            "the evidence check can catch it — and it does."
        ),
        "behaved_as_documented": stopped,
        "gates": [{
            "id": "E1", "title": kit.gates["E1"].title,
            "status": result.status, "passed": not stopped,
        }],
        "findings": [
            {
                "artifact": finding.ref, "code": finding.code,
                "detail": finding.detail, "fix": finding.fix,
            }
            for finding in result.findings
        ],
        "checks": [
            {"name": check.name, "status": check.status, "detail": check.detail}
            for check in result.checks
        ],
    }


def _scenario_three(kit: Kit, run_dir: pathlib.Path) -> dict:
    change_data_after_freeze(run_dir)
    run = load_run(run_dir, kit)
    invalidated = invalidated_gates(run, kit)
    gates = _gate_rows(run, kit, ("T2", "V1", "M1"))
    retired = not all(row["passed"] for row in gates)
    return {
        "id": "3",
        "title": "Changed data invalidates the approvals that used it",
        "expectation": "Approvals that depended on the old data are retired.",
        "consequence": (
            "A dataset record changed after the protocol was frozen. Decisions made "
            "on the old bytes no longer cover the new ones, so they stop counting."
        ),
        "behaved_as_documented": retired,
        "gates": gates,
        "causes": [
            f"{name}.json changed after the protocol freeze" for name in root_causes(run)
        ],
        "invalidated": sorted(invalidated),
    }


RUNNERS = {"1": _scenario_one, "2": _scenario_two, "3": _scenario_three}


def scenarios(kit: Kit) -> dict:
    """Run all three over throwaway copies and report what actually happened."""
    results = []
    for scenario_id in ("1", "2", "3"):
        with tempfile.TemporaryDirectory(prefix="rgraph-demo-") as tmp:
            run_dir = copy_fixture(kit, pathlib.Path(tmp) / "run")
            results.append(RUNNERS[scenario_id](kit, run_dir))
    return {
        "scenarios": results,
        "as_documented": all(item["behaved_as_documented"] for item in results),
        "note": SYNTHETIC_NOTE,
        "boundary": "Scientific correctness was not determined.",
    }
