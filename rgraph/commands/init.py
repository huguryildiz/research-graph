"""`rgraph init` — create a run, guided in a terminal and scriptable in CI."""

from __future__ import annotations

import datetime as _dt
import json
import pathlib
import re
import shutil
import subprocess

from rgraph.hashing import document_hash
from rgraph.interactive import (
    InteractionCancelled, ask_text, choose, confirm, is_terminal, split_items,
)
from rgraph.render import console
from rgraph.yamlmini import YamlError, load_file

PLACEHOLDER = "Replace this with the research question."


def register(subparsers) -> None:
    parser = subparsers.add_parser("init", help="create a guided research run")
    parser.add_argument("--force", action="store_true", help="overwrite an existing run/")
    parser.add_argument("--edit", action="store_true",
                        help="update only the study setup files in an existing run")
    parser.add_argument("--guided", action="store_true",
                        help="prompt for the study details even when stdin is not a TTY")
    parser.add_argument("--from", dest="source", metavar="FILE",
                        help="read study details from a JSON or YAML file")
    parser.set_defaults(handler=handle)


def _envelope(artifact_id: str, body: dict, when: str) -> dict:
    document = {
        "artifact_id": artifact_id,
        "version": 1,
        "produced_by": {"role": "human", "identity": "human/manual"},
        "produced_at": when,
        "inputs": [],
        "body": body,
    }
    document["content_hash"] = document_hash(document)
    return document


def _problem_spec(when: str, body: dict | None = None) -> dict:
    if body is not None:
        return _envelope("problem_spec", body, when)
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


def _governance_record(when: str, body: dict | None = None) -> dict:
    if body is not None:
        return _envelope("governance_record", body, when)
    return _envelope("governance_record", {
        "ethics_applicable": False,
        "ethics_reference": None,
        "data_governance": ["Replace with where the data comes from and what governs it."],
        "legal_notes": ["Replace with licence and third-party terms, or state there are none."],
        "approvals": [{"name": "Replace with the approving name", "date": when[:10]}],
    }, when)


