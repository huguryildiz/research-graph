"""`rgraph setup` — detect providers, propose the assignment with the most separation."""

from __future__ import annotations

import pathlib
import shutil
import subprocess

from rgraph.config import ROLE_REQUIRES, ROLES, Assignment, ConfigError, Kit
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
ROLE_MODEL = {"planning": "opus-5", "synthesis": "fable-5"}


def register(subparsers) -> None:
    parser = subparsers.add_parser("setup", help="detect providers and write assignment.yaml")
    parser.add_argument("--preset", help='e.g. "producers=claude-code,reviewer=grok"')
    parser.add_argument("--yes", action="store_true", help="accept the proposal without asking")
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
    provider = kit.providers.get(provider_id)
    return provider is not None and ROLE_REQUIRES[role] <= provider.capabilities


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
    plan["reviewer"] = Assignment("reviewer", reviewer, _model(reviewer, "reviewer"))
    return plan


def capability_conflicts(kit: Kit, plan) -> list[str]:
    out = []
    for role, assignment in plan.items():
        provider = kit.providers.get(assignment.provider)
        if provider is None:
            out.append(f"{role}: unknown provider '{assignment.provider}'")
            continue
        missing = ROLE_REQUIRES[role] - provider.capabilities
        if missing:
            out.append(
                f"{role}: '{assignment.provider}' cannot be assigned; "
                f"it lacks {', '.join(sorted(missing))}"
            )
    return out


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
    level = level_for(plan["execution"], plan["reviewer"])
    note = None
    if level == "context_only":
        from rgraph.separation import CONTEXT_ONLY_NOTE

        note = CONTEXT_ONLY_NOTE
    render_setup(detected, plan, level, note, conflicts)
    if conflicts:
        return 1
    if not args.yes:
        answer = input("Write assignment.yaml? [Y/n] ").strip().lower()
        if answer not in ("", "y", "yes"):
            console.print("No file has been written.")
            return 0
    lines = ["# Generated by `rgraph setup`.", ""]
    for role in ROLES:
        assignment = plan[role]
        lines.append(
            f"{role + ':':<14}{{provider: {assignment.provider}, model: {assignment.model}}}"
        )
    (pathlib.Path(args.root) / "assignment.yaml").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    console.print("Wrote assignment.yaml")
    return 0
