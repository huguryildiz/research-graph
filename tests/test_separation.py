import pathlib

import pytest

from rgraph.config import Assignment, load_kit
from rgraph.separation import CONTEXT_ONLY_NOTE, evaluate, level_for, rank

ROOT = pathlib.Path(__file__).resolve().parents[1]

CLAUDE_SONNET = Assignment("execution", "claude-code", "sonnet-5")
CLAUDE_OPUS = Assignment("planning", "claude-code", "opus-5")
CLAUDE_SONNET_REVIEW = Assignment("reviewer", "claude-code", "sonnet-5")
CODEX = Assignment("reviewer", "codex", "gpt-5.6")


@pytest.mark.parametrize(
    "producer, reviewer, expected",
    [
        (CLAUDE_SONNET, CLAUDE_SONNET_REVIEW, "context_only"),
        (CLAUDE_SONNET, CLAUDE_OPUS, "separate_model"),
        (CLAUDE_SONNET, CODEX, "separate_provider"),
    ],
)
def test_level_for(producer, reviewer, expected):
    assert level_for(producer, reviewer) == expected


def test_rank_is_ordered():
    assert rank("context_only") < rank("separate_model") < rank("separate_provider")


def test_context_only_note_is_the_spec_text():
    assert CONTEXT_ONLY_NOTE == (
        "Reviewer uses a separate session, but the same model\n"
        "and provider. Correlated errors may remain."
    )


def test_below_preferred_is_a_caveat_not_a_failure():
    gate = load_kit(ROOT).gates["M1"]
    verdict = evaluate(gate, CLAUDE_SONNET, CLAUDE_SONNET_REVIEW)
    assert verdict.level == "context_only"
    assert verdict.status == "CAVEAT"
    assert verdict.note == CONTEXT_ONLY_NOTE


def test_meeting_preferred_passes_without_a_note():
    gate = load_kit(ROOT).gates["M1"]
    verdict = evaluate(gate, CLAUDE_SONNET, CODEX)
    assert verdict.status == "PASS"
    assert verdict.note is None


def test_human_gates_have_no_separation_requirement():
    gate = load_kit(ROOT).gates["H2"]
    assert gate.separation_required is None
    assert evaluate(gate, None, None).status == "PASS"


def test_gates_yaml_inputs_are_all_known_artifacts():
    kit = load_kit(ROOT)
    assert len(kit.gates) == 10
    for gate in kit.gates.values():
        for artifact in gate.inputs:
            assert kit.graph.producer_of(artifact) is not None, (gate.id, artifact)
