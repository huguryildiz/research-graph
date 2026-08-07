"""Every screen. Colour reinforces status; the status word always carries it."""

from __future__ import annotations

import textwrap

from rich.console import Console
from rich.text import Text

from rgraph.separation import LABELS as SEP_LABELS

BODY_STYLE = "#d1d5db"
MAIN_STYLE = "bold #e5e7eb"
MUTED_STYLE = "#8a8a8a"
SECTION_STYLE = "bold #94a3b8"
COMMAND_STYLE = "bold #4fa98b"
CONTENT_INDENT = "    "

console = Console(highlight=False, soft_wrap=False, style=BODY_STYLE)


def _encodable(value: str) -> bool:
    """Whether the active output stream can carry a decorative glyph."""
    try:
        value.encode(console.encoding)
    except (LookupError, TypeError, UnicodeEncodeError):
        return False
    return True


UNICODE_DECORATION = _encodable("◆●─╰↺▉▇")
DIAMOND = "◆" if UNICODE_DECORATION else "*"
DOT = "●" if UNICODE_DECORATION else "o"
HLINE = "─" if UNICODE_DECORATION else "-"
CORNER = "╰" if UNICODE_DECORATION else "\\"
REVISION = "↺" if UNICODE_DECORATION else "r"

STATUS_STYLE = {
    "PASS": "bold green", "FAIL": "bold red", "WAIT": "dim",
    "READY": "bold cyan", "STALE": "bold yellow", "BLOCKED": "bold red",
    "CAVEAT": "bold yellow", "----": "dim", "SKIP": "dim",
    "AWAITING": "bold cyan", "APPROVED": "bold green",
    "UNVERIFIED": "bold yellow",
}
CLAIM_BOUNDARY_LINE = "[----] Scientific correctness was not determined"
WORDMARK_STYLE = "bold white"
WORDMARK_ACCENT = "bold #6ee7b7"
WORDMARK_REVISION = "bold #f472b6"


def print_banner(compact: bool = False) -> None:
    """Print the full supplied wordmark only when the terminal can hold it."""
    from rgraph import banner

    console.print()
    if compact or not UNICODE_DECORATION:
        console.print(
            Text(f"  {DIAMOND}", style=WORDMARK_ACCENT)
            + Text(f"  {banner.WORDMARK}", style=WORDMARK_STYLE)
        )
        if not compact:
            console.print(Text(f"     {banner.TAGLINE}", style=MUTED_STYLE))
        console.print()
        return
    console.print(Text(banner.RESEARCH_ART, style=WORDMARK_STYLE))
    console.print()
    console.print(Text(banner.GRAPH_ART, style=WORDMARK_ACCENT))
    console.print()
    console.print(
        Text(f"  {DOT}{HLINE * 2}{DOT}{HLINE * 2}", style=MUTED_STYLE)
        + Text(DIAMOND, style=WORDMARK_ACCENT)
        + Text(f"  {banner.TAGLINE}", style=MUTED_STYLE)
    )
    console.print(
        Text(f"  {CORNER}{HLINE * 4}", style=MUTED_STYLE)
        + Text(REVISION, style=WORDMARK_REVISION)
    )
    console.print()


def rule(title: str, status: str | None = None, width: int = 49) -> None:
    width = min(width, console.width)
    if status is None:
        console.print(Text(title, style="bold"))
    else:
        pad = max(1, width - len(title) - len(status))
        console.print(Text(title, style="bold") + Text(" " * pad) + status_text(status))
    console.print(Text(HLINE * width, style=MUTED_STYLE))


def status_text(status: str) -> Text:
    return Text(status, style=STATUS_STYLE.get(status, ""))


def marked(status: str, label: str) -> Text:
    return (
        Text(f"{CONTENT_INDENT}[", style=MUTED_STYLE)
        + status_text(status)
        + Text("] ", style=MUTED_STYLE)
        + Text(label)
    )


def section(label: str, style: str = SECTION_STYLE) -> None:
    """Print a quiet ledger heading without adding another container."""
    console.print(Text(label.upper(), style=style))


