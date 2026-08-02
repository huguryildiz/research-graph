"""Banner art. Two literal blocks; nothing here is generated."""

_FULL = """\
  ████  █████ █████ █████ █████ ████  █████ █   █
  █  █  █     █     █     █   █ █  █  █     █   █
  ████  ████  █████ ████  █████ ████  █     █████
  █ █   █         █ █     █   █ █ █   █     █   █
  █  █  █████ █████ █████ █   █ █  █  █████ █   █

  █████ ████  █████ █████ █   █
  █     █  █  █   █ █   █ █   █
  █  ██ ████  █████ █████ █████
  █   █ █ █   █   █ █     █   █
  █████ █  █  █   █ █     █   █

  ○──▶○──▶◆──▶○──▶◆        contract-gated agentic research
  │            │           v0.2.0 · graph engineering, verified
  └────────────┘
"""

_COMPACT = """\
  ████  █████ ████  █████ █████ █   █
  █  █  █     █  █  █   █ █   █ █   █
  ████  █  ██ ████  █████ █████ █████
  █ █   █   █ █ █   █   █ █     █   █
  █  █  █████ █  █  █   █ █     █   █
"""


def render_banner(compact: bool = False) -> str:
    """Return the banner. ``compact`` drops the motif for narrow terminals."""
    return _COMPACT if compact else _FULL
