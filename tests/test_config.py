import pathlib

import pytest

from rgraph.config import ARTIFACTS, ConfigError, ROLES, load_kit

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_reference_graph_loads():
    kit = load_kit(ROOT)
    assert len(kit.graph.units()) == 12
    assert kit.graph.node("u05").title == "Experiment design & modeling"
    assert kit.graph.node("u05").stage == "plan"
    assert kit.graph.node("u07").produces == ("run_manifest", "raw_results")


def test_every_artifact_has_exactly_one_producer():
    kit = load_kit(ROOT)
    producers: dict[str, list[str]] = {}
    for node in kit.graph.nodes.values():
        for artifact in node.produces:
            producers.setdefault(artifact, []).append(node.id)
    assert sorted(producers) == sorted(ARTIFACTS)
    assert all(len(owners) == 1 for owners in producers.values()), producers


def test_scalar_carries_is_normalised_to_a_tuple():
    kit = load_kit(ROOT)
    edge = next(e for e in kit.graph.edges if e.frm == "E1" and e.to == "u01")
    assert edge.kind == "return"
    assert edge.carries == ("evidence_gap",)
    assert edge.budget == 3


def test_providers_and_capabilities():
    kit = load_kit(ROOT)
    assert kit.providers["codex"].exec_argv == ("codex", "exec", "-c", "model={model}", "-")
    assert kit.providers["grok"].kind == "web"
    assert kit.providers["grok"].capabilities == frozenset({"manual"})


def test_assignment_identity_substitutes_the_model():
    kit = load_kit(ROOT, assignment="assignment.example.yaml")
    assert sorted(kit.assignment) == sorted(ROLES)
    assert kit.assignment["verification"].identity(kit.providers) == "codex/gpt-5.6"


def test_unknown_node_kind_is_rejected(tmp_path):
    (tmp_path / "graph.yaml").write_text("nodes:\n  - {id: x, kind: wizard}\nedges: []\n")
    (tmp_path / "providers.yaml").write_text("codex: {kind: cli, invoke: codex}\n")
    with pytest.raises(ConfigError, match="unknown node kind 'wizard'"):
        load_kit(tmp_path)


def test_edge_to_missing_node_is_rejected(tmp_path):
    (tmp_path / "graph.yaml").write_text(
        "nodes:\n  - {id: a, kind: agent}\nedges:\n  - {from: a, to: ghost, kind: handoff}\n"
    )
    (tmp_path / "providers.yaml").write_text("codex: {kind: cli, invoke: codex}\n")
    with pytest.raises(ConfigError, match="edge a -> ghost: unknown node 'ghost'"):
        load_kit(tmp_path)
