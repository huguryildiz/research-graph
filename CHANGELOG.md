# Changelog

Notable changes, newest first. This project is pre-1.0; until it isn't, the CLI
surface may still move.

## [Unreleased]

### Added

- **`rgraph decide <GATE>`, and human gates that need a human.** A human gate
  used to pass on file presence alone, and the record it wrote named a *model*
  as the person who decided it — `decided_by: {role: human, identity:
  codex/gpt-5.6}` — while nobody had been asked anything. Human gates now stay
  `AWAITING` until somebody answers them. `rgraph decide` puts each claim the
  gate declares it `proves` to a person one at a time, and records the answers
  and who gave them under `attestation`. The questions are not new: they are the
  `proves` entries that were already in `gates.yaml` and had never been read.
- **An attestation is pinned to what was on the table.** It covers the digests
  that existed when it was given, so editing an artifact afterwards retires it.
  Resealing repairs the hash; it cannot repair the reading, so the gate asks
  again.

### Fixed

- **`check` no longer writes a human gate's record.** A command that can write
  its own attestation can forge one, so the two verbs are split: `decide`
  decides, `check` verifies. The shipped `example-run/` is now read-only to
  every writing command rather than to `check` alone — `rgraph review` had been
  quietly creating `release_manifest.json` and `gates/FINAL.json` inside it.

- **`rgraph setup` wrote inside the installed package.** Off a checkout, the kit
  root is the packaged copy, so the assignment landed in `site-packages` — where
  the user could not see it and the next `uv tool upgrade` would delete it. It
  now writes `~/.config/rgraph/assignment.yaml` (`$XDG_CONFIG_HOME` honoured) as
  the machine default, and `rgraph setup --here` writes `./assignment.yaml` for a
  single study. Every command reads the study copy first, then the machine
  default, then the kit root.

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
