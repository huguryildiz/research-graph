"""Local links must be relative, so the page also works from file:// and a subpath."""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
PUBLIC_HTML = ("index.html", "architecture.html", "reference-run.html")


def test_no_local_link_is_root_absolute():
    for name in PUBLIC_HTML:
        text = (ROOT / name).read_text(encoding="utf-8")
        offenders = re.findall(r'(?:href|src)\s*=\s*"(/[^/][^"]*)"', text)
        assert offenders == [], (name, offenders)


def test_every_local_link_target_exists():
    for name in PUBLIC_HTML:
        text = (ROOT / name).read_text(encoding="utf-8")
        for target in re.findall(r'href\s*=\s*"([^"#:]+\.html)"', text):
            assert (ROOT / target).exists(), (name, target)


def test_vercel_deploys_every_public_page():
    allowlist = {
        line.strip()
        for line in (ROOT / ".vercelignore").read_text(encoding="utf-8").splitlines()
        if line.startswith("!")
    }
    for name in PUBLIC_HTML:
        assert f"!{name}" in allowlist, name


def test_public_quickstarts_lead_with_the_plain_language_demo():
    for name in ("README.md", "index.html"):
        text = (ROOT / name).read_text(encoding="utf-8")
        first_demo = text.index("rgraph demo")
        assert text[first_demo:].startswith("rgraph demo"), name


def test_readme_has_platform_specific_environment_paths():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "source .venv/bin/activate" in text
    assert ".venv\\Scripts\\Activate.ps1" in text
    assert ".venv\\Scripts\\activate.bat" in text


def test_a_gate_screen_in_the_docs_never_drops_the_claim_boundary():
    """The README shows a gate screen to say what a gate does. An abridged one
    that leaves out the line every gate screen prints argues the opposite of the
    paragraph beneath it, and reads as the tool having judged the science."""
    from rgraph.render import CLAIM_BOUNDARY_LINE

    text = (ROOT / "README.md").read_text(encoding="utf-8")
    screens = re.findall(r"```\n(GATE .+?)```", text, re.S)
    assert screens, "the README no longer shows a gate screen"
    for screen in screens:
        assert CLAIM_BOUNDARY_LINE.strip() in screen, screen


def test_architecture_does_not_present_separation_as_independence():
    text = (ROOT / "architecture.html").read_text(encoding="utf-8").lower()
    assert "independent review role" not in text
    assert "independent actor" not in text
    assert "separate review role" in text


def test_landing_page_links_to_redacted_real_run():
    text = (ROOT / "index.html").read_text(encoding="utf-8")
    assert 'href="reference-run.html"' in text
    assert ">Inspect a real run</a>" in text


def test_reference_run_page_preserves_evidence_boundary_and_redaction():
    text = (ROOT / "reference-run.html").read_text(encoding="utf-8")
    assert "rg-20260802-001" in text
    assert "12 / 12" in text
    assert "21" in text
    assert "HISTORICAL / PARTIAL" in text.upper()
    assert "does not establish scientific correctness" in text
    assert "not a qualification run for the current release" in text
    assert "/Users/" not in text
    assert "Hüseyin Uğur Yıldız" not in text