def body_text(
    value: str, *, indent: str = CONTENT_INDENT, hang: str = "  ",
    style: str = BODY_STYLE,
) -> None:
    """Print body copy with the terminal system's stable hanging indent."""
    for line in _hanging(str(value), indent, hang):
        console.print(Text(line, style=style))


def muted(value: str, *, indent: str = CONTENT_INDENT, hang: str = "  ") -> None:
    body_text(value, indent=indent, hang=hang, style=MUTED_STYLE)


def key_value(
    label: str, value: object, *, width: int = 15,
    indent: str = CONTENT_INDENT, value_style: str = BODY_STYLE,
) -> None:
    """Render aligned ledger metadata without relying on color for meaning."""
    value_text = str(value)
    value_floor = min(12, max(4, len(value_text)))
    label_width = min(width, max(4, console.width - len(indent) - value_floor))
    if len(label) > label_width:
        muted(label, indent=indent)
        body_text(value_text, indent=indent + "  ", style=value_style)
        return
    prefix = f"{indent}{label:<{label_width}}"
    available = max(1, console.width - len(prefix))
    lines = textwrap.wrap(value_text, width=available) or [value_text]
    for index, line in enumerate(lines):
        left = prefix if index == 0 else " " * len(prefix)
        console.print(
            Text(left, style=MUTED_STYLE) + Text(line, style=value_style)
        )


def table_row(
    label: str, value: object, *, width: int = 16,
    indent: str = CONTENT_INDENT, value_style: str = BODY_STYLE,
) -> None:
    key_value(label, value, width=width, indent=indent, value_style=value_style)


def render_next_action(value: str) -> None:
    section("Next action")
    render_command(value)


def render_error(message: str) -> None:
    """Keep the CLI's stable `error:` contract while giving it semantic color."""
    console.print(
        Text("error: ", style=STATUS_STYLE["FAIL"])
        + Text(message, style=BODY_STYLE)
    )


def prompt_input(label: str, *, suffix: str = "", marker: str = ": ") -> str:
    """Style interactive prompts while retaining builtins.input for testability."""
    console.print(
        Text(f"{CONTENT_INDENT}{label}", style=MAIN_STYLE)
        + Text(suffix, style=MUTED_STYLE)
        + Text(marker, style=MUTED_STYLE),
        end="",
    )
    return input()


def render_help(value: str) -> None:
    """Render argparse help through the same flat ledger hierarchy.

    The help text remains plain and complete when color is unavailable. This
    function changes only presentation; argparse still owns every option,
    default, command, and wrapping decision.
    """
    lines = value.rstrip().splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("usage: "):
            usage = [line.removeprefix("usage: ").strip()]
            index += 1
            while index < len(lines) and lines[index].startswith(" "):
                usage.append(lines[index].strip())
                index += 1
            section("Usage")
            body_text(" ".join(usage), style=MAIN_STYLE)
            continue
        if line and not line.startswith(" ") and line.endswith(":"):
            section(line[:-1])
        elif line.startswith("  "):
            # Argparse already calculated the label/description column. Shift
            # it into the four-cell content grid without disturbing that work.
            console.print(Text(f"{CONTENT_INDENT}{line[2:]}", style=BODY_STYLE))
        elif line:
            body_text(line)
        else:
            console.print()
        index += 1


def render_command(value: str) -> None:
    """Print a paste-ready action with stable indentation when it wraps."""
    lines = textwrap.wrap(value, width=max(12, console.width - 8)) or [value]
    for index, line in enumerate(lines):
        prefix = f"{CONTENT_INDENT}$ " if index == 0 else f"{CONTENT_INDENT}  "
        continuation = " \\" if index < len(lines) - 1 else ""
        console.print(
            Text(prefix, style=MUTED_STYLE)
            + Text(line, style=COMMAND_STYLE)
            + Text(continuation, style=MUTED_STYLE)
        )


