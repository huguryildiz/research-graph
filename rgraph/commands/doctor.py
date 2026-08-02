"""`rgraph doctor` — preflight the assignment before a provider is trusted."""

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
    Provider,
    assignability,
    load_kit,
    resolve_assignment,
)
from rgraph.render import (
    body_text,
    console,
    marked,
    muted,
    render_error,
    render_next_action,
    section,
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


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "doctor",
        help="preflight providers, login, assignment and models",
        description=(
            "Check the effective assignment, provider executables, login state and "
            "role capabilities before a unit runs. Model names remain UNVERIFIED "
            "unless --probe-models makes a small real provider call."
        ),
        epilog=(
            "Examples:\n"
            "  rgraph doctor\n"
            "  rgraph doctor --probe-models\n"
            "  rgraph doctor --probe-models --timeout 90"
        ),
    )
    parser.add_argument(
        "--probe-models",
        action="store_true",
        help="make one minimal real call per distinct provider/model assignment",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        metavar="SECONDS",
        help="timeout for each login or model probe (default: 60)",
    )
    parser.set_defaults(handler=handle)


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


def inspect(args) -> list[Finding]:
    if args.timeout < 1:
        raise ConfigError("--timeout must be at least 1 second")
    root = pathlib.Path(args.root)
    assignment_path = resolve_assignment(root)
    if assignment_path is None:
        raise ConfigError("no assignment found; run `rgraph setup` first")
    kit = load_kit(root, assignment=assignment_path)
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
                findings.append(_login(provider, args.timeout))

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
        from rgraph.commands.setup import separation_warnings

        for warning in separation_warnings(kit, kit.assignment):
            findings.append(Finding("FAIL", "Gate viability", warning, True))

    assignments = {
        (item.provider, item.model, item.effort): item
        for item in kit.assignment.values()
        if item.provider in kit.providers
    }
    if args.probe_models:
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
            for provider_id, _model, _effort in sorted(assignments):
                provider = kit.providers[provider_id]
                findings.append(
                    _probe(provider, assignments[(provider_id, _model, _effort)], args.timeout, probe_dir)
                )
    else:
        for provider_id, model, _effort in sorted(assignments):
            findings.append(Finding(
                "UNVERIFIED",
                f"{provider_id}/{model} model",
                "the CLI exposes no provider-neutral model catalogue; rerun with "
                "`rgraph doctor --probe-models` for a small real call.",
            ))
    return findings


def handle(args) -> int:
    try:
        findings = inspect(args)
    except ConfigError as exc:
        render_error(str(exc))
        console.print()
        render_next_action("rgraph setup")
        return 2

    section("Provider preflight")
    for finding in findings:
        console.print(marked(finding.status, finding.label))
        muted(finding.detail, indent="        ")
    blockers = [finding for finding in findings if finding.blocking]
    console.print()
    section("Result")
    if blockers:
        body_text(f"BLOCKED — {len(blockers)} preflight failure(s) must be fixed.")
        console.print()
        render_next_action("rgraph setup")
        return 2
    body_text("READY — the assignment can be invoked with the caveats shown above.")
    console.print()
    run = pathlib.Path(args.run)
    render_next_action("rgraph status" if (run / "meta.json").exists() else "rgraph init")
    return 0
