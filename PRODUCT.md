# Product

<!-- impeccable:product-schema 1 -->

## Platform

terminal / CLI

## Users

The primary user is a researcher or research software developer operating a
governed research run from a terminal. They need to understand the run's
current state, identify blocked or stale work, and execute the next safe action
without learning the repository's internal graph first.

## Product Purpose

`research-graph` is a provider-neutral, contract-gated verification layer for
multi-agent research pipelines. It makes versioned artifacts, provenance
links, gate conditions, reviewer separation, and bounded revision inspectable
and executable. A successful terminal experience makes the current state and
next action legible within seconds while preserving the exact scope of every
check.

## Positioning

The product verifies declared research-process contracts and tamper-evident
artifact relationships without orchestrating agents, calling model APIs, or
claiming that the underlying science is correct.

## Operating Context

Users work in a shell, often inside a repository checkout or an installed
package. The primary journey is setup, run initialization, status inspection,
unit execution, gate checking, bounded revision, provenance tracing, and a
human release decision. Output must remain useful in interactive terminals,
narrow windows, CI logs, pipes, and files.

## Capabilities and Constraints

- Status words such as `PASS`, `FAIL`, `WAIT`, `STALE`, `BLOCKED`, and
  `CAVEAT` carry meaning independently of color.
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

The product name is `research-graph`. Its terminal identity assumes the user's
dark canvas without painting over terminal preferences, then uses cool neutral
text with emerald verification, amber caution, and pink bounded-revision
accents. These colors reinforce rather than replace text. The voice is direct,
precise, calm, and evidence-bounded.

## Evidence on Hand

The repository includes the executable CLI, tests, a synthetic demonstration
fixture, `assets/icon.svg`, `README.md`, `index.html`, and
`architecture.html`. No customer claims, production benchmarks, or real-study
outcomes may be inferred from these assets.

## Product Principles

1. Lead with current state and the next safe action.
2. Make verification scope and uncertainty visible, not decorative footnotes.
3. Use progressive disclosure: summary first, evidence and detail on demand.
4. Preserve semantic clarity without color, animation, or a wide terminal.
5. Treat every mutation as attributable, bounded, and recoverable.

## Accessibility & Inclusion

The CLI must remain operable without color and readable in narrow terminals,
CI logs, pipes, and files. Status cannot be communicated by color alone.
