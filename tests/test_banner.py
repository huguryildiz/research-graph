from rgraph import __version__
from rgraph.banner import render_banner


def test_full_banner_fits_an_80_column_terminal():
    for line in render_banner().splitlines():
        assert len(line) <= 78, line


def test_compact_banner_fits_a_40_column_terminal():
    for line in render_banner(compact=True).splitlines():
        assert len(line) <= 40, line


def test_full_banner_carries_the_tagline():
    assert "contract-gated agentic research" in render_banner()


def test_full_banner_states_no_version():
    assert __version__ not in render_banner()


def test_full_banner_carries_the_provenance_and_revision_spines():
    out = render_banner()
    assert "●──●──◆" in out
    assert "╰────↺" in out


def test_full_banner_carries_both_cell_grid_wordmarks():
    out = render_banner()
    assert out.count("▉▉▉") >= 8
    assert len(out.splitlines()) >= 18


def test_compact_banner_is_the_wordmark_alone():
    assert "contract-gated" not in render_banner(compact=True)
    assert "◆  research-graph" in render_banner(compact=True)
