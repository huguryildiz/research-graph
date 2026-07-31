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
