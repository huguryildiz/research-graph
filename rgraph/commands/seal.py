"""`rgraph seal` — stamp hand-authored artifacts so their digests are true.

A human writes `problem_spec` and `governance_record`, and no human can compute a
canonical SHA-256 by hand. Sealing recomputes each artifact's `content_hash` from
its own body and refreshes the `inputs[]` hashes from what the run holds today.

It changes digests, never content. An artifact whose body you have not touched
seals to the same hash it already had, so running it twice is a no-op.
"""

from __future__ import annotations

import json

from rgraph.config import ARTIFACTS, ConfigError
from rgraph.hashing import content_hash
from rgraph.render import console
from rgraph.run import RunError


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "seal", help="recompute content_hash for hand-authored artifacts"
    )
    parser.add_argument(
        "artifact", nargs="*",
        help="artifact ids to seal; default is every artifact present in the run",
    )
    parser.set_defaults(handler=handle)


def seal_document(document: dict, current: dict[str, str]) -> tuple[dict, list[str]]:
    """Return the sealed document and a note per field that moved."""
    changes: list[str] = []
    for reference in document.get("inputs", []):
        upstream = current.get(reference.get("artifact_id"))
        if upstream and reference.get("content_hash") != upstream:
            changes.append(f"input {reference['artifact_id']} -> {upstream[:19]}...")
            reference["content_hash"] = upstream
    digest = content_hash(document.get("body", {}))
    if document.get("content_hash") != digest:
        changes.append(f"content_hash -> {digest[:19]}...")
        document["content_hash"] = digest
    return document, changes


def handle(args) -> int:
    from rgraph.commands.check import load_for_run

    try:
        _, run = load_for_run(args)
    except (ConfigError, RunError) as exc:
        print(f"error: {exc}")
        return 2

    wanted = args.artifact or [a.id for a in run.artifacts.values() if a.present]
    unknown = [a for a in wanted if a not in ARTIFACTS]
    if unknown:
        print(f"error: unknown artifact(s): {', '.join(unknown)}")
        return 2

    # Seal in dependency order so an upstream digest is final before anything
    # downstream copies it. ARTIFACTS is already in production order.
    ordered = [a for a in ARTIFACTS if a in set(wanted)]
    current: dict[str, str] = {
        a.id: a.content_hash for a in run.artifacts.values()
        if a.present and a.content_hash
    }

    sealed = 0
    for artifact_id in ordered:
        artifact = run.artifacts.get(artifact_id)
        if artifact is None or not artifact.present:
            console.print(f"  {artifact_id:<24}not in this run")
            continue
        try:
            document = json.loads(artifact.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"error: {artifact.path} is not valid JSON: {exc}")
            return 2
        document, changes = seal_document(document, current)
        current[artifact_id] = document["content_hash"]
        if not changes:
            console.print(f"  {artifact_id:<24}already sealed")
            continue
        artifact.path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        sealed += 1
        console.print(f"  {artifact_id:<24}{changes[0]}")
        for note in changes[1:]:
            console.print(f"  {'':<24}{note}")

    console.print()
    console.print(f"Sealed {sealed} artifact(s).")
    if sealed:
        console.print()
        console.print("Run next:")
        console.print("  rgraph status")
    return 0
