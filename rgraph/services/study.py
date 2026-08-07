"""Creating a governed run: the human-authored files and where they may land.

`rgraph init` and the browser wizard both come through here, so a destination
the CLI would refuse cannot be created from a browser, and the two paths write
byte-identical study files.
"""

from __future__ import annotations

import datetime as _dt
import json
import pathlib
import re
import shutil
import subprocess

from rgraph.hashing import document_hash
from rgraph.yamlmini import YamlError, load_file

PLACEHOLDER = "Replace this with the research question."

# Directories a study must never be written into or over. A run directory is
# created, filled and later rewritten by sealing; pointing that at a home or a
# repository root would put those rewrites on top of unrelated files.
RESERVED_NAMES = frozenset({
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    ".ssh", ".config", ".local", "Library", "System", "Windows",
})


class StudyError(ValueError):
    """A study setup or destination that must be refused, with the reason."""


def now() -> str:
    return (
        _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
        .isoformat().replace("+00:00", "Z")
    )


def git_user_name() -> str:
    try:
        result = subprocess.run(
            ["git", "config", "user.name"], capture_output=True, text=True,
            timeout=3, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip()


def run_id_for(when: str) -> str:
    return f"rg-{when[:10].replace('-', '')}-001"


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


def problem_spec(when: str, body: dict | None = None) -> dict:
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


def governance_record(when: str, body: dict | None = None) -> dict:
    if body is not None:
        return _envelope("governance_record", body, when)
    return _envelope("governance_record", {
        "ethics_applicable": False,
        "ethics_reference": None,
        "data_governance": ["Replace with where the data comes from and what governs it."],
        "legal_notes": ["Replace with licence and third-party terms, or state there are none."],
        "approvals": [{"name": "Replace with the approving name", "date": when[:10]}],
    }, when)


def _list(value, field: str, *, required: bool = False) -> list[str]:
    if value is None and not required:
        return []
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise StudyError(f"{field} must be a list of non-empty strings")
    if required and not value:
        raise StudyError(f"{field} cannot be empty")
    return [item.strip() for item in value]


def normalise_details(raw, when: str) -> dict:
    """Turn one study description into the exact bodies the run will carry.

    The shape accepted here is `study.example.yaml`'s, which is also what the
    browser wizard posts, so both paths get the same refusals in the same words.
    """
    if not isinstance(raw, dict):
        raise StudyError("the study file must contain a mapping")
    question = raw.get("question")
    if not isinstance(question, str) or not question.strip():
        raise StudyError("question must be a non-empty string")
    scope = raw.get("scope", {})
    governance = raw.get("governance", {})
    if not isinstance(scope, dict) or not isinstance(governance, dict):
        raise StudyError("scope and governance must be mappings")
    mode = str(raw.get("mode", "GUIDED")).upper()
    if mode not in ("GUIDED", "MANUAL"):
        raise StudyError("mode must be GUIDED or MANUAL")
    ethics = governance.get("ethics_applicable", False)
    if not isinstance(ethics, bool):
        raise StudyError("governance.ethics_applicable must be true or false")
    reference = governance.get("ethics_reference")
    if ethics and (not isinstance(reference, str) or not reference.strip()):
        raise StudyError("governance.ethics_reference is required when ethics applies")
    approver = governance.get("approver") or git_user_name()
    if not isinstance(approver, str) or not approver.strip():
        raise StudyError("governance.approver is required (or configure git user.name)")
    run_id = raw.get("run_id") or run_id_for(when)
    if not isinstance(run_id, str) or not re.fullmatch(r"rg-[0-9]{8}-[0-9]{3}", run_id):
        raise StudyError("run_id must have the form rg-YYYYMMDD-NNN")
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


def details_from_file(path: pathlib.Path, when: str) -> dict:
    if not path.exists():
        raise StudyError(f"{path} does not exist")
    try:
        if path.suffix.lower() == ".json":
            raw = json.loads(path.read_text(encoding="utf-8"))
        else:
            raw = load_file(path)
    except (json.JSONDecodeError, YamlError, OSError) as exc:
        raise StudyError(str(exc)) from exc
    return normalise_details(raw, when)


def resolve_destination(target: pathlib.Path | str) -> pathlib.Path:
    """Refuse a destination that is too broad to own a run directory.

    A study directory is created, rewritten and resealed. Somewhere that already
    holds unrelated work — a home directory, a filesystem root, a repository
    root, a Git or virtualenv directory — cannot be that, so it is refused
    before anything is written rather than repaired afterwards.
    """
    raw = str(target).strip()
    if not raw:
        raise StudyError("choose a folder name for this study")
    candidate = pathlib.Path(raw).expanduser()
    try:
        resolved = candidate.resolve()
    except OSError as exc:
        raise StudyError(f"that destination cannot be resolved: {exc}") from exc
    if resolved.parent == resolved:
        raise StudyError("a filesystem root cannot hold a study directory")
    if resolved == pathlib.Path.home().resolve():
        raise StudyError("the home directory cannot itself be a study directory")
    if resolved.name in RESERVED_NAMES:
        raise StudyError(f"'{resolved.name}' is reserved and cannot be a study directory")
    if any(part in RESERVED_NAMES for part in resolved.parts[:-1]):
        raise StudyError("that destination is inside a reserved system directory")
    for marker in ("graph.yaml", "pyproject.toml", ".git"):
        if (resolved / marker).exists():
            raise StudyError(
                f"{resolved} looks like a project root (it contains {marker}); "
                "choose a new folder inside it instead"
            )
    if resolved.exists():
        if not resolved.is_dir():
            raise StudyError(f"{resolved} is a file, not a directory")
        if (resolved / "meta.json").exists():
            raise StudyError(
                f"{resolved} already holds a run; open it instead of overwriting it"
            )
        if any(resolved.iterdir()):
            raise StudyError(f"{resolved} is not empty; choose a new folder")
    return resolved


def write_study_files(target: pathlib.Path, details: dict | None, when: str) -> None:
    """Stamp meta.json and the two human-authored artifacts into a copied template."""
    if details is not None:
        meta = json.loads((target / "meta.json").read_text(encoding="utf-8"))
        meta.update(
            run_id=details["run_id"], question=details["question"], mode=details["mode"]
        )
        meta.pop("content_hash", None)
        meta["content_hash"] = document_hash(meta)
        (target / "meta.json").write_text(
            json.dumps(meta, indent=2) + "\n", encoding="utf-8"
        )
    for artifact_id, document in (
        ("problem_spec", problem_spec(when, details["problem"] if details else None)),
        ("governance_record", governance_record(
            when, details["governance"] if details else None,
        )),
    ):
        (target / f"{artifact_id}.json").write_text(
            json.dumps(document, indent=2) + "\n", encoding="utf-8"
        )


def create_run(
    root: pathlib.Path, target: pathlib.Path, details: dict | None, when: str,
) -> pathlib.Path:
    """Copy the template and stamp the study into it. The caller has already asked."""
    template = root / "template-run"
    if not (template / "meta.json").exists():
        raise StudyError(f"{template}/ is missing from this installation")
    if not target.exists():
        shutil.copytree(template, target)
    write_study_files(target, details, when)
    return target


def write_preview(target: pathlib.Path, root: pathlib.Path, details: dict) -> dict:
    """Exactly which files a create would write, before one byte is written."""
    template = root / "template-run"
    template_files = sorted(
        path.relative_to(template).as_posix()
        for path in template.rglob("*") if path.is_file()
    ) if template.is_dir() else []
    return {
        "destination": str(target),
        "exists": target.exists(),
        "run_id": details["run_id"],
        "question": details["question"],
        "responsible": details["governance"]["approvals"][0]["name"],
        "files": template_files,
        "stamped": ["meta.json", "problem_spec.json", "governance_record.json"],
        "note": (
            "The template is copied, then the research question, governance record "
            "and run identity are stamped into it. Nothing outside this folder is "
            "touched, and no model is called."
        ),
    }
