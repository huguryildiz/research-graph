"""Accepting a unit's output: what a provider was allowed to change, and did.

`rgraph next` and the browser's background job manager must judge one finished
invocation identically, so the whole boundary — declared outputs, hash-bound
sidecars, producer identity, the invocation window, and the execution receipt —
is computed here and only reported by the callers.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib

from rgraph.campaigns import reused_run_ids
from rgraph.git_provenance import verify_committed_source
from rgraph.hashing import file_hash
from rgraph.provenance import body_mismatch, hash_mismatch, payload_mismatch
from rgraph.run import RunError
from rgraph.schemas import registry


def output_state(run, artifact_ids) -> dict[str, tuple[str | None, str | None]]:
    state = {}
    for artifact_id in artifact_ids:
        artifact = run.artifacts[artifact_id]
        envelope = file_hash(artifact.path) if artifact.path.is_file() else None
        payload = (
            file_hash(artifact.payload_path)
            if artifact.payload_path is not None and artifact.payload_path.is_file()
            else None
        )
        state[artifact_id] = (envelope, payload)
    return state


def campaign_preservation_state(run) -> dict:
    manifest = run.get("run_manifest")
    raw = run.get("raw_results")
    return {
        "payload_hash": (
            file_hash(raw.payload_path)
            if raw.payload_path is not None and raw.payload_path.is_file() else None
        ),
        "run_ids": sorted(
            item.get("run_id") for item in manifest.body.get("runs", [])
            if isinstance(item.get("run_id"), str)
        ),
        "manifest_body": json.dumps(manifest.body, sort_keys=True, separators=(",", ":")),
        "raw_body": json.dumps(raw.body, sort_keys=True, separators=(",", ":")),
    }


def campaign_preservation_problems(before: dict, run) -> list[str]:
    after = campaign_preservation_state(run)
    labels = {
        "payload_hash": "raw payload bytes",
        "run_ids": "run ID set",
        "manifest_body": "run_manifest body",
        "raw_body": "raw_results body",
    }
    return [
        f"preserve-payload mode: provider changed {labels[key]}"
        for key in labels if before.get(key) != after.get(key)
    ]


def run_boundary_state(root) -> dict[str, str]:
    state = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] == "logs":
            continue
        state[relative.as_posix()] = file_hash(path)
    return state


def allowed_output_paths(run, unit) -> set[str]:
    """Exactly the files this unit is permitted to write, envelopes and payloads.

    The live activity watcher marks anything else, so this is the same boundary
    reported during a run and enforced after it.
    """
    allowed = set()
    for artifact_id in unit.produces:
        artifact = run.artifacts[artifact_id]
        allowed.add(artifact.path.relative_to(run.root).as_posix())
        if artifact.payload_path is not None:
            allowed.add(artifact.payload_path.relative_to(run.root).as_posix())
    return allowed


def _manifest_sidecars(run, unit) -> tuple[set[str], list[str]]:
    """Safe, hash-bound files that are part of a declared data manifest."""
    allowed: set[str] = set()
    problems: list[str] = []
    if "data_manifest" not in unit.produces:
        return allowed, problems
    artifact = run.get("data_manifest")
    if not artifact.present or artifact.errors:
        return allowed, problems
    for dataset in artifact.body.get("datasets", []):
        value = dataset.get("path")
        relative = pathlib.PurePosixPath(value) if isinstance(value, str) else None
        if (
            relative is None or relative.is_absolute() or not relative.parts
            or relative.parts[0] != "data" or ".." in relative.parts
        ):
            problems.append(
                f"data_manifest: dataset path {value!r} must stay below run/data"
            )
            continue
        candidate = (run.root / relative).resolve()
        try:
            candidate.relative_to(run.root.resolve())
        except ValueError:
            problems.append(f"data_manifest: dataset path {value!r} escapes the run")
            continue
        allowed.add(relative.as_posix())
        if not candidate.is_file():
            problems.append(f"data_manifest: declared dataset is missing: {value}")
            continue
        actual_hash = file_hash(candidate).removeprefix("sha256:")
        if actual_hash != dataset.get("sha256"):
            problems.append(f"data_manifest: dataset digest does not match: {value}")
        if candidate.stat().st_size != dataset.get("bytes"):
            problems.append(f"data_manifest: dataset byte count does not match: {value}")
    return allowed, problems


def _code_sidecars(run, unit) -> tuple[set[str], list[str]]:
    """Safe source files bound by ``code_commit.body.files`` digests."""
    allowed: set[str] = set()
    problems: list[str] = []
    if "code_commit" not in unit.produces:
        return allowed, problems
    artifact = run.get("code_commit")
    if not artifact.present or artifact.errors:
        return allowed, problems
    declared: set[str] = set()
    reserved = {".git", ".venv", "__pycache__"}
    for item in artifact.body.get("files", []):
        value = item.get("path")
        relative = pathlib.PurePosixPath(value) if isinstance(value, str) else None
        if (
            relative is None or relative.is_absolute() or not relative.parts
            or relative.parts[0] != "code" or ".." in relative.parts
            or reserved.intersection(relative.parts)
        ):
            problems.append(
                f"code_commit: file path {value!r} must stay below run/code "
                "and outside reserved environment directories"
            )
            continue
        name = relative.as_posix()
        if name in declared:
            problems.append(f"code_commit: duplicate file path: {value}")
            continue
        declared.add(name)
        candidate = (run.root / relative).resolve()
        try:
            candidate.relative_to(run.root.resolve())
        except ValueError:
            problems.append(f"code_commit: file path {value!r} escapes the run")
            continue
        allowed.add(name)
        if not candidate.is_file():
            problems.append(f"code_commit: declared source file is missing: {value}")
            continue
        actual_hash = file_hash(candidate).removeprefix("sha256:")
        if actual_hash != item.get("sha256"):
            problems.append(f"code_commit: source digest does not match: {value}")
    entrypoint = artifact.body.get("entrypoint")
    if entrypoint not in declared:
        problems.append("code_commit: entrypoint is not listed in files")
    if (artifact.document or {}).get("version", 1) >= 2:
        bundle_value = artifact.body.get("bundle_path")
        bundle_relative = (
            pathlib.PurePosixPath(bundle_value)
            if isinstance(bundle_value, str) else None
        )
        if (
            bundle_relative is not None and not bundle_relative.is_absolute()
            and bundle_relative.parts and bundle_relative.parts[0] == "code"
            and ".." not in bundle_relative.parts
        ):
            allowed.add(bundle_relative.as_posix())
        problems.extend(
            f"code_commit: {issue.code}: {issue.detail}"
            for issue in verify_committed_source(
                run.root, artifact.document or {}
            )
        )
    return allowed, problems


def _environment_sidecars(run, unit) -> tuple[set[str], list[str]]:
    """Dependency lock material bound by environment_lock version 2."""
    allowed: set[str] = set()
    problems: list[str] = []
    if "environment_lock" not in unit.produces:
        return allowed, problems
    artifact = run.get("environment_lock")
    if not artifact.present or artifact.errors:
        return allowed, problems
    value = artifact.body.get("lock_path")
    if value is None and (artifact.document or {}).get("version", 1) < 2:
        return allowed, problems
    relative = pathlib.PurePosixPath(value) if isinstance(value, str) else None
    if (
        relative is None or relative.is_absolute() or not relative.parts
        or relative.parts[0] != "environment" or ".." in relative.parts
    ):
        problems.append(
            f"environment_lock: lock path {value!r} must stay below run/environment"
        )
        return allowed, problems
    name = relative.as_posix()
    candidate = (run.root / relative).resolve()
    try:
        candidate.relative_to(run.root.resolve())
    except ValueError:
        problems.append(f"environment_lock: lock path {value!r} escapes the run")
        return allowed, problems
    allowed.add(name)
    if not candidate.is_file():
        problems.append(f"environment_lock: dependency lock is missing: {value}")
    elif file_hash(candidate).removeprefix("sha256:") != artifact.body.get(
        "lock_sha256"
    ):
        problems.append(f"environment_lock: dependency-lock digest does not match: {value}")
    return allowed, problems


def _configuration_sidecars(run, unit) -> tuple[set[str], list[str]]:
    """Exact run configurations and invocations bound by run_manifest v2."""
    allowed: set[str] = set()
    problems: list[str] = []
    if "run_manifest" not in unit.produces:
        return allowed, problems
    artifact = run.get("run_manifest")
    if not artifact.present or artifact.errors:
        return allowed, problems
    declared_inputs = {
        item.get("artifact_id") for item in (artifact.document or {}).get("inputs", [])
    }
    missing_inputs = sorted(
        {"code_commit", "environment_lock", "data_manifest"} - declared_inputs
    )
    if missing_inputs:
        problems.append(
            "run_manifest: execution provenance does not bind "
            + ", ".join(missing_inputs)
        )
    configurations = artifact.body.get("configurations", [])
    if not configurations and (artifact.document or {}).get("version", 1) < 2:
        overlap = reused_run_ids(run)
        if overlap:
            problems.append(
                "run_manifest: replacement campaign reuses "
                f"{len(overlap)} retired run_id value(s)"
            )
        return allowed, problems
    declared_paths: set[str] = set()
    declared_hashes: set[str] = set()
    for item in configurations:
        value = item.get("path")
        relative = pathlib.PurePosixPath(value) if isinstance(value, str) else None
        if (
            relative is None or relative.is_absolute() or not relative.parts
            or relative.parts[0] != "config" or ".." in relative.parts
        ):
            problems.append(
                f"run_manifest: configuration path {value!r} must stay below run/config"
            )
            continue
        name = relative.as_posix()
        if name in declared_paths:
            problems.append(f"run_manifest: duplicate configuration path: {value}")
            continue
        declared_paths.add(name)
        declared_hashes.add(item.get("sha256"))
        candidate = (run.root / relative).resolve()
        try:
            candidate.relative_to(run.root.resolve())
        except ValueError:
            problems.append(f"run_manifest: configuration path {value!r} escapes the run")
            continue
        allowed.add(name)
        if not candidate.is_file():
            problems.append(f"run_manifest: configuration snapshot is missing: {value}")
        elif file_hash(candidate).removeprefix("sha256:") != item.get("sha256"):
            problems.append(f"run_manifest: configuration digest does not match: {value}")
    unbound = sorted({
        item.get("config_sha256") for item in artifact.body.get("runs", [])
        if item.get("config_sha256") not in declared_hashes
    })
    if unbound:
        problems.append(
            "run_manifest: run config_sha256 is not bound to a configuration snapshot"
        )
    overlap = reused_run_ids(run)
    if overlap:
        problems.append(
            "run_manifest: replacement campaign reuses "
            f"{len(overlap)} retired run_id value(s)"
        )
    return allowed, problems


def _figure_sidecars(run, unit) -> tuple[set[str], list[str]]:
    """Figure scripts declared and digest-bound by ``figure_registry``.

    The registry schema requires every figure to name the script that produced
    it and bind that script's SHA-256. A fresh u11 therefore has to be able to
    create that script, while the unit boundary must still reject arbitrary
    files. Only regular files below ``run/code`` whose bytes match the declared
    digest cross that boundary.
    """
    allowed: set[str] = set()
    problems: list[str] = []
    if "figure_registry" not in unit.produces:
        return allowed, problems
    artifact = run.get("figure_registry")
    if not artifact.present or artifact.errors:
        return allowed, problems
    declared: dict[str, str] = {}
    reserved = {".git", ".venv", "__pycache__"}
    for figure in artifact.body.get("figures", []):
        script = figure.get("script") or {}
        value = script.get("path")
        digest = script.get("sha256")
        relative = pathlib.PurePosixPath(value) if isinstance(value, str) else None
        if (
            relative is None or relative.is_absolute() or not relative.parts
            or relative.parts[0] != "code" or ".." in relative.parts
            or reserved.intersection(relative.parts)
        ):
            problems.append(
                f"figure_registry: script path {value!r} must stay below run/code "
                "and outside reserved environment directories"
            )
            continue
        name = relative.as_posix()
        previous = declared.get(name)
        if previous is not None and previous != digest:
            problems.append(
                f"figure_registry: script path {value!r} has conflicting digests"
            )
            continue
        declared[name] = digest
        candidate = (run.root / relative).resolve()
        try:
            candidate.relative_to(run.root.resolve())
        except ValueError:
            problems.append(f"figure_registry: script path {value!r} escapes the run")
            continue
        allowed.add(name)
        if not candidate.is_file():
            problems.append(f"figure_registry: declared script is missing: {value}")
            continue
        if file_hash(candidate).removeprefix("sha256:") != digest:
            problems.append(f"figure_registry: script digest does not match: {value}")
    return allowed, problems


def output_problems(
    run, kit, unit, before, boundary_before, *, started_at=None, finished_at=None,
) -> list[str]:
    problems: list[str] = []
    current = output_state(run, unit.produces)
    if current == before:
        problems.append("provider exited 0 but changed none of the declared outputs")
    boundary_after = run_boundary_state(run.root)
    changed = {
        name for name in boundary_before.keys() | boundary_after.keys()
        if boundary_before.get(name) != boundary_after.get(name)
    }
    data_sidecars, data_problems = _manifest_sidecars(run, unit)
    code_sidecars, code_problems = _code_sidecars(run, unit)
    environment_sidecars, environment_problems = _environment_sidecars(run, unit)
    configuration_sidecars, configuration_problems = _configuration_sidecars(run, unit)
    figure_sidecars, figure_problems = _figure_sidecars(run, unit)
    problems.extend(data_problems)
    problems.extend(code_problems)
    problems.extend(environment_problems)
    problems.extend(configuration_problems)
    problems.extend(figure_problems)
    unexpected = sorted(
        changed - allowed_output_paths(run, unit) - data_sidecars - code_sidecars
        - environment_sidecars - configuration_sidecars - figure_sidecars
    )
    if unexpected:
        problems.append(
            "provider changed files outside the declared unit outputs: "
            + ", ".join(unexpected[:8])
        )
    expected_identity = kit.assignment[unit.role_name].identity(kit.providers)
    start = _dt.datetime.fromisoformat(started_at.replace("Z", "+00:00")) \
        if started_at else None
    finish = _dt.datetime.fromisoformat(finished_at.replace("Z", "+00:00")) \
        if finished_at else None
    clock_tolerance = _dt.timedelta(minutes=5)
    for artifact_id in unit.produces:
        artifact = run.get(artifact_id)
        if not artifact.present:
            problems.append(f"{artifact_id}: output is missing")
            continue
        if artifact.errors:
            problems.append(f"{artifact_id}: output does not match its schema")
            continue
        if artifact_id == "statistical_report" and (
            artifact.document or {}
        ).get("version", 1) < 2:
            problems.append(
                "statistical_report: new u09 outputs must use version 2 with "
                "configuration-bound denominators"
            )
        if artifact.identity != expected_identity:
            problems.append(
                f"{artifact_id}: produced_by.identity is {artifact.identity!r}; "
                f"expected {expected_identity!r}"
            )
        produced_at = (artifact.document or {}).get("produced_at")
        if start is not None and finish is not None and isinstance(produced_at, str):
            produced = _dt.datetime.fromisoformat(produced_at.replace("Z", "+00:00"))
            if produced < start - clock_tolerance or produced > finish + clock_tolerance:
                problems.append(
                    f"{artifact_id}: produced_at {produced_at} is outside the "
                    "provider invocation window"
                )
        body = body_mismatch(artifact)
        if body:
            problems.append(f"{artifact_id}: {body}")
        payload = payload_mismatch(run, artifact)
        if payload:
            problems.append(f"{artifact_id}: {payload}")
        for upstream, _, _ in hash_mismatch(run, artifact):
            problems.append(f"{artifact_id}: input {upstream} does not match")
    return problems


def acquire_unit_lock(run, unit_id: str) -> pathlib.Path:
    """Atomically prevent concurrent provider calls for one run unit."""
    directory = run.root / "logs" / ".locks"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{unit_id}.lock"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RunError(
            f"{unit_id} is already executing; wait for that invocation to finish. "
            f"If it crashed, inspect and remove the stale lock: {path}"
        ) from exc
    payload = {"pid": os.getpid(), "started_at": now()}
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
        handle.write("\n")
    return path


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _artifact_refs(run, artifact_ids) -> list[dict]:
    return [
        {"artifact_id": artifact_id, "content_hash": run.get(artifact_id).content_hash}
        for artifact_id in artifact_ids
        if run.get(artifact_id).present and run.get(artifact_id).content_hash
    ]


def write_execution_record(
    run, current, kit, unit, plan, *, started_at, finished_at, exit_code, problems,
):
    assignment = kit.assignment[unit.role_name]
    log_path = plan.log_path if plan.log_path and plan.log_path.is_file() else None
    record = {
        "unit_id": unit.id,
        "invocation_id": plan.invocation_id or "legacy-invocation",
        "outcome": "rejected" if problems or exit_code else "accepted",
        "started_at": started_at,
        "finished_at": finished_at,
        "assignment": {
            "provider": assignment.provider,
            "model": assignment.model,
            "identity": assignment.identity(kit.providers),
        },
        "argv": plan.argv,
        "exit_code": exit_code,
        "log": log_path.relative_to(run.root).as_posix() if log_path else None,
        "log_sha256": file_hash(log_path) if log_path else None,
        "inputs": _artifact_refs(run, [artifact_id for artifact_id, _ in plan.inputs]),
        "outputs": _artifact_refs(current, unit.produces),
        "problems": problems,
    }
    errors = registry(kit.root).validate("execution_record", record)
    if errors:
        first = errors[0]
        raise RunError(f"generated execution record is invalid: {first.path}: {first.message}")
    return run.write_execution_record(record)