def render_home(run_path, has_run: bool) -> None:
    """Render the bare-command home screen around one primary next action."""
    if has_run:
        section("Active run")
        body_text(str(run_path), style=MAIN_STYLE)
        muted("Existing research run detected.")
        console.print()
        section("Next action")
        render_command(f"rgraph --run {run_path} status")
        console.print()
        section("Explore")
        table_row("demo", "rgraph demo", width=7)
        table_row("help", "rgraph --help", width=7)
        return

    section("Explore the verified flow")
    render_command("rgraph demo")
    muted("30-second synthetic tour; no model calls and no file changes.")
    console.print()
    section("Start a governed study")
    table_row("1", "rgraph setup", width=3, value_style=MAIN_STYLE)
    muted("Choose providers for each role.", indent="       ")
    table_row("2", "rgraph init", width=3, value_style=MAIN_STYLE)
    muted("Create the research run.", indent="       ")
    console.print()
    muted("Full command index: rgraph --help")


SYNTHETIC_NOTICE = (
    "This run is a fixture. Its artifacts were authored, not produced by the "
    "identities they name, and no gate was decided by a reviewer. The data, "
    "statistics and DOIs are real; the provenance identities are illustrative."
)


def render_provenance_notice(run) -> None:
    """Print once, at the top of any screen, when the run declares itself a fixture."""
    if run.meta.get("provenance") != "synthetic":
        return
    console.print(marked("CAVEAT", "SYNTHETIC PROVENANCE"))
    for line in _hanging(SYNTHETIC_NOTICE, " " * 13):
        console.print(Text(line, style=MUTED_STYLE))
    console.print()


def _hanging(text: str, indent: str = "", hang: str = "") -> list[str]:
    """Wrap to the terminal, keeping continuation lines under the first one.

    rich soft-wraps an over-long line back to column zero, which loses the
    indentation saying which finding a line belongs to. A digest is long enough
    to trigger that at eighty columns, so a failing gate — the screen that most
    needs reading — is the one that comes apart first.
    """
    width = max(len(indent) + len(hang) + 16, console.width)
    return textwrap.wrap(
        text, width=width, initial_indent=indent, subsequent_indent=indent + hang,
    ) or [indent + text]


def render_claim_boundary() -> None:
    for line in _hanging(CLAIM_BOUNDARY_LINE, CONTENT_INDENT, " " * 5):
        console.print(Text(line, style=MUTED_STYLE))


# ── static lint ────────────────────────────────────────────────────────────

def render_static_report(findings) -> None:
    failures = [f for f in findings if f.status == "FAIL"]
    rule("STATIC GRAPH CHECK", "FAIL" if failures else "PASS")
    console.print()
    for check in ("type_match", "acyclic", "bounded", "reachable", "dead_node"):
        rows = [f for f in findings if f.check == check]
        worst = "FAIL" if any(r.status == "FAIL" for r in rows) else "PASS"
        console.print(marked(worst, check))
        for row in rows:
            if row.status == "FAIL":
                for line in _hanging(row.subject, " " * 8):
                    console.print(line)
                for line in _hanging(row.detail, " " * 8):
                    console.print(line)
                for line in _hanging(f"Fix: {row.fix}", " " * 8, " " * 5):
                    console.print(line)
    console.print()
    section("What this check covered")
    console.print(marked("PASS", "Graph structure"))
    render_claim_boundary()


# ── gate result ────────────────────────────────────────────────────────────

def render_stale_chain(causes) -> None:
    section("Stale chain detected", STATUS_STYLE["STALE"])
    for cause in causes:
        for line in _hanging(cause, "  ", "  "):
            console.print(line)


