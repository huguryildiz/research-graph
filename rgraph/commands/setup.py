"""`rgraph setup` — detect providers, propose the assignment with the most separation."""

from __future__ import annotations

import pathlib
import shutil
import subprocess

from rgraph.config import (
    ROLE_REQUIRES, ROLES, Assignment, ConfigError, Kit, assignability,
    machine_assignment_path,
)
from rgraph.render import console, render_setup
from rgraph.separation import level_for

PRODUCER_ROLES = ("retrieval", "planning", "execution", "verification", "synthesis")
DEFAULT_MODEL = {
    "claude-code": "sonnet-5",
    "codex": "gpt-5.6",
    "gemini": "gemini-3-pro",
    "ollama": "llama4",
    "grok": "grok-5",
}
ROLE_MODEL = {"planning": "opus-5", "synthesis": "fable-5", "verification": "opus-5"}


def register(subparsers) -> None:
    parser = subparsers.add_parser("setup", help="detect providers and write assignment.yaml")
    parser.add_argument("--preset", help='e.g. "producers=claude-code,reviewer=grok"')
    parser.add_argument("--yes", action="store_true", help="accept the proposal without asking")
    parser.add_argument("--here", action="store_true",
                        help="write ./assignment.yaml for this study only")
    parser.set_defaults(handler=handle)


def parse_preset(text: str) -> dict[str, str]:
    out = {}
    for chunk in text.split(","):
        if "=" not in chunk:
            raise ConfigError(f"malformed preset fragment: {chunk!r}")
        key, value = chunk.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def detect(kit: Kit) -> dict[str, str]:
    states: dict[str, str] = {}
    for provider in kit.providers.values():
        if provider.kind == "web":
            states[provider.id] = "WEB"
            continue
        if provider.invoke is None or shutil.which(provider.invoke) is None:
            states[provider.id] = "NOT INSTALLED"
            continue
        if not provider.login_check:
            states[provider.id] = "FOUND"
            continue
        try:
            completed = subprocess.run(
                list(provider.login_check), capture_output=True, timeout=5, check=False
            )
            states[provider.id] = "FOUND" if completed.returncode == 0 else "FOUND (not logged in)"
        except (OSError, subprocess.SubprocessError):
            states[provider.id] = "FOUND (not logged in)"
    return states


def _model(provider_id: str, role: str) -> str:
    if provider_id == "claude-code":
        return ROLE_MODEL.get(role, DEFAULT_MODEL[provider_id])
    return DEFAULT_MODEL.get(provider_id, "default")


def _capable(kit: Kit, provider_id: str, role: str) -> bool:
    """True when the provider can take the role without human relay."""
    provider = kit.providers.get(provider_id)
    return provider is not None and assignability(provider, role) == "ok"


def propose(kit: Kit, detected: dict[str, str], preset: dict[str, str] | None = None):
    if preset:
        producer = preset.get("producers")
        reviewer = preset.get("reviewer", producer)
        plan = {r: Assignment(r, producer, _model(producer, r)) for r in PRODUCER_ROLES}
        plan["reviewer"] = Assignment("reviewer", reviewer, _model(reviewer, "reviewer"))
        return plan

    available = [p for p, state in detected.items() if state.startswith("FOUND")]
    web = [p for p, state in detected.items() if state == "WEB"]
    if not available:
        available = web[:1] or list(kit.providers)

    producer_pool = [p for p in available if _capable(kit, p, "execution")]
    producer = producer_pool[0] if producer_pool else available[0]

    reviewer_pool = [
        p for p in available + web if p != producer and _capable(kit, p, "reviewer")
    ]
    reviewer = reviewer_pool[0] if reviewer_pool else producer

    plan = {r: Assignment(r, producer, _model(producer, r)) for r in PRODUCER_ROLES}

    # T2 is decided by the verification role over what execution produced, so
    # the two must not resolve to one identity or that gate can never pass.
    verifier_pool = [
        p for p in available if p != producer and _capable(kit, p, "verification")
    ]
    verifier = verifier_pool[0] if verifier_pool else producer
    plan["verification"] = Assignment(
        "verification", verifier, _model(verifier, "verification")
    )

    plan["reviewer"] = Assignment("reviewer", reviewer, _model(reviewer, "reviewer"))
    return plan


