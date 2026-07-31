"""Local links must be relative, so the page also works from file:// and a subpath."""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_no_local_link_is_root_absolute():
    for name in ("index.html", "architecture.html"):
        text = (ROOT / name).read_text(encoding="utf-8")
        offenders = re.findall(r'(?:href|src)\s*=\s*"(/[^/][^"]*)"', text)
        assert offenders == [], (name, offenders)


def test_every_local_link_target_exists():
    text = (ROOT / "index.html").read_text(encoding="utf-8")
    for target in re.findall(r'href\s*=\s*"([^"#:]+\.html)"', text):
        assert (ROOT / target).exists(), target
