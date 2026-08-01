"""The run directory: what exists, what validates, what the gates recorded."""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field

from rgraph.config import ARTIFACTS, PAYLOAD_ARTIFACTS, Kit
from rgraph.hashing import content_hash
from rgraph.schemas import SchemaError, registry


class RunError(Exception):
    pass


@dataclass
class Artifact:
    id: str
    path: pathlib.Path
    document: dict | None = None
    payload_path: pathlib.Path | None = None
    errors: list[SchemaError] = field(default_factory=list)

    @property
    def present(self) -> bool:
        return self.document is not None

    @property
    def body(self) -> dict:
        return (self.document or {}).get("body", {})

    @property
    def content_hash(self) -> str | None:
        """The digest the file claims. What the chain links against."""
        return (self.document or {}).get("content_hash")

    @property
    def body_hash(self) -> str | None:
        """The digest the body actually has today.

        Without recomputing this, the chain only proves that the recorded hashes
        agree with each other: editing a body and leaving its `content_hash`
        alone would pass every gate.
        """
        if self.document is None:
            return None
        return content_hash(self.document.get("body", {}))

    @property
    def inputs(self) -> list[dict]:
        return (self.document or {}).get("inputs", [])

    @property
    def identity(self) -> str | None:
        return ((self.document or {}).get("produced_by") or {}).get("identity")


@dataclass
class Run:
    root: pathlib.Path
    meta: dict
    artifacts: dict[str, Artifact]

    def get(self, artifact_id: str) -> Artifact:
        return self.artifacts[artifact_id]

    def present_ids(self) -> list[str]:
        return [a.id for a in self.artifacts.values() if a.present]

    def gate_record(self, gate_id: str) -> dict | None:
        path = self.root / "gates" / f"{gate_id}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def write_gate_record(self, record: dict) -> pathlib.Path:
        directory = self.root / "gates"
        directory.mkdir(exist_ok=True)
        path = directory / f"{record['gate_id']}.json"
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        return path

    def save_meta(self) -> None:
        (self.root / "meta.json").write_text(
            json.dumps(self.meta, indent=2) + "\n", encoding="utf-8"
        )


def _artifact_paths(root: pathlib.Path, artifact_id: str):
    payload = PAYLOAD_ARTIFACTS.get(artifact_id)
    if payload is None:
        return root / f"{artifact_id}.json", None
    return root / f"{artifact_id}.meta.json", root / payload


def load_run(root: pathlib.Path | str, kit: Kit) -> Run:
    root = pathlib.Path(root)
    meta_path = root / "meta.json"
    if not meta_path.exists():
        raise RunError(f"not a run directory: {meta_path} is missing")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RunError(f"{meta_path} is not valid JSON: {exc}") from exc
    reg = registry(kit.root)
    meta_errors = reg.validate("run_meta", meta)
    if meta_errors:
        raise RunError(
            f"meta.json is invalid: {meta_errors[0].path}: {meta_errors[0].message}"
        )

    artifacts: dict[str, Artifact] = {}
    for artifact_id in ARTIFACTS:
        path, payload = _artifact_paths(root, artifact_id)
        artifact = Artifact(id=artifact_id, path=path, payload_path=payload)
        if path.exists():
            try:
                artifact.document = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                artifact.errors = [SchemaError(path="<file>", message=f"invalid JSON: {exc}")]
            else:
                artifact.errors = reg.validate(artifact_id, artifact.document)
        artifacts[artifact_id] = artifact
    return Run(root=root, meta=meta, artifacts=artifacts)
