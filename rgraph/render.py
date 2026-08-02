"""Every screen. Colour reinforces status; the status word always carries it."""

from __future__ import annotations

import textwrap

from rich.console import Console
from rich.text import Text

from rgraph.separation import LABELS as SEP_LABELS

console = Console(highlight=False, soft_wrap=False)

STATUS_STYLE = {
    "PASS": "bold green", "FAIL": "bold red", "WAIT": "dim",
    "READY": "bold cyan", "STALE": "bold yellow", "BLOCKED": "bold red",
    "CAVEAT": "bold yellow", "----": "dim", "SKIP": "dim",
    "AWAITING": "bold cyan",
}
CLAIM_BOUNDARY_LINE = "  [----] Scientific correctness was not determined"


def rule(title: str, status: str | None = None, width: int = 49) -> None:
    width = min(width, console.width)
    if status is None:
        console.print(Text(title, style="bold"))
    else:
        pad = max(1, width - len(title) - len(status))
        console.print(Text(title, style="bold") + Text(" " * pad) + status_text(status))
    console.print("-" * width)


def status_text(status: str) -> Text:
    return Text(status, style=STATUS_STYLE.get(status, ""))


def marked(status: str, label: str) -> Text:
    return (
        Text("  [", style="dim")
        + status_text(status)
        + Text("] ", style="dim")
        + Text(label)
    )


SYNTHETIC_NOTICE = (
    "This run is a fixture. Its artifacts were authored, not produced by the "
    "identities they name, and no gate was decided by a reviewer. The data, "
    "statistics and DOIs are real; the provenance identities are illustrative."
)


def render_provenance_notice(run) -> None:
    """Print once, at the top of any screen, when the run declares itself a fixture."""
    if run.meta.get("provenance") != "synthetic":
        return
    console.print(Text("SYNTHETIC PROVENANCE", style=STATUS_STYLE["CAVEAT"]))
    console.print(Text(SYNTHETIC_NOTICE, style=STATUS_STYLE["CAVEAT"]))
    console.print()


def render_claim_boundary() -> None:
    console.print(Text(CLAIM_BOUNDARY_LINE, style="dim"))


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
                console.print(f"        {row.subject}")
                console.print(f"        {row.detail}")
                console.print(f"        Fix: {row.fix}")
    console.print()
    console.print("What this check covered")
    console.print("  [PASS] Graph structure")
    render_claim_boundary()


# ── gate result ────────────────────────────────────────────────────────────

def render_stale_chain(causes) -> None:
    console.print(Text("STALE CHAIN DETECTED", style=STATUS_STYLE["STALE"]))
    for cause in causes:
        console.print(f"  {cause}")


def _wrap_detail(detail: str, width: int = 60) -> list[str]:
    return textwrap.wrap(detail, width=width) or [detail]


def render_gate_result(
    result, gate, invalidated=None, downstream=(), *, show_next: bool = True,
) -> None:
    rule(f"GATE {result.gate_id} / {gate.title.upper()}", result.status)
    console.print()
    if result.findings:
        subjects = len({f.ref for f in result.findings})
        console.print(f"{subjects} item(s) need revision.")
        console.print()
        width = max(6, *(len(f.ref) for f in result.findings)) + 2
        for finding in result.findings:
            console.print(f"  {finding.ref:<{width}}{finding.code}")
            for line in finding.detail.splitlines():
                console.print(f"        {line}")
            if finding.fix:
                console.print(f"        Fix: {finding.fix}")
            console.print()
    if invalidated:
        render_stale_chain(invalidated)
        if downstream:
            console.print(
                f"  Invalidated: {', '.join(sorted(downstream))}  "
                f"(must re-run before they can pass)"
            )
        console.print()
    if result.separation:
        console.print("Review separation")
        console.print(f"  Level : {SEP_LABELS.get(result.separation.level, 'n/a')}")
        if result.separation.note:
            first, *rest = result.separation.note.splitlines()
            console.print(f"  Note  : {first}")
            for line in rest:
                console.print(f"          {line}")
        console.print()
    console.print("What this gate checked")
    for check in result.checks:
        mark = check.status if check.status in STATUS_STYLE else "----"
        console.print(marked(mark, check.name.replace("_", " ").capitalize()))
        # A failing check that named nothing above leaves the reader with no
        # next move, so it says here what it found.
        if check.status == "FAIL" and check.detail and not result.findings:
            for line in _wrap_detail(check.detail):
                console.print(f"         {line}")
    render_claim_boundary()
    console.print()
    if not show_next:
        return
    if gate.kind == "human" and result.status == "STALE":
        # A stale human gate is one whose own past decision no longer covers the
        # file. Nothing upstream produced the change and no unit can undo it, so
        # the revision budget is the wrong instrument: the cure is reading the
        # artifact again and answering again.
        console.print("Run next:")
        console.print(f"  rgraph decide {result.gate_id}")
    elif result.return_to:
        console.print(f"Return to       {result.return_to}")
        remaining = result.budget[1] - result.budget[0]
        console.print(f"Revision budget {remaining} -> {max(0, remaining - 1)}")
        console.print()
        console.print("Run next:")
        console.print(f"  rgraph revise {result.gate_id}")


