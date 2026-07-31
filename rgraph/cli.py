"""Command dispatch. Exit codes: 0 pass, 1 fail, 2 usage/config error."""

from __future__ import annotations

import argparse
import shutil
import sys

from rgraph import __version__
from rgraph.banner import render_banner

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

BANNER_COMMANDS = frozenset({"setup"})


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
    parser.add_argument("--root", default=".", metavar="DIR", help="kit root holding the YAML config")
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    from rgraph.commands import check as check_cmd

    check_cmd.register(subparsers)
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
