# Product

<!-- impeccable:product-schema 1 -->

## Platform

local browser application + terminal CLI

## Users

The primary user is a researcher or research software developer operating a
governed research run locally. Mixed-experience teams should be able to start,
inspect, and navigate a study in the browser without learning artifact JSON or
provider syntax. Technical users also need a stable CLI for scripts, CI, exact
diagnostics, and attributable human decisions.

## Product Purpose

`research-graph` is a provider-neutral, contract-gated verification layer for
multi-agent research pipelines. It makes versioned artifacts, provenance
links, gate conditions, reviewer separation, and bounded revision inspectable
and executable. A successful experience makes the current state and next safe
action legible within seconds on either surface while preserving the exact
scope of every check.

## Positioning

The product verifies declared research-process contracts and tamper-evident
artifact relationships without orchestrating agents, calling model APIs, or
claiming that the underlying science is correct.

## Operating Context

Users launch `rgraph ui` from a shell, then work in a loopback-only browser
application backed by the same services as the CLI. The browser is the primary
surface for guided setup, study creation, workflow navigation, evidence
inspection, and explicitly approved provider jobs. The terminal remains the
bootstrap and automation surface and the only place that records human gates or
the final release decision. Both surfaces must agree about what is permitted.

## Capabilities and Constraints

- Status words such as `PASS`, `FAIL`, `WAIT`, `STALE`, `BLOCKED`, and
  `CAVEAT` carry meaning independently of color.
- The browser derives its study map, gates, evidence, and next actions from the
  executable graph and shared services rather than a second workflow model.
- Browser mutations require a session token; provider execution requires a
  separate single-use approval bound to the exact plan shown.
- The browser may display a human decision state and copy the terminal command,
  but it has no route that records a human or final decision.
- The local server binds to loopback and adds no remote service or database.
- Regular screens remain readable within 80 columns and adapt to narrow
  terminals.
- `--no-banner`, `NO_COLOR`, and non-interactive output remain first-class.
- Every gate screen retains the limitation that scientific correctness was not
  determined.
- Exit codes remain `0` for success, `1` for gate or lint failure, and `2` for
  usage or configuration failure.
- The synthetic `example-run/` is a fixture, not evidence from a real
  multi-agent study.

## Brand Commitments

The product name is `research-graph`; the PyPI distribution and CLI are
`rgraph`. The local evidence desk uses a calm navy, sage, and amber system with
generous spacing and clear evidence hierarchy. The terminal identity assumes
the user's canvas without painting over terminal preferences, then uses cool
neutral text with emerald verification, amber caution, and pink
bounded-revision accents. Color reinforces rather than replaces text. The
voice is direct, precise, calm, and evidence-bounded.

## Evidence on Hand

The repository includes the executable CLI, tests, a synthetic demonstration
fixture, `assets/icon.svg`, `README.md`, `index.html`, and
`architecture.html`. No customer claims, production benchmarks, or real-study
outcomes may be inferred from these assets.

## Product Principles

1. Lead with current state and the next safe action.
2. Make verification scope and uncertainty visible, not decorative footnotes.
3. Use progressive disclosure: summary first, evidence and detail on demand.
4. Preserve semantic clarity without color, animation, a pointer, or a wide
   terminal.
5. Treat every mutation as attributable, bounded, and recoverable.

## Accessibility & Inclusion

The browser must retain keyboard navigation, visible focus, adequate targets,
drawer focus containment, and readable narrow layouts. The CLI must remain
operable without color and readable in narrow terminals, CI logs, pipes, and
files. Neither surface may communicate status by color alone.