def render_gate_result(
    result, gate, invalidated=None, downstream=(), *, show_next: bool = True,
) -> None:
    rule(f"GATE {result.gate_id} / {gate.title.upper()}", result.status)
    console.print()
    if result.findings:
        subjects = len({f.ref for f in result.findings})
        body_text(f"{subjects} item(s) need revision.")
        console.print()
        width = max(6, *(len(f.ref) for f in result.findings)) + 2
        for finding in result.findings:
            console.print(f"{CONTENT_INDENT}{finding.ref:<{width}}{finding.code}")
            for detail in finding.detail.splitlines():
                for line in _hanging(detail, " " * 8):
                    console.print(line)
            if finding.fix:
                for line in _hanging(f"Fix: {finding.fix}", " " * 8, " " * 5):
                    console.print(line)
            console.print()
    if invalidated:
        render_stale_chain(invalidated)
        if downstream:
            for line in _hanging(
                f"Invalidated: {', '.join(sorted(downstream))}  "
                f"(must re-run before they can pass)", "  ", "  ",
            ):
                console.print(line)
        console.print()
    if result.separation:
        section("Review separation")
        key_value("Level", SEP_LABELS.get(result.separation.level, "n/a"), width=8)
        if result.separation.note:
            first, *rest = result.separation.note.splitlines()
            key_value("Note", first, width=8)
            for extra in rest:
                body_text(extra, indent=" " * 12)
        console.print()
    section("What this gate checked")
    for check in result.checks:
        mark = (
            "WAIT"
            if result.status == "AWAITING"
            and check.name == "decision"
            and check.status == "FAIL"
            else check.status if check.status in STATUS_STYLE else "----"
        )
        console.print(marked(mark, check.name.replace("_", " ").capitalize()))
        # A failing check that named nothing above leaves the reader with no
        # next move, so it says here what it found.
        if check.status == "FAIL" and check.detail and not result.findings:
            for line in _hanging(check.detail, " " * 9):
                console.print(line)
    render_claim_boundary()
    console.print()
    if not show_next:
        return
    if gate.kind == "human" and result.status == "STALE":
        # A stale human gate is one whose own past decision no longer covers the
        # file. Nothing upstream produced the change and no unit can undo it, so
        # the revision budget is the wrong instrument: the cure is reading the
        # artifact again and answering again.
        render_next_action(f"rgraph decide {result.gate_id}")
    elif result.return_to:
        key_value("Return to", result.return_to)
        remaining = result.budget[1] - result.budget[0]
        key_value("Revision budget", f"{remaining} -> {max(0, remaining - 1)}")
        console.print()
        render_next_action(f"rgraph revise {result.gate_id}")


# ── status ─────────────────────────────────────────────────────────────────

STAGE_LABELS = {"retrieve": "RETRIEVE", "plan": "PLAN", "execute": "EXECUTE",
                "verify": "VERIFY", "write": "WRITE"}


def render_status(view, verbose: bool = False) -> None:
    section("Research run")
    console.print(Text(f"{CONTENT_INDENT}{view.run_id}", style="bold"))
    for line in _hanging(view.question, CONTENT_INDENT):
        console.print(line)
    metadata = f"{view.mode}  ·  {view.protocol}  ·  {view.revision_line}"
    for line in _hanging(metadata, CONTENT_INDENT, "  "):
        console.print(Text(line, style=MUTED_STYLE))
    console.print()
    section("Pipeline")

    if console.width < 68:
        for index, ((stage, state), (gate, gate_state)) in enumerate(
            zip(view.stages, view.gate_row)
        ):
            console.print(marked(state, STAGE_LABELS[stage]))
            console.print(
                Text(f"       gate {gate:<5}", style=MUTED_STYLE)
                + status_text(gate_state)
            )
            human, human_state = view.human_row[index]
            if human:
                console.print(
                    Text(f"       human {human:<4}", style=MUTED_STYLE)
                    + status_text(human_state)
                )
        console.print()
    else:
        _render_status_pipeline(view)

    valid, stale, pending = view.artifact_counts
    section("Run state")
    console.print(f"{CONTENT_INDENT}Progress     {view.units_complete} / 12 units complete")
    artifacts = f"Artifacts    {valid} valid  ·  {stale} stale  ·  {pending} pending"
    for line in _hanging(artifacts, CONTENT_INDENT, " " * 13):
        console.print(line)
    console.print(f"{CONTENT_INDENT}Last gate    {view.last_gate}")
    if view.next_unit:
        console.print(f"{CONTENT_INDENT}Next unit    {view.next_unit}")
    console.print()
    section("Next action")
    if view.next_action.startswith("none"):
        console.print(Text(f"{CONTENT_INDENT}{view.next_action}", style=MUTED_STYLE))
    else:
        render_command(view.next_action)

    if verbose:
        console.print()
        section("Units")
        for unit_id, title, state in view.units:
            console.print(marked(state, f"{unit_id}  {title}"))


