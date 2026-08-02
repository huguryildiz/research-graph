"""Per-gate content checks. Each returns findings; an empty list means PASS."""

from __future__ import annotations

import re
import pathlib
import urllib.error
import urllib.request
from dataclasses import dataclass

from rgraph.config import Gate, Kit
from rgraph.hashing import file_hash
from rgraph.render import muted
from rgraph.run import Run

DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")


@dataclass(frozen=True)
class CheckFinding:
    ref: str
    code: str
    detail: str
    fix: str = ""


def resolve_doi(doi: str, timeout: float = 5.0) -> str:
    """`resolved`, `not_found`, or `unreachable`.

    A DOI that does not exist and a DOI we could not ask about are different
    facts. Collapsing them into one would have this check tell an offline user
    to delete a citation that is perfectly good.
    """
    request = urllib.request.Request(f"https://doi.org/{doi}", method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return "resolved" if 200 <= response.status < 400 else "not_found"
    except urllib.error.HTTPError as exc:
        return "not_found" if exc.code in (404, 410) else "unreachable"
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return "unreachable"


def _source_support(run: Run, kit: Kit, gate: Gate, online: bool = False) -> list[CheckFinding]:
    corpus = {s["source_id"]: s for s in run.get("corpus_snapshot").body.get("sources", [])}
    findings: list[CheckFinding] = []
    referenced: set[str] = set()
    unreachable: list[str] = []

    rows = [
        (row["claim_id"], row["source_id"], row.get("locator"))
        for row in run.get("evidence_matrix").body.get("rows", [])
    ] + [
        (edge["from_claim"], edge["source_id"], edge.get("locator"))
        for edge in run.get("kg_snapshot").body.get("edges", [])
    ]
    for claim_id, source_id, locator in rows:
        referenced.add(source_id)
        if source_id not in corpus:
            findings.append(CheckFinding(
                claim_id, "SOURCE MISSING", f"source {source_id} is not in corpus_snapshot",
                f"add {source_id} to the corpus snapshot or drop the claim"))
            continue
        if not locator or not locator.get("value"):
            findings.append(CheckFinding(
                claim_id, "SUPPORT LOCATOR MISSING",
                "Source exists, but no page, section, table, or passage\nsupports this claim.",
                "add a direct locator or narrow the claim"))

    for source_id in sorted(referenced):
        source = corpus.get(source_id)
        if source is None:
            continue
        doi = source.get("doi")
        if not doi or not DOI_RE.match(doi):
            findings.append(CheckFinding(
                source_id, "SOURCE NOT RESOLVED", f"DOI: {doi}",
                f"replace or remove source {source_id}"))
        elif source.get("retracted"):
            findings.append(CheckFinding(
                source_id, "SOURCE RETRACTED", f"DOI: {doi}",
                f"remove source {source_id} and every claim that rests on it"))
        elif online:
            state = resolve_doi(doi)
            if state == "not_found":
                findings.append(CheckFinding(
                    source_id, "SOURCE NOT RESOLVED", f"DOI: {doi}",
                    f"replace or remove source {source_id}"))
            elif state == "unreachable":
                unreachable.append(source_id)
    if unreachable:
        muted(
            f"Note: {len(unreachable)} DOI(s) could not be reached "
            f"({', '.join(unreachable)}); they were not judged."
        )
        muted("Re-run with a network connection to check them.")
        findings.append(CheckFinding(
            "doi.org", "DOI CHECK INCOMPLETE",
            f"the network could not reach {len(unreachable)} referenced DOI(s)",
            "re-run with a network connection to complete the requested online check",
        ))
    return findings


def _design_traceability(run: Run, kit: Kit, gate: Gate, online: bool = False):
    accepted = {
        h["hypothesis_id"]
        for h in run.get("hypothesis_registry").body.get("hypotheses", [])
        if h["decision"] == "accepted"
    }
    return [
        CheckFinding(
            experiment["experiment_id"], "HYPOTHESIS NOT REGISTERED",
            f"{experiment['hypothesis_id']} is not an accepted hypothesis",
            "register the hypothesis, or point the experiment at an accepted one")
        for experiment in run.get("design_protocol").body.get("experiments", [])
        if experiment["hypothesis_id"] not in accepted
    ]


def _freeze_completeness(run: Run, kit: Kit, gate: Gate, online: bool = False):
    body = run.get("frozen_protocol").body
    findings = []
    if len(body.get("seeds", [])) != body.get("replications"):
        findings.append(CheckFinding(
            "frozen_protocol", "FREEZE INCOMPLETE",
            f"{len(body.get('seeds', []))} seeds recorded for "
            f"{body.get('replications')} replications",
            "list one seed per replication before freezing"))
    for field_name in ("stopping_rule", "multiplicity_plan", "analysis_plan"):
        if not (body.get(field_name) or "").strip():
            findings.append(CheckFinding(
                "frozen_protocol", "FREEZE INCOMPLETE", f"{field_name} is empty",
                f"record the {field_name.replace('_', ' ')} before freezing"))
    return findings


def _run_integrity(run: Run, kit: Kit, gate: Gate, online: bool = False):
    manifest = run.get("run_manifest").body
    frozen = run.get("frozen_protocol").body
    findings = []
    if manifest.get("replications") != len(manifest.get("runs", [])):
        findings.append(CheckFinding(
            "run_manifest", "N MISMATCH",
            f"declares {manifest.get('replications')} replications "
            f"but records {len(manifest.get('runs', []))} runs",
            "re-run the missing replications or correct the count"))
    if sorted(manifest.get("seeds", [])) != sorted(frozen.get("seeds", [])):
        findings.append(CheckFinding(
            "run_manifest", "SEED SET MISMATCH",
            "run seeds differ from the seeds fixed in frozen_protocol",
            "run exactly the frozen seeds, or return to H4 and re-freeze"))
    for dataset in run.get("data_manifest").body.get("datasets", []):
        relative = pathlib.PurePosixPath(dataset["path"])
        if (
            relative.is_absolute() or not relative.parts
            or relative.parts[0] != "data" or ".." in relative.parts
        ):
            findings.append(CheckFinding(
                dataset["dataset_id"], "DATASET PATH INVALID",
                f"{dataset['path']} is not a safe path below run/data",
                "store the dataset below run/data and record that relative path"))
            continue
        path = (run.root / relative).resolve()
        try:
            path.relative_to(run.root.resolve())
        except ValueError:
            findings.append(CheckFinding(
                dataset["dataset_id"], "DATASET PATH INVALID",
                f"{dataset['path']} escapes the run directory",
                "store the dataset below run/data and record that relative path"))
            continue
        if not path.is_file():
            findings.append(CheckFinding(
                dataset["dataset_id"], "DATASET MISSING",
                f"{dataset['path']} is not present",
                "restore the recorded dataset or rerun the producing unit"))
        elif file_hash(path).removeprefix("sha256:") != dataset["sha256"]:
            findings.append(CheckFinding(
                dataset["dataset_id"], "DIGEST MISMATCH",
                f"{dataset['path']} does not match its recorded digest",
                "restore the dataset or re-record the manifest and re-run"))
        elif path.stat().st_size != dataset["bytes"]:
            findings.append(CheckFinding(
                dataset["dataset_id"], "BYTE COUNT MISMATCH",
                f"{dataset['path']} has {path.stat().st_size} bytes, not {dataset['bytes']}",
                "restore the dataset or correct and reseal the manifest"))
    if run.get("raw_results").body.get("records", 0) < 1:
        findings.append(CheckFinding(
            "raw_results", "N MISMATCH", "no records", "re-run the experiment"))
    return findings


def _statistical_support(run: Run, kit: Kit, gate: Gate, online: bool = False):
    manifest = run.get("run_manifest").body
    ok_runs = sum(1 for r in manifest.get("runs", []) if r["status"] == "ok")
    findings = []
    for estimate in run.get("statistical_report").body.get("estimates", []):
        if not estimate["ci_lower"] < estimate["estimate"] < estimate["ci_upper"]:
            findings.append(CheckFinding(
                estimate["result_id"], "CI MISSING",
                f"estimate {estimate['estimate']} lies outside its own interval "
                f"[{estimate['ci_lower']}, {estimate['ci_upper']}]",
                "recompute the interval from raw results"))
        if estimate["n"] != ok_runs:
            findings.append(CheckFinding(
                estimate["result_id"], "N MISMATCH",
                f"n = {estimate['n']} but {ok_runs} runs completed",
                "recompute from raw_results, or account for the excluded runs"))
    report = run.get("reproduction_report").body
    if report.get("reproduction_rate", 0) < 1.0 and not run.get(
        "verification_report"
    ).body.get("findings"):
        findings.append(CheckFinding(
            "reproduction_report", "N MISMATCH",
            f"reproduction rate {report.get('reproduction_rate')} with no finding recorded",
            "record a verification_report finding that accounts for the gap"))
    return findings


def _claim_support(run: Run, kit: Kit, gate: Gate, online: bool = False):
    results = {e["result_id"] for e in run.get("statistical_report").body.get("estimates", [])}
    sources = {s["source_id"] for s in run.get("corpus_snapshot").body.get("sources", [])}
    limitations = " ".join(run.get("verification_report").body.get("limitations", []))
    findings = []

    # The manuscript and the map have to name the same claims. A section citing
    # a claim the map never registered is unsupported by construction, and a
    # mapped claim nobody makes is bookkeeping rather than evidence.
    sections = run.get("manuscript").body.get("sections", [])
    cited = {claim_id for section in sections for claim_id in section.get("claim_ids", [])}
    mapped = {c["claim_id"] for c in run.get("claim_evidence_map").body.get("claims", [])}
    for claim_id in sorted(cited - mapped):
        findings.append(CheckFinding(
            claim_id, "CLAIM NOT MAPPED",
            "the manuscript cites this claim but claim_evidence_map has no entry for it",
            f"map {claim_id} to a result or a source, or drop the citation"))

    for claim in run.get("claim_evidence_map").body.get("claims", []):
        if claim["claim_id"] not in cited:
            findings.append(CheckFinding(
                claim["claim_id"], "CLAIM UNSUPPORTED",
                "the map registers this claim but no manuscript section makes it",
                "cite the claim in a section, or remove it from the map"))
        support = claim["supported_by"]
        if not support["result_ids"] and not support["source_ids"]:
            findings.append(CheckFinding(
                claim["claim_id"], "CLAIM UNSUPPORTED",
                "no result and no source is mapped to this claim",
                "map the claim to a result, or remove it"))
        for result_id in support["result_ids"]:
            if result_id not in results:
                findings.append(CheckFinding(
                    claim["claim_id"], "RESULT NOT FOUND",
                    f"{result_id} is not in statistical_report",
                    "point at a computed result, or narrow the claim"))
        for source_id in support["source_ids"]:
            if source_id not in sources:
                findings.append(CheckFinding(
                    claim["claim_id"], "SOURCE MISSING",
                    f"{source_id} is not in corpus_snapshot",
                    "cite a snapshotted source"))
        if claim["scope"] == "extrapolation" and claim["claim_id"] not in limitations:
            findings.append(CheckFinding(
                claim["claim_id"], "CLAIM UNSUPPORTED",
                "claim is marked as an extrapolation but no limitation records it",
                "add the extrapolation to verification_report.limitations, "
                "or narrow the claim"))
    return findings


CONTENT_CHECKS = {
    "source_support": _source_support,
    "design_traceability": _design_traceability,
    "freeze_completeness": _freeze_completeness,
    "run_integrity": _run_integrity,
    "statistical_support": _statistical_support,
    "claim_support": _claim_support,
}
