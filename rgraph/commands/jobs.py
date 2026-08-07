"""`rgraph jobs` — what ran in this study, from the terminal.

The browser watches an execution while it happens. This answers the question
that comes afterwards, when the browser is closed: what ran, when, and how did
it end. It reads the same operational records the console does and writes
nothing.
"""

from __future__ import annotations

import pathlib

from rgraph.render import (
    MAIN_STYLE, body_text, console, key_value, muted, render_error,
    render_next_action, section, table_row,
)
from rgraph.services import joblog


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "jobs",
        help="what a provider ran in this study, and how it ended",
        description=(
            "List the recorded provider executions for a run, or show one in "
            "full. These are operational records, not research artifacts."
        ),
        epilog=(
            "Examples:\n"
            "  rgraph jobs\n"
            "  rgraph jobs u01\n"
            "  rgraph jobs 3ab2feb --log"
        ),
    )
    parser.add_argument(
        "job", nargs="?",
        help="a job id, the short id from its file name, or a unit or gate id",
    )
    parser.add_argument(
        "--log", action="store_true",
        help="also print the provider's own captured output",
    )
    parser.set_defaults(handler=handle)


def _summary_line(record: dict) -> str:
    started = (record.get("started_at") or record.get("created_at") or "")[:19].replace("T", " ")
    seconds = record.get("elapsed_seconds")
    elapsed = "—" if seconds is None else f"{int(seconds)}s"
    return (
        f"{started}  {record.get('target', '?'):<6} "
        f"{record.get('provider')}/{record.get('model')}  {elapsed}"
    )


def handle(args) -> int:
    run = pathlib.Path(args.run)
    if not (run / "meta.json").exists():
        render_error(f"not a run directory: {run}/meta.json is missing")
        return 2
    records = joblog.records(run)
    if not records:
        section("No recorded executions")
        body_text(f"No provider has been launched in {run}/ by this application.")
        console.print()
        render_next_action("rgraph next")
        return 0

    if args.job is None:
        section(f"Recorded executions in {run}")
        for record in records:
            table_row(
                record.get("state", "?"), _summary_line(record), width=12,
            )
        muted(
            "These are operational records under logs/jobs/, not research "
            "artifacts. Each has a readable transcript beside it."
        )
        console.print()
        render_next_action(f"rgraph --run {run} jobs {records[0].get('target')}")
        return 0

    record = joblog.find(run, args.job)
    if record is None:
        render_error(
            f"no recorded execution matches '{args.job}'; "
            f"try one of {', '.join(sorted({r.get('target', '?') for r in records}))}"
        )
        return 2

    events = joblog.events(run, record)
    section(f"{record.get('target')} · {record.get('title') or ''}")
    key_value("Outcome", record.get("state"), value_style=MAIN_STYLE)
    muted(joblog.OUTCOME_LINE.get(str(record.get("state")), ""))
    key_value("Started", record.get("started_at") or "not started")
    key_value("Elapsed", joblog.duration(record))
    key_value("Provider", f"{record.get('provider')}/{record.get('model')}")
    key_value("Command", " ".join(record.get("argv") or []))
    key_value("Exit code", record.get("exit_code") if record.get("exit_code") is not None else "—")
    key_value("Provider log", record.get("log") or "—")

    activity = [item for item in events if item.get("channel") == "activity"]
    if activity:
        console.print()
        section("What it changed")
        for item in activity:
            table_row(str(item.get("at", ""))[11:19], str(item.get("text")), width=10)
        muted("Observed from the study directory. This reports files, not intentions.")

    validation = record.get("validation") or {}
    if validation.get("stages"):
        console.print()
        section("Outcome")
        for stage in validation["stages"]:
            table_row(str(stage.get("status")), str(stage.get("name")), width=12)
    problems = validation.get("problems") or []
    if problems:
        console.print()
        section("What was wrong")
        for problem in problems:
            body_text(problem, indent="    ")

    if args.log:
        log_path = run / str(record.get("log") or "")
        console.print()
        section("Provider output")
        if record.get("log") and log_path.is_file():
            body_text(log_path.read_text(encoding="utf-8", errors="replace"))
            muted(
                "This is the provider's own log, exactly as captured. It is not "
                "redacted and may contain anything the provider printed."
            )
        else:
            muted("The provider log for this execution is not on disk.")

    console.print()
    transcript = joblog.jobs_dir(run) / f"{joblog.slug(record)}.md"
    if transcript.is_file():
        key_value("Full transcript", transcript)
    render_next_action(f"rgraph --run {run} status")
    return 0
