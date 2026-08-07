"""Execution records on disk, in a shape a person can read tomorrow.

Three files travel together for one execution. The provider's own log is
written by the runner and never touched here — its SHA-256 is bound into the
execution receipt, so its bytes are not ours to reformat. Beside it sit a JSON
record, which is what the browser reads, and a Markdown transcript, which is
what a person reads when the browser is closed and the question is "what
happened last night".

Nothing in this module is integrity-bearing. It is bookkeeping about a run, not
evidence from one, which is why it lives under `logs/`.
"""

from __future__ import annotations

import datetime as _dt
import json
import pathlib
import re

BOUNDARY = (
    "Mechanical checks establish only their declared conditions. "
    "Scientific correctness was not determined."
)
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def jobs_dir(run_root: pathlib.Path | str) -> pathlib.Path:
    return pathlib.Path(run_root) / "logs" / "jobs"


def slug(record: dict) -> str:
    """`20260807T0825-u01-3ab2feb`: sortable, and obvious without opening it."""
    stamp = str(record.get("created_at") or "")[:16].replace("-", "").replace(":", "")
    target = _UNSAFE.sub("-", str(record.get("target") or "job"))[:24]
    short = str(record.get("id") or "")[:7]
    return "-".join(part for part in (stamp, target, short) if part) or "job"


def _read_json(path: pathlib.Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeError):
        return None
    return value if isinstance(value, dict) and isinstance(value.get("id"), str) else None


def stored(run_root: pathlib.Path | str) -> list[tuple[pathlib.Path, dict]]:
    """Every record with the file it came from, newest first.

    A record written before job files were named readably still lives under its
    bare id, and rewriting it has to land on that file rather than on the name
    it would be given today.
    """
    directory = jobs_dir(run_root)
    if not directory.is_dir():
        return []
    found = [
        (path, record) for path in directory.glob("*.json")
        if (record := _read_json(path)) is not None
    ]
    return sorted(found, key=lambda item: item[1].get("created_at") or "", reverse=True)


def records(run_root: pathlib.Path | str) -> list[dict]:
    """Every execution this study has a record of, newest first."""
    return [record for _, record in stored(run_root)]


def find(run_root: pathlib.Path | str, reference: str) -> dict | None:
    """Match a job by full id, by the short id in its filename, or by unit.

    A person reading a file name should be able to type what they see. The
    newest match wins, so `rgraph jobs u01` answers about the last u01 run.
    """
    reference = reference.strip()
    if not reference:
        return None
    for record in records(run_root):
        if record["id"] == reference or record["id"].startswith(reference):
            return record
    for record in records(run_root):
        if record.get("target") == reference or slug(record).endswith(reference):
            return record
    return None


def events(run_root: pathlib.Path | str, record: dict, after: int = 0) -> list[dict]:
    directory = jobs_dir(run_root)
    candidates = [
        directory / f"{slug(record)}.events.jsonl",
        directory / f"{record['id']}.events.jsonl",   # records written before slugs
    ]
    for path in candidates:
        if not path.is_file():
            continue
        out = []
        try:
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(event, dict) and event.get("seq", 0) > after:
                        out.append(event)
        except OSError:
            return []
        return out
    return []


def _clock(value) -> str:
    return str(value or "")[11:19] or "--:--:--"


def _readable_bytes(value: int) -> str:
    if value < 1024:
        return f"{value} bytes"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} kB"
    return f"{value / (1024 * 1024):.1f} MB"


def duration(record: dict) -> str:
    seconds = record.get("elapsed_seconds")
    if seconds is None:
        return "—"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}m {seconds % 60}s"


OUTCOME_LINE = {
    "COMPLETE": "the declared outputs were written, validated and recorded",
    "FAILED": "the declared outputs were not accepted",
    "CANCELLED": "stopped before it finished; nothing was sealed and no checkpoint passed",
    "INTERRUPTED": "started by an earlier server process; its outcome cannot be observed",
    "RUNNING": "still running at the time this file was written",
    "QUEUED": "accepted, not yet started",
    "VALIDATING": "the process exited; its files were being checked",
    "CANCELLING": "being stopped",
}


