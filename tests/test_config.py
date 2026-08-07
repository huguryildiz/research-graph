import pathlib

import pytest

from rgraph.config import ARTIFACTS, Assignment, ConfigError, ROLES, load_kit

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _minimal_kit_files(tmp_path: pathlib.Path) -> None:
    """A throwaway root carrying the real provider registry.

    The effort rules are properties of what `providers.yaml` declares, so these
    tests read the shipped file rather than a stand-in that could drift from it.
    """
    (tmp_path / "graph.yaml").write_text("nodes: []\nedges: []\n", encoding="utf-8")
    (tmp_path / "providers.yaml").write_text(
        (ROOT / "providers.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )


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


def test_each_challenge_reads_every_artifact_from_its_declared_producer():
    """A gate cannot review reproduction fields it never receives.

    The graph already carried ``frozen_protocol`` from u05 to T1 when the gate
    input list accidentally omitted it. Keep producer handoffs and challenge
    decision boundaries aligned.
    """
    kit = load_kit(ROOT)
    for gate in kit.gates.values():
        if gate.kind != "challenge" or gate.producer is None:
            continue
        produced = set(kit.graph.node(gate.producer).produces)
        assert produced <= set(gate.inputs), (gate.id, produced, set(gate.inputs))


def test_scalar_carries_is_normalised_to_a_tuple():
    kit = load_kit(ROOT)
    edge = next(e for e in kit.graph.edges if e.frm == "E1" and e.to == "u01")
    assert edge.kind == "return"
    assert edge.carries == ("evidence_gap",)
    assert edge.budget == 3


def test_providers_and_capabilities():
    kit = load_kit(ROOT)
    assert kit.providers["codex"].exec_argv == (
        "codex", "exec", "-c", "model={model}", "{effort_argv}", "-")
    assert kit.providers["grok"].kind == "web"
    assert kit.providers["grok"].capabilities == frozenset({"read_files", "manual"})
    assert kit.providers["claude-code"].default_model == "claude-sonnet-5"
    assert kit.providers["claude-code"].role_models["planning"] == "claude-opus-5"
    assert kit.providers["codex"].models == (
        "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna",
    )
    assert kit.providers["codex"].aliases == ("openai",)
    assert "mistral" in kit.provider_candidates


def test_assignment_identity_substitutes_the_model():
    kit = load_kit(ROOT, assignment="assignment.example.yaml")
    assert sorted(kit.assignment) == sorted(ROLES)
    assert kit.assignment["verification"].identity(kit.providers) == "codex/gpt-5.6-terra"


def test_effort_stays_out_of_the_identity():
    """Separation asks for a second opinion; the same model thinking longer is not one."""
    kit = load_kit(ROOT)
    deep = Assignment("verification", "codex", "gpt-5.6-terra", "xhigh")
    shallow = Assignment("execution", "codex", "gpt-5.6-terra")
    assert deep.identity(kit.providers) == shallow.identity(kit.providers)


def test_an_effort_the_command_line_would_swallow_is_refused(tmp_path):
    """grok has nowhere to put an effort, so naming one fails loudly rather than silently."""
    _minimal_kit_files(tmp_path)
    (tmp_path / "assignment.yaml").write_text(
        "reviewer: {provider: grok, model: grok-5, effort: high}\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="takes no effort setting"):
        load_kit(tmp_path)


def test_an_effort_the_provider_does_not_list_is_refused(tmp_path):
    """`ultra` is a codex level; typing it at claude would be dropped without this."""
    _minimal_kit_files(tmp_path)
    (tmp_path / "assignment.yaml").write_text(
        "planning: {provider: claude-code, model: claude-opus-5, effort: ultra}\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="does not list effort"):
        load_kit(tmp_path)


def test_unknown_node_kind_is_rejected(tmp_path):
    (tmp_path / "graph.yaml").write_text("nodes:\n  - {id: x, kind: wizard}\nedges: []\n")
    (tmp_path / "providers.yaml").write_text("codex: {kind: cli, invoke: codex}\n")
    with pytest.raises(ConfigError, match="unknown node kind 'wizard'"):
        load_kit(tmp_path)


def test_unknown_check_name_in_gates_is_rejected(tmp_path):
    """A check nobody can run must fail at load rather than pass at the gate.

    `evaluate_gate` skips a name it does not recognise, so one dropped letter in
    `gates.yaml` used to disable that gate's content check and still report PASS.
    """
    _minimal_kit_files(tmp_path)
    (tmp_path / "graph.yaml").write_text(
        "nodes:\n  - {id: M1, kind: gate, gate: challenge}\nedges: []\n", encoding="utf-8"
    )
    (tmp_path / "gates.yaml").write_text(
        "M1:\n"
        "  kind: challenge\n"
        "  owner: reviewer\n"
        "  checks: [presence, schema, claim_suport]\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="unknown check 'claim_suport'"):
        load_kit(tmp_path)


def test_every_check_the_reference_gates_name_can_be_run():
    """The shipped gates.yaml must name only checks that exist."""
    load_kit(ROOT)


def test_edge_to_missing_node_is_rejected(tmp_path):
    (tmp_path / "graph.yaml").write_text(
        "nodes:\n  - {id: a, kind: agent}\nedges:\n  - {from: a, to: ghost, kind: handoff}\n"
    )
    (tmp_path / "providers.yaml").write_text("codex: {kind: cli, invoke: codex}\n")
    with pytest.raises(ConfigError, match="edge a -> ghost: unknown node 'ghost'"):
        load_kit(tmp_path)
