"""`rgraph setup` — detect providers, propose the assignment with the most separation."""

from __future__ import annotations

import glob
import os
import pathlib
import shutil
import subprocess
import sys

from rgraph.config import (
    ROLE_REQUIRES, ROLES, Assignment, ConfigError, Kit, assignability,
    machine_assignment_path,
)
from rgraph.render import console, render_plan, render_setup
from rgraph.separation import level_for

PRODUCER_ROLES = ("retrieval", "planning", "execution", "verification", "synthesis")
DEFAULT_MODEL = {
    "claude-code": "claude-sonnet-5",
    "codex": "gpt-5.6-terra",
    "sakana": "fugu",
    "gemini": "gemini-3-pro",
    "ollama": "llama4",
    "qwen": "qwen3-coder-plus",
    "kimi": "kimi-k3",
    "deepseek": "deepseek-v4-pro",
    "grok": "grok-5",
}
ROLE_MODEL = {
    "planning": "claude-opus-5",
    "synthesis": "claude-fable-5",
    "verification": "claude-opus-5",
}

# What the proposal reaches for first. `architecture.html` draws one such
# pairing — Opus formulating, Sonnet implementing, Fable writing — but that is a
# recommendation, not a constraint: every role is asked, and any provider/model
# string is accepted, including one this table has never heard of.
#
# These are the identifiers the CLIs actually answer to, which is not always the
# name the model is sold under: `claude` rejects `sonnet-5` and takes
# `claude-sonnet-5`, and codex has no `gpt-5.6` — only the three below.
SUGGESTED_MODELS = {
    "claude-code": ("claude-opus-5", "claude-sonnet-5", "claude-fable-5",
                    "claude-haiku-4-5-20251001"),
    "codex": ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"),
    "sakana": ("fugu", "fugu-ultra"),
    "gemini": ("gemini-3-pro",),
    "ollama": ("llama4",),
    "qwen": ("qwen3-coder-plus",),
    "kimi": ("kimi-k3",),
    "deepseek": ("deepseek-v4-pro", "deepseek-v4-flash"),
    "grok": ("grok-5",),
}

# CLIs this kit has no entry for. Naming one is not endorsing it: rgraph invents
# no call form, so an unregistered CLI is reported and left for the user to
# describe in `providers.yaml`.
KNOWN_CLI_NAMES = (
    "qwen", "deepseek", "deepcode", "dsc", "glm", "kimi", "mistral", "opencode",
    "aider", "goose", "crush", "amp", "droid", "cursor-agent", "copilot", "llm",
)


# Where a CLI lands when its installer does not reach the system PATH. This is
# knowledge about Unix install conventions, not about any provider, which is why
# it can live in code while every provider fact stays in `providers.yaml`.
SEARCH_DIRS = (
    "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin",
    "~/.local/bin", "~/bin", "~/.npm-global/bin", "~/.bun/bin",
    "~/.cargo/bin", "~/.deno/bin", "~/.volta/bin",
)
SEARCH_GLOBS = (
    "~/.nvm/versions/node/*/bin",
    "~/.local/share/mise/installs/node/*/bin",
    "~/.asdf/installs/nodejs/*/bin",
)


def candidate_dirs() -> list[pathlib.Path]:
    found = [pathlib.Path(d).expanduser() for d in SEARCH_DIRS]
    for pattern in SEARCH_GLOBS:
        found.extend(
            pathlib.Path(hit) for hit in sorted(glob.glob(os.path.expanduser(pattern)))
        )
    return found


def locate(name: str) -> pathlib.Path | None:
    """Where a CLI sits when it is not on this process's PATH.

    `which` answers the only question that decides anything, because `Popen`
    resolves the same way: not on this PATH means rgraph cannot invoke it. This
    answers the next question — why the miss — so that "not found" is never
    claimed of a CLI that is merely out of reach.
    """
    for directory in candidate_dirs():
        candidate = directory / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def shorten(path: pathlib.Path) -> str:
    home = pathlib.Path.home()
    return f"~/{path.relative_to(home)}" if path.is_relative_to(home) else str(path)


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
        key, value = key.strip(), value.strip()
        if key not in ("producers", "reviewer"):
            raise ConfigError(
                f"unknown preset key {key!r}; expected 'producers' or 'reviewer'"
            )
        if not value:
            raise ConfigError(f"preset value for {key!r} cannot be empty")
        out[key] = value
    if "producers" not in out:
        raise ConfigError("preset must name 'producers'")
    return out


def detect(kit: Kit) -> dict[str, str]:
    states: dict[str, str] = {}
    for provider in kit.providers.values():
        if provider.kind == "web":
            states[provider.id] = "WEB"
            continue
        if provider.invoke is None:
            states[provider.id] = "NOT FOUND"
            continue
        on_path = shutil.which(provider.invoke)
        if on_path is None:
            # `which` has established that this cannot be invoked, and nothing
            # below changes that. It only says whether the reason is worth acting on.
            elsewhere = locate(provider.invoke)
            states[provider.id] = (
                f"NOT ON PATH — found at {shorten(elsewhere.parent)}"
                if elsewhere else "NOT FOUND"
            )
            continue
        # Which copy answered matters: two installs of the same CLI on one PATH
        # is how a run ends up on a version nobody meant to use, and a provider
        # that borrows another's binary — sakana runs through codex — says so here.
        where = f" — {shorten(pathlib.Path(on_path))}"
        if not provider.login_check:
            states[provider.id] = f"FOUND{where}"
            continue
        try:
            completed = subprocess.run(
                list(provider.login_check), capture_output=True, timeout=5, check=False
            )
        except (OSError, subprocess.SubprocessError):
            # A check that timed out or would not start taught us nothing about
            # the subscription. Reporting that as "not logged in" states a fact
            # this never established.
            states[provider.id] = f"FOUND (login unknown){where}"
            continue
        signed_in = "" if completed.returncode == 0 else " (not logged in)"
        states[provider.id] = f"FOUND{signed_in}{where}"
    return states


