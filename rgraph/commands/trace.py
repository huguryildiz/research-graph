"""`rgraph trace <claim>` — the chain from a manuscript claim to raw data."""

from __future__ import annotations


from rgraph.config import ConfigError
from rgraph.provenance import trace
from rgraph.render import render_provenance_notice, render_trace
from rgraph.run import RunError


def register(subparsers) -> None:
    parser = subparsers.add_parser("trace", help="follow a claim down to raw data")
    parser.add_argument("claim", help="claim id, e.g. c-03")
    parser.set_defaults(handler=handle)


def handle(args) -> int:
    from rgraph.commands.check import load_for_run

    try:
        kit, run = load_for_run(args)
    except (ConfigError, RunError) as exc:
        print(f"error: {exc}")
        return 2
    render_provenance_notice(run)
    for artifact_id in (
        "claim_evidence_map", "manuscript", "statistical_report",
        "raw_results", "run_manifest",
    ):
        artifact = run.get(artifact_id)
        if artifact.present and artifact.errors:
            first = artifact.errors[0]
            print(f"error: {artifact_id} is invalid: {first.path}: {first.message}")
            return 2
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
