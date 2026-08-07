"""The studies this machine has opened, so nobody has to retype a path.

This list is convenience, never evidence. It records where a study was and what
it was called; it never records a gate, a decision, a digest or an outcome, and
removing an entry removes the entry and nothing else. It lives beside
`assignment.yaml` because it is a property of the machine, not of any run.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
import tempfile

from rgraph.config import machine_assignment_path

LIMIT = 12
VERSION = 1


def store_path() -> pathlib.Path:
    return machine_assignment_path().parent / "recent.json"


def _now() -> str:
    return (
        _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
        .isoformat().replace("+00:00", "Z")
    )


def _read() -> list[dict]:
    path = store_path()
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeError):
        # A damaged convenience list is not worth an error screen; it is worth
        # starting again. Nothing in it was load-bearing.
        return []
    if not isinstance(raw, dict) or raw.get("version") != VERSION:
        return []
    entries = raw.get("studies")
    if not isinstance(entries, list):
        return []
    clean: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            continue
        clean.append({
            "path": entry["path"],
            "run_id": entry.get("run_id") if isinstance(entry.get("run_id"), str) else None,
            "question": (
                entry.get("question") if isinstance(entry.get("question"), str) else None
            ),
            "opened_at": (
                entry.get("opened_at") if isinstance(entry.get("opened_at"), str) else None
            ),
        })
    return clean


def _write(entries: list[dict]) -> None:
    path = store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {"version": VERSION, "studies": entries[:LIMIT]}, indent=2,
    ) + "\n"
    # Written whole and moved into place: a crash mid-write leaves the previous
    # list intact rather than a half-parsed one.
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=".recent-", suffix=".json",
        delete=False,
    )
    try:
        with handle:
            handle.write(payload)
        os.replace(handle.name, path)
    except OSError:
        pathlib.Path(handle.name).unlink(missing_ok=True)
        raise


def _describe(run: pathlib.Path) -> dict:
    meta_path = run / "meta.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeError):
        meta = {}
    return {
        "run_id": meta.get("run_id") if isinstance(meta.get("run_id"), str) else None,
        "question": meta.get("question") if isinstance(meta.get("question"), str) else None,
    }


def remember(run: pathlib.Path | str) -> None:
    """Record one opened study. A directory with no meta.json is not recorded."""
    resolved = pathlib.Path(run).expanduser().resolve()
    if not (resolved / "meta.json").is_file():
        return
    entry = {"path": str(resolved), "opened_at": _now(), **_describe(resolved)}
    entries = [item for item in _read() if item["path"] != str(resolved)]
    _write([entry, *entries])


def forget(run: pathlib.Path | str) -> bool:
    """Drop one entry from the list. The study directory is never touched."""
    resolved = str(pathlib.Path(run).expanduser().resolve())
    entries = _read()
    kept = [item for item in entries if item["path"] != resolved]
    if len(kept) == len(entries):
        return False
    _write(kept)
    return True


def studies(*, prune: bool = True) -> list[dict]:
    """The list as it stands, with paths that no longer hold a run dropped.

    Pruning removes the *entry*, never the directory: a study on an unmounted
    disk disappears from this list and comes back when the disk does.
    """
    entries = _read()
    live, missing = [], False
    for entry in entries:
        path = pathlib.Path(entry["path"])
        if (path / "meta.json").is_file():
            live.append({**entry, "available": True})
        else:
            missing = True
    if prune and missing:
        _write([{k: v for k, v in item.items() if k != "available"} for item in live])
    return live