def _render_status_pipeline(view) -> None:
    """Render the five-column overview when the terminal can hold it."""

    cells = [STAGE_LABELS[s] for s, _ in view.stages]
    widths = [max(len(c), 8) for c in cells]
    separator = f" {HLINE * 3} "
    console.print(CONTENT_INDENT + separator.join(c.ljust(w) for c, w in zip(cells, widths)))
    line = Text(CONTENT_INDENT)
    for (_, state), width in zip(view.stages, widths):
        line += status_text(state.ljust(width)) + Text("      ")
    console.print(line)

    def aligned(pairs, prefix):
        row_a, row_b = Text(CONTENT_INDENT), Text(CONTENT_INDENT)
        for (label, state), width in zip(pairs, widths):
            row_a += Text(f"{prefix}{label}".ljust(width)) + Text("      ")
            row_b += status_text(state.ljust(width)) + Text("      ")
        console.print(row_a)
        console.print(row_b)

    aligned(view.gate_row, "gate:")
    if view.human_row:
        row_a, row_b = Text(CONTENT_INDENT), Text(CONTENT_INDENT)
        for (label, state), width in zip(view.human_row, widths):
            row_a += Text(f"human:{label}".ljust(width) if label else "".ljust(width))
            row_a += Text("      ")
            row_b += status_text(state.ljust(width)) + Text("      ")
        console.print(row_a)
        console.print(row_b)
    console.print()


# ── next ───────────────────────────────────────────────────────────────────

def render_next(
    plan, unit, gate_id: str, manual: bool, *, show_choices: bool = True,
) -> None:
    rule(f"UNIT {unit.id[1:]} / {unit.title.upper()}", None, 30)
    console.print()
    key_value("Provider", f"{plan.provider} / {plan.model}")
    console.print()
    section("Inputs")
    for artifact_id, state in plan.inputs:
        table_row(f"run/{artifact_id}.json", state, width=33)
    console.print()
    section("Will produce")
    output_paths = plan.output_paths or tuple(f"{item}.json" for item in plan.produces)
    for output_path in output_paths:
        body_text(f"run/{output_path}", style=MAIN_STYLE)
    console.print()
    section("Next checkpoint")
    body_text(gate_id, style=MAIN_STYLE)
    console.print()
    if manual:
        section("Manual relay")
        muted("This provider is web-only.")
        table_row("1", "Open a new session at the provider.", width=3)
        table_row("2", f"Paste the contents of {plan.role_path}.", width=3)
        table_row("3", "Save the output to the paths under Will produce.", width=3)
        table_row("4", "Run rgraph status.", width=3)
        console.print()
    if show_choices:
        muted("No command has been executed.")
        console.print()
        section("Choose next")
        table_row("1", "Execute — run this one provider command", width=3)
        table_row("2", "Dry run — show the exact command only", width=3)
        table_row("3", "Stop — make no changes", width=3)
        muted("Shortcuts: E / D / S")


# ── trace ──────────────────────────────────────────────────────────────────

def render_trace(chain, text: str) -> None:
    section("Claim")
    body_text(chain.claim, style=MAIN_STYLE)
    muted(f'"{text}"')
    console.print()
    for index, link in enumerate(chain.links):
        last = index == len(chain.links) - 1
        stem = "`--" if last else "+--"
        suffix = f"{' ' * max(1, 34 - len(link.label))}{link.status}" if link.status else ""
        console.print(f"{CONTENT_INDENT}{stem} {link.label}{suffix}")
        if link.detail:
            branch = "   " if last else "|  "
            console.print(f"{CONTENT_INDENT}{branch} `-- {link.detail}")
    console.print()
    section("Assurance")
    if chain.complete:
        console.print(marked("PASS", "Provenance chain is complete."))
    else:
        console.print(marked("FAIL", "Provenance chain is incomplete."))
        for gap in chain.missing:
            body_text(gap, indent="        ")
    muted("Scientific validity still requires human review.")


