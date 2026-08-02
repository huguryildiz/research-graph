import json
import pathlib

import pytest

from rgraph.config import ARTIFACTS, load_kit
from rgraph.hashing import document_hash
from rgraph.provenance import (
    invalidated_gates, payload_mismatch, stale_artifacts, trace,
)
from rgraph.run import RunError, load_run

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _kit():
    return load_kit(ROOT, assignment="assignment.example.yaml")


def _rehash(path: pathlib.Path, mutate) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document["body"])
    document["content_hash"] = document_hash(document)
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")


# ── run loading ────────────────────────────────────────────────────────────

def test_empty_run_reports_every_artifact_absent(tmp_path):
    (tmp_path / "meta.json").write_text(
        '{"run_id":"rg-20260731-001","question":"q","mode":"GUIDED",'
        '"protocol":"OPEN","revisions":{},"history":[]}'
    )
    run = load_run(tmp_path, _kit())
    assert run.present_ids() == []
    assert run.get("evidence_matrix").present is False


def test_missing_meta_is_a_run_error(tmp_path):
    with pytest.raises(RunError, match="meta.json"):
        load_run(tmp_path, _kit())


def test_example_run_is_present_and_schema_clean(example_run):
    run = load_run(example_run, _kit())
    assert len(run.present_ids()) == len(ARTIFACTS) - 1  # release_manifest comes at FINAL
    assert [a.id for a in run.artifacts.values() if a.errors] == []


def test_payload_artifacts_expose_their_payload_path(example_run):
    run = load_run(example_run, _kit())
    assert run.get("manuscript").payload_path.name == "manuscript.md"
    assert run.get("raw_results").payload_path.name == "raw_results.jsonl"


def test_schema_violation_is_reported_not_raised(example_run):
    (example_run / "evidence_matrix.json").write_text('{"artifact_id":"evidence_matrix"}')
    run = load_run(example_run, _kit())
    assert run.get("evidence_matrix").errors != []


# ── provenance ─────────────────────────────────────────────────────────────

def test_untouched_run_has_no_stale_artifacts(example_run):
    assert stale_artifacts(load_run(example_run, _kit())) == {}


def test_editing_data_after_the_freeze_cascades(example_run):
    _rehash(example_run / "data_manifest.json",
            lambda body: body["datasets"][0].__setitem__("bytes", body["datasets"][0]["bytes"] + 1))
    kit = _kit()
    run = load_run(example_run, kit)
    assert "run_manifest" in stale_artifacts(run)
    assert set(invalidated_gates(run, kit)) >= {"T2", "V1", "M1"}


def test_payload_edit_is_detected(example_run):
    (example_run / "manuscript.md").write_text("# tampered\n")
    run = load_run(example_run, _kit())
    assert payload_mismatch(run, run.get("manuscript")) is not None


def test_trace_walks_manuscript_to_raw_results(example_run):
    kit = _kit()
    chain = trace(load_run(example_run, kit), kit, "c-01")
    labels = [link.label for link in chain.links]
    assert labels[0] == "manuscript.md"
    assert "claim_evidence_map.json" in labels
    assert "statistical_report.json" in labels
    assert "raw_results.jsonl" in labels
    assert chain.complete is True


def test_trace_uses_the_valid_h4_decision_not_the_template_protocol_flag(example_run):
    meta_path = example_run / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["protocol"] = "OPEN"
    meta["frozen_at"] = None
    meta["content_hash"] = document_hash(meta)
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    kit = _kit()
    chain = trace(load_run(example_run, kit), kit, "c-01")

    assert chain.complete is True
    frozen = next(
        link for link in chain.links if link.label == "frozen_protocol.json"
    )
    assert frozen.status == "FROZEN"


def test_trace_of_an_unknown_claim_is_incomplete(example_run):
    kit = _kit()
    chain = trace(load_run(example_run, kit), kit, "c-99")
    assert chain.complete is False
    assert "c-99" in " ".join(chain.missing)


def test_sealing_once_leaves_nothing_stale(example_run):
    """`seal` walks ARTIFACTS, so an input must come before whatever consumes it.

    figure_registry sat after claim_evidence_map, which consumes it, so a single
    pass sealed the consumer against a digest the producer had not taken yet.
    """
    from rgraph.commands.seal import seal_document
    from rgraph.config import ARTIFACTS, PAYLOAD_ARTIFACTS
    from rgraph.provenance import stale_artifacts

    kit = load_kit(ROOT, assignment="assignment.example.yaml")
    current: dict[str, str] = {}
    for artifact_id in ARTIFACTS:
        payload_name = PAYLOAD_ARTIFACTS.get(artifact_id)
        path = example_run / (
            f"{artifact_id}.meta.json" if payload_name else f"{artifact_id}.json"
        )
        if not path.exists():
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        document, _ = seal_document(
            document, current, example_run / payload_name if payload_name else None
        )
        current[artifact_id] = document["content_hash"]
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    assert stale_artifacts(load_run(example_run, kit)) == {}