def separation_warnings(kit: Kit, plan) -> list[str]:
    """Pairs that a gate requires to differ but this plan collapses into one."""
    out = []
    identity = {
        role: assignment.identity(kit.providers) for role, assignment in plan.items()
    }
    if identity.get("execution") == identity.get("verification"):
        out.append(
            f"T2 cannot pass: execution and verification are both "
            f"{identity['execution']}; T2 is decided by verification over what "
            f"execution produced"
        )
    if identity.get("synthesis") == identity.get("reviewer"):
        out.append(
            f"M1 cannot pass: synthesis and reviewer are both {identity['reviewer']}"
        )
    return out


def capability_conflicts(kit: Kit, plan) -> list[str]:
    """Assignments that cannot work at all. Manual relay is a warning, not a conflict."""
    out = []
    for role, assignment in plan.items():
        provider = kit.providers.get(assignment.provider)
        if provider is None:
            out.append(f"{role}: unknown provider '{assignment.provider}'")
            continue
        if assignability(provider, role) == "blocked":
            missing = ROLE_REQUIRES[role] - provider.capabilities
            out.append(
                f"{role}: '{assignment.provider}' cannot be assigned; "
                f"it lacks {', '.join(sorted(missing))}"
            )
    return out


def manual_roles(kit: Kit, plan) -> list[str]:
    """Assignments that work only with a human relaying files."""
    return [
        f"{role}: '{assignment.provider}' has no filesystem access; "
        f"you will paste the role file and save the output by hand"
        for role, assignment in plan.items()
        if (provider := kit.providers.get(assignment.provider)) is not None
        and assignability(provider, role) == "manual"
    ]


def handle(args) -> int:
    from rgraph.commands.check import load

    try:
        kit = load(args)
    except ConfigError as exc:
        print(f"error: {exc}")
        return 2
    detected = detect(kit)
    try:
        preset = parse_preset(args.preset) if args.preset else None
    except ConfigError as exc:
        print(f"error: {exc}")
        return 2
    plan = propose(kit, detected, preset)
    conflicts = capability_conflicts(kit, plan)
    manual = manual_roles(kit, plan)
    warnings = separation_warnings(kit, plan)
    level = level_for(plan["execution"], plan["reviewer"])
    note = None
    if level == "context_only":
        from rgraph.separation import CONTEXT_ONLY_NOTE

        note = CONTEXT_ONLY_NOTE
    render_setup(detected, plan, level, note, conflicts, manual, warnings)
    if conflicts:
        return 1

    target = pathlib.Path("assignment.yaml") if args.here else machine_assignment_path()
    if not args.yes:
        prompt = (
            f"Overwrite {target}? [y/N] " if target.exists()
            else f"Write {target}? [Y/n] "
        )
        default_yes = not target.exists()
        try:
            answer = input(prompt).strip().lower()
        except EOFError:
            console.print()
            console.print("No terminal to ask on. Re-run with --yes to accept this plan.")
            return 2
        accepted = answer in ("y", "yes") or (default_yes and answer == "")
        if not accepted:
            console.print("No file has been written.")
            return 0
    elif target.exists():
        backup = target.with_suffix(".yaml.bak")
        backup.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
        console.print(f"Existing assignment.yaml saved as {backup.name}")

    lines = ["# Generated by `rgraph setup`.", ""]
    for role in ROLES:
        assignment = plan[role]
        lines.append(
            f"{role + ':':<14}{{provider: {assignment.provider}, model: {assignment.model}}}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    console.print(f"Wrote {target}")
    if not args.here:
        console.print("  This is the machine default; every study uses it unless a")
        console.print("  study directory holds its own (`rgraph setup --here`).")
    console.print()
    console.print("Run next:")
    console.print("  rgraph init      # create run/ and the artifacts you write")
    return 0
