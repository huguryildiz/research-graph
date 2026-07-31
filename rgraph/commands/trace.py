"""`rgraph trace <claim>` — the chain from a manuscript claim to raw data."""

from __future__ import annotations

import pathlib

from rgraph.config import ConfigError
from rgraph.provenance import trace
from rgraph.render import render_provenance_notice, render_trace
from rgraph.run import RunError, load_run


def register(subparsers) -> None:
    parser = subparsers.add_parser("trace", help="follow a claim down to raw data")
    parser.add_argument("claim", help="claim id, e.g. c-03")
    parser.set_defaults(handler=handle)


def handle(args) -> int:
    from rgraph.commands.check import load

    try:
        kit = load(args)
        run = load_run(pathlib.Path(args.run), kit)
    except (ConfigError, RunError) as exc:
        print(f"error: {exc}")
        return 2
    render_provenance_notice(run)
    chain = trace(run, kit, args.claim)
    claim = next(
        (c for c in run.get("claim_evidence_map").body.get("claims", [])
         if c["claim_id"] == args.claim),
        None,
    )
    if claim is None:
        print(f"CLAIM {args.claim}")
        print(f"  {args.claim} is not in claim_evidence_map")
        return 1
    render_trace(chain, claim["text"])
    return 0 if chain.complete else 1
