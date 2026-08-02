"""`rgraph trace <claim>` — the chain from a manuscript claim to raw data."""

from __future__ import annotations


from rgraph.config import ConfigError
from rgraph.interactive import InteractionCancelled, choose, is_terminal
from rgraph.provenance import trace
from rgraph.render import console, render_provenance_notice, render_trace
from rgraph.run import RunError


def register(subparsers) -> None:
    parser = subparsers.add_parser("trace", help="follow a claim down to raw data")
    parser.add_argument("claim", nargs="?", help="claim id, e.g. c-03; omit for a menu")
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
    claim_id = args.claim
    claims = run.get("claim_evidence_map").body.get("claims", [])
    if claim_id is None:
        if not claims:
            console.print("There are no claims to trace yet.")
            console.print("Run `rgraph status` to see the next action.")
            return 1
        if not is_terminal():
            expected = ", ".join(item["claim_id"] for item in claims)
            print(f"error: choose a claim: rgraph trace <CLAIM> ({expected})")
            return 2
        try:
            claim_id = choose(
                "Which claim would you like to trace?",
                [(item["claim_id"], f"{item['claim_id']} — {item['text']}") for item in claims],
                allow_cancel=True,
            )
        except InteractionCancelled:
            claim_id = None
        if claim_id is None:
            console.print("Stopped.")
            return 0
    chain = trace(run, kit, claim_id)
    claim = next(
        (c for c in run.get("claim_evidence_map").body.get("claims", [])
         if c["claim_id"] == claim_id),
        None,
    )
    if claim is None:
        print(f"CLAIM {claim_id}")
        print(f"  {claim_id} is not in claim_evidence_map")
        print("  Run next:  rgraph status")
        return 1
    render_trace(chain, claim["text"])
    console.print()
    console.print("Run next:")
    console.print("  rgraph status")
    return 0 if chain.complete else 1
