"""The fixture must declare itself, and the separation check must read artifacts."""

import json
import pathlib

from rgraph.cli import main
from rgraph.config import load_kit
from rgraph.gates import evaluate_gate, recorded_producer_identity
from rgraph.run import load_run

ROOT = pathlib.Path(__file__).resolve().parents[1]
R = ["--root", str(ROOT), "--no-banner"]


def test_example_run_declares_itself_synthetic():
    meta = json.loads((ROOT / "example-run" / "meta.json").read_text())
    assert meta["provenance"] == "synthetic"


def test_every_screen_prints_the_synthetic_notice(example_run, capsys):
    for argv in (["status"], ["check", "E1"], ["trace", "c-01"],
                 ["review", "--outcome", "stop"]):
        main([*R, "--run", str(example_run), *argv])
        assert "SYNTHETIC PROVENANCE" in capsys.readouterr().out, argv


def test_a_recorded_run_prints_no_notice(example_run, capsys):
    meta_path = example_run / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["provenance"] = "recorded"
    meta_path.write_text(json.dumps(meta))
    main([*R, "--run", str(example_run), "status"])
    assert "SYNTHETIC PROVENANCE" not in capsys.readouterr().out


def test_gate_records_agree_with_the_artifacts_they_reviewed():
    kit = load_kit(ROOT, assignment="assignment.example.yaml")
    run = load_run(ROOT / "example-run", kit)
    for gate_id in ("E1", "T1", "T2", "V1", "M1"):
        record = run.gate_record(gate_id)
        assert record is not None, gate_id
        assert record["producer_identity"] == recorded_producer_identity(
            run, kit, kit.gates[gate_id]
        ), gate_id


def test_rewriting_who_produced_an_artifact_breaks_its_digest(example_run):
    """The digest covers who produced an artifact, not only what it says.

    Separation rests on `produced_by.identity`. While the digest covered the
    body alone, that field could be rewritten with every hash still agreeing.
    """
    kit = load_kit(ROOT, assignment="assignment.example.yaml")
    path = example_run / "claim_evidence_map.json"
    document = json.loads(path.read_text())
    document["produced_by"]["identity"] = "somebody/else"
    path.write_text(json.dumps(document, indent=2))

    result = evaluate_gate(load_run(example_run, kit), kit, "M1")
    assert any(f.code == "BODY EDITED AFTER HASHING" for f in result.findings)
    assert result.status in ("FAIL", "STALE")


def test_dropping_an_input_reference_breaks_the_digest(example_run):
    """Unlinking an artifact from its inputs is an edit, and the digest says so."""
    kit = load_kit(ROOT, assignment="assignment.example.yaml")
    path = example_run / "claim_evidence_map.json"
    document = json.loads(path.read_text())
    document["inputs"] = []
    path.write_text(json.dumps(document, indent=2))

    result = evaluate_gate(load_run(example_run, kit), kit, "M1")
    assert any(f.code == "BODY EDITED AFTER HASHING" for f in result.findings)
    assert result.status in ("FAIL", "STALE")


def test_separation_reads_every_artifact_the_unit_produced(example_run, reseal):
    """u12 produces manuscript *and* claim_evidence_map; the reviewer may write neither.

    Reading only the first entry of `produces` let the reviewer author the
    claim-evidence map — the artifact the gate exists to audit — and still pass.
    """
    kit = load_kit(ROOT, assignment="assignment.example.yaml")
    reviewer = kit.assignment["reviewer"].identity(kit.providers)
    path = example_run / "claim_evidence_map.json"
    document = json.loads(path.read_text())
    document["produced_by"]["identity"] = reviewer
    path.write_text(json.dumps(document, indent=2))
    reseal(example_run)  # the chain is sound; separation is the only thing left

    result = evaluate_gate(load_run(example_run, kit), kit, "M1")
    assert result.separation.status == "FAIL"
    assert result.status == "FAIL"
    assert any(f.code == "REVIEWER IS THE PRODUCER" for f in result.findings)


def test_separation_reports_the_weakest_level_across_a_unit(example_run, reseal):
    """A gate is only as separated as the least separated artifact under it."""
    kit = load_kit(ROOT, assignment="assignment.example.yaml")
    path = example_run / "claim_evidence_map.json"
    document = json.loads(path.read_text())
    # manuscript stays claude-code/fable-5, which is a separate provider from the
    # grok reviewer; this one shares the reviewer's provider.
    document["produced_by"]["identity"] = "grok/grok-4"
    path.write_text(json.dumps(document, indent=2))
    reseal(example_run)

    result = evaluate_gate(load_run(example_run, kit), kit, "M1")
    assert result.separation.level == "separate_model"


def test_separation_reads_the_artifact_not_the_config(example_run, tmp_path):
    """Point assignment.yaml at one provider; the recorded identities still decide."""
    kit_dir = tmp_path / "kit"
    kit_dir.mkdir()
    for name in ("graph.yaml", "providers.yaml", "gates.yaml"):
        (kit_dir / name).write_text((ROOT / name).read_text(encoding="utf-8"), encoding="utf-8")
    (kit_dir / "schemas").symlink_to(ROOT / "schemas")
    (kit_dir / "assignment.yaml").write_text(
        "\n".join(
            f"{role}: {{provider: codex, model: gpt-5.6}}"
            for role in ("retrieval", "planning", "execution",
                         "verification", "synthesis", "reviewer")
        ) + "\n"
    )
    kit = load_kit(kit_dir)
    result = evaluate_gate(load_run(example_run, kit), kit, "E1")
    assert result.producer_identity == "claude-code/sonnet-5"
    assert result.separation.level == "separate_provider"


def test_editing_the_revision_budget_by_hand_is_visible(example_run):
    """meta.json holds the revision budget, so it carries a digest like anything else.

    Without one, a gate that had run out of attempts could be reopened by
    editing `used` back to zero, and nothing in the run would object.
    """
    kit = load_kit(ROOT, assignment="assignment.example.yaml")
    meta_path = example_run / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["revisions"]["M1"] = {"max": 99, "used": 0}
    meta_path.write_text(json.dumps(meta, indent=2))

    result = evaluate_gate(load_run(example_run, kit), kit, "M1")
    assert any(f.code == "META EDITED AFTER HASHING" for f in result.findings)
    assert result.status != "PASS"