def unregistered(kit: Kit) -> list[str]:
    """CLIs on PATH that `providers.yaml` says nothing about.

    `detect` answers "which of the providers I know about are installed". This
    answers the other half — what is installed that nobody described — so a
    newcomer with a CLI the kit has never seen learns that it can be used, and
    where to say so.
    """
    registered = {p.invoke for p in kit.providers.values() if p.invoke}
    registered |= set(kit.providers)
    return [name for name in KNOWN_CLI_NAMES
            if name not in registered and shutil.which(name) is not None]


def label(assignment: Assignment) -> str:
    suffix = f"@{assignment.effort}" if assignment.effort else ""
    return f"{assignment.provider}/{assignment.model}{suffix}"


def parse_choice(text: str, current: Assignment, role: str) -> Assignment:
    """`provider/model`, a bare model that keeps the provider, or `@effort`.

    What you type is what you get: naming a model without an `@` leaves the role
    at the provider's own default depth. `@high` on its own is the exception —
    it changes the depth and nothing else.
    """
    head, _, effort = text.partition("@")
    effort = effort.strip() or None
    head = head.strip()
    if not head:
        return Assignment(role, current.provider, current.model, effort)
    provider, _, model = head.partition("/")
    if not model:
        return Assignment(role, current.provider, provider, effort)
    return Assignment(role, provider, model, effort)


def choose_assignments(kit: Kit, plan: dict) -> dict:
    """Ask every role, one line each, with the proposal as the default.

    The plate pairs a model with each role, and the proposal follows it. Neither
    is binding: the person paying for the subscriptions decides which model reads
    which role file, so this accepts anything `providers.yaml` can name.
    """
    console.print("Choose a provider/model for each role. Enter keeps the suggestion.")
    for provider_id in sorted(kit.providers):
        models = SUGGESTED_MODELS.get(provider_id)
        listed = ", ".join(models) if models else "any model it accepts"
        console.print(f"  {provider_id:<14}{listed}")
    console.print("Append @effort for reasoning depth, e.g. codex/gpt-5.6-terra@xhigh.")
    console.print()

    chosen = dict(plan)
    for role in ROLES:
        current = chosen[role]
        while True:
            try:
                answer = input(f"  {role:<14}[{label(current)}] > ").strip()
            except EOFError:
                console.print()
                return chosen
            if not answer:
                break
            picked = parse_choice(answer, current, role)
            provider = kit.providers.get(picked.provider)
            if provider is None:
                console.print(
                    f"  {'':<14}'{picked.provider}' is not in providers.yaml "
                    f"({', '.join(sorted(kit.providers))})"
                )
                continue
            # Caught here rather than after the last question, so a refusal costs
            # one line instead of the whole round.
            if assignability(provider, role) == "blocked":
                missing = ROLE_REQUIRES[role] - provider.capabilities
                console.print(
                    f"  {'':<14}'{picked.provider}' cannot take {role}; "
                    f"it lacks {', '.join(sorted(missing))}"
                )
                continue
            if picked.effort is not None and not provider.takes_effort:
                console.print(
                    f"  {'':<14}'{picked.provider}' takes no effort setting"
                )
                continue
            if (picked.effort is not None and provider.efforts
                    and picked.effort not in provider.efforts):
                console.print(
                    f"  {'':<14}'{picked.provider}' takes "
                    f"{', '.join(provider.efforts)}, not '{picked.effort}'"
                )
                continue
            chosen[role] = picked
            break
    console.print()
    return chosen


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


def review(kit: Kit, plan):
    """Everything the screen says about a plan, recomputed after any change."""
    conflicts = capability_conflicts(kit, plan)
    manual = manual_roles(kit, plan)
    if conflicts:
        # Separation needs provider identities. An invalid provider has no
        # identity to compare, so report the assignment defect first.
        return conflicts, manual, [], "none", None
    level = level_for(plan["execution"], plan["reviewer"])
    note = None
    if level == "context_only":
        from rgraph.separation import CONTEXT_ONLY_NOTE

        note = CONTEXT_ONLY_NOTE
    return (
        conflicts, manual, separation_warnings(kit, plan), level, note,
    )


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
    conflicts, manual, warnings, level, note = review(kit, plan)
    render_setup(detected, plan, level, note, conflicts, manual, warnings,
                 unregistered(kit))
    if conflicts:
        return 1

    # The proposal follows the plate's pairing. Which model reads which role file
    # is the subscriber's call, so it is offered rather than imposed.
    if not args.yes and sys.stdin.isatty():
        plan = choose_assignments(kit, plan)
        conflicts, manual, warnings, level, note = review(kit, plan)
        render_plan(plan, level, note, conflicts, manual, warnings, heading="Assignment")
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
        effort = f", effort: {assignment.effort}" if assignment.effort else ""
        lines.append(
            f"{role + ':':<14}"
            f"{{provider: {assignment.provider}, model: {assignment.model}{effort}}}"
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
