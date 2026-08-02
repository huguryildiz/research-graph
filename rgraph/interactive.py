"""Small, dependency-free prompts shared by the interactive CLI journey."""

from __future__ import annotations

import sys
from collections.abc import Iterable

from rgraph.render import MUTED_STYLE, muted, prompt_input, section, table_row


class InteractionCancelled(Exception):
    """The user stopped a prompt before committing a change."""


def is_terminal() -> bool:
    try:
        return bool(sys.stdin.isatty())
    except (AttributeError, ValueError):
        return False


def ask_text(label: str, *, default: str | None = None, required: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        try:
            value = prompt_input(label, suffix=suffix).strip()
        except (EOFError, KeyboardInterrupt) as exc:
            raise InteractionCancelled from exc
        if value:
            return value
        if default is not None:
            return default
        if not required:
            return ""
        muted("Please enter a value, or press Ctrl-C to cancel.")


def confirm(label: str, *, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    while True:
        try:
            value = prompt_input(label, suffix=f" [{hint}]", marker=" ").strip().lower()
        except (EOFError, KeyboardInterrupt) as exc:
            raise InteractionCancelled from exc
        if not value:
            return default
        if value in ("y", "yes"):
            return True
        if value in ("n", "no"):
            return False
        muted("Please answer y or n.")


def choose(
    label: str,
    options: Iterable[tuple[str, str]],
    *,
    default: str | None = None,
    allow_cancel: bool = False,
) -> str | None:
    """Choose by number or key; labels explain unfamiliar internal values."""
    rows = list(options)
    if not rows:
        raise ValueError("choose() needs at least one option")
    section(label)
    for index, (key, description) in enumerate(rows, start=1):
        marker = " (default)" if key == default else ""
        table_row(str(index), description + marker, width=3)
    if allow_cancel:
        table_row("0", "Cancel", width=3, value_style=MUTED_STYLE)
    by_key = {key.lower(): key for key, _ in rows}
    while True:
        try:
            answer = prompt_input("Choose", marker=": ").strip().lower()
        except (EOFError, KeyboardInterrupt) as exc:
            raise InteractionCancelled from exc
        if not answer and default is not None:
            return default
        if allow_cancel and answer in ("0", "cancel", "q", "quit"):
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(rows):
            return rows[int(answer) - 1][0]
        if answer in by_key:
            return by_key[answer]
        muted(
            f"Choose 1-{len(rows)}"
            + (", or 0 to cancel." if allow_cancel else ".")
        )


def split_items(value: str) -> list[str]:
    """Turn one friendly semicolon-separated answer into clean list entries."""
    return [item.strip() for item in value.split(";") if item.strip()]
