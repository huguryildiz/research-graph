# Contributing

## Setup

```bash
python3 --version                 # 3.11 or newer
uv sync --frozen --extra dev      # installs the committed dependency graph
uv run --frozen --extra dev pytest -q
```

A clean checkout should report every test passing. If it does not, that is a bug
worth an issue on its own — the suite is meant to be green before you change
anything. Contributors who do not use `uv` may still install `.[dev]` into a
virtual environment, but that resolves the declared compatibility ranges rather
than reproducing the repository's locked environment.

## What CI checks

Four jobs, each guarding something that once broke silently.

- **lock** — rejects drift between `pyproject.toml` and `uv.lock`, installs the
  frozen environment, and checks its dependency consistency.

- **test** — the suite on Python 3.11, 3.12 and 3.13 across Linux, macOS and
  Windows, plus `pip check`.
- **wheel** — builds the wheel, installs it into a fresh environment, and runs
  `rgraph` from a directory that is not the repository. The suite runs from a
  checkout, where every config file is one relative path away; this job is what
  would catch a wheel that shipped no schemas.
- **onboarding** — runs the commands the README gives a newcomer, in order:
  `demo`, then `setup`, then `demo` again, then `init` → `decide H1` →
  `check H1` → first-agent dry-run.
  A change that makes `setup` break the demo fails here.

## House rules

**The example run is a fixture, and it says so.** `example-run/meta.json` carries
`"provenance": "synthetic"`. `rgraph check` never writes gate records, and
`rgraph challenge` refuses to invoke a reviewer against the committed fixture,
so verifying it never restamps who decided what. If you need
to change it, change it deliberately and reseal it — do not let a command do it
for you.

**Digests are recomputed, never trusted.** Every artifact's `content_hash` is
checked against its own body on read. If you add a code path that reads an
artifact, it inherits this for free through `rgraph.run.Artifact`; do not reach
around it.

**Schema `$id`s name an address we can answer for.** They are identifiers, and
the registry resolves them from disk without touching the network, so it is
tempting to treat them as decoration. An `$id` under a domain nobody here owns
is one anyone could register and then serve different schemas from. They point
at this repository's raw files, and a test enforces that every `$id` matches its
own filename and every `$ref` stays inside that prefix. Moving them is fine;
moving them somewhere unowned is not.

**The claim boundary is load-bearing.** Every gate screen prints
`Scientific correctness was not determined`, passing or failing. Tests assert
this. It is not decoration.

**Separation is a level, never a word.** The kit prints `CONTEXT ONLY`,
`SEPARATE MODEL` or `SEPARATE PROVIDER`, with the caveat attached when the level
is weak. It never prints "independent".

## Changing the graph or gates

`graph.yaml`, `gates.yaml` and `schemas/` are authoritative. After changing an
artifact producer, gate input, criterion, route, separation policy or revision
budget, regenerate the architecture contract data:

```bash
python scripts/generate_architecture_contracts.py
python scripts/generate_architecture_contracts.py --check
pytest -q tests/test_architecture_generation.py tests/test_diagram_matches_graph.py
```

Do not hand-edit the marked `ARTIFACTS` and `CONTRACTS` block in
`architecture.html`. The generator changes only that block; the SVG, CSS,
layout, theme and interaction code remain manually designed.

## Adding a provider

`providers.yaml` only. `rgraph` knows no provider — it carries identity strings
and an argv template, so a new entry needs no code. If you find yourself editing
Python to add one, something has leaked and it is worth an issue.

## Reporting something

Include the command you ran, its exit code, and the output. Exit codes are a
contract: `0` pass, `1` a gate or lint failed, `2` usage or configuration error.
A traceback is always a bug, whatever caused it.
