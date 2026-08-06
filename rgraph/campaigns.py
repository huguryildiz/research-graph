"""Retention and identity rules for replacement execution campaigns."""

from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import datetime as dt

from rgraph.hashing import file_hash


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def reused_run_ids(run) -> set[str]:
    """Return current run IDs that were already retired by an earlier campaign."""
    retired = set(run.meta.get("retired_run_ids", []))
    current = {
        item.get("run_id")
        for item in run.get("run_manifest").body.get("runs", [])
        if isinstance(item.get("run_id"), str)
    }
    return current & retired


def retire_current_campaign(run) -> pathlib.Path | None:
    """Archive a superseded campaign and bind its run IDs into signed metadata.

    Repeated provider retries do not create duplicate archives: once every
    current run ID is retired, this function is a no-op.
    """
    manifest = run.get("run_manifest")
    raw = run.get("raw_results")
    if not manifest.present or not raw.present or raw.payload_path is None:
        return None
    current_ids = sorted({
        item.get("run_id")
        for item in manifest.body.get("runs", [])
        if isinstance(item.get("run_id"), str)
    })
    retired = set(run.meta.get("retired_run_ids", []))
    if not current_ids or set(current_ids).issubset(retired):
        return None

    manifest_digest = file_hash(manifest.path).removeprefix("sha256:")
    relative_archive = pathlib.PurePosixPath(
        "logs", "rejected-campaigns", manifest_digest[:16]
    )
    archive = run.root / relative_archive
    archive.mkdir(parents=True, exist_ok=True)

    artifact_ids = (
        "frozen_protocol", "governance_record", "code_commit",
        "environment_lock", "data_manifest", "run_manifest", "raw_results",
    )
    for artifact_id in artifact_ids:
        artifact = run.get(artifact_id)
        if artifact.path.is_file():
            shutil.copy2(artifact.path, archive / artifact.path.name)
        if artifact.payload_path is not None and artifact.payload_path.is_file():
            shutil.copy2(artifact.payload_path, archive / artifact.payload_path.name)
    for directory_name in ("code", "config", "data", "environment"):
        source = run.root / directory_name
        target = archive / directory_name
        if source.is_dir() and not target.exists():
            shutil.copytree(source, target)
    for unit_id in ("u06", "u07"):
        source = run.root / "executions" / f"{unit_id}.json"
        if source.is_file():
            shutil.copy2(source, archive / f"{unit_id}.execution.json")

    ids_digest = hashlib.sha256(
        (json.dumps(current_ids, separators=(",", ":")) + "\n").encode("utf-8")
    ).hexdigest()
    run.meta["retired_run_ids"] = sorted(retired | set(current_ids))
    history = run.meta.setdefault("campaign_history", [])
    history.append({
        "archived_at": _now(),
        "archive_path": relative_archive.as_posix(),
        "run_count": len(current_ids),
        "run_ids_sha256": ids_digest,
        "run_manifest_content_hash": manifest.content_hash,
        "raw_results_content_hash": raw.content_hash,
        "payload_sha256": file_hash(raw.payload_path),
    })
    run.save_meta()
    return archive
