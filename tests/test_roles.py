import pathlib
import re

from rgraph.config import ROLE_REQUIRES, ROLES, load_kit
from rgraph.yamlmini import loads

ROOT = pathlib.Path(__file__).resolve().parents[1]
SECTIONS = ("## Role", "## Inputs", "## Outputs", "## Required fields",
            "## Acceptance criterion", "## Revision budget", "## Claim boundary")


def _text(role: str) -> str:
    return (ROOT / "roles" / f"{role}.md").read_text(encoding="utf-8")


def _frontmatter(text: str):
    return loads(re.match(r"^---\n(.*?)\n---\n", text, re.S).group(1))


def test_every_role_file_exists_and_has_all_sections():
    for role in ROLES:
        text = _text(role)
        for section in SECTIONS:
            assert section in text, (role, section)


def test_frontmatter_requires_matches_the_capability_table():
    for role in ROLES:
        meta = _frontmatter(_text(role))
        assert set(meta["requires"]) == set(ROLE_REQUIRES[role]), role


def test_frontmatter_produces_matches_the_graph():
    kit = load_kit(ROOT)
    for role in ROLES:
        meta = _frontmatter(_text(role))
        expected = sorted(
            artifact
            for node in kit.graph.nodes.values() if node.role_name == role
            for artifact in node.produces
        )
        assert sorted(meta["produces"] or []) == expected, role


def test_frontmatter_units_match_the_graph():
    kit = load_kit(ROOT)
    for role in ROLES:
        meta = _frontmatter(_text(role))
        expected = sorted(n.id for n in kit.graph.units() if n.role_name == role)
        assert sorted(meta["units"] or []) == expected, role


def test_every_role_carries_the_claim_boundary():
    for role in ROLES:
        assert "does not establish scientific correctness" in _text(role).lower()


def test_role_files_are_english_only():
    turkish = set("çğıöşüÇĞİÖŞÜ")
    for role in ROLES:
        assert not (turkish & set(_text(role))), role


def test_retrieval_role_preserves_source_native_technical_categories():
    text = _text("retrieval")
    assert "meta-estimator" in text
    assert "do not relabel" in text


def test_reviewer_checks_source_native_technical_categories():
    text = _text("reviewer")
    assert "meta-estimator" in text
    assert "may not be relabelled" in text