# ── status ─────────────────────────────────────────────────────────────────

STAGE_LABELS = {"retrieve": "RETRIEVE", "plan": "PLAN", "execute": "EXECUTE",
                "verify": "VERIFY", "write": "WRITE"}


def render_status(view, verbose: bool = False) -> None:
    console.print(f"RESEARCH RUN  {view.run_id}")
    console.print(f"Question      {view.question}")
    console.print(f"Mode          {view.mode}")
    console.print(f"Protocol      {view.protocol}")
    console.print(f"Revision      {view.revision_line}")
    console.print()
    console.print("PIPELINE")

    if console.width < 68:
        for index, ((stage, state), (gate, gate_state)) in enumerate(
            zip(view.stages, view.gate_row)
        ):
            line = Text(f"  {STAGE_LABELS[stage]:<10}") + status_text(state)
            console.print(line)
            console.print(
                Text(f"    gate {gate:<5}") + status_text(gate_state)
            )
            human, human_state = view.human_row[index]
            if human:
                console.print(
                    Text(f"    human {human:<4}") + status_text(human_state)
                )
        console.print()
    else:
        _render_status_pipeline(view)

    valid, stale, pending = view.artifact_counts
    console.print(f"Progress      {view.units_complete} / 12 units complete")
    console.print(f"Artifacts     {valid} valid, {stale} stale, {pending} pending")
    console.print(f"Last gate     {view.last_gate}")
    console.print(f"Next unit     {view.next_unit or 'none'}")
    console.print(f"Next action   {view.next_action}")

    if verbose:
        console.print()
        console.print("UNITS")
        for unit_id, title, state in view.units:
            console.print(marked(state, f"{unit_id}  {title}"))


def _render_status_pipeline(view) -> None:
    """Render the five-column overview when the terminal can hold it."""

    cells = [STAGE_LABELS[s] for s, _ in view.stages]
    widths = [max(len(c), 8) for c in cells]
    console.print("  " + " ---> ".join(c.ljust(w) for c, w in zip(cells, widths)))
    line = Text("  ")
    for (_, state), width in zip(view.stages, widths):
        line += status_text(state.ljust(width)) + Text("      ")
    console.print(line)

    def aligned(pairs, prefix):
        row_a, row_b = Text("  "), Text("  ")
        for (label, state), width in zip(pairs, widths):
            row_a += Text(f"{prefix}{label}".ljust(width)) + Text("      ")
            row_b += status_text(state.ljust(width)) + Text("      ")
        console.print(row_a)
        console.print(row_b)

    aligned(view.gate_row, "gate:")
    if view.human_row:
        row_a, row_b = Text("  "), Text("  ")
        for (label, state), width in zip(view.human_row, widths):
            row_a += Text(f"human:{label}".ljust(width) if label else "".ljust(width))
            row_a += Text("      ")
            row_b += status_text(state.ljust(width)) + Text("      ")
        console.print(row_a)
        console.print(row_b)
    console.print()


# ── next ───────────────────────────────────────────────────────────────────

def render_next(plan, unit, gate_id: str, manual: bool) -> None:
    rule(f"UNIT {unit.id[1:]} / {unit.title.upper()}", None, 30)
    console.print()
    console.print(f"Provider       {plan.provider} / {plan.model}")
    console.print("Inputs")
    for artifact_id, state in plan.inputs:
        console.print(f"  {('run/' + artifact_id + '.json'):<31}{state}")
    console.print("Will produce")
    for artifact_id in plan.produces:
        console.print(f"  run/{artifact_id}.json")
    console.print("Next checkpoint")
    console.print(f"  {gate_id}")
    console.print()
    if manual:
        console.print("This provider is web-only. Manual steps:")
        console.print("  1. Open a new session at the provider.")
        console.print(f"  2. Paste the contents of {plan.role_path}.")
        console.print("  3. Save the output to the paths listed under 'Will produce'.")
        console.print("  4. Run: rgraph status")
        console.print()
    console.print("No command has been executed.")
    console.print()
    console.print("Choose what happens next:")
    console.print("  1. Execute — run this one provider command")
    console.print("  2. Dry run — show the exact command only")
    console.print("  3. Stop — make no changes")
    console.print("  Shortcuts: E / D / S")


