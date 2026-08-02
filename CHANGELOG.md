# Changelog

Notable changes, newest first. This project is pre-1.0; until it isn't, the CLI
surface may still move.

## [Unreleased]

## [0.1.0] — 2026-08-02

First public release. The verifier, the reference graph, the nine gates and a
worked example that exercises all of them.

### Added

- **`rgraph` CLI, ten commands** — `demo`, `setup`, `init`, `status`, `next`,
  `seal`, `check`, `revise`, `trace`, `review`. Global flags are accepted on
  either side of the command name.
- **Layer 1, static** — `rgraph check --static` lints the graph for type
  mismatches, cycles outside `return` edges, unbounded correction loops,
  unreachable gates and dead nodes.
- **Layer 2, dynamic** — existence, JSON Schema, provenance, staleness, reviewer
  separation and the revision budget over a `run/` directory.
- **Integrity that recomputes** — every artifact is checked against its own
  `content_hash` on read, so a body edited without resealing invalidates its
  gate and everything downstream.
- **`rgraph init` and `rgraph seal`** — a run directory with the two artifacts no
  agent produces, and the canonical SHA-256 nobody types by hand. `init`, `seal`,
  `check H1` reaches a green gate from nothing.
- **Separation levels** — `CONTEXT ONLY`, `SEPARATE MODEL`, `SEPARATE PROVIDER`,
  always printed with the caveat when the level is weak. The word "independent"
  is never used.
- **21 artifact schemas** plus the gate record and envelope schemas.
- **Six role contracts** in `roles/`, shared by the Claude Code and Codex plugin
  manifests without being copied.
- **`example-run/`** — a synthetic-provenance fixture with real data, real
  statistics and four Crossref-resolvable DOIs, reporting an honest negative.
- **Packaged runtime** — the graph, gates, schemas, roles and both example runs
  ship inside the wheel, so `pip install` works away from a checkout.
- **CI** — tests on Python 3.11–3.13 across Linux, macOS and Windows; a wheel
  installed into a clean environment and run from outside the repository; and the
  newcomer command sequence itself.

### Known limits

- The reviewer/producer check compares strings. It is a discipline mechanism, not
  a cryptographic one — see [SECURITY.md](SECURITY.md).
- `rgraph` judges provenance, never scientific correctness. Every gate screen
  says so, passing or failing.
- Offline by default. `check E1 --online` is the only command that touches the
  network; without one it reports which DOIs it could not reach instead of
  calling them fabricated.

[Unreleased]: https://github.com/huguryildiz/research-graph/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/huguryildiz/research-graph/releases/tag/v0.1.0
