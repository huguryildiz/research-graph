import json
import pathlib
import re

from rgraph.config import ROLE_REQUIRES, ROLES, load_kit

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _page() -> str:
    return (ROOT / "index.html").read_text(encoding="utf-8")


def test_landing_page_makes_no_external_requests():
    text = (ROOT / "index.html").read_text(encoding="utf-8")
    external = re.findall(r'(?:src|href)\s*=\s*"(https?://[^"]+)"', text)
    assert all("github.com" in url for url in external), external
    assert "git clone" in text


def test_pages_pull_in_no_cdn_asset():
    for name in ("index.html", "architecture.html"):
        text = (ROOT / name).read_text(encoding="utf-8")
        for needle in ("cdn.", "googleapis", "unpkg", "jsdelivr"):
            assert needle not in text, (name, needle)


def test_configurator_knows_every_role():
    text = _page()
    assert "ROLE_REQUIRES" in text
    assert "assignment.yaml" in text
    for role in ROLES:
        assert role in text, role


def test_configurator_capability_table_matches_the_python_one():
    block = re.search(r"const ROLE_REQUIRES\s*=\s*\{(.*?)\};", _page(), re.S).group(1)
    parsed = dict(
        (role, sorted(re.findall(r'"([a-z_]+)"', caps)))
        for role, caps in re.findall(r"(\w+):\s*\[([^\]]*)\]", block)
    )
    assert parsed == {role: sorted(caps) for role, caps in ROLE_REQUIRES.items()}


def test_configurator_provider_capabilities_match_providers_yaml():
    block = re.search(r"const PROVIDERS\s*=\s*\{(.*?)\n  \};", _page(), re.S).group(1)
    parsed = {}
    for provider, caps in re.findall(r'"([\w-]+)":\s*\{[^}]*caps:\s*\[([^\]]*)\]', block):
        parsed[provider] = sorted(re.findall(r'"([a-z_]+)"', caps))
    kit = load_kit(ROOT)
    assert parsed == {p.id: sorted(p.capabilities) for p in kit.providers.values()}


def test_configurator_blocks_web_providers_for_shell_roles():
    block = re.search(r"const ROLE_REQUIRES\s*=\s*\{(.*?)\};", _page(), re.S).group(1)
    assert "shell" in block
    assert "execution:" in block


def test_configurator_carries_the_context_only_caveat():
    text = _page()
    assert "CONTEXT ONLY" in text
    assert "Correlated errors may remain." in text


def test_vercel_config_is_valid_json_and_serves_clean_urls():
    config = json.loads((ROOT / "vercel.json").read_text())
    assert config["cleanUrls"] is True
