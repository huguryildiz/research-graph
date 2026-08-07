"""`rgraph setup` — detect providers, propose the assignment with the most separation.

The rules live in `rgraph.services.providers`; this module is the terminal
screen over them. The browser wizard calls the same service, so a plan the CLI
would refuse cannot be written from a browser either.
"""

from __future__ import annotations

import pathlib
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
from rgraph.services.providers import (  # noqa: F401  (public surface of `rgraph setup`)
    PRODUCER_ROLES, SEARCH_DIRS, SEARCH_GLOBS, assignment_text, candidate_dirs,
    capability_conflicts, default_model as _model, detect, label, locate, manual_roles,
    parse_choice, parse_preset, propose, review, separation_warnings, shorten,
    unregistered, unverified_model_defaults as _unverified_model_defaults,
    write_assignment,
)


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
        models = list(provider.models)
        current_model = (
            chosen[role].model if chosen[role].provider == provider_id
            else _model(kit, provider_id, role)
        )
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
        models = kit.providers[provider_id].models
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
            picked = parse_choice(kit, answer, current, role)
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

    for provider_id in _unverified_model_defaults(kit, plan):
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

    write_assignment(target, plan)
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
