from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

from rgraph.cli import main
import rgraph.render as render


def test_version_flag_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "0.4.0" in capsys.readouterr().out


@pytest.mark.parametrize("port", ("-1", "0", "99999", "abc"))
def test_ui_rejects_invalid_ports_as_usage_errors(port, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--no-banner", "ui", "--port", port, "--no-open"])
    assert exc.value.code == 2
    assert "Traceback" not in capsys.readouterr().err


def test_bare_invocation_prints_banner(capsys):
    assert main([]) == 0
    assert "contract-gated agentic research" in capsys.readouterr().out


def test_no_banner_flag_suppresses_it(capsys):
    assert main(["--no-banner"]) == 0
    assert "contract-gated" not in capsys.readouterr().out


def test_bare_first_use_leads_with_the_plain_language_demo(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["--no-banner"]) == 0
    out = capsys.readouterr().out
    assert "$ rgraph demo" in out
    assert "rgraph setup" in out and "rgraph init" in out


def test_help_names_the_demo_start_and_own_study_paths(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "Start here:  rgraph demo" in out
    assert "Own study:   rgraph setup, then rgraph init" in out


def test_help_uses_the_shared_terminal_hierarchy(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert out.startswith("USAGE\n    rgraph")
    assert "\nCOMMANDS\n" in out
    assert "\nOPTIONS\n" in out


def test_subcommand_help_calls_positional_values_arguments(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["check", "--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "\nARGUMENTS\n" in out
    assert "\nCOMMANDS\n" not in out


@pytest.mark.parametrize(
    "command",
    ("demo", "setup", "init", "status", "next", "seal", "check", "decide",
     "revise", "trace", "review"),
)
def test_every_subcommand_help_is_task_focused(command, capsys):
    with pytest.raises(SystemExit) as exc:
        main([command, "--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "\nEXAMPLES\n" in out
    assert f"rgraph {command}" in out


def test_home_applies_the_reference_terminal_palette(monkeypatch):
    sink = StringIO()
    styled = Console(
        file=sink,
        force_terminal=True,
        color_system="truecolor",
        no_color=False,
        width=80,
        highlight=False,
        soft_wrap=False,
        style=render.BODY_STYLE,
    )
    monkeypatch.setattr(render, "console", styled)

    render.render_home(Path("run"), True)

    out = sink.getvalue()
    assert "38;2;148;163;184mACTIVE RUN" in out  # slate section heading
    assert "38;2;229;231;235m    run" in out     # primary text
    assert "38;2;138;138;138m    Existing" in out  # muted body, AA on #1f1f1f
    assert "38;2;79;169;139mrgraph --run run status" in out  # emerald action


def test_unknown_command_exits_two_and_points_to_help(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["nosuchcommand"])
    assert exc.value.code == 2
    assert "Run next:  rgraph --help" in capsys.readouterr().err
