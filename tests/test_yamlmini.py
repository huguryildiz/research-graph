import pytest

from rgraph.yamlmini import YamlError, loads


def test_block_mapping_and_scalar_types():
    assert loads("a: 1\nb: 2.5\nc: hello\nd: true\ne: null\n") == {
        "a": 1, "b": 2.5, "c": "hello", "d": True, "e": None,
    }


def test_nested_block_mapping():
    assert loads("outer:\n  inner:\n    leaf: 7\n") == {"outer": {"inner": {"leaf": 7}}}


def test_block_sequence_of_flow_mappings():
    text = "nodes:\n  - {id: u01, kind: agent}\n  - {id: E1, kind: gate}\n"
    assert loads(text) == {
        "nodes": [{"id": "u01", "kind": "agent"}, {"id": "E1", "kind": "gate"}]
    }


def test_flow_sequence_inside_flow_mapping():
    text = "n: {id: u01, produces: [a, b, c]}\n"
    assert loads(text) == {"n": {"id": "u01", "produces": ["a", "b", "c"]}}


def test_flow_mapping_may_span_lines():
    text = "n: {id: u01,\n    kind: agent,\n    produces: [a]}\n"
    assert loads(text) == {"n": {"id": "u01", "kind": "agent", "produces": ["a"]}}


def test_quoted_scalar_keeps_special_characters():
    assert loads('a: "codex/{model}"\nb: \'x: y\'\n') == {"a": "codex/{model}", "b": "x: y"}


def test_comments_and_blank_lines_are_ignored():
    assert loads("# top\na: 1  # trailing\n\nb: 2\n") == {"a": 1, "b": 2}


def test_sequence_of_block_mappings():
    text = "items:\n  - id: one\n    v: 1\n  - id: two\n    v: 2\n"
    assert loads(text) == {"items": [{"id": "one", "v": 1}, {"id": "two", "v": 2}]}


@pytest.mark.parametrize(
    "text, needle",
    [
        ("a: &anchor 1\n", "anchor"),
        ("a: *ref\n", "alias"),
        ("a: !!str 1\n", "tag"),
        ("a: |\n  block\n", "block scalar"),
        ("---\na: 1\n", "multi-document"),
        ("a:\n\t- 1\n", "tab"),
    ],
)
def test_unsupported_constructs_are_refused(text, needle):
    with pytest.raises(YamlError) as exc:
        loads(text, source="graph.yaml")
    assert needle in str(exc.value)
    assert "graph.yaml" in str(exc.value)


def test_error_reports_the_line_number():
    with pytest.raises(YamlError) as exc:
        loads("a: 1\nb: {unclosed\n")
    assert exc.value.line == 2