# ── revise ─────────────────────────────────────────────────────────────────

def render_revise(gate_id, reason, target, remaining, unit_title) -> None:
    rule(f"REVISE {gate_id}", None, 30)
    console.print()
    key_value("Reason", reason, width=16)
    key_value("Return to", f"{target}  {unit_title}", width=16)
    key_value("Revision budget", f"{remaining + 1} -> {remaining}", width=16)
    console.print()
    render_next_action(f"rgraph next --unit {target}")


# ── review / completion ────────────────────────────────────────────────────

def render_completion(view) -> None:
    rule(view.headline, None, 25)
    console.print()
    key_value("Units", f"{view.units_complete} / 12 complete")
    key_value("Gates", view.gate_line)
    key_value("Artifacts", view.artifact_line)
    key_value("Review", view.review_level)
    key_value("Human release", view.release_state)
    console.print()
    if view.ready:
        body_text("The run is ready for a human release decision.")
    else:
        body_text("The run is not ready for release; unresolved gates remain.")
    muted("It has not been approved for publication.")
    console.print()


# ── setup ──────────────────────────────────────────────────────────────────

def _detected_style(state: str) -> str:
    if state.startswith("FOUND"):
        return COMMAND_STYLE
    if state == "WEB":
        return STATUS_STYLE["READY"]
    if state.startswith("NOT ON PATH"):
        return STATUS_STYLE["CAVEAT"]
    return MUTED_STYLE

def render_setup(detected, plan, level, note, conflicts, manual=(), warnings=(),
                 unregistered=(), support=()) -> None:
    section("Detected")
    for provider_id, state in sorted(detected.items()):
        table_row(provider_id, state, value_style=_detected_style(state))
    if any(state.startswith("NOT ON PATH") for state in detected.values()):
        console.print()
        section("Path action", STATUS_STYLE["CAVEAT"])
        body_text(
            "Installed providers outside PATH cannot be invoked. Add their directory "
            "to PATH, or use an absolute path in both `invoke` and the first "
            "`exec_argv` element in providers.yaml."
        )
    if unregistered:
        console.print()
        section("On PATH, not in providers.yaml")
        for name in unregistered:
            table_row(name, "describe it there to assign it a role")
    if support:
        console.print()
        section("Draft provider integrations", STATUS_STYLE["CAVEAT"])
        for provider_id, support_note in support:
            table_row(provider_id, "DRAFT", value_style=STATUS_STYLE["CAVEAT"])
            muted(support_note, indent=" " * 20)
        muted(
            "Draft describes registry maturity; availability and model acceptance "
            "still require doctor checks."
        )
    console.print()
    render_plan(plan, level, note, conflicts, manual, warnings)


def render_plan(plan, level, note, conflicts, manual=(), warnings=(),
                heading="Proposed assignment") -> None:
    section(heading)
    for role, assignment in plan.items():
        effort = f"@{assignment.effort}" if assignment.effort else ""
        table_row(role, f"{assignment.provider}/{assignment.model}{effort}")
    table_row("separation", SEP_LABELS.get(level, level), value_style=MAIN_STYLE)
    if note:
        for line in note.splitlines():
            muted(line, indent=" " * 20)
    if manual:
        console.print()
        section("Manual relay required", STATUS_STYLE["CAVEAT"])
        for message in manual:
            body_text(message)
    if warnings:
        console.print()
        section("Gates this plan cannot pass", STATUS_STYLE["FAIL"])
        for message in warnings:
            body_text(message)
    if conflicts:
        console.print()
        section("Blocked assignments", STATUS_STYLE["FAIL"])
        for message in conflicts:
            body_text(message)
    console.print()
