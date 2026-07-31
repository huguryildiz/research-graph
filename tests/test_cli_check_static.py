import pathlib

from rgraph.cli import main

ROOT = str(pathlib.Path(__file__).resolve().parents[1])


def test_static_check_on_the_reference_graph_exits_zero(capsys):
    assert main(["--root", ROOT, "--no-banner", "check", "--static"]) == 0
    out = capsys.readouterr().out
    assert "STATIC GRAPH CHECK" in out
    assert "PASS" in out
    assert "[----] Scientific correctness was not determined" in out


def test_static_check_on_a_broken_graph_exits_one(tmp_path, capsys):
    (tmp_path / "graph.yaml").write_text(
        "nodes:\n"
        "  - {id: a, kind: agent, stage: retrieve, produces: [evidence_matrix]}\n"
        "  - {id: b, kind: agent, stage: plan}\n"
        "edges:\n"
        "  - {from: a, to: b, kind: handoff, carries: [manuscript]}\n"
    )
    (tmp_path / "providers.yaml").write_text("codex: {kind: cli, invoke: codex}\n")
    assert main(["--root", str(tmp_path), "--no-banner", "check", "--static"]) == 1
    assert "FAIL" in capsys.readouterr().out
