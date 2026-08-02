"""The run directory: what exists, what validates, what the gates recorded."""

from __future__ import annotations

import json
import hashlib
import pathlib
from dataclasses import dataclass, field

from rgraph.config import ARTIFACTS, PAYLOAD_ARTIFACTS, Kit
from rgraph.hashing import document_hash
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
    def declared_hash(self) -> str | None:
        """The digest the document actually has today, envelope included.

        Without recomputing this, the chain only proves that the recorded hashes
        agree with each other: editing an artifact and leaving its
        `content_hash` alone would pass every gate.
        """
        if self.document is None:
            return None
        return document_hash(self.document)

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
    # The shipped example-run is a fixture, not a workspace. Every command that
    # writes goes through here, so the guard lives here rather than in each one.
    read_only: bool = False

    def refuse_write(self, what: str) -> bool:
        if self.read_only:
            # Imported lazily to keep the data model independent at load time
            # while ensuring this user-facing guard uses the shared CLI voice.
            from rgraph.render import muted

            muted(f"Note: {self.root.name}/ is a shipped fixture; {what} was not written.")
        return self.read_only

    @property
    def meta_mismatch(self) -> str | None:
        """meta.json against its own digest.

        The revision budget lives here, so a run whose meta is unsigned can have
        an exhausted gate reopened by editing `used` back to zero. An older run
        that carries no digest yet is not accused of anything; `rgraph seal`
        stamps one.
        """
        declared = self.meta.get("content_hash")
        if declared is None:
            return None
        actual = document_hash(self.meta)
        if declared == actual:
            return None
        return (
            f"meta.json no longer matches its content_hash: "
            f"declared {str(declared)[:19]}..., actual {actual[:19]}..."
        )

    def get(self, artifact_id: str) -> Artifact:
        return self.artifacts[artifact_id]

    def present_ids(self) -> list[str]:
        return [a.id for a in self.artifacts.values() if a.present]

    def gate_record(self, gate_id: str) -> dict | None:
        path = self.root / "gates" / f"{gate_id}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def write_gate_record(self, record: dict) -> pathlib.Path | None:
        if self.refuse_write(f"the {record['gate_id']} record"):
            return None
        directory = self.root / "gates"
        directory.mkdir(exist_ok=True)
        path = directory / f"{record['gate_id']}.json"
        payload = (json.dumps(record, indent=2) + "\n").encode("utf-8")
        if path.exists():
            previous = path.read_bytes()
            if previous == payload:
                return path
            digest = hashlib.sha256(previous).hexdigest()
            history = directory / "history"
            history.mkdir(exist_ok=True)
            archived = history / f"{record['gate_id']}-{digest}.json"
            if not archived.exists():
                archived.write_bytes(previous)
        path.write_bytes(payload)
        return path

    def save_meta(self) -> None:
        if self.refuse_write("meta.json"):
            return
        self.meta["content_hash"] = document_hash(self.meta)
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

    gates_dir = root / "gates"
    if gates_dir.exists():
        for path in sorted(gates_dir.glob("*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise RunError(f"{path} is not valid JSON: {exc}") from exc
            record_errors = reg.validate("gate_record", record)
            if record_errors:
                first = record_errors[0]
                raise RunError(
                    f"{path.name} is invalid: {first.path}: {first.message}"
                )
    return Run(root=root, meta=meta, artifacts=artifacts)
