import json
import pathlib
import re

from rgraph.commands import setup
from rgraph.config import ROLE_REQUIRES, ROLES, load_kit

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _page() -> str:
    return (ROOT / "index.html").read_text(encoding="utf-8")


def test_landing_page_loads_no_external_assets_and_links_only_to_owned_sites():
    text = (ROOT / "index.html").read_text(encoding="utf-8")
    external_assets = re.findall(r'src\s*=\s*"(https?://[^"]+)"', text)
    assert external_assets == []
    external_links = re.findall(r'href\s*=\s*"(https?://[^"]+)"', text)
    allowed = (
        "https://github.com/huguryildiz/research-graph",
        "https://huguryildiz.com/",
    )
    assert all(url.startswith(allowed) for url in external_links), external_links
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


def test_configurator_provider_support_status_matches_providers_yaml():
    kit = load_kit(ROOT)
    assert _table("SUPPORT_STATUS") == {
        provider.id: provider.support_status
        for provider in kit.providers.values()
        if provider.support_status != "configured"
    }
    assert _table("SUPPORT_NOTE") == {
        provider.id: provider.support_note
        for provider in kit.providers.values()
        if provider.support_note
    }
    assert 'SUPPORT_STATUS[provider] === "draft" ? " · DRAFT"' in _page()


def _table(name: str) -> dict[str, str]:
    block = re.search(rf"const {name}\s*=\s*\{{(.*?)\n  \}};", _page(), re.S).group(1)
    return dict(re.findall(r'"?([\w-]+)"?\s*:\s*"([^"]+)"', block))


def test_configurator_offers_the_models_setup_suggests():
    block = re.search(r"const MODELS\s*=\s*\{(.*?)\n  \};", _page(), re.S).group(1)
    parsed = {
        provider: re.findall(r'"([^"]+)"', models)
        for provider, models in re.findall(r'"([\w-]+)":\s*\[([^\]]*)\]', block)
    }
    kit = load_kit(ROOT)
    assert parsed == {provider.id: list(provider.models) for provider in kit.providers.values()}


def test_configurator_defaults_to_the_model_setup_would_pick():
    kit = load_kit(ROOT)
    assert _table("DEFAULT_MODEL") == {
        provider.id: provider.default_model for provider in kit.providers.values()
    }
    assert _table("ROLE_MODEL") == {
        role: model
        for provider in kit.providers.values()
        for role, model in provider.role_models.items()
    }


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