def transcript(record: dict, event_list: list[dict]) -> str:
    """One execution as Markdown: what ran, what it touched, and how it ended."""
    state = str(record.get("state", "UNKNOWN"))
    lines = [
        f"# {record.get('target', '?')} · {record.get('title') or ''}".rstrip(),
        "",
        f"**{state}** — {OUTCOME_LINE.get(state, 'state not recognised')}",
        "",
        "| | |",
        "|---|---|",
        f"| Started | {record.get('started_at') or 'not started'} |",
        f"| Finished | {record.get('ended_at') or '—'} |",
        f"| Elapsed | {duration(record)} |",
        f"| Provider / model | {record.get('provider')} / {record.get('model')} |",
        f"| Role | {record.get('role') or '—'} |",
        f"| Command | `{' '.join(record.get('argv') or [])}` |",
        f"| Process id | {record.get('pid') if record.get('pid') is not None else '—'} |",
        f"| Exit code | {record.get('exit_code') if record.get('exit_code') is not None else '—'} |",
        f"| Provider log | `{record.get('log') or '—'}` |",
        f"| Job id | `{record.get('id')}` |",
    ]
    if record.get("cancel_requested_at"):
        lines.append(
            f"| Stop requested | {record['cancel_requested_at']} "
            f"by {record.get('cancel_requested_by') or 'unknown'} |"
        )
    lines.append("")

    inputs = record.get("inputs") or []
    if inputs:
        lines += ["## What it read", ""]
        for item in inputs:
            digest = str(item.get("content_hash") or "not sealed")
            lines.append(
                f"- `{item.get('artifact_id')}` — {item.get('state')} — {digest[:23]}…"
            )
        lines.append("")

    activity = [item for item in event_list if item.get("channel") == "activity"]
    lines += ["## What it changed", ""]
    if activity:
        lines += [f"- {_clock(item.get('at'))} {item.get('text')}" for item in activity]
        lines += [
            "",
            "_Observed by comparing the study directory while the provider ran. This "
            "reports files, not intentions._",
        ]
    else:
        lines.append("- no file in the study changed while this ran")
    lines.append("")

    expected = record.get("expected_outputs") or []
    if expected:
        lines += ["## What was expected", ""]
        lines += [f"- `{name}`" for name in expected]
        lines.append("")

    lines += ["## Transcript", "", "```"]
    if event_list:
        for item in event_list:
            marker = {"output": "  ", "state": "· ", "notice": "! ", "activity": "→ "}.get(
                item.get("channel"), "  ")
            lines.append(f"{_clock(item.get('at'))} {marker}{item.get('text')}")
    else:
        lines.append("(no events were recorded)")
    lines += ["```", ""]
    if record.get("truncated"):
        lines += [
            "_The live transcript reached its display limit; the complete provider "
            "log on disk is longer._",
            "",
        ]

    validation = record.get("validation") or {}
    lines += ["## Outcome", ""]
    for stage in validation.get("stages") or []:
        lines.append(f"- **{stage.get('status')}** {stage.get('name')} — {stage.get('detail')}")
    problems = validation.get("problems") or []
    if problems:
        lines += ["", "Problems:", ""]
        lines += [f"- {problem}" for problem in problems]
    produced = validation.get("produced") or []
    if produced:
        lines += ["", f"Artifacts present afterwards: {', '.join(produced)}."]
    if record.get("interrupted_note"):
        lines += ["", record["interrupted_note"]]
    lines += [
        "",
        "---",
        "",
        BOUNDARY,
        "",
        "_This file is operational bookkeeping. It is not a research artifact, "
        "carries no schema, and is never read as evidence._",
        "",
    ]
    return "\n".join(lines)


def write_transcript(run_root: pathlib.Path | str, record: dict,
                     event_list: list[dict]) -> pathlib.Path | None:
    directory = jobs_dir(run_root)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{slug(record)}.md"
        path.write_text(transcript(record, event_list), encoding="utf-8")
        return path
    except OSError:
        return None
