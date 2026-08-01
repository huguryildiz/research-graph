# Contributing

## Setup

```bash
python3 --version                  # 3.11 or newer
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
```

A clean checkout should report every test passing. If it does not, that is a bug
worth an issue on its own — the suite is meant to be green before you change
anything.

## What CI checks

Three jobs, each guarding something that once broke silently.

- **test** — the suite on Python 3.11, 3.12 and 3.13 across Linux, macOS and
  Windows, plus `pip check`.
- **wheel** — builds the wheel, installs it into a fresh environment, and runs
  `rgraph` from a directory that is not the repository. The suite runs from a
  checkout, where every config file is one relative path away; this job is what
  would catch a wheel that shipped no schemas.
- **onboarding** — runs the commands the README gives a newcomer, in order:
  `demo`, then `setup`, then `demo` again, then `init` → `seal` → `check H1`.
  A change that makes `setup` break the demo fails here.

## House rules

**The example run is a fixture, and it says so.** `example-run/meta.json` carries
`"provenance": "synthetic"`. `rgraph check` refuses to write gate records into
the committed copy, so verifying it never restamps who decided what. If you need
to change it, change it deliberately and reseal it — do not let a command do it
for you.

**Digests are recomputed, never trusted.** Every artifact's `content_hash` is
checked against its own body on read. If you add a code path that reads an
artifact, it inherits this for free through `rgraph.run.Artifact`; do not reach
around it.

**The claim boundary is load-bearing.** Every gate screen prints
`Scientific correctness was not determined`, passing or failing. Tests assert
this. It is not decoration.

**Separation is a level, never a word.** The kit prints `CONTEXT ONLY`,
`SEPARATE MODEL` or `SEPARATE PROVIDER`, with the caveat attached when the level
is weak. It never prints "independent".

## Adding a provider

`providers.yaml` only. `rgraph` knows no provider — it carries identity strings
and an argv template, so a new entry needs no code. If you find yourself editing
Python to add one, something has leaked and it is worth an issue.

## Reporting something

Include the command you ran, its exit code, and the output. Exit codes are a
contract: `0` pass, `1` a gate or lint failed, `2` usage or configuration error.
A traceback is always a bug, whatever caused it.
