"""`rgraph init` — create a run, guided in a terminal and scriptable in CI."""

from __future__ import annotations

import json
import pathlib
import shutil

from rgraph.interactive import (
    InteractionCancelled, ask_text, choose, confirm, is_terminal, split_items,
)
from rgraph.render import (
    MAIN_STYLE, body_text, console, key_value, muted, render_error,
    render_next_action, section,
)
from rgraph.services.study import (  # noqa: F401  (public surface of `rgraph init`)
    PLACEHOLDER, StudyError, details_from_file, git_user_name as _git_user_name,
    governance_record as _governance_record, now as _now,
    problem_spec as _problem_spec, run_id_for as _run_id, write_study_files,
)


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "init",
        help="create a guided research run",
        description=(
            "Create the human-authored study setup and initialize a governed run "
            "directory."
        ),
        epilog=(
            "Examples:\n"
            "  rgraph init --guided\n"
            "  rgraph init --from study.yaml\n"
            "  rgraph init --edit"
        ),
    )
    parser.add_argument("--force", action="store_true", help="overwrite an existing run/")
    parser.add_argument("--edit", action="store_true",
                        help="update only the study setup files in an existing run")
    parser.add_argument("--guided", action="store_true",
                        help="prompt for the study details even when stdin is not a TTY")
    parser.add_argument("--from", dest="source", metavar="FILE",
                        help="read study details from a JSON or YAML file")
    parser.set_defaults(handler=handle)


def _guided_details(when: str) -> dict | None:
    section("Create a research run")
    muted("Answer in ordinary language. Use semicolons to list multiple items.")
    muted("Nothing is written until you approve the summary.")
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
        muted("Cancelled. No files have been written.")
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
    section("Summary")
    key_value("Run ID", details["run_id"])
    key_value("Question", question)
    key_value("In scope", "; ".join(in_scope))
    key_value("Success", "; ".join(success))
    key_value("Ethics", "yes — " + ethics_reference if ethics else "not applicable")
    key_value("Responsible", approver)
    console.print()
    try:
        if not confirm("Create this run?", default=True):
            muted("Cancelled. No files have been written.")
            return None
    except InteractionCancelled:
        console.print()
        muted("Cancelled. No files have been written.")
        return None
    return details


def handle(args) -> int:
    root = pathlib.Path(args.root)
    template = root / "template-run"
    target = pathlib.Path(args.run)

    if args.source is not None and not args.source.strip():
        render_error("--from FILE cannot be empty")
        return 2
    if not (template / "meta.json").exists():
        render_error(f"{template}/ is missing from this checkout")
        return 2
    if args.force and args.edit:
        render_error("--force and --edit cannot be used together")
        return 2
    if args.edit and not target.exists():
        render_error(f"{target}/ does not exist; omit --edit to create it")
        return 2
    if target.exists() and not (args.force or args.edit):
        render_error(f"{target}/ already exists; pass --edit to update its setup")
        return 2
    when = _now()
    details = None
    if args.source is not None:
        try:
            details = details_from_file(pathlib.Path(args.source), when)
        except StudyError as exc:
            render_error(str(exc))
            return 2
    elif args.guided or is_terminal():
        details = _guided_details(when)
        if details is None:
            return 0
    if args.edit and details is None:
        render_error("--edit needs an interactive terminal, --guided, or --from FILE")
        return 2

    if target.exists() and args.force:
        shutil.rmtree(target)
    if not target.exists():
        shutil.copytree(template, target)

    write_study_files(target, details, when)

    if details is None:
        section("Draft created")
        body_text(f"{target}/", style=MAIN_STYLE)
        muted("This non-interactive fallback contains placeholders.")
        console.print()
        render_next_action(f"rgraph --run {target} init --guided --edit")
    else:
        section("Research run created")
        body_text(f"{target}/", style=MAIN_STYLE)
        muted("The three human-authored files are valid and sealed.")
        console.print()
        render_next_action(f"rgraph --run {target} decide H1")
    return 0
