"""Offline verification of source files committed inside a retained Git bundle."""

from __future__ import annotations

import hashlib
import pathlib
import subprocess
import tempfile
from dataclasses import dataclass


@dataclass(frozen=True)
class CodeProvenanceIssue:
    code: str
    detail: str
    fix: str


def _safe_relative(value: object, *, prefix: str | None = None) -> pathlib.PurePosixPath | None:
    if not isinstance(value, str):
        return None
    path = pathlib.PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        return None
    if prefix is not None and path.parts[0] != prefix:
        return None
    return path


def verify_committed_source(run_root: pathlib.Path, document: dict) -> list[CodeProvenanceIssue]:
    """Verify v2 code provenance without a network connection.

    Version 1 remains readable for compatibility. Version 2 binds a portable
    Git bundle, a full commit ID and the repository path of every run-side
    source file.
    """
    if document.get("version", 1) < 2:
        return []

    body = document.get("body", {})
    issues: list[CodeProvenanceIssue] = []
    if body.get("dirty") is not False:
        issues.append(CodeProvenanceIssue(
            "DIRTY CODE", "version 2 requires a clean committed source snapshot",
            "record a clean commit and retain its Git bundle",
        ))

    bundle_value = body.get("bundle_path")
    bundle_relative = _safe_relative(bundle_value, prefix="code")
    if bundle_relative is None or bundle_relative.suffix != ".bundle":
        return issues + [CodeProvenanceIssue(
            "BUNDLE PATH INVALID", f"{bundle_value!r} is not a safe .bundle path below run/code",
            "store the Git bundle below run/code and record that relative path",
        )]
    bundle = (run_root / bundle_relative).resolve()
    try:
        bundle.relative_to(run_root.resolve())
    except ValueError:
        return issues + [CodeProvenanceIssue(
            "BUNDLE PATH INVALID", f"{bundle_value!r} escapes the run directory",
            "store the Git bundle below run/code",
        )]
    if not bundle.is_file():
        return issues + [CodeProvenanceIssue(
            "BUNDLE MISSING", f"{bundle_value} is not present",
            "restore the recorded Git bundle or rerun the producing unit",
        )]
    actual_bundle_hash = hashlib.sha256(bundle.read_bytes()).hexdigest()
    recorded_bundle_hash = body.get("bundle_sha256")
    if isinstance(recorded_bundle_hash, str):
        recorded_bundle_hash = recorded_bundle_hash.removeprefix("sha256:")
    if actual_bundle_hash != recorded_bundle_hash:
        return issues + [CodeProvenanceIssue(
            "BUNDLE DIGEST MISMATCH", f"{bundle_value} does not match its recorded digest",
            "restore the bundle or re-record code_commit and rerun",
        )]

    commit = body.get("commit")
    if not isinstance(commit, str) or len(commit) != 40:
        return issues + [CodeProvenanceIssue(
            "COMMIT INVALID", "version 2 requires a full 40-hex commit identifier",
            "record the full commit identifier contained by the Git bundle",
        )]

    for item in body.get("files", []):
        repo_path = _safe_relative(item.get("repo_path"))
        if repo_path is None or ".git" in repo_path.parts:
            issues.append(CodeProvenanceIssue(
                "REPOSITORY PATH INVALID", f"{item.get('repo_path')!r} is not a safe repository path",
                "record each source file's relative path inside the committed repository",
            ))
    if issues:
        return issues

    try:
        with tempfile.TemporaryDirectory(prefix="rgraph-code-") as temporary:
            checkout = pathlib.Path(temporary) / "repo"
            cloned = subprocess.run(
                ["git", "clone", "--quiet", "--no-checkout", str(bundle), str(checkout)],
                capture_output=True, text=True, timeout=30, check=False,
            )
            if cloned.returncode != 0:
                detail = (cloned.stderr or cloned.stdout).strip() or "git clone failed"
                return issues + [CodeProvenanceIssue(
                    "BUNDLE INVALID", detail,
                    "create a complete Git bundle containing the recorded commit",
                )]
            commit_check = subprocess.run(
                ["git", "-C", str(checkout), "cat-file", "-e", f"{commit}^{{commit}}"],
                capture_output=True, text=True, timeout=10, check=False,
            )
            if commit_check.returncode != 0:
                return issues + [CodeProvenanceIssue(
                    "COMMIT MISSING", f"commit {commit} is not contained in {bundle_value}",
                    "bundle the exact clean commit recorded by code_commit",
                )]
            for item in body.get("files", []):
                repo_path = item["repo_path"]
                shown = subprocess.run(
                    ["git", "-C", str(checkout), "show", f"{commit}:{repo_path}"],
                    capture_output=True, timeout=10, check=False,
                )
                if shown.returncode != 0:
                    issues.append(CodeProvenanceIssue(
                        "COMMITTED FILE MISSING",
                        f"{repo_path} is not present at commit {commit}",
                        "commit the exact executed source and rebuild the Git bundle",
                    ))
                    continue
                actual = hashlib.sha256(shown.stdout).hexdigest()
                if actual != item.get("sha256"):
                    issues.append(CodeProvenanceIssue(
                        "COMMITTED DIGEST MISMATCH",
                        f"{repo_path} at commit {commit} does not match {item.get('path')}",
                        "commit the exact executed bytes, then rebuild and re-record the bundle",
                    ))
    except FileNotFoundError:
        issues.append(CodeProvenanceIssue(
            "GIT UNAVAILABLE", "git is required to inspect a version 2 source bundle",
            "install Git and rerun the integrity check",
        ))
    except (OSError, subprocess.SubprocessError) as exc:
        issues.append(CodeProvenanceIssue(
            "BUNDLE CHECK FAILED", str(exc),
            "inspect the Git installation and retained source bundle, then rerun",
        ))
    return issues
