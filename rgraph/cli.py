"""Command dispatch. Exit codes: 0 pass, 1 fail, 2 usage/config error."""

from __future__ import annotations

import argparse
import pathlib
import shutil
import sys

from rgraph import __version__
from rgraph.banner import render_banner

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

BANNER_COMMANDS = frozenset({"setup"})


def default_root() -> str:
    """Where to look for graph.yaml when nobody said.

    A checkout you are standing in wins, because that is the copy you edit. Off
    a checkout, the wheel carries its own, so `pip install research-graph` gives
    a working command rather than one that only starts.
    """
    if pathlib.Path("graph.yaml").exists():
        return "."
    packaged = pathlib.Path(__file__).resolve().parent / "kit"
    return str(packaged) if (packaged / "graph.yaml").exists() else "."


class _WithCommonFlags:
    """Passes the global flags down to every subparser that registers itself."""

    def __init__(self, inner, common: argparse.ArgumentParser):
        self._inner = inner
        self._common = common

    def add_parser(self, name: str, **kwargs):
        kwargs.setdefault("parents", [self._common])
        return self._inner.add_parser(name, **kwargs)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rgraph",
        description="Graph engineering, verified.",
        add_help=True,
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--no-banner", action="store_true", help="never print the banner")
    parser.add_argument("--verbose", action="store_true", help="echo provider logs to stdout")
    parser.add_argument("--run", default="run", metavar="DIR", help="run directory (default: run)")
    parser.add_argument("--root", default=default_root(), metavar="DIR",
                        help="kit root holding the YAML config (default: cwd, else the packaged copy)")

    # The same flags again on every subcommand, so `rgraph status --run X` works
    # as readily as `rgraph --run X status`. SUPPRESS keeps an unused copy from
    # overwriting what the main parser already read.
    common = argparse.ArgumentParser(add_help=False)
    for flag, action in (("--no-banner", "store_true"), ("--verbose", "store_true")):
        common.add_argument(flag, action=action, default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    for flag in ("--run", "--root"):
        common.add_argument(flag, metavar="DIR", default=argparse.SUPPRESS, help=argparse.SUPPRESS)

    subparsers = _WithCommonFlags(parser.add_subparsers(dest="command", metavar="COMMAND"), common)

    from rgraph.commands import (
        check as check_cmd,
        demo as demo_cmd,
        init as init_cmd,
        next_ as next_cmd,
        review as review_cmd,
        revise as revise_cmd,
        seal as seal_cmd,
        setup as setup_cmd,
        status as status_cmd,
        trace as trace_cmd,
    )

    for module in (demo_cmd, setup_cmd, init_cmd, status_cmd, next_cmd,
                   seal_cmd, check_cmd, revise_cmd, trace_cmd, review_cmd):
        module.register(subparsers)
    return parser


def _print_banner(args: argparse.Namespace) -> None:
    if args.no_banner:
        return
    compact = shutil.get_terminal_size((80, 24)).columns < 52
    print(render_banner(compact=compact))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        _print_banner(args)
        parser.print_help()
        return EXIT_OK
    if args.command in BANNER_COMMANDS:
        _print_banner(args)
    handler = getattr(args, "handler", None)
    if handler is None:  # pragma: no cover - guarded by argparse
        parser.error(f"unknown command: {args.command}")
    try:
        return handler(args)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
