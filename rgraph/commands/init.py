"""`rgraph init` — create a run directory you can actually take to the first gate.

`template-run/` holds the shape. What a newcomer also needs is the two artifacts
no agent produces: `problem_spec` and `governance_record` are written by the
human, and gate H1 will not open without them. This writes both as filled-in
skeletons, sealed, so `rgraph check H1` fails on content you have not edited yet
rather than on a file you did not know to create.
"""

from __future__ import annotations

import datetime as _dt
import json
import pathlib
import shutil

from rgraph.hashing import content_hash
from rgraph.render import console

PLACEHOLDER = "Replace this with the research question."


def register(subparsers) -> None:
    parser = subparsers.add_parser("init", help="create run/ from the template")
    parser.add_argument("--force", action="store_true", help="overwrite an existing run/")
    parser.set_defaults(handler=handle)


def _envelope(artifact_id: str, body: dict, when: str) -> dict:
    return {
        "artifact_id": artifact_id,
        "version": 1,
        "produced_by": {"role": "human", "identity": "human/manual"},
        "produced_at": when,
        "inputs": [],
        "content_hash": content_hash(body),
        "body": body,
    }


def _problem_spec(when: str) -> dict:
    return _envelope("problem_spec", {
        "question": PLACEHOLDER,
        "scope": {
            "in_scope": ["Replace with what this study covers."],
            "out_of_scope": ["Replace with what this study deliberately excludes."],
        },
        "constraints": ["Replace with a real constraint: compute, data, time."],
        "success_criteria": ["Replace with what would count as an answer."],
        "mode": "GUIDED",
    }, when)


def _governance_record(when: str) -> dict:
    return _envelope("governance_record", {
        "ethics_applicable": False,
        "ethics_reference": None,
        "data_governance": ["Replace with where the data comes from and what governs it."],
        "legal_notes": ["Replace with licence and third-party terms, or state there are none."],
        "approvals": [{"name": "Replace with the approving name", "date": when[:10]}],
    }, when)


def handle(args) -> int:
    root = pathlib.Path(args.root)
    template = root / "template-run"
    target = pathlib.Path(args.run)

    if not (template / "meta.json").exists():
        print(f"error: {template}/ is missing from this checkout")
        return 2
    if target.exists() and not args.force:
        print(f"error: {target}/ already exists; pass --force to replace it")
        return 2
    if target.exists():
        shutil.rmtree(target)

    shutil.copytree(template, target)
    when = (
        _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
        .isoformat().replace("+00:00", "Z")
    )
    for artifact_id, document in (
        ("problem_spec", _problem_spec(when)),
        ("governance_record", _governance_record(when)),
    ):
        (target / f"{artifact_id}.json").write_text(
            json.dumps(document, indent=2) + "\n", encoding="utf-8"
        )

    console.print(f"Created {target}/ with problem_spec.json and governance_record.json.")
    console.print()
    console.print("Edit these three, then seal and check:")
    console.print(f"  {target}/meta.json                 the question and run id")
    console.print(f"  {target}/problem_spec.json         scope, constraints, success criteria")
    console.print(f"  {target}/governance_record.json    ethics, data governance, approvals")
    console.print()
    console.print("Run next:")
    console.print("  rgraph seal")
    console.print("  rgraph check H1")
    return 0
