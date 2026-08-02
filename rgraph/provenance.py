"""Provenance: recorded input hashes versus what the files say today."""

from __future__ import annotations

from dataclasses import dataclass, field

from rgraph.config import Kit
from rgraph.hashing import file_hash
from rgraph.run import Artifact, Run


@dataclass(frozen=True)
class TraceLink:
    label: str
    detail: str
    status: str = ""


@dataclass
class TraceChain:
    claim: str
    links: list[TraceLink] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.missing


def hash_mismatch(run: Run, artifact: Artifact) -> list[tuple[str, str, str]]:
    out = []
    for reference in artifact.inputs:
        upstream = run.artifacts.get(reference["artifact_id"])
        if upstream is None or not upstream.present:
            out.append((reference["artifact_id"], reference["content_hash"], "absent"))
        elif upstream.content_hash != reference["content_hash"]:
            out.append((reference["artifact_id"], reference["content_hash"], upstream.content_hash))
    return out


def body_mismatch(artifact: Artifact) -> str | None:
    """The declared `content_hash` against the digest the document actually has.

    An artifact that is not checked against its own digest cannot anchor a chain:
    every downstream reference would still agree while the file underneath it had
    changed. This is the check that makes editing a file by hand visible, and it
    covers the envelope as well as the body — rewriting `produced_by` or
    dropping an `inputs[]` reference is an edit like any other.
    """
    if not artifact.present:
        return None
    declared = artifact.content_hash
    if declared is None:
        return None
    actual = artifact.declared_hash
    if declared == actual:
        return None
    return (
        f"file no longer matches its content_hash: "
        f"declared {str(declared)[:19]}..., actual {str(actual)[:19]}..."
    )


def payload_mismatch(run: Run, artifact: Artifact) -> str | None:
    if artifact.payload_path is None or not artifact.present:
        return None
    if not artifact.payload_path.exists():
        return f"{artifact.payload_path.name} is missing"
    recorded = artifact.body.get("payload_sha256")
    actual = file_hash(artifact.payload_path).removeprefix("sha256:")
    if recorded == actual:
        return None
    return (
        f"{artifact.payload_path.name} digest changed: recorded {str(recorded)[:12]}..., "
        f"actual {actual[:12]}..."
    )


def stale_artifacts(run: Run) -> dict[str, list[str]]:
    stale: dict[str, list[str]] = {}
    for artifact in run.artifacts.values():
        if not artifact.present:
            continue
        causes = [f"{name} changed" for name, _, _ in hash_mismatch(run, artifact)]
        body = body_mismatch(artifact)
        if body:
            causes.append(body)
        payload = payload_mismatch(run, artifact)
        if payload:
            causes.append(payload)
        if causes:
            stale[artifact.id] = causes
    for _ in range(len(run.artifacts)):
        grew = False
        for artifact in run.artifacts.values():
            if not artifact.present or artifact.id in stale:
                continue
            upstream = [r["artifact_id"] for r in artifact.inputs if r["artifact_id"] in stale]
            if upstream:
                stale[artifact.id] = [f"{name} is stale" for name in upstream]
                grew = True
        if not grew:
            break
    return stale


def invalidated_gates(run: Run, kit: Kit) -> dict[str, list[str]]:
    stale = stale_artifacts(run)
    out: dict[str, list[str]] = {}
    for gate in kit.gates.values():
        record = run.gate_record(gate.id)
        if record is None or record.get("outcome") not in ("pass", "release"):
            continue
        causes = [
            f"{name} changed after {gate.id} passed" for name in gate.inputs if name in stale
        ]
        for reference in record.get("inputs", []):
            current = run.artifacts.get(reference["artifact_id"])
            if current and current.present and current.content_hash != reference["content_hash"]:
                causes.append(f"{reference['artifact_id']} changed after {gate.id} passed")
        if causes:
            out[gate.id] = sorted(set(causes))
    return out


def trace(run: Run, kit: Kit, claim_id: str) -> TraceChain:
    chain = TraceChain(claim=claim_id)
    cem = run.get("claim_evidence_map")
    claim = next((c for c in cem.body.get("claims", []) if c["claim_id"] == claim_id), None)
    if claim is None:
        chain.missing.append(f"claim {claim_id} is not in claim_evidence_map")
        return chain

    manuscript = run.get("manuscript")
    section = next(
        (s for s in manuscript.body.get("sections", []) if claim_id in s.get("claim_ids", [])),
        None,
    )
    chain.links.append(
        TraceLink("manuscript.md", section["heading"] if section else "not located")
    )
    if section is None:
        chain.missing.append(f"{claim_id} appears in no manuscript section")

    result_ids = claim["supported_by"]["result_ids"]
    chain.links.append(TraceLink(
        "claim_evidence_map.json",
        f"{claim_id} -> " + (", ".join(result_ids) if result_ids else "no result"),
    ))

    stats = run.get("statistical_report")
    for result_id in result_ids:
        estimate = next(
            (e for e in stats.body.get("estimates", []) if e["result_id"] == result_id), None
        )
        if estimate is None:
            chain.missing.append(f"{result_id} is not in statistical_report")
            continue
        chain.links.append(TraceLink(
            "statistical_report.json",
            f"estimate {estimate['estimate']} | 95% CI "
            f"[{estimate['ci_lower']}, {estimate['ci_upper']}] | n {estimate['n']}",
        ))

    raw = run.get("raw_results")
    run_ids = raw.body.get("run_ids", [])
    chain.links.append(TraceLink("raw_results.jsonl", f"{len(run_ids)} records"))
    if not run_ids:
        chain.missing.append("raw_results records no run")

    manifest = run.get("run_manifest")
    manifest_status = "HASH VALID" if not hash_mismatch(run, manifest) else "HASH CHANGED"
    chain.links.append(TraceLink("run_manifest.json", "", manifest_status))
    if manifest_status != "HASH VALID":
        chain.missing.append("run_manifest inputs changed")

    frozen = "FROZEN" if run.meta.get("protocol") == "FROZEN" else "OPEN"
    chain.links.append(TraceLink("frozen_protocol.json", "", frozen))
    if frozen != "FROZEN":
        chain.missing.append("protocol is not frozen")

    record = run.gate_record("M1")
    if record is None:
        chain.missing.append("M1 has no gate record")
    else:
        level = (record.get("separation_level") or "unknown").replace("_", "-").upper()
        chain.links.append(TraceLink("gates/M1.json", "", f"{level} {record['outcome'].upper()}"))
    return chain
