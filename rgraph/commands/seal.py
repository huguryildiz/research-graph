"""`rgraph seal` — stamp hand-authored artifacts so their digests are true.

A human writes `problem_spec` and `governance_record`, and no human can compute a
canonical SHA-256 by hand. Sealing recomputes each artifact's `content_hash` from
its own body, refreshes the `inputs[]` hashes from what the run holds today, and
re-digests the payload file of any artifact that points at one.

It changes digests, never content. An artifact whose body you have not touched
seals to the same hash it already had, so running it twice is a no-op.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

from rgraph.config import ARTIFACTS, ConfigError
from rgraph.hashing import document_hash
from rgraph.render import (
    MAIN_STYLE, console, muted, render_error, render_next_action, section, table_row,
)
from rgraph.run import RunError


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "seal",
        help="recompute content_hash for hand-authored artifacts",
        description=(
            "Refresh provenance hashes after an intentional hand edit. Content is "
            "not rewritten."
        ),
        epilog=(
            "Examples:\n"
            "  rgraph seal\n"
            "  rgraph seal problem_spec governance_record"
        ),
    )
    parser.add_argument(
        "artifact", nargs="*",
        help="artifact ids to seal; default is every artifact present in the run",
    )
    parser.set_defaults(handler=handle)


def seal_document(
    document: dict, current: dict[str, str], payload: pathlib.Path | None = None
) -> tuple[dict, list[str]]:
    """Return the sealed document and a note per field that moved.

    An artifact whose body is a pointer to a payload file -- `manuscript`,
    `raw_results` -- carries that file's digest inside the body. Sealing the
    body without refreshing the pointer first would compute a true hash of a
    stale claim, which is the one failure this command must not have: hand
    editing the payload is exactly why `seal` exists.
    """
    changes: list[str] = []
    for reference in document.get("inputs", []):
        upstream = current.get(reference.get("artifact_id"))
        if upstream and reference.get("content_hash") != upstream:
            changes.append(f"input {reference['artifact_id']} -> {upstream[:19]}...")
            reference["content_hash"] = upstream
    body = document.get("body", {})
    if payload is not None and payload.exists() and "payload_sha256" in body:
        actual = hashlib.sha256(payload.read_bytes()).hexdigest()
        if body["payload_sha256"] != actual:
            changes.append(f"payload {payload.name} -> {actual[:12]}...")
            body["payload_sha256"] = actual
    digest = document_hash(document)
    if document.get("content_hash") != digest:
        changes.append(f"content_hash -> {digest[:19]}...")
        document["content_hash"] = digest
    return document, changes


def handle(args) -> int:
    from rgraph.commands.check import load_for_run

    try:
        _, run = load_for_run(args)
    except (ConfigError, RunError) as exc:
        render_error(str(exc))
        return 2

    wanted = args.artifact or [a.id for a in run.artifacts.values() if a.present]
    unknown = [a for a in wanted if a not in ARTIFACTS]
    if unknown:
        render_error(f"unknown artifact(s): {', '.join(unknown)}")
        return 2

    # Seal in dependency order so an upstream digest is final before anything
    # downstream copies it. ARTIFACTS is already in production order.
    ordered = [a for a in ARTIFACTS if a in set(wanted)]
    current: dict[str, str] = {
        a.id: a.content_hash for a in run.artifacts.values()
        if a.present and a.content_hash
    }

    sealed = 0
    section("Artifacts")
    for artifact_id in ordered:
        artifact = run.artifacts.get(artifact_id)
        if artifact is None or not artifact.present:
            table_row(artifact_id, "not in this run", width=26)
            continue
        try:
            document = json.loads(artifact.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            render_error(f"{artifact.path} is not valid JSON: {exc}")
            return 2
        document, changes = seal_document(document, current, artifact.payload_path)
        current[artifact_id] = document["content_hash"]
        if not changes:
            table_row(artifact_id, "already sealed", width=26)
            continue
        if run.refuse_write(f"{artifact_id}.json"):
            return 0
        artifact.path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        sealed += 1
        table_row(artifact_id, changes[0], width=26, value_style=MAIN_STYLE)
        for note in changes[1:]:
            muted(note, indent=" " * 30)

    # meta.json holds the revision budget, so it is sealed alongside the
    # artifacts rather than left as the one unsigned file in the run.
    stale_meta = run.meta_mismatch is not None or "content_hash" not in run.meta
    if not args.artifact and stale_meta:
        if not run.refuse_write("meta.json"):
            run.save_meta()
            sealed += 1
            table_row(
                "meta.json", f"content_hash -> {run.meta['content_hash'][:19]}...",
                width=26, value_style=MAIN_STYLE,
            )

    console.print()
    section("Seal result")
    table_row("sealed", f"{sealed} artifact(s)", value_style=MAIN_STYLE)
    if sealed:
        console.print()
        render_next_action("rgraph status")
    return 0
