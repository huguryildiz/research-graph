"""Every screen. Colour reinforces status; the status word always carries it."""

from __future__ import annotations

from rich.console import Console
from rich.text import Text

console = Console(highlight=False, soft_wrap=False)

STATUS_STYLE = {
    "PASS": "bold green", "FAIL": "bold red", "WAIT": "dim",
    "READY": "bold cyan", "STALE": "bold yellow", "BLOCKED": "bold red",
    "CAVEAT": "bold yellow", "----": "dim", "SKIP": "dim",
}
CLAIM_BOUNDARY_LINE = "  [----] Scientific correctness was not determined"


def rule(title: str, status: str | None = None, width: int = 49) -> None:
    if status is None:
        console.print(Text(title, style="bold"))
    else:
        pad = max(1, width - len(title) - len(status))
        console.print(
            Text(title, style="bold") + Text(" " * pad) + status_text(status)
        )
    console.print("-" * width)


def status_text(status: str) -> Text:
    return Text(status, style=STATUS_STYLE.get(status, ""))


def render_claim_boundary() -> None:
    console.print(Text(CLAIM_BOUNDARY_LINE, style="dim"))


def render_static_report(findings) -> None:
    failures = [f for f in findings if f.status == "FAIL"]
    rule("STATIC GRAPH CHECK", "FAIL" if failures else "PASS")
    console.print()
    for check in ("type_match", "acyclic", "bounded", "reachable", "dead_node"):
        rows = [f for f in findings if f.check == check]
        worst = "FAIL" if any(r.status == "FAIL" for r in rows) else "PASS"
        console.print(
            Text("  [", style="dim") + status_text(worst) + Text("] ", style="dim")
            + Text(check)
        )
        for row in rows:
            if row.status == "FAIL":
                console.print(f"        {row.subject}")
                console.print(f"        {row.detail}")
                console.print(f"        Fix: {row.fix}")
    console.print()
    console.print("What this check covered")
    console.print("  [PASS] Graph structure")
    render_claim_boundary()
