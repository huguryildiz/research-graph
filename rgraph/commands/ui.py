"""`rgraph ui` — open the local evidence desk in a browser."""

from __future__ import annotations

from rgraph.config import ConfigError
from rgraph.run import RunError
from rgraph.webui.server import serve


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "ui",
        help="manage a run in a local browser",
        description=(
            "Open an offline-first browser interface for status, gates, artifacts, "
            "claim traces, and explicitly approved work-unit execution."
        ),
        epilog=(
            "Examples:\n"
            "  rgraph ui\n"
            "  rgraph ui --run path/to/run\n"
            "  rgraph ui --port 9090 --no-open"
        ),
    )
    parser.add_argument("--host", default="127.0.0.1", help="loopback host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="local port (default: 8765)")
    parser.add_argument("--no-open", action="store_true", help="print the URL without opening a browser")
    parser.set_defaults(handler=handle)


def handle(args) -> int:
    try:
        serve(args.root, args.run, host=args.host, port=args.port, open_browser=not args.no_open)
    except (ConfigError, RunError, OSError, ValueError) as exc:
        print(f"error: {exc}")
        return 2
    return 0
