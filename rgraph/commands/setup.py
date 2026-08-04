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
from rgraph.interactive import InteractionCancelled, ask_text, choose, confirm as prompt_confirm
from rgraph.render import (
    MAIN_STYLE, body_text, console, muted, prompt_input,
    render_error, render_next_action, render_plan, render_setup, section, table_row,
)
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

PROVIDER_ALIASES = {
    "claude": "claude-code",
    "openai": "codex",
}


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
    parser = subparsers.add_parser(
        "setup",
        help="detect providers and write assignment.yaml",
        description=(
            "Detect available providers, propose one provider/model assignment per "
            "role, and write assignment.yaml only after confirmation."
        ),
        epilog=(
            "Examples:\n"
            "  rgraph setup\n"
            "  rgraph setup --yes --preset producers=claude-code,reviewer=codex\n"
            "  rgraph setup --here"
        ),
    )
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
        provider_id = PROVIDER_ALIASES.get(provider, provider)
        if provider_id in DEFAULT_MODEL:
            return Assignment(role, provider_id, _model(provider_id, role), effort)
        return Assignment(role, current.provider, provider, effort)
    return Assignment(role, provider, model, effort)


def customize_assignments(kit: Kit, plan: dict, detected: dict[str, str] | None = None) -> dict:
    """Edit only the roles the user chooses, using menus instead of ID syntax."""
    chosen = dict(plan)
    while True:
        console.print()
        role = choose(
            "Which role would you like to change?",
            [(name, f"{name:<12} {label(chosen[name])}") for name in ROLES]
            + [("done", "Done — review this assignment")],
            default="done",
        )
        if role == "done":
            return chosen

        providers = [
            provider for provider in sorted(kit.providers)
            if assignability(kit.providers[provider], role) != "blocked"
            and (
                detected is None
                or detected.get(provider, "").startswith("FOUND")
                or detected.get(provider) == "WEB"
                or provider == chosen[role].provider
            )
        ]
        provider_id = choose(
            f"Provider for {role}",
            [(
                provider,
                provider if detected is None else
                f"{provider} — {detected.get(provider, 'availability unknown')}"
            ) for provider in providers],
            default=chosen[role].provider if chosen[role].provider in providers else providers[0],
        )
        provider = kit.providers[provider_id]
        models = list(SUGGESTED_MODELS.get(provider_id, ()))
        current_model = chosen[role].model if chosen[role].provider == provider_id else _model(provider_id, role)
        if current_model not in models:
            models.insert(0, current_model)
        model_choice = choose(
            f"Model for {role}",
            [(model, model) for model in models] + [("__custom__", "Enter another model name")],
            default=current_model,
        )
        model = (
            ask_text("Model name", required=True) if model_choice == "__custom__" else model_choice
        )
        effort = None
        if provider.takes_effort and provider.efforts:
            default_effort = (
                chosen[role].effort
                if chosen[role].provider == provider_id
                and chosen[role].effort in provider.efforts
                else "__default__"
            )
            effort_choice = choose(
                f"Reasoning effort for {role}",
                [("__default__", "Provider default")]
                + [(value, value) for value in provider.efforts],
                default=default_effort,
            )
            effort = None if effort_choice == "__default__" else effort_choice
        chosen[role] = Assignment(role, provider_id, model, effort)
        table_row(role, label(chosen[role]), value_style=MAIN_STYLE)


def choose_assignments(kit: Kit, plan: dict) -> dict:
    """Ask every role, one line each, with the proposal as the default.

    The plate pairs a model with each role, and the proposal follows it. Neither
    is binding: the person paying for the subscriptions decides which model reads
    which role file, so this accepts anything `providers.yaml` can name.
    """
    section("Provider model choices")
    muted("Enter keeps the suggested assignment.")
    for provider_id in sorted(kit.providers):
        models = SUGGESTED_MODELS.get(provider_id)
        listed = ", ".join(models) if models else "any model it accepts"
        table_row(provider_id, listed)
    muted("Append @effort for reasoning depth, e.g. codex/gpt-5.6-terra@xhigh.")
    console.print()

    chosen = dict(plan)
    for role in ROLES:
        current = chosen[role]
        while True:
            try:
                answer = prompt_input(
                    role, suffix=f" [{label(current)}]", marker=" > ",
                ).strip()
            except EOFError:
                console.print()
                return chosen
            if not answer:
                break
            picked = parse_choice(answer, current, role)
            provider = kit.providers.get(picked.provider)
            if provider is None:
                body_text(
                    f"'{picked.provider}' is not in providers.yaml "
                    f"({', '.join(sorted(kit.providers))})."
                )
                continue
            # Caught here rather than after the last question, so a refusal costs
            # one line instead of the whole round.
            if assignability(provider, role) == "blocked":
                missing = ROLE_REQUIRES[role] - provider.capabilities
                body_text(
                    f"'{picked.provider}' cannot take {role}; "
                    f"it lacks {', '.join(sorted(missing))}."
                )
                continue
            if picked.effort is not None and not provider.takes_effort:
                body_text(f"'{picked.provider}' takes no effort setting.")
                continue
            if (picked.effort is not None and provider.efforts
                    and picked.effort not in provider.efforts):
                body_text(
                    f"'{picked.provider}' takes {', '.join(provider.efforts)}, "
                    f"not '{picked.effort}'."
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


def _unverified_model_defaults(plan) -> list[str]:
    return sorted({
        assignment.provider for assignment in plan.values()
        if assignment.provider not in DEFAULT_MODEL and assignment.model == "default"
    })


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
        render_error(str(exc))
        return 2
    detected = detect(kit)
    try:
        preset = parse_preset(args.preset) if args.preset else None
    except ConfigError as exc:
        render_error(str(exc))
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
        try:
            if prompt_confirm("Would you like to change any role?", default=False):
                plan = customize_assignments(kit, plan, detected)
        except InteractionCancelled:
            console.print()
            muted("Cancelled. No assignment has been written.")
            return 0
        conflicts, manual, warnings, level, note = review(kit, plan)
        render_plan(plan, level, note, conflicts, manual, warnings, heading="Assignment")
        if conflicts:
            return 1

    for provider_id in _unverified_model_defaults(plan):
        body_text(
            f"Warning: '{provider_id}' has no verified setup model default; "
            "the assignment will use the unverified model name 'default'."
        )

    target = pathlib.Path("assignment.yaml") if args.here else machine_assignment_path()
    if not args.yes:
        default_yes = not target.exists()
        try:
            accepted = prompt_confirm(
                f"{'Overwrite' if target.exists() else 'Write'} {target}?",
                default=default_yes,
            )
        except InteractionCancelled:
            console.print()
            body_text("No terminal to ask on. Re-run with --yes to accept this plan.")
            return 2
        if not accepted:
            muted("No file has been written.")
            return 0
    elif target.exists():
        backup = target.with_suffix(".yaml.bak")
        backup.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
        body_text(f"Existing assignment.yaml saved as {backup.name}.")

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
    section("Assignment written")
    body_text(str(target), style=MAIN_STYLE)
    if not args.here:
        muted(
            "This is the machine default. A study directory can override it "
            "with `rgraph setup --here`."
        )
    console.print()
    render_next_action("rgraph init")
    muted("Answer the short study setup wizard.")
    return 0