def _git_user_name() -> str:
    try:
        result = subprocess.run(
            ["git", "config", "user.name"], capture_output=True, text=True,
            timeout=3, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip()


def _run_id(when: str) -> str:
    return f"rg-{when[:10].replace('-', '')}-001"


def _guided_details(when: str) -> dict | None:
    console.print("CREATE A RESEARCH RUN")
    console.print("Answer in ordinary language. Use semicolons to list multiple items.")
    console.print("Nothing is written until you approve the summary.")
    console.print()
    try:
        question = ask_text("Research question", required=True)
        in_scope = split_items(ask_text("What is in scope", required=True))
        out_scope = split_items(ask_text("What is deliberately out of scope"))
        constraints = split_items(ask_text(
            "Constraints (data, compute, time, policy)", required=True,
        ))
        success = split_items(ask_text("What would count as success", required=True))
        mode = choose(
            "How should rgraph guide this run?",
            (("GUIDED", "Guided — show the next recommended action"),
             ("MANUAL", "Manual — show status without workflow guidance")),
            default="GUIDED",
        )
        ethics = confirm("Does this study require an ethics approval or exemption?", default=False)
        ethics_reference = (
            ask_text("Ethics approval or exemption reference", required=True) if ethics else None
        )
        data_governance = split_items(ask_text(
            "Where does the data come from, and what rules govern it?", required=True,
        ))
        legal = split_items(ask_text(
            "Licence or third-party restrictions",
            default="No known additional legal restrictions.",
        ))
        approver = ask_text("Responsible person", default=_git_user_name() or None, required=True)
    except InteractionCancelled:
        console.print()
        console.print("Cancelled. No files have been written.")
        return None

    details = {
        "run_id": _run_id(when),
        "question": question,
        "mode": mode,
        "problem": {
            "question": question,
            "scope": {"in_scope": in_scope, "out_of_scope": out_scope},
            "constraints": constraints,
            "success_criteria": success,
            "mode": mode,
        },
        "governance": {
            "ethics_applicable": ethics,
            "ethics_reference": ethics_reference,
            "data_governance": data_governance,
            "legal_notes": legal,
            "approvals": [{"name": approver, "date": when[:10]}],
        },
    }
    console.print()
    console.print("SUMMARY")
    console.print(f"  Run ID       {details['run_id']}")
    console.print(f"  Question     {question}")
    console.print(f"  In scope     {'; '.join(in_scope)}")
    console.print(f"  Success      {'; '.join(success)}")
    console.print(f"  Ethics       {'yes — ' + ethics_reference if ethics else 'not applicable'}")
    console.print(f"  Responsible  {approver}")
    console.print()
    try:
        if not confirm("Create this run?", default=True):
            console.print("Cancelled. No files have been written.")
            return None
    except InteractionCancelled:
        console.print()
        console.print("Cancelled. No files have been written.")
        return None
    return details


def _list(value, field: str, *, required: bool = False) -> list[str]:
    if value is None and not required:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{field} must be a list of non-empty strings")
    if required and not value:
        raise ValueError(f"{field} cannot be empty")
    return [item.strip() for item in value]


def _source_details(path: pathlib.Path, when: str) -> dict:
    if not path.exists():
        raise ValueError(f"{path} does not exist")
    try:
        if path.suffix.lower() == ".json":
            raw = json.loads(path.read_text(encoding="utf-8"))
        else:
            raw = load_file(path)
    except (json.JSONDecodeError, YamlError, OSError) as exc:
        raise ValueError(str(exc)) from exc
    if not isinstance(raw, dict):
        raise ValueError("the study file must contain a mapping")
    question = raw.get("question")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a non-empty string")
    scope = raw.get("scope", {})
    governance = raw.get("governance", {})
    if not isinstance(scope, dict) or not isinstance(governance, dict):
        raise ValueError("scope and governance must be mappings")
    mode = str(raw.get("mode", "GUIDED")).upper()
    if mode not in ("GUIDED", "MANUAL"):
        raise ValueError("mode must be GUIDED or MANUAL")
    ethics = governance.get("ethics_applicable", False)
    if not isinstance(ethics, bool):
        raise ValueError("governance.ethics_applicable must be true or false")
    reference = governance.get("ethics_reference")
    if ethics and (not isinstance(reference, str) or not reference.strip()):
        raise ValueError("governance.ethics_reference is required when ethics applies")
    approver = governance.get("approver") or _git_user_name()
    if not isinstance(approver, str) or not approver.strip():
        raise ValueError("governance.approver is required (or configure git user.name)")
    run_id = raw.get("run_id") or _run_id(when)
    if not isinstance(run_id, str) or not re.fullmatch(r"rg-[0-9]{8}-[0-9]{3}", run_id):
        raise ValueError("run_id must have the form rg-YYYYMMDD-NNN")
    return {
        "run_id": run_id,
        "question": question.strip(),
        "mode": mode,
        "problem": {
            "question": question.strip(),
            "scope": {
                "in_scope": _list(scope.get("in_scope"), "scope.in_scope", required=True),
                "out_of_scope": _list(scope.get("out_of_scope"), "scope.out_of_scope"),
            },
            "constraints": _list(raw.get("constraints"), "constraints", required=True),
            "success_criteria": _list(
                raw.get("success_criteria"), "success_criteria", required=True,
            ),
            "mode": mode,
        },
        "governance": {
            "ethics_applicable": ethics,
            "ethics_reference": reference.strip() if isinstance(reference, str) else None,
            "data_governance": _list(
                governance.get("data_governance"), "governance.data_governance", required=True,
            ),
            "legal_notes": _list(governance.get("legal_notes"), "governance.legal_notes"),
            "approvals": [{"name": approver.strip(), "date": when[:10]}],
        },
    }


def handle(args) -> int:
    root = pathlib.Path(args.root)
    template = root / "template-run"
    target = pathlib.Path(args.run)

    if not (template / "meta.json").exists():
        print(f"error: {template}/ is missing from this checkout")
        return 2
    if args.force and args.edit:
        print("error: --force and --edit cannot be used together")
        return 2
    if args.edit and not target.exists():
        print(f"error: {target}/ does not exist; omit --edit to create it")
        return 2
    if target.exists() and not (args.force or args.edit):
        print(f"error: {target}/ already exists; pass --edit to update its setup")
        return 2
    when = (
        _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
        .isoformat().replace("+00:00", "Z")
    )
    details = None
    if args.source:
        try:
            details = _source_details(pathlib.Path(args.source), when)
        except ValueError as exc:
            print(f"error: {exc}")
            return 2
    elif args.guided or is_terminal():
        details = _guided_details(when)
        if details is None:
            return 0
    if args.edit and details is None:
        print("error: --edit needs an interactive terminal, --guided, or --from FILE")
        return 2

    if target.exists() and args.force:
        shutil.rmtree(target)
    if not target.exists():
        shutil.copytree(template, target)

    if details is not None:
        meta = json.loads((target / "meta.json").read_text(encoding="utf-8"))
        meta.update(run_id=details["run_id"], question=details["question"], mode=details["mode"])
        meta.pop("content_hash", None)
        meta["content_hash"] = document_hash(meta)
        (target / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    for artifact_id, document in (
        ("problem_spec", _problem_spec(when, details["problem"] if details else None)),
        ("governance_record", _governance_record(
            when, details["governance"] if details else None,
        )),
    ):
        (target / f"{artifact_id}.json").write_text(
            json.dumps(document, indent=2) + "\n", encoding="utf-8"
        )

    if details is None:
        console.print(f"Created a draft in {target}/.")
        console.print("This non-interactive fallback contains placeholders.")
        console.print("Run next from a terminal:")
        console.print(f"  rgraph --run {target} init --guided --edit")
    else:
        console.print(f"Created {target}/. The three human-authored files are valid and sealed.")
        console.print()
        console.print("Run next:")
        console.print(f"  rgraph --run {target} decide H1")
    return 0