# ── trace ──────────────────────────────────────────────────────────────────

def render_trace(chain, text: str) -> None:
    console.print(f"CLAIM {chain.claim}")
    console.print(f'"{text}"')
    console.print()
    for index, link in enumerate(chain.links):
        last = index == len(chain.links) - 1
        stem = "`--" if last else "+--"
        suffix = f"{' ' * max(1, 34 - len(link.label))}{link.status}" if link.status else ""
        console.print(f"{stem} {link.label}{suffix}")
        if link.detail:
            console.print(f"{'   ' if last else '|  '} `-- {link.detail}")
    console.print()
    console.print("Assurance")
    if chain.complete:
        console.print("  Provenance chain is complete.")
    else:
        console.print(Text("  Provenance chain is incomplete.", style=STATUS_STYLE["FAIL"]))
        for gap in chain.missing:
            console.print(f"    {gap}")
    console.print("  Scientific validity still requires human review.")


# ── revise ─────────────────────────────────────────────────────────────────

def render_revise(gate_id, reason, target, remaining, unit_title) -> None:
    rule(f"REVISE {gate_id}", None, 30)
    console.print()
    console.print(f"Reason          {reason}")
    console.print(f"Return to       {target}  {unit_title}")
    console.print(f"Revision budget {remaining + 1} -> {remaining}")
    console.print()
    console.print("Run next:")
    console.print(f"  rgraph next --unit {target}")


# ── review / completion ────────────────────────────────────────────────────

def render_completion(view) -> None:
    rule(view.headline, None, 25)
    console.print()
    console.print(f"Units         {view.units_complete} / 12 complete")
    console.print(f"Gates         {view.gate_line}")
    console.print(f"Artifacts     {view.artifact_line}")
    console.print(f"Review        {view.review_level}")
    console.print(f"Human release {view.release_state}")
    console.print()
    if view.ready:
        console.print("The run is ready for a human release decision.")
    else:
        console.print("The run is not ready for release; unresolved gates remain.")
    console.print("It has not been approved for publication.")
    console.print()


# ── setup ──────────────────────────────────────────────────────────────────

def render_setup(detected, plan, level, note, conflicts, manual=(), warnings=(),
                 unregistered=()) -> None:
    console.print("Detected")
    for provider_id, state in sorted(detected.items()):
        console.print(f"  {provider_id:<14}{state}")
    if any(state.startswith("NOT ON PATH") for state in detected.values()):
        console.print()
        console.print("Installed, but rgraph cannot invoke it: it runs the command the")
        console.print("same way your shell resolves it, so a directory missing from this")
        console.print("PATH is out of reach. Add that directory to your PATH, or write an")
        console.print("absolute path into providers.yaml — in both `invoke` and the first")
        console.print("element of `exec_argv`, which is what actually gets executed.")
    if unregistered:
        console.print()
        console.print("On PATH, not in providers.yaml")
        for name in unregistered:
            console.print(f"  {name:<14}describe it there to assign it a role")
    console.print()
    render_plan(plan, level, note, conflicts, manual, warnings)


def render_plan(plan, level, note, conflicts, manual=(), warnings=(),
                heading="Proposed assignment") -> None:
    console.print(heading)
    for role, assignment in plan.items():
        effort = f"@{assignment.effort}" if assignment.effort else ""
        console.print(f"  {role:<14}{assignment.provider}/{assignment.model}{effort}")
    console.print(f"  {'separation':<14}{SEP_LABELS.get(level, level)}")
    if note:
        for line in note.splitlines():
            console.print(f"  {'':<14}{line}")
    if manual:
        console.print()
        console.print(Text("Manual relay required", style=STATUS_STYLE["CAVEAT"]))
        for message in manual:
            console.print(f"  {message}")
    if warnings:
        console.print()
        console.print(Text("Gates this plan cannot pass", style=STATUS_STYLE["FAIL"]))
        for message in warnings:
            console.print(f"  {message}")
    if conflicts:
        console.print()
        console.print(Text("Blocked assignments", style=STATUS_STYLE["FAIL"]))
        for message in conflicts:
            console.print(f"  {message}")
    console.print()
