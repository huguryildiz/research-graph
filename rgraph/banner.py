"""The responsive cell-grid wordmark used by the terminal renderer.

THESIS: The opening is a circuit-built research mark followed by a proof ledger.
OWN-WORLD: White and emerald cell-grid letters with provenance/revision traces.
STORY: Identify the product, inspect evidence state, then take one safe action.
FIRST VIEWPORT: Wide terminals get the full mark; narrow terminals get one line.
FORM: The supplied tiled circuit wordmark inside the release-proof ledger.
"""

RESEARCH_ART = """\
  ▉▉▉█  ▉▉▉▉█ ▉▉▉▉█ ▉▉▉▉█ ▉▉▉▉█ ▉▉▉█  ▉▉▉▉█ █   █
  ▇   █ ▇     ▇     ▇     ▇   ▇ ▇   █ ▇     ▇   ▇
  ▇   ▇ ▇     ▇     ▇     ▇   ▇ ▇   ▇ ▇     ▇   ▇
  ▉▉▉█  ▉▉▉█  ▉▉▉▉█ ▉▉▉█  ▉▉▉▉▇ ▉▉▉█  ▇     ▉▉▉▉▇
  ▇ ▉▇  ▇         ▇ ▇     ▇   ▇ ▇ ▉▇  ▇     ▇   ▇
  ▇  ▉█ ▇         ▇ ▇     ▇   ▇ ▇  ▉█ ▇     ▇   ▇
  ▇   ▇ ▉▉▉▉█ ▉▉▉▉▇ ▉▉▉▉█ ▇   ▇ ▇   ▇ ▉▉▉▉█ ▇   ▇"""

GRAPH_ART = """\
  ▉▉▉▉█ ▉▉▉█  ▉▉▉▉█ ▉▉▉▉█ █   █
  ▇     ▇   █ ▇   ▇ ▇   ▇ ▇   ▇
  ▇     ▇   ▇ ▇   ▇ ▇   ▇ ▇   ▇
  ▇ ▉▉█ ▉▉▉█  ▉▉▉▉▇ ▉▉▉▉▇ ▉▉▉▉▇
  ▇   ▇ ▇ ▉▇  ▇   ▇ ▇     ▇   ▇
  ▇   ▇ ▇  ▉█ ▇   ▇ ▇     ▇   ▇
  ▉▉▉▉▇ ▇   ▇ ▇   ▇ ▇     ▇   ▇"""

PROVENANCE_SPINE = "●──●──◆"
REVISION_SPINE = "╰────↺"
WORDMARK = "research-graph"
TAGLINE = "contract-gated agentic research"


def render_banner(compact: bool = False) -> str:
    """Return the wordmark without terminal colour or styling."""
    if compact:
        return f"  ◆  {WORDMARK}\n"
    return "\n".join((
        "", RESEARCH_ART, "", GRAPH_ART, "",
        f"  {PROVENANCE_SPINE}  {TAGLINE}",
        f"  {REVISION_SPINE}", "",
    ))
