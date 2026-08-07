"""Preflight: what the assignment can actually do before a unit runs.

Everything here is either free (reading PATH, comparing capabilities) or a
declared login check. The one operation that spends a model call — the model
probe — is separated out so a caller can show it, price it, and ask first.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

from rgraph.config import (
    ROLE_REQUIRES,
    ROLES,
    Assignment,
    ConfigError,
    Kit,
    Provider,
    assignability,
    load_kit,
    resolve_assignment,
)
from rgraph.runner import build_argv

PROBE_TEXT = (
    "Reply with exactly RGRAPH_MODEL_OK. Do not read or modify files and do not use tools."
)


@dataclass(frozen=True)
class Finding:
    status: str
    label: str
    detail: str
    blocking: bool = False


def _excerpt(completed: subprocess.CompletedProcess) -> str:
    text = (completed.stderr or completed.stdout or "").strip()
    if not text:
        return f"exit {completed.returncode}"
    return " ".join(text.split())[:240]


def _login(provider: Provider, timeout: int) -> Finding:
    if not provider.login_check:
        return Finding(
            "UNVERIFIED",
            f"{provider.id} login",
            "providers.yaml declares no non-interactive login check.",
        )
    try:
        completed = subprocess.run(
            list(provider.login_check),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return Finding(
            "FAIL",
            f"{provider.id} login",
            f"login check timed out after {timeout}s; run {' '.join(provider.login_check)} manually.",
            True,
        )
    except OSError as exc:
        return Finding(
            "FAIL", f"{provider.id} login", f"login check could not start: {exc}", True
        )
    if completed.returncode != 0:
        return Finding(
            "FAIL",
            f"{provider.id} login",
            f"login check failed ({_excerpt(completed)}). Run {' '.join(provider.login_check)}.",
            True,
        )
    return Finding("PASS", f"{provider.id} login", "non-interactive login check succeeded.")


def _probe(
    provider: Provider,
    assignment: Assignment,
    timeout: int,
    probe_dir: pathlib.Path,
) -> Finding:
    label = f"{provider.id}/{assignment.model} model"
    if provider.kind != "cli":
        return Finding(
            "UNVERIFIED", label, "web/manual providers have no executable model probe."
        )
    argv = build_argv(provider, assignment)
    if not argv:
        return Finding("FAIL", label, "provider has no executable command template.", True)
    try:
        completed = subprocess.run(
            argv,
            input=PROBE_TEXT,
            cwd=probe_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return Finding(
            "FAIL", label, f"provider call timed out after {timeout}s.", True
        )
    except OSError as exc:
        return Finding("FAIL", label, f"provider call could not start: {exc}", True)
    if completed.returncode != 0:
        return Finding(
            "FAIL",
            label,
            f"provider rejected or could not run this model ({_excerpt(completed)}).",
            True,
        )
    return Finding(
        "PASS",
        label,
        "the configured provider accepted this model and returned successfully; "
        "this does not establish response quality or scientific correctness.",
    )


def probe_targets(kit: Kit) -> list[Assignment]:
    """The distinct provider/model/effort calls one probe campaign would make.

    Two roles on the same model are one call, and that is the number a person is
    asked to approve — not the number of roles.
    """
    seen: dict[tuple[str, str, str | None], Assignment] = {}
    for item in kit.assignment.values():
        if item.provider in kit.providers:
            seen.setdefault((item.provider, item.model, item.effort), item)
    return [seen[key] for key in sorted(seen, key=lambda k: (k[0], k[1], k[2] or ""))]


def probe_plan(kit: Kit) -> list[dict]:
    """The exact calls, argv included, so an approval names what it approves."""
    plan = []
    for assignment in probe_targets(kit):
        provider = kit.providers[assignment.provider]
        plan.append({
            "provider": assignment.provider,
            "model": assignment.model,
            "effort": assignment.effort,
            "kind": provider.kind,
            "command": build_argv(provider, assignment) if provider.kind == "cli" else [],
            "roles": sorted(
                role for role, item in kit.assignment.items()
                if (item.provider, item.model, item.effort)
                == (assignment.provider, assignment.model, assignment.effort)
            ),
        })
    return plan


def run_probes(kit: Kit, timeout: int, budget: int) -> list[Finding]:
    """Spend at most `budget` real provider calls, one per distinct assignment."""
    targets = probe_targets(kit)
    if budget < len(targets):
        raise ConfigError(
            f"the approved budget of {budget} call(s) is below the "
            f"{len(targets)} distinct provider/model call(s) this probe would make"
        )
    findings: list[Finding] = []
    spent = 0
    with tempfile.TemporaryDirectory(prefix="rgraph-model-probe-") as raw_dir:
        probe_dir = pathlib.Path(raw_dir)
        # Codex refuses a non-repository working directory. The empty repo
        # also ensures no project instructions or user files enter a probe.
        try:
            subprocess.run(
                ["git", "init", "-q"], cwd=probe_dir, timeout=10,
                capture_output=True, text=True, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            pass
        for assignment in targets:
            if spent >= budget:
                findings.append(Finding(
                    "UNVERIFIED",
                    f"{assignment.provider}/{assignment.model} model",
                    "the approved call budget was reached before this probe ran.",
                ))
                continue
            spent += 1
            findings.append(
                _probe(kit.providers[assignment.provider], assignment, timeout, probe_dir)
            )
    return findings


def load_assigned_kit(root: pathlib.Path) -> tuple[Kit, pathlib.Path]:
    assignment_path = resolve_assignment(root)
    if assignment_path is None:
        raise ConfigError("no assignment found; run `rgraph setup` first")
    return load_kit(root, assignment=assignment_path), assignment_path


def inspect_assignment(
    root: pathlib.Path | str, *, timeout: int = 60, probe_models: bool = False,
    probe_budget: int | None = None,
) -> list[Finding]:
    if timeout < 1:
        raise ConfigError("--timeout must be at least 1 second")
    kit, assignment_path = load_assigned_kit(pathlib.Path(root))
    findings = [
        Finding("PASS", "Assignment", f"loaded {assignment_path}"),
    ]

    missing = [role for role in ROLES if role not in kit.assignment]
    if missing:
        findings.append(Finding(
            "FAIL", "Assignment roles", f"missing {', '.join(missing)}; run `rgraph setup`.", True
        ))
    else:
        findings.append(Finding("PASS", "Assignment roles", "all six roles are assigned."))

    used: dict[str, list[str]] = {}
    for role, assignment in kit.assignment.items():
        used.setdefault(assignment.provider, []).append(role)

    for provider_id, roles in sorted(used.items()):
        provider = kit.providers.get(provider_id)
        if provider is None:
            findings.append(Finding(
                "FAIL", provider_id, f"unknown provider assigned to {', '.join(roles)}.", True
            ))
            continue
        if provider.kind == "web":
            findings.append(Finding(
                "CAVEAT",
                f"{provider_id} executable",
                "manual web provider; rgraph cannot execute it or verify its session.",
            ))
        elif not provider.invoke:
            findings.append(Finding(
                "FAIL", f"{provider_id} executable", "providers.yaml has no invoke command.", True
            ))
        else:
            executable = shutil.which(provider.invoke)
            if executable is None:
                findings.append(Finding(
                    "FAIL",
                    f"{provider_id} executable",
                    f"'{provider.invoke}' is not on PATH; install it or fix PATH, then rerun doctor.",
                    True,
                ))
            else:
                findings.append(Finding(
                    "PASS", f"{provider_id} executable", str(pathlib.Path(executable))
                ))
                findings.append(_login(provider, timeout))

        for role in roles:
            state = assignability(provider, role)
            if state == "ok":
                findings.append(Finding(
                    "PASS", f"{role} capability", f"{provider_id} supplies the required capabilities."
                ))
            elif state == "manual":
                findings.append(Finding(
                    "CAVEAT", f"{role} capability", f"{provider_id} requires human file relay."
                ))
            else:
                missing_caps = ROLE_REQUIRES[role] - provider.capabilities
                findings.append(Finding(
                    "FAIL",
                    f"{role} capability",
                    f"{provider_id} lacks {', '.join(sorted(missing_caps))}.",
                    True,
                ))

    # A configuration that collapses either mandatory reviewer/producer pair
    # can execute, but it can never finish. Treat that as a preflight failure.
    if not missing:
        from rgraph.services.providers import separation_warnings

        for warning in separation_warnings(kit, kit.assignment):
            findings.append(Finding("FAIL", "Gate viability", warning, True))

    targets = probe_targets(kit)
    if probe_models:
        findings.extend(run_probes(
            kit, timeout, len(targets) if probe_budget is None else probe_budget
        ))
    else:
        for assignment in targets:
            findings.append(Finding(
                "UNVERIFIED",
                f"{assignment.provider}/{assignment.model} model",
                "the CLI exposes no provider-neutral model catalogue; rerun with "
                "`rgraph doctor --probe-models` for a small real call.",
            ))
    return findings


def findings_view(findings: list[Finding]) -> dict:
    blockers = [item for item in findings if item.blocking]
    return {
        "findings": [
            {
                "status": item.status,
                "label": item.label,
                "detail": item.detail,
                "blocking": item.blocking,
            }
            for item in findings
        ],
        "blocked": bool(blockers),
        "blocking_count": len(blockers),
        "summary": (
            f"BLOCKED — {len(blockers)} preflight failure(s) must be fixed."
            if blockers else
            "READY — the assignment can be invoked with the caveats shown."
        ),
    }
