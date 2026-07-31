from rgraph.banner import render_banner


def test_full_banner_fits_an_80_column_terminal():
    for line in render_banner().splitlines():
        assert len(line) <= 78, line


def test_compact_banner_fits_a_40_column_terminal():
    for line in render_banner(compact=True).splitlines():
        assert len(line) <= 40, line


def test_full_banner_carries_the_thesis_motif_and_version():
    out = render_banner()
    assert "○──▶○──▶◆──▶○──▶◆" in out
    assert "contract-gated agentic research" in out
    assert "v0.1.0 · graph engineering, verified" in out


def test_compact_banner_has_no_motif():
    assert "○──▶" not in render_banner(compact=True)
