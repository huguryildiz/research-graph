# research-graph v0.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a clonable starter kit that machine-verifies the claims of the `architecture.html` reference diagram — a graph linter, an artifact/provenance verifier, six executable role contracts, and a filled end-to-end example run — behind an eight-command `rgraph` CLI.

**Architecture:** Three config files separate concerns (`graph.yaml` = architecture, `assignment.yaml` = who runs which role, `providers.yaml` = what each provider can do), and `gates.yaml` binds gates to required artifacts, independence levels and revision budgets. The CLI is a *verification layer*, not an orchestrator: it reads a `run/` directory of JSON artifacts, validates them against JSON Schema, walks the provenance hash chain, and returns an exit code. The only execution it performs is a single-shot, user-approved subprocess call to one provider CLI (`rgraph next` → `[E] Execute`).

**Tech Stack:** Python ≥3.11, `jsonschema>=4.18`, `rich>=13.0`. Dev-only: `pytest`. Static site: plain HTML on Vercel, zero build step.

## Global Constraints

Every task's requirements implicitly include this section.

- **Language.** The repository, README, role files, schemas, code comments and *all* CLI output are English. Only `docs/2026-07-31-research-graph-design.md` (the spec) and files under `docs/superpowers/` stay Turkish.
- **Runtime dependencies are exactly `jsonschema>=4.18` and `rich>=13.0`.** Nothing else. In particular **no PyYAML** — Task 2 builds a strict YAML-subset loader. `referencing` may be imported because `jsonschema>=4.18` already depends on it.
- **Dev dependencies are exactly `pytest`.** No plugins, no fixtures libraries, no coverage tooling.
- **Python floor:** `requires-python = ">=3.11"`.
- **No orchestrator.** No scheduler, queue, retry loop, or multi-step state machine. `rgraph next` may spawn exactly one subprocess per invocation and must then return control to the user.
- **No network on the default path.** DOI resolution over HTTP happens only under an explicit `--online` flag, using `urllib.request` from the standard library. Criterion 6 (clean machine, five minutes) must pass with networking disabled.
- **No scientific-correctness judgement.** Every gate result — PASS, FAIL and CAVEAT alike — prints the literal line `  [----] Scientific correctness was not determined`.
- **Status vocabulary is closed:** `PASS · FAIL · WAIT · READY · STALE · BLOCKED · CAVEAT`. No other status word may appear in CLI output. Colour may reinforce a status but must never be its only carrier.
- **Exit codes:** `0` = every requested check passed (CAVEAT still exits 0); `1` = at least one FAIL, STALE or BLOCKED; `2` = usage, config or I/O error.
- **Banner policy:** `rgraph` with no arguments and `rgraph setup` print the banner. `status`, `next`, `check`, `revise`, `trace`, `review` never do. `--no-banner` suppresses it everywhere.
- **Verbosity:** model reasoning, token counts and provider logs never reach stdout. They go to `run/logs/<unit>-<timestamp>.log` and are echoed only under `--verbose`.

### Locked scope decisions (deviations from the spec, decided 2026-07-31)

These four points resolve ambiguities or conflicts in the spec. They are binding; the README records each one.

1. **21 artifact schemas**, not 18. The spec's §11 count is wrong: `architecture.html`'s normative `ARTIFACTS` registry holds 20 entries, and `kg_snapshot` (spec §4.1, §7) is the 21st. Writing all 21 means every gate input in the diagram's `CONTRACTS` table has a schema, so the static reachability lint has no blind spot.
2. **Graph nodes are the 12 work units**, not the 5 pipeline stages. Spec §4.1's `{id: retrieval, ...}` snippet is illustrative; the CLI output it must feed (`Next unit 05 Experiment execution`, `Return to Unit 02 / Evidence mapping`, `Progress 4 / 12 units complete`) requires unit granularity. Each unit node carries a `stage:` field, and `rgraph status` aggregates the five-stage pipeline row from it.
3. **Run artifacts are JSON, config files are YAML.** Spec §9.0.3 shows `run/frozen_protocol.yaml`; v0.1 writes `run/frozen_protocol.json`. Reason: the YAML-subset loader (Task 2) is deliberately small and must not become the parser for user-authored evidence. Only `graph.yaml`, `assignment.yaml`, `providers.yaml` and `gates.yaml` are YAML.
4. **Gate decisions are gate records, not an artifact.** Spec §9.0.6's `reviewer_report.json` line becomes `gates/M1.json`. Gate records live in `run/gates/<GATE>.json` under their own `gate_record.schema.json` and are *not* counted among the 21 artifacts.

### Canonical registries (copy these verbatim; every task depends on them)

**Six roles** → `roles/{retrieval,planning,execution,verification,synthesis,reviewer}.md`

| Role | `requires` capabilities | Web-only provider |
|---|---|---|
| `retrieval` | `filesystem` | manual |
| `planning` | `filesystem` | manual |
| `execution` | `filesystem`, `shell` | not assignable |
| `verification` | `filesystem`, `shell` | not assignable |
| `synthesis` | `filesystem` | manual |
| `reviewer` | `read_files` | ideal |

**Twelve units** (`id`, `stage`, `role`, `title`, `produces`):

| id | stage | role | title | produces |
|---|---|---|---|---|
| `u01` | `retrieve` | retrieval | Literature retrieval & evidence extraction | `search_protocol`, `corpus_snapshot`, `kg_snapshot` |
| `u02` | `retrieve` | retrieval | Evidence matrix | `evidence_matrix` |
| `u03` | `plan` | planning | Hypothesis registry | `hypothesis_registry` |
| `u04` | `plan` | planning | Research plan | `design_protocol` |
| `u05` | `plan` | planning | Experiment design & modeling | `frozen_protocol` |
| `u06` | `execute` | execution | Code generation & execution | `code_commit`, `environment_lock`, `data_manifest` |
| `u07` | `execute` | execution | Experimental results | `run_manifest`, `raw_results` |
| `u08` | `verify` | verification | Validation & reproducibility | `reproduction_report` |
| `u09` | `verify` | verification | Statistical verification | `statistical_report` |
| `u10` | `verify` | verification | Verification report | `verification_report` |
| `u11` | `write` | synthesis | Result synthesis & visualization | `figure_registry` |
| `u12` | `write` | synthesis | Manuscript | `manuscript`, `claim_evidence_map` |

Plus `human` (produces `problem_spec`, `governance_record`, `release_manifest`) and `reviewer` (produces nothing; owns challenge gates).

**Twenty-one artifacts**, in dependency order:
`problem_spec · governance_record · search_protocol · corpus_snapshot · kg_snapshot · evidence_matrix · hypothesis_registry · design_protocol · frozen_protocol · code_commit · environment_lock · data_manifest · run_manifest · raw_results · reproduction_report · statistical_report · verification_report · claim_evidence_map · figure_registry · manuscript · release_manifest`

Two of them carry a payload file plus a JSON sidecar: `manuscript.md` + `manuscript.meta.json`, `raw_results.jsonl` + `raw_results.meta.json`. The other nineteen are `run/<artifact_id>.json`.

**Nine gates plus FINAL** (`id`, `kind`, `owner`, `producer`):

| id | kind | owner | producer unit | short |
|---|---|---|---|---|
| `H1` | human | human | — | Scope, constraints & research intent |
| `E1` | challenge | reviewer | `u02` | Evidence fidelity |
| `H2` | human | human | `u02` | Evidence completeness & adequacy |
| `H3` | human | human | `u03` | Hypothesis relevance & feasibility |
| `T1` | challenge | reviewer | `u05` | Design & reproduction |
| `H4` | human | human | `u05` | Frozen protocol, resources & risk |
| `T2` | challenge | verification | `u07` | Code, data & run integrity |
| `V1` | challenge | reviewer | `u10` | Verification evidence |
| `M1` | challenge | reviewer | `u12` | Manuscript claims |
| `FINAL` | release | human | `u12` | Release · revise · narrow · null · stop |

**Seven typed return reasons:** `evidence_gap · hypothesis_defect · scope_plan_defect · assumption_violation · code_run_defect · claim_support_gap · revision`

**Three independence levels:** `context_only · separate_model · separate_provider`

---

## File Structure

```
research-graph/
├── README.md
├── LICENSE                      # MIT
├── pyproject.toml
├── index.html                   # Vercel entry: thin strip + <iframe>-free inline of diagram
├── architecture.html            # v5.1 diagram, extended with the configurator panel
├── vercel.json
├── graph.yaml                   # 12 units + 3 stores + human + reviewer + 10 gates + terminal
├── assignment.example.yaml
├── providers.yaml
├── gates.yaml
├── roles/
│   ├── retrieval.md  planning.md  execution.md
│   └── verification.md  synthesis.md  reviewer.md
├── schemas/
│   ├── _envelope.schema.json     # provenance envelope, $ref'd by all 21
│   ├── gate_record.schema.json
│   ├── run_meta.schema.json
│   └── <21 artifact>.schema.json
├── rgraph/
│   ├── __init__.py               # __version__
│   ├── __main__.py               # python -m rgraph
│   ├── cli.py                    # argparse dispatch, exit codes, global flags
│   ├── banner.py                 # two literal art constants + motif
│   ├── yamlmini.py               # strict YAML-subset loader
│   ├── config.py                 # load + normalise the four YAML files
│   ├── hashing.py                # canonical JSON, sha256, file digests
│   ├── schemas.py                # schema registry + validate()
│   ├── run.py                    # run/ discovery, meta.json, artifact loading
│   ├── provenance.py             # input chain, staleness, trace assembly
│   ├── separation.py             # independence level from assignment+providers
│   ├── lint.py                   # Layer 1: five static checks
│   ├── checks.py                 # Layer 2: per-gate content checks
│   ├── gates.py                  # gate evaluation engine, gate record writing
│   ├── render.py                 # every screen, rich-based
│   ├── runner.py                 # single-shot approved subprocess exec
│   └── commands/
│       ├── __init__.py  demo.py  setup.py  status.py  next_.py
│       └── check.py  revise.py  trace.py  review.py
├── template-run/                 # empty skeleton + meta.json stub
├── example-run/                  # filled, all nine gates green
│   ├── meta.json  <artifacts>  manuscript.md  raw_results.jsonl
│   ├── gates/H1.json … gates/M1.json
│   └── code/estimator_bench.py   # the experiment that produced raw_results.jsonl
├── tests/
│   ├── test_yamlmini.py  test_config.py  test_lint.py  test_hashing.py
│   ├── test_schemas.py  test_provenance.py  test_separation.py
│   ├── test_checks.py  test_gates.py  test_render.py  test_runner.py
│   ├── test_cli_<command>.py …
│   └── test_acceptance.py
├── .claude-plugin/plugin.json
├── .agents/plugins/marketplace.json
└── plugins/research-graph/.codex-plugin/plugin.json
```

---

### Task 1: Repository skeleton, packaging and banner

**Files:**
- Create: `pyproject.toml`, `LICENSE`, `rgraph/__init__.py`, `rgraph/__main__.py`, `rgraph/cli.py`, `rgraph/banner.py`
- Test: `tests/test_banner.py`, `tests/test_cli_smoke.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `rgraph.__version__: str`; `rgraph.banner.render_banner(compact: bool = False) -> str`; `rgraph.cli.main(argv: list[str] | None = None) -> int`; `rgraph.cli.build_parser() -> argparse.ArgumentParser`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_banner.py
from rgraph.banner import render_banner

def test_full_banner_fits_an_80_column_terminal():
    for line in render_banner().splitlines():
        assert len(line) <= 78, line

def test_compact_banner_fits_a_40_column_terminal():
    for line in render_banner(compact=True).splitlines():
        assert len(line) <= 40, line

def test_full_banner_carries_the_thesis_motif_and_version():
    out = render_banner()
    assert "○──▶○──▶◆──▶○──▶◆" in out
    assert "contract-gated agentic research" in out
    assert "v0.1.0 · graph engineering, verified" in out

def test_compact_banner_has_no_motif():
    assert "○──▶" not in render_banner(compact=True)
```

```python
# tests/test_cli_smoke.py
import pytest
from rgraph.cli import main

def test_version_flag_exits_zero(capsys):
    assert main(["--version"]) == 0
    assert "0.1.0" in capsys.readouterr().out

def test_bare_invocation_prints_banner(capsys):
    assert main([]) == 0
    assert "contract-gated agentic research" in capsys.readouterr().out

def test_no_banner_flag_suppresses_it(capsys):
    assert main(["--no-banner"]) == 0
    assert "contract-gated" not in capsys.readouterr().out

def test_unknown_command_exits_two():
    with pytest.raises(SystemExit) as exc:
        main(["nosuchcommand"])
    assert exc.value.code == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_banner.py tests/test_cli_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rgraph'`

- [ ] **Step 3: Write `pyproject.toml` and `LICENSE`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "research-graph"
version = "0.1.0"
description = "Graph engineering, verified: a contract-gated verification layer for agentic research pipelines"
readme = "README.md"
requires-python = ">=3.11"
license = "MIT"
authors = [{name = "Hüseyin Uğur Yıldız"}]
keywords = ["graph-engineering", "agentic-research", "provenance", "verification"]
dependencies = ["jsonschema>=4.18", "rich>=13.0"]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
rgraph = "rgraph.cli:main"

[project.urls]
Homepage = "https://github.com/huguryildiz/research-graph"

[tool.hatch.build.targets.wheel]
packages = ["rgraph"]
include = ["schemas/**", "roles/**", "graph.yaml", "gates.yaml", "providers.yaml", "assignment.example.yaml", "template-run/**"]
```

Write the standard MIT licence text into `LICENSE` with `Copyright (c) 2026 Hüseyin Uğur Yıldız`.

- [ ] **Step 4: Write `rgraph/banner.py`**

The two art blocks are transcribed **verbatim** from spec §9.0 — do not regenerate them from a font table, and do not alter a single cell.

```python
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
  │            │           v0.1.0 · graph engineering, verified
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
```

- [ ] **Step 5: Write `rgraph/__init__.py`, `rgraph/__main__.py` and `rgraph/cli.py`**

```python
# rgraph/__init__.py
__version__ = "0.1.0"
```

```python
# rgraph/__main__.py
import sys

from rgraph.cli import main

sys.exit(main())
```

```python
# rgraph/cli.py
"""Command dispatch. Exit codes: 0 pass, 1 fail, 2 usage/config error."""

from __future__ import annotations

import argparse
import shutil
import sys

from rgraph import __version__
from rgraph.banner import render_banner

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

BANNER_COMMANDS = frozenset({"setup"})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rgraph",
        description="Graph engineering, verified.",
        add_help=True,
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--no-banner", action="store_true", help="never print the banner")
    parser.add_argument("--verbose", action="store_true", help="echo provider logs to stdout")
    parser.add_argument("--run", default="run", metavar="DIR", help="run directory (default: run)")
    parser.add_argument("--root", default=".", metavar="DIR", help="kit root holding the YAML config")
    parser.add_subparsers(dest="command", metavar="COMMAND")
    return parser


def _print_banner(args: argparse.Namespace) -> None:
    if args.no_banner:
        return
    compact = shutil.get_terminal_size((80, 24)).columns < 52
    print(render_banner(compact=compact))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        _print_banner(args)
        parser.print_help()
        return EXIT_OK
    if args.command in BANNER_COMMANDS:
        _print_banner(args)
    handler = getattr(args, "handler", None)
    if handler is None:  # pragma: no cover - guarded by argparse
        parser.error(f"unknown command: {args.command}")
    try:
        return handler(args)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
```

Subcommands register themselves in later tasks by adding a parser to the subparsers object and calling `set_defaults(handler=...)`. Task 5 introduces the first one; keep `build_parser` free of command-specific code until then.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pip install -e ".[dev]" && python -m pytest tests/ -v`
Expected: 8 passed.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml LICENSE rgraph/ tests/
git commit -m "feat: package skeleton, CLI dispatch and banner"
```

---

### Task 2: Strict YAML-subset loader

The kit reads four YAML files and takes no YAML dependency, so it parses a
deliberately small subset and refuses everything else with a line-numbered
error. Supported: block mappings, block sequences, inline flow mappings and
flow sequences, `#` comments, quoted and bare scalars, `null`/`true`/`false`,
integers and floats. Refused: anchors, aliases, tags, multi-document streams,
block scalars (`|`, `>`), complex keys, tabs for indentation.

**Files:**
- Create: `rgraph/yamlmini.py`
- Test: `tests/test_yamlmini.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `rgraph.yamlmini.loads(text: str, *, source: str = "<string>") -> dict | list`; `rgraph.yamlmini.load_file(path: pathlib.Path) -> dict | list`; `rgraph.yamlmini.YamlError(Exception)` with attributes `line: int`, `source: str`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_yamlmini.py
import pytest

from rgraph.yamlmini import YamlError, loads


def test_block_mapping_and_scalar_types():
    assert loads("a: 1\nb: 2.5\nc: hello\nd: true\ne: null\n") == {
        "a": 1, "b": 2.5, "c": "hello", "d": True, "e": None,
    }


def test_nested_block_mapping():
    assert loads("outer:\n  inner:\n    leaf: 7\n") == {"outer": {"inner": {"leaf": 7}}}


def test_block_sequence_of_flow_mappings():
    text = "nodes:\n  - {id: u01, kind: agent}\n  - {id: E1, kind: gate}\n"
    assert loads(text) == {
        "nodes": [{"id": "u01", "kind": "agent"}, {"id": "E1", "kind": "gate"}]
    }


def test_flow_sequence_inside_flow_mapping():
    text = "n: {id: u01, produces: [a, b, c]}\n"
    assert loads(text) == {"n": {"id": "u01", "produces": ["a", "b", "c"]}}


def test_flow_mapping_may_span_lines():
    text = "n: {id: u01,\n    kind: agent,\n    produces: [a]}\n"
    assert loads(text) == {"n": {"id": "u01", "kind": "agent", "produces": ["a"]}}


def test_quoted_scalar_keeps_special_characters():
    assert loads('a: "codex/{model}"\nb: \'x: y\'\n') == {"a": "codex/{model}", "b": "x: y"}


def test_comments_and_blank_lines_are_ignored():
    assert loads("# top\na: 1  # trailing\n\nb: 2\n") == {"a": 1, "b": 2}


def test_sequence_of_block_mappings():
    text = "items:\n  - id: one\n    v: 1\n  - id: two\n    v: 2\n"
    assert loads(text) == {"items": [{"id": "one", "v": 1}, {"id": "two", "v": 2}]}


@pytest.mark.parametrize(
    "text, needle",
    [
        ("a: &anchor 1\n", "anchor"),
        ("a: *ref\n", "alias"),
        ("a: !!str 1\n", "tag"),
        ("a: |\n  block\n", "block scalar"),
        ("---\na: 1\n", "multi-document"),
        ("a:\n\t- 1\n", "tab"),
    ],
)
def test_unsupported_constructs_are_refused(text, needle):
    with pytest.raises(YamlError) as exc:
        loads(text, source="graph.yaml")
    assert needle in str(exc.value)
    assert "graph.yaml" in str(exc.value)


def test_error_reports_the_line_number():
    with pytest.raises(YamlError) as exc:
        loads("a: 1\nb: {unclosed\n")
    assert exc.value.line == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_yamlmini.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rgraph.yamlmini'`

- [ ] **Step 3: Write `rgraph/yamlmini.py`**

```python
"""A strict YAML subset. Refuses anything it does not fully understand.

Grammar, informally:
    document   := block_mapping
    block_map  := (key ':' (inline | eol nested))*
    block_seq  := ('-' (inline | block_map_inline))*
    inline     := flow_map | flow_seq | scalar
Everything outside this grammar raises YamlError with a line number.
"""

from __future__ import annotations

import pathlib
import re

_BANNED = (
    (re.compile(r"(?<!\\)&[A-Za-z0-9_-]+"), "anchor"),
    (re.compile(r"(?<![\w\"'])\*[A-Za-z0-9_-]+"), "alias"),
    (re.compile(r"(?<![\w\"'])!!?[A-Za-z]"), "tag"),
    (re.compile(r":\s*[|>][-+0-9]*\s*$"), "block scalar"),
)
_NUM = re.compile(r"^-?\d+$")
_FLOAT = re.compile(r"^-?\d+\.\d+([eE][-+]?\d+)?$")
_KEY = re.compile(r"^([A-Za-z0-9_.$/-]+|\"[^\"]*\"|'[^']*')\s*:(\s|$)")


class YamlError(Exception):
    def __init__(self, message: str, line: int, source: str) -> None:
        super().__init__(f"{source}:{line}: {message}")
        self.line = line
        self.source = source


class _Line:
    __slots__ = ("indent", "text", "no")

    def __init__(self, indent: int, text: str, no: int) -> None:
        self.indent, self.text, self.no = indent, text, no


def load_file(path: pathlib.Path) -> dict | list:
    return loads(path.read_text(encoding="utf-8"), source=str(path))


def loads(text: str, *, source: str = "<string>") -> dict | list:
    lines = _prepare(text, source)
    if not lines:
        return {}
    value, index = _parse_block(lines, 0, lines[0].indent, source)
    if index != len(lines):
        raise YamlError("unexpected content after document end", lines[index].no, source)
    return value


def _prepare(text: str, source: str) -> list[_Line]:
    raw = text.splitlines()
    joined: list[_Line] = []
    pending: str | None = None
    pending_no = 0
    pending_indent = 0
    depth = 0
    for no, line in enumerate(raw, start=1):
        if line.strip() in ("---", "..."):
            raise YamlError("multi-document streams are not supported", no, source)
        if "\t" in line[: len(line) - len(line.lstrip())]:
            raise YamlError("tab indentation is not supported", no, source)
        stripped = _strip_comment(line)
        if not stripped.strip():
            continue
        for pattern, name in _BANNED:
            if pattern.search(stripped):
                raise YamlError(f"{name}s are not supported", no, source)
        indent = len(stripped) - len(stripped.lstrip())
        body = stripped.strip()
        if pending is None:
            pending, pending_no, pending_indent = body, no, indent
        else:
            pending += " " + body
        depth = pending.count("{") - pending.count("}") + pending.count("[") - pending.count("]")
        if depth > 0:
            continue
        if depth < 0:
            raise YamlError("unbalanced flow brackets", no, source)
        joined.append(_Line(pending_indent, pending, pending_no))
        pending = None
    if pending is not None:
        raise YamlError("unclosed flow collection", pending_no, source)
    return joined


def _strip_comment(line: str) -> str:
    out, quote = [], None
    for index, char in enumerate(line):
        if quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "#" and (index == 0 or line[index - 1] in " \t"):
            break
        out.append(char)
    return "".join(out).rstrip()


def _parse_block(lines: list[_Line], index: int, indent: int, source: str):
    if lines[index].text.startswith("- "):
        return _parse_seq(lines, index, indent, source)
    return _parse_map(lines, index, indent, source)


def _parse_map(lines: list[_Line], index: int, indent: int, source: str):
    result: dict = {}
    while index < len(lines) and lines[index].indent == indent:
        line = lines[index]
        match = _KEY.match(line.text)
        if not match:
            raise YamlError(f"expected 'key: value', got {line.text!r}", line.no, source)
        key = _scalar(match.group(1), line.no, source)
        rest = line.text[match.end(1) + 1 :].strip()
        if rest:
            result[key] = _parse_inline(rest, line.no, source)
            index += 1
            continue
        if index + 1 < len(lines) and lines[index + 1].indent > indent:
            result[key], index = _parse_block(lines, index + 1, lines[index + 1].indent, source)
        else:
            result[key] = None
            index += 1
    return result, index


def _parse_seq(lines: list[_Line], index: int, indent: int, source: str):
    result: list = []
    while index < len(lines) and lines[index].indent == indent and lines[index].text.startswith("- "):
        line = lines[index]
        body = line.text[2:].strip()
        if _KEY.match(body):
            inner = [_Line(indent + 2, body, line.no)]
            probe = index + 1
            while probe < len(lines) and lines[probe].indent > indent:
                inner.append(lines[probe])
                probe += 1
            item, consumed = _parse_map(inner, 0, indent + 2, source)
            if consumed != len(inner):
                raise YamlError("ragged indentation inside sequence item", line.no, source)
            result.append(item)
            index = probe
        else:
            result.append(_parse_inline(body, line.no, source))
            index += 1
    return result, index


def _parse_inline(text: str, no: int, source: str):
    text = text.strip()
    if text.startswith("{"):
        value, rest = _flow_map(text, no, source)
    elif text.startswith("["):
        value, rest = _flow_seq(text, no, source)
    else:
        return _scalar(text, no, source)
    if rest.strip():
        raise YamlError(f"trailing content after flow collection: {rest!r}", no, source)
    return value


def _flow_map(text: str, no: int, source: str):
    result, cursor = {}, 1
    while True:
        cursor = _skip_ws(text, cursor)
        if cursor >= len(text):
            raise YamlError("unclosed flow mapping", no, source)
        if text[cursor] == "}":
            return result, text[cursor + 1 :]
        key_end = text.index(":", cursor)
        key = _scalar(text[cursor:key_end].strip(), no, source)
        value, text_rest = _flow_value(text[key_end + 1 :], no, source)
        result[key] = value
        text, cursor = text_rest, 0
        cursor = _skip_ws(text, cursor)
        if cursor < len(text) and text[cursor] == ",":
            cursor += 1


def _flow_seq(text: str, no: int, source: str):
    result, cursor = [], 1
    while True:
        cursor = _skip_ws(text, cursor)
        if cursor >= len(text):
            raise YamlError("unclosed flow sequence", no, source)
        if text[cursor] == "]":
            return result, text[cursor + 1 :]
        value, text = _flow_value(text[cursor:], no, source)
        result.append(value)
        cursor = _skip_ws(text, 0)
        if cursor < len(text) and text[cursor] == ",":
            cursor += 1


def _flow_value(text: str, no: int, source: str):
    text = text.lstrip()
    if text.startswith("{"):
        return _flow_map(text, no, source)
    if text.startswith("["):
        return _flow_seq(text, no, source)
    end = 0
    quote = None
    while end < len(text):
        char = text[end]
        if quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char in ",}]":
            break
        end += 1
    return _scalar(text[:end].strip(), no, source), text[end:]


def _skip_ws(text: str, cursor: int) -> int:
    while cursor < len(text) and text[cursor] in " \t":
        cursor += 1
    return cursor


def _scalar(token: str, no: int, source: str):
    if not token:
        raise YamlError("empty scalar", no, source)
    if token[0] == token[-1] and token[0] in "\"'" and len(token) >= 2:
        return token[1:-1]
    if token in ("null", "~"):
        return None
    if token in ("true", "True"):
        return True
    if token in ("false", "False"):
        return False
    if _NUM.match(token):
        return int(token)
    if _FLOAT.match(token):
        return float(token)
    return token
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_yamlmini.py -v`
Expected: 15 passed.

- [ ] **Step 5: Commit**

```bash
git add rgraph/yamlmini.py tests/test_yamlmini.py
git commit -m "feat: strict YAML-subset loader with line-numbered refusals"
```

---

### Task 3: The four config files and the config loader

**Files:**
- Create: `graph.yaml`, `providers.yaml`, `assignment.example.yaml`, `rgraph/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `rgraph.yamlmini.load_file`.
- Produces:
  - `rgraph.config.Kit` — frozen dataclass with `root: Path`, `graph: Graph`, `providers: dict[str, Provider]`, `assignment: dict[str, Assignment]`, `gates: dict[str, Gate]` (gates filled in Task 4; until then the field defaults to `{}`).
  - `rgraph.config.Node` — `id, kind, stage, role, title, produces: tuple[str, ...], gate, reviewer`.
  - `rgraph.config.Edge` — `frm, to, kind, carries: tuple[str, ...], budget: int | None`.
  - `rgraph.config.Graph` — `nodes: dict[str, Node]`, `edges: tuple[Edge, ...]`, helpers `units() -> list[Node]`, `node(id) -> Node`, `out_edges(id) -> list[Edge]`, `in_edges(id) -> list[Edge]`.
  - `rgraph.config.Provider` — `id, kind, invoke, exec_argv: tuple[str, ...], stdin, identity, capabilities: frozenset[str], login_check: tuple[str, ...]`.
  - `rgraph.config.Assignment` — `role, provider, model`, plus `identity(providers) -> str`.
  - `rgraph.config.load_kit(root: Path) -> Kit`, `rgraph.config.ConfigError(Exception)`.
  - Module constants `ROLES`, `ARTIFACTS`, `RETURN_REASONS`, `NODE_KINDS`, `EDGE_KINDS`, `ROLE_REQUIRES`.

- [ ] **Step 1: Write `graph.yaml`**

`carries` is a scalar or a list; on `handoff` edges it names artifacts, on `return` edges it names one typed reason. Stores and terminals exist so no edge dangles.

```yaml
# research-graph reference graph — the academic pipeline of architecture.html v5.1
version: 0.1
run_id_prefix: rg

nodes:
  - {id: corpus,    kind: store, title: "Paper corpus"}
  - {id: kg_store,  kind: store, title: "Knowledge graph (RAG)"}
  - {id: doc_store, kind: store, title: "Document store"}
  - {id: terminal_release, kind: store, title: "Release"}

  - {id: human, kind: human, title: "Human researcher",
     produces: [problem_spec, governance_record, release_manifest]}
  - {id: reviewer, kind: agent, stage: audit, role: roles/reviewer.md,
     title: "Independent review role", produces: []}

  - {id: u01, kind: agent, stage: retrieve, role: roles/retrieval.md,
     title: "Literature retrieval & evidence extraction",
     produces: [search_protocol, corpus_snapshot, kg_snapshot]}
  - {id: u02, kind: agent, stage: retrieve, role: roles/retrieval.md,
     title: "Evidence matrix", produces: [evidence_matrix]}
  - {id: u03, kind: agent, stage: plan, role: roles/planning.md,
     title: "Hypothesis registry", produces: [hypothesis_registry]}
  - {id: u04, kind: agent, stage: plan, role: roles/planning.md,
     title: "Research plan", produces: [design_protocol]}
  - {id: u05, kind: agent, stage: plan, role: roles/planning.md,
     title: "Experiment design & modeling", produces: [frozen_protocol]}
  - {id: u06, kind: agent, stage: execute, role: roles/execution.md,
     title: "Code generation & execution",
     produces: [code_commit, environment_lock, data_manifest]}
  - {id: u07, kind: agent, stage: execute, role: roles/execution.md,
     title: "Experimental results", produces: [run_manifest, raw_results]}
  - {id: u08, kind: agent, stage: verify, role: roles/verification.md,
     title: "Validation & reproducibility", produces: [reproduction_report]}
  - {id: u09, kind: agent, stage: verify, role: roles/verification.md,
     title: "Statistical verification", produces: [statistical_report]}
  - {id: u10, kind: agent, stage: verify, role: roles/verification.md,
     title: "Verification report", produces: [verification_report]}
  - {id: u11, kind: agent, stage: write, role: roles/synthesis.md,
     title: "Result synthesis & visualization", produces: [figure_registry]}
  - {id: u12, kind: agent, stage: write, role: roles/synthesis.md,
     title: "Manuscript", produces: [manuscript, claim_evidence_map]}

  - {id: H1, kind: gate, gate: human}
  - {id: E1, kind: gate, gate: challenge, reviewer: reviewer}
  - {id: H2, kind: gate, gate: human}
  - {id: H3, kind: gate, gate: human}
  - {id: T1, kind: gate, gate: challenge, reviewer: reviewer}
  - {id: H4, kind: gate, gate: human}
  - {id: T2, kind: gate, gate: challenge, reviewer: u08}
  - {id: V1, kind: gate, gate: challenge, reviewer: reviewer}
  - {id: M1, kind: gate, gate: challenge, reviewer: reviewer}
  - {id: FINAL, kind: gate, gate: release}

edges:
  - {from: corpus,    to: u01, kind: read_only}
  - {from: kg_store,  to: u01, kind: read_only}
  - {from: doc_store, to: u01, kind: read_only}

  - {from: human, to: H1,  kind: handoff, carries: [problem_spec, governance_record]}
  - {from: H1,    to: u01, kind: handoff}

  - {from: u01, to: u02, kind: handoff, carries: [search_protocol, corpus_snapshot, kg_snapshot]}
  - {from: u02, to: E1,  kind: handoff, carries: [evidence_matrix]}
  - {from: reviewer, to: E1, kind: read_only}
  - {from: E1,  to: u01, kind: return, carries: evidence_gap, budget: 3}
  - {from: E1,  to: H2,  kind: handoff, carries: [evidence_matrix]}
  - {from: H2,  to: u01, kind: return, carries: evidence_gap, budget: 3}
  - {from: H2,  to: u03, kind: handoff, carries: [evidence_matrix]}

  - {from: u03, to: H3,  kind: handoff, carries: [hypothesis_registry]}
  - {from: H3,  to: u03, kind: return, carries: hypothesis_defect, budget: 3}
  - {from: H3,  to: u04, kind: handoff, carries: [hypothesis_registry]}
  - {from: u04, to: u05, kind: handoff, carries: [design_protocol]}
  - {from: u05, to: T1,  kind: handoff, carries: [frozen_protocol]}
  - {from: reviewer, to: T1, kind: read_only}
  - {from: T1,  to: u05, kind: return, carries: revision, budget: 3}
  - {from: T1,  to: H4,  kind: handoff, carries: [frozen_protocol]}
  - {from: H4,  to: u05, kind: return, carries: revision, budget: 3}
  - {from: H4,  to: u06, kind: handoff, carries: [frozen_protocol, governance_record]}

  - {from: u06, to: u07, kind: handoff, carries: [code_commit, environment_lock, data_manifest]}
  - {from: u07, to: T2,  kind: handoff, carries: [run_manifest, raw_results]}
  - {from: T2,  to: u06, kind: return, carries: code_run_defect, budget: 3}
  - {from: T2,  to: u08, kind: handoff, carries: [run_manifest, raw_results]}
  - {from: T2,  to: u09, kind: handoff, carries: [raw_results]}

  - {from: u08, to: u10, kind: handoff, carries: [reproduction_report]}
  - {from: u09, to: u10, kind: handoff, carries: [statistical_report]}
  - {from: u10, to: V1,  kind: handoff, carries: [verification_report]}
  - {from: reviewer, to: V1, kind: read_only}
  - {from: V1,  to: u06, kind: return, carries: code_run_defect, budget: 3}
  - {from: V1,  to: u04, kind: return, carries: scope_plan_defect, budget: 3}
  - {from: V1,  to: u05, kind: return, carries: assumption_violation, budget: 3}
  - {from: V1,  to: u11, kind: handoff, carries: [verification_report]}

  - {from: u11, to: u12, kind: handoff, carries: [figure_registry]}
  - {from: u12, to: M1,  kind: handoff, carries: [manuscript, claim_evidence_map]}
  - {from: reviewer, to: M1, kind: read_only}
  - {from: M1,  to: u11, kind: return, carries: claim_support_gap, budget: 3}
  - {from: M1,  to: FINAL, kind: handoff,
     carries: [manuscript, claim_evidence_map, verification_report, figure_registry]}
  - {from: FINAL, to: u11, kind: return, carries: claim_support_gap, budget: 2}
  - {from: FINAL, to: u04, kind: return, carries: scope_plan_defect, budget: 2}
  - {from: FINAL, to: terminal_release, kind: handoff, carries: [release_manifest]}
```

- [ ] **Step 2: Write `providers.yaml`**

`exec_argv` and `stdin` extend spec §4.3 — `invoke` alone cannot build the verified
call forms of spec §8. `{model}` is the only substitution.

```yaml
# Provider registry. rgraph knows no provider; it only carries identity strings.
claude-code:
  kind: cli
  invoke: claude
  exec_argv: [claude, "-p", "--model", "{model}"]
  stdin: role_file
  identity: "claude-code/{model}"
  capabilities: [filesystem, shell, read_files]
  login_check: [claude, "--version"]

codex:
  kind: cli
  invoke: codex
  exec_argv: [codex, exec, "-c", "model={model}", "-"]
  stdin: role_file
  identity: "codex/{model}"
  capabilities: [filesystem, shell, read_files]
  login_check: [codex, login, status]

gemini:
  kind: cli
  invoke: gemini
  exec_argv: [gemini, "-m", "{model}", "-p", "-"]
  stdin: role_file
  identity: "gemini/{model}"
  capabilities: [filesystem, shell, read_files]

ollama:
  kind: cli
  invoke: ollama
  exec_argv: [ollama, run, "{model}"]
  stdin: role_file
  identity: "ollama/{model}"
  capabilities: [filesystem, shell, read_files]

grok:
  kind: web
  url: grok.com
  identity: "grok/{model}"
  capabilities: [manual]
```

- [ ] **Step 3: Write `assignment.example.yaml`**

```yaml
# Which provider runs which role. Copy to assignment.yaml and edit,
# or generate one with `rgraph setup`.
retrieval:    {provider: claude-code, model: sonnet-5}
planning:     {provider: claude-code, model: opus-5}
execution:    {provider: claude-code, model: sonnet-5}
verification: {provider: codex,       model: gpt-5.6}
synthesis:    {provider: claude-code, model: fable-5}
reviewer:     {provider: grok,        model: grok-5}
```

- [ ] **Step 4: Write the failing tests**

```python
# tests/test_config.py
import pathlib

import pytest

from rgraph.config import ARTIFACTS, ConfigError, ROLES, load_kit

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_reference_graph_loads():
    kit = load_kit(ROOT)
    assert len(kit.graph.units()) == 12
    assert kit.graph.node("u05").title == "Experiment design & modeling"
    assert kit.graph.node("u05").stage == "plan"
    assert kit.graph.node("u07").produces == ("run_manifest", "raw_results")


def test_every_artifact_has_exactly_one_producer():
    kit = load_kit(ROOT)
    producers: dict[str, list[str]] = {}
    for node in kit.graph.nodes.values():
        for artifact in node.produces:
            producers.setdefault(artifact, []).append(node.id)
    assert sorted(producers) == sorted(ARTIFACTS)
    assert all(len(owners) == 1 for owners in producers.values()), producers


def test_scalar_carries_is_normalised_to_a_tuple():
    kit = load_kit(ROOT)
    edge = next(e for e in kit.graph.edges if e.frm == "E1" and e.to == "u01")
    assert edge.kind == "return"
    assert edge.carries == ("evidence_gap",)
    assert edge.budget == 3


def test_providers_and_capabilities():
    kit = load_kit(ROOT)
    assert kit.providers["codex"].exec_argv == ("codex", "exec", "-c", "model={model}", "-")
    assert kit.providers["grok"].kind == "web"
    assert kit.providers["grok"].capabilities == frozenset({"manual"})


def test_assignment_identity_substitutes_the_model():
    kit = load_kit(ROOT, assignment="assignment.example.yaml")
    assert sorted(kit.assignment) == sorted(ROLES)
    assert kit.assignment["verification"].identity(kit.providers) == "codex/gpt-5.6"


def test_unknown_node_kind_is_rejected(tmp_path):
    (tmp_path / "graph.yaml").write_text("nodes:\n  - {id: x, kind: wizard}\nedges: []\n")
    (tmp_path / "providers.yaml").write_text("codex: {kind: cli, invoke: codex}\n")
    with pytest.raises(ConfigError, match="unknown node kind 'wizard'"):
        load_kit(tmp_path)


def test_edge_to_missing_node_is_rejected(tmp_path):
    (tmp_path / "graph.yaml").write_text(
        "nodes:\n  - {id: a, kind: agent}\nedges:\n  - {from: a, to: ghost, kind: handoff}\n"
    )
    (tmp_path / "providers.yaml").write_text("codex: {kind: cli, invoke: codex}\n")
    with pytest.raises(ConfigError, match="edge a -> ghost: unknown node 'ghost'"):
        load_kit(tmp_path)
```

- [ ] **Step 5: Run the tests to verify they fail**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rgraph.config'`

- [ ] **Step 6: Write `rgraph/config.py`**

```python
"""Load and normalise graph.yaml, providers.yaml, assignment.yaml, gates.yaml."""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field

from rgraph.yamlmini import YamlError, load_file

ROLES = (
    "retrieval", "planning", "execution", "verification", "synthesis", "reviewer",
)
ROLE_REQUIRES = {
    "retrieval": frozenset({"filesystem"}),
    "planning": frozenset({"filesystem"}),
    "execution": frozenset({"filesystem", "shell"}),
    "verification": frozenset({"filesystem", "shell"}),
    "synthesis": frozenset({"filesystem"}),
    "reviewer": frozenset({"read_files"}),
}
ARTIFACTS = (
    "problem_spec", "governance_record", "search_protocol", "corpus_snapshot",
    "kg_snapshot", "evidence_matrix", "hypothesis_registry", "design_protocol",
    "frozen_protocol", "code_commit", "environment_lock", "data_manifest",
    "run_manifest", "raw_results", "reproduction_report", "statistical_report",
    "verification_report", "claim_evidence_map", "figure_registry", "manuscript",
    "release_manifest",
)
PAYLOAD_ARTIFACTS = {"manuscript": "manuscript.md", "raw_results": "raw_results.jsonl"}
RETURN_REASONS = (
    "evidence_gap", "hypothesis_defect", "scope_plan_defect", "assumption_violation",
    "code_run_defect", "claim_support_gap", "revision",
)
NODE_KINDS = ("agent", "store", "gate", "human")
EDGE_KINDS = ("handoff", "return", "read_only")
STAGES = ("retrieve", "plan", "execute", "verify", "write", "audit")


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Node:
    id: str
    kind: str
    stage: str | None = None
    role: str | None = None
    title: str = ""
    produces: tuple[str, ...] = ()
    gate: str | None = None
    reviewer: str | None = None

    @property
    def is_unit(self) -> bool:
        return self.kind == "agent" and self.stage != "audit"

    @property
    def role_name(self) -> str | None:
        return pathlib.PurePosixPath(self.role).stem if self.role else None


@dataclass(frozen=True)
class Edge:
    frm: str
    to: str
    kind: str
    carries: tuple[str, ...] = ()
    budget: int | None = None


@dataclass(frozen=True)
class Graph:
    nodes: dict[str, Node]
    edges: tuple[Edge, ...]

    def node(self, node_id: str) -> Node:
        try:
            return self.nodes[node_id]
        except KeyError:
            raise ConfigError(f"unknown node '{node_id}'") from None

    def units(self) -> list[Node]:
        return [n for n in self.nodes.values() if n.is_unit]

    def out_edges(self, node_id: str) -> list[Edge]:
        return [e for e in self.edges if e.frm == node_id]

    def in_edges(self, node_id: str) -> list[Edge]:
        return [e for e in self.edges if e.to == node_id]

    def producer_of(self, artifact: str) -> Node | None:
        for node in self.nodes.values():
            if artifact in node.produces:
                return node
        return None


@dataclass(frozen=True)
class Provider:
    id: str
    kind: str
    invoke: str | None = None
    url: str | None = None
    exec_argv: tuple[str, ...] = ()
    stdin: str | None = None
    identity: str = ""
    capabilities: frozenset[str] = frozenset()
    login_check: tuple[str, ...] = ()


@dataclass(frozen=True)
class Assignment:
    role: str
    provider: str
    model: str

    def identity(self, providers: dict[str, Provider]) -> str:
        try:
            template = providers[self.provider].identity
        except KeyError:
            raise ConfigError(
                f"role '{self.role}' is assigned to unknown provider '{self.provider}'"
            ) from None
        return template.replace("{model}", self.model)


@dataclass(frozen=True)
class Kit:
    root: pathlib.Path
    graph: Graph
    providers: dict[str, Provider]
    assignment: dict[str, Assignment] = field(default_factory=dict)
    gates: dict = field(default_factory=dict)


def _as_tuple(value) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(value)


def _read(root: pathlib.Path, name: str, required: bool = True):
    path = root / name
    if not path.exists():
        if required:
            raise ConfigError(f"missing config file: {path}")
        return None
    try:
        return load_file(path)
    except YamlError as exc:
        raise ConfigError(str(exc)) from None


def _build_graph(raw) -> Graph:
    nodes: dict[str, Node] = {}
    for entry in raw.get("nodes") or []:
        kind = entry.get("kind")
        if kind not in NODE_KINDS:
            raise ConfigError(f"unknown node kind {kind!r} on node {entry.get('id')!r}")
        stage = entry.get("stage")
        if stage is not None and stage not in STAGES:
            raise ConfigError(f"unknown stage {stage!r} on node {entry.get('id')!r}")
        node = Node(
            id=entry["id"], kind=kind, stage=stage, role=entry.get("role"),
            title=entry.get("title", ""), produces=_as_tuple(entry.get("produces")),
            gate=entry.get("gate"), reviewer=entry.get("reviewer"),
        )
        if node.id in nodes:
            raise ConfigError(f"duplicate node id {node.id!r}")
        for artifact in node.produces:
            if artifact not in ARTIFACTS:
                raise ConfigError(f"node {node.id!r} produces unknown artifact {artifact!r}")
        nodes[node.id] = node

    edges: list[Edge] = []
    for entry in raw.get("edges") or []:
        frm, to = entry["from"], entry["to"]
        kind = entry.get("kind")
        if kind not in EDGE_KINDS:
            raise ConfigError(f"edge {frm} -> {to}: unknown edge kind {kind!r}")
        for endpoint in (frm, to):
            if endpoint not in nodes:
                raise ConfigError(f"edge {frm} -> {to}: unknown node {endpoint!r}")
        carries = _as_tuple(entry.get("carries"))
        if kind == "return":
            if len(carries) != 1 or carries[0] not in RETURN_REASONS:
                raise ConfigError(
                    f"edge {frm} -> {to}: a return edge must carry exactly one of {RETURN_REASONS}"
                )
        else:
            for artifact in carries:
                if artifact not in ARTIFACTS:
                    raise ConfigError(f"edge {frm} -> {to}: unknown artifact {artifact!r}")
        edges.append(Edge(frm=frm, to=to, kind=kind, carries=carries, budget=entry.get("budget")))
    return Graph(nodes=nodes, edges=tuple(edges))


def _build_providers(raw) -> dict[str, Provider]:
    providers = {}
    for provider_id, entry in (raw or {}).items():
        kind = entry.get("kind")
        if kind not in ("cli", "web"):
            raise ConfigError(f"provider {provider_id!r}: kind must be 'cli' or 'web'")
        providers[provider_id] = Provider(
            id=provider_id, kind=kind, invoke=entry.get("invoke"), url=entry.get("url"),
            exec_argv=_as_tuple(entry.get("exec_argv")), stdin=entry.get("stdin"),
            identity=entry.get("identity", f"{provider_id}/{{model}}"),
            capabilities=frozenset(_as_tuple(entry.get("capabilities"))),
            login_check=_as_tuple(entry.get("login_check")),
        )
    return providers


def _build_assignment(raw) -> dict[str, Assignment]:
    assignment = {}
    for role, entry in (raw or {}).items():
        if role not in ROLES:
            raise ConfigError(f"unknown role {role!r}; expected one of {ROLES}")
        assignment[role] = Assignment(role=role, provider=entry["provider"], model=str(entry["model"]))
    return assignment


def load_kit(
    root: pathlib.Path | str,
    *,
    assignment: str = "assignment.yaml",
) -> Kit:
    root = pathlib.Path(root)
    graph = _build_graph(_read(root, "graph.yaml"))
    providers = _build_providers(_read(root, "providers.yaml"))
    raw_assignment = _read(root, assignment, required=False)
    gates_raw = _read(root, "gates.yaml", required=False)
    return Kit(
        root=root,
        graph=graph,
        providers=providers,
        assignment=_build_assignment(raw_assignment),
        gates=_build_gates(gates_raw, graph) if gates_raw else {},
    )
```

`_build_gates` lands in Task 4. Until then define it as `def _build_gates(raw, graph): return {}` so the module imports cleanly, and delete that stub in Task 4.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: 7 passed.

- [ ] **Step 8: Commit**

```bash
git add graph.yaml providers.yaml assignment.example.yaml rgraph/config.py tests/test_config.py
git commit -m "feat: reference graph, provider registry and config loader"
```

---

### Task 4: gates.yaml and the independence-level model

Every gate declares which artifacts it reads, what it proves, what it explicitly does
*not* prove, the minimum and preferred separation levels, and the revision budget.
Falling below `preferred` produces CAVEAT (exit 0); falling below `required` produces
FAIL (exit 1).

**Files:**
- Create: `gates.yaml`, `rgraph/separation.py`
- Modify: `rgraph/config.py` (replace the `_build_gates` stub, add the `Gate` dataclass)
- Test: `tests/test_separation.py`, extend `tests/test_config.py`

**Interfaces:**
- Consumes: `rgraph.config.Kit`, `rgraph.config.Assignment`, `rgraph.config.Provider`.
- Produces:
  - `rgraph.config.Gate` — `id, kind, title, owner, producer, inputs: tuple[str, ...], requires: tuple[str, ...], outcomes: tuple[str, ...], max_revisions: int, routes: dict, checks: tuple[str, ...], proves: tuple[str, ...], separation_required: str, separation_preferred: str`.
  - `rgraph.separation.LEVELS = ("context_only", "separate_model", "separate_provider")`
  - `rgraph.separation.rank(level: str) -> int`
  - `rgraph.separation.level_for(producer: Assignment, reviewer: Assignment) -> str`
  - `rgraph.separation.CONTEXT_ONLY_NOTE: str` — the exact two-line note of spec §5.1.
  - `rgraph.separation.evaluate(gate, producer, reviewer) -> SeparationVerdict` with fields `level, status ("PASS"|"CAVEAT"|"FAIL"), note: str | None`.

- [ ] **Step 1: Write `gates.yaml`**

```yaml
# Nine gates plus the FINAL release decision.
# separation.required : below this the gate FAILs.
# separation.preferred: below this the gate PASSes WITH CAVEATS.
H1:
  kind: human
  title: "Scope, constraints & research intent"
  owner: human
  inputs: [problem_spec, governance_record]
  requires: []
  outcomes: [pass, revise, block]
  max_revisions: 3
  routes: {pass: u01, revise: {default: human}, block: "terminal:blocked"}
  checks: [presence, schema, provenance]
  proves: ["Scope and constraints recorded", "Governance applicability recorded"]

E1:
  kind: challenge
  title: "Evidence fidelity"
  owner: reviewer
  producer: u02
  inputs: [search_protocol, corpus_snapshot, kg_snapshot, evidence_matrix]
  requires: [H1]
  outcomes: [pass, revise, block]
  max_revisions: 3
  separation: {required: context_only, preferred: separate_provider}
  routes: {pass: H2, revise: {evidence_gap: u01, default: u01}, block: "terminal:blocked"}
  checks: [presence, schema, provenance, staleness, separation, budget, source_support]
  proves: ["Source identity", "Direct-support locator"]

H2:
  kind: human
  title: "Evidence completeness & adequacy"
  owner: human
  inputs: [search_protocol, corpus_snapshot, evidence_matrix]
  requires: [H1, E1]
  outcomes: [pass, revise, block]
  max_revisions: 3
  routes: {pass: u03, revise: {evidence_gap: u01, default: u01}, block: "terminal:blocked"}
  checks: [presence, schema, provenance, staleness, budget]
  proves: ["Search coverage reviewed", "Unresolved gaps recorded"]

H3:
  kind: human
  title: "Hypothesis relevance & feasibility"
  owner: human
  inputs: [hypothesis_registry]
  requires: [H2]
  outcomes: [pass, revise, block]
  max_revisions: 3
  routes: {pass: u04, revise: {hypothesis_defect: u03, default: u03}, block: "terminal:blocked"}
  checks: [presence, schema, provenance, staleness, budget]
  proves: ["Falsifiability recorded", "Novelty status recorded"]

T1:
  kind: challenge
  title: "Design & reproduction"
  owner: reviewer
  producer: u05
  inputs: [design_protocol, hypothesis_registry, evidence_matrix]
  requires: [H3]
  outcomes: [pass, revise, block]
  max_revisions: 3
  separation: {required: context_only, preferred: separate_model}
  distinct_actor_from: [V1, M1]
  routes: {pass: H4, revise: {default: u05}, block: "terminal:blocked"}
  checks: [presence, schema, provenance, staleness, separation, budget, design_traceability]
  proves: ["Design traces to a registered hypothesis", "Reproducibility fields present"]

H4:
  kind: human
  title: "Frozen protocol, resources & risk"
  owner: human
  inputs: [frozen_protocol, governance_record]
  requires: [T1]
  outcomes: [pass, revise, block]
  max_revisions: 3
  freezes: frozen_protocol
  routes: {pass: u06, revise: {default: u05}, block: "terminal:blocked"}
  checks: [presence, schema, provenance, staleness, budget, freeze_completeness]
  proves: ["Stopping rule recorded", "Replications and seeds fixed before execution"]

T2:
  kind: challenge
  title: "Code, data & run integrity"
  owner: verification
  producer: u07
  inputs: [code_commit, environment_lock, data_manifest, run_manifest, raw_results]
  requires: [H4]
  outcomes: [pass, revise, block]
  max_revisions: 3
  separation: {required: context_only, preferred: separate_model}
  routes: {pass: u08, revise: {code_run_defect: u06, default: u06}, block: "terminal:blocked"}
  checks: [presence, schema, provenance, staleness, separation, budget, run_integrity]
  proves: ["Run count matches the frozen protocol", "Every dataset digest verified"]

V1:
  kind: challenge
  title: "Verification evidence"
  owner: reviewer
  producer: u10
  inputs: [reproduction_report, statistical_report, verification_report, raw_results,
           code_commit, run_manifest, frozen_protocol]
  requires: [T2]
  outcomes: [pass, revise, block]
  max_revisions: 3
  separation: {required: context_only, preferred: separate_provider}
  routes:
    pass: u11
    revise: {code_run_defect: u06, scope_plan_defect: u04, assumption_violation: u05, default: u08}
    block: "terminal:blocked"
  checks: [presence, schema, provenance, staleness, separation, budget, statistical_support]
  proves: ["Estimates recomputed from raw results", "Uncertainty interval present for every estimate"]

M1:
  kind: challenge
  title: "Manuscript claims"
  owner: reviewer
  producer: u12
  inputs: [corpus_snapshot, evidence_matrix, hypothesis_registry, frozen_protocol,
           code_commit, raw_results, verification_report, claim_evidence_map,
           figure_registry, manuscript]
  requires: [V1]
  outcomes: [pass, revise, block]
  max_revisions: 3
  separation: {required: context_only, preferred: separate_provider}
  routes: {pass: FINAL, revise: {claim_support_gap: u11, default: u11}, block: "terminal:blocked"}
  checks: [presence, schema, provenance, staleness, separation, budget, claim_support]
  proves: ["Every manuscript claim maps to a result or a source", "No claim exceeds its evidence scope"]

FINAL:
  kind: release
  title: "Release · revise · narrow · null · stop"
  owner: human
  inputs: [verification_report, claim_evidence_map, figure_registry, manuscript]
  requires: [M1]
  outcomes: [release, revise, narrow, "null-result", stop]
  max_revisions: 2
  produces: release_manifest
  routes:
    release: "terminal:release"
    revise: {claim_support_gap: u11, default: u11}
    narrow: {scope_plan_defect: u04, default: u04}
    "null-result": "terminal:null-result"
    stop: "terminal:stop"
  checks: [presence, schema, provenance, staleness]
  proves: ["Human release decision recorded"]
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_separation.py
import pathlib

import pytest

from rgraph.config import Assignment, load_kit
from rgraph.separation import CONTEXT_ONLY_NOTE, evaluate, level_for, rank

ROOT = pathlib.Path(__file__).resolve().parents[1]

CLAUDE_SONNET = Assignment("execution", "claude-code", "sonnet-5")
CLAUDE_OPUS = Assignment("planning", "claude-code", "opus-5")
CLAUDE_SONNET_REVIEW = Assignment("reviewer", "claude-code", "sonnet-5")
CODEX = Assignment("reviewer", "codex", "gpt-5.6")


@pytest.mark.parametrize(
    "producer, reviewer, expected",
    [
        (CLAUDE_SONNET, CLAUDE_SONNET_REVIEW, "context_only"),
        (CLAUDE_SONNET, CLAUDE_OPUS, "separate_model"),
        (CLAUDE_SONNET, CODEX, "separate_provider"),
    ],
)
def test_level_for(producer, reviewer, expected):
    assert level_for(producer, reviewer) == expected


def test_rank_is_ordered():
    assert rank("context_only") < rank("separate_model") < rank("separate_provider")


def test_context_only_note_is_the_spec_text():
    assert CONTEXT_ONLY_NOTE == (
        "Reviewer uses a separate session, but the same model\n"
        "and provider. Correlated errors may remain."
    )


def test_below_preferred_is_a_caveat_not_a_failure():
    gate = load_kit(ROOT).gates["M1"]
    verdict = evaluate(gate, CLAUDE_SONNET, CLAUDE_SONNET_REVIEW)
    assert verdict.level == "context_only"
    assert verdict.status == "CAVEAT"
    assert verdict.note == CONTEXT_ONLY_NOTE


def test_meeting_preferred_passes_without_a_note():
    gate = load_kit(ROOT).gates["M1"]
    verdict = evaluate(gate, CLAUDE_SONNET, CODEX)
    assert verdict.status == "PASS"
    assert verdict.note is None


def test_human_gates_have_no_separation_requirement():
    gate = load_kit(ROOT).gates["H2"]
    assert gate.separation_required is None
    assert evaluate(gate, None, None).status == "PASS"


def test_gates_yaml_inputs_are_all_known_artifacts():
    kit = load_kit(ROOT)
    assert len(kit.gates) == 10
    for gate in kit.gates.values():
        for artifact in gate.inputs:
            assert kit.graph.producer_of(artifact) is not None, (gate.id, artifact)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m pytest tests/test_separation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rgraph.separation'`

- [ ] **Step 4: Add the `Gate` dataclass and real `_build_gates` to `rgraph/config.py`**

```python
GATE_KINDS = ("human", "challenge", "release")


@dataclass(frozen=True)
class Gate:
    id: str
    kind: str
    title: str
    owner: str
    producer: str | None = None
    inputs: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    outcomes: tuple[str, ...] = ()
    max_revisions: int = 3
    routes: dict = field(default_factory=dict)
    checks: tuple[str, ...] = ()
    proves: tuple[str, ...] = ()
    freezes: str | None = None
    produces: str | None = None
    distinct_actor_from: tuple[str, ...] = ()
    separation_required: str | None = None
    separation_preferred: str | None = None


def _build_gates(raw, graph: Graph) -> dict[str, Gate]:
    gates: dict[str, Gate] = {}
    for gate_id, entry in (raw or {}).items():
        kind = entry.get("kind")
        if kind not in GATE_KINDS:
            raise ConfigError(f"gate {gate_id!r}: unknown kind {kind!r}")
        separation = entry.get("separation") or {}
        inputs = _as_tuple(entry.get("inputs"))
        for artifact in inputs:
            if artifact not in ARTIFACTS:
                raise ConfigError(f"gate {gate_id!r}: unknown input artifact {artifact!r}")
        gates[gate_id] = Gate(
            id=gate_id, kind=kind, title=entry.get("title", ""), owner=entry["owner"],
            producer=entry.get("producer"), inputs=inputs,
            requires=_as_tuple(entry.get("requires")),
            outcomes=_as_tuple(entry.get("outcomes")),
            max_revisions=int(entry.get("max_revisions", 3)),
            routes=entry.get("routes") or {},
            checks=_as_tuple(entry.get("checks")),
            proves=_as_tuple(entry.get("proves")),
            freezes=entry.get("freezes"), produces=entry.get("produces"),
            distinct_actor_from=_as_tuple(entry.get("distinct_actor_from")),
            separation_required=separation.get("required"),
            separation_preferred=separation.get("preferred"),
        )
    for gate in gates.values():
        for required in gate.requires:
            if required not in gates:
                raise ConfigError(f"gate {gate.id!r}: requires unknown gate {required!r}")
        if gate.id not in graph.nodes:
            raise ConfigError(f"gate {gate.id!r} has no node in graph.yaml")
    return gates
```

- [ ] **Step 5: Write `rgraph/separation.py`**

```python
"""Independence levels. The word 'independent' is never printed; a level is."""

from __future__ import annotations

from dataclasses import dataclass

from rgraph.config import Assignment, Gate

LEVELS = ("context_only", "separate_model", "separate_provider")
LABELS = {
    "context_only": "CONTEXT ONLY",
    "separate_model": "SEPARATE MODEL",
    "separate_provider": "SEPARATE PROVIDER",
}
CONTEXT_ONLY_NOTE = (
    "Reviewer uses a separate session, but the same model\n"
    "and provider. Correlated errors may remain."
)


@dataclass(frozen=True)
class SeparationVerdict:
    level: str | None
    status: str
    note: str | None = None


def rank(level: str) -> int:
    return LEVELS.index(level)


def level_for(producer: Assignment, reviewer: Assignment) -> str:
    if producer.provider != reviewer.provider:
        return "separate_provider"
    if producer.model != reviewer.model:
        return "separate_model"
    return "context_only"


def evaluate(
    gate: Gate,
    producer: Assignment | None,
    reviewer: Assignment | None,
) -> SeparationVerdict:
    if gate.separation_required is None:
        return SeparationVerdict(level=None, status="PASS")
    if producer is None or reviewer is None:
        return SeparationVerdict(level=None, status="FAIL", note="No assignment for this gate.")
    level = level_for(producer, reviewer)
    if rank(level) < rank(gate.separation_required):
        return SeparationVerdict(
            level=level, status="FAIL",
            note=f"Gate {gate.id} requires at least {LABELS[gate.separation_required]}.",
        )
    if gate.separation_preferred and rank(level) < rank(gate.separation_preferred):
        note = CONTEXT_ONLY_NOTE if level == "context_only" else (
            f"Reviewer shares a provider with the producer. "
            f"{LABELS[gate.separation_preferred]} would be stronger."
        )
        return SeparationVerdict(level=level, status="CAVEAT", note=note)
    return SeparationVerdict(level=level, status="PASS")
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_separation.py tests/test_config.py -v`
Expected: 16 passed.

- [ ] **Step 7: Commit**

```bash
git add gates.yaml rgraph/separation.py rgraph/config.py tests/test_separation.py
git commit -m "feat: gate contracts and verifiable independence levels"
```

---

### Task 5: Layer 1 — the five static checks, and `rgraph check --static`

Runs without a run directory, on `graph.yaml` + `gates.yaml` alone. This is the layer
that turns `codejunkie99/graph-engineering`'s advice into a compiler.

| Check | Rule | Catches |
|---|---|---|
| `type_match` | on a `handoff` edge whose source node kind is `agent` or `human`, every id in `carries` is in `source.produces` | a stage expecting an output nobody produces |
| `acyclic` | the subgraph of `handoff` edges is a DAG; cycles are legal only on `return` edges | a hidden infinite loop |
| `bounded` | every `return` edge has an integer `budget >= 1` | an unbounded correction spiral |
| `reachable` | for every gate, every id in `inputs` is produced by a node with a `handoff` path to that gate | a gate that can never be passed |
| `dead_node` | every `agent`/`human` node has at least one outgoing edge, and every artifact it produces appears in some `handoff.carries` or some `gate.inputs` | a decorative box (a "fake edge") |

**Files:**
- Create: `rgraph/lint.py`, `rgraph/commands/__init__.py`, `rgraph/commands/check.py`
- Modify: `rgraph/cli.py` (register the `check` subcommand)
- Test: `tests/test_lint.py`, `tests/test_cli_check_static.py`

**Interfaces:**
- Consumes: `rgraph.config.Kit`, `Graph`, `Gate`.
- Produces:
  - `rgraph.lint.Finding` — frozen dataclass `check: str`, `status: str` (`"PASS"`/`"FAIL"`), `subject: str`, `detail: str`, `fix: str`.
  - `rgraph.lint.run_static(kit) -> list[Finding]` — one Finding per *failure*, plus one PASS Finding per clean check.
  - `rgraph.lint.CHECKS: tuple[str, ...]` = `("type_match", "acyclic", "bounded", "reachable", "dead_node")`.
  - `rgraph.commands.check.register(subparsers) -> None`, `rgraph.commands.check.handle(args) -> int`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_lint.py
import pathlib

from rgraph.config import Edge, Graph, Node, load_kit
from rgraph.lint import CHECKS, run_static

ROOT = pathlib.Path(__file__).resolve().parents[1]


def failures(findings):
    return [f for f in findings if f.status == "FAIL"]


def test_reference_graph_is_clean():
    findings = run_static(load_kit(ROOT))
    assert failures(findings) == []
    assert {f.check for f in findings} == set(CHECKS)


def _kit_with(monkeypatch_graph):
    kit = load_kit(ROOT)
    return type(kit)(
        root=kit.root, graph=monkeypatch_graph, providers=kit.providers,
        assignment=kit.assignment, gates=kit.gates,
    )


def test_type_match_catches_an_unproduced_artifact():
    kit = load_kit(ROOT)
    broken = Graph(
        nodes=kit.graph.nodes,
        edges=kit.graph.edges + (Edge("u03", "u04", "handoff", ("manuscript",)),),
    )
    found = failures(run_static(_kit_with(broken)))
    assert any(f.check == "type_match" and "manuscript" in f.detail for f in found)


def test_acyclic_catches_a_handoff_cycle():
    kit = load_kit(ROOT)
    broken = Graph(
        nodes=kit.graph.nodes,
        edges=kit.graph.edges + (Edge("u12", "u11", "handoff", ()),),
    )
    found = failures(run_static(_kit_with(broken)))
    assert any(f.check == "acyclic" for f in found)


def test_bounded_catches_a_budgetless_return():
    kit = load_kit(ROOT)
    edges = tuple(
        Edge(e.frm, e.to, e.kind, e.carries, None) if e.kind == "return" else e
        for e in kit.graph.edges
    )
    found = failures(run_static(_kit_with(Graph(kit.graph.nodes, edges))))
    assert any(f.check == "bounded" for f in found)


def test_dead_node_catches_an_artifact_nobody_reads():
    kit = load_kit(ROOT)
    nodes = dict(kit.graph.nodes)
    nodes["u09"] = Node(
        id="u09", kind="agent", stage="verify", role="roles/verification.md",
        title="Statistical verification", produces=("statistical_report", "figure_registry"),
    )
    edges = tuple(e for e in kit.graph.edges if not (e.frm == "u11" and e.to == "u12"))
    found = failures(run_static(_kit_with(Graph(nodes, edges))))
    assert any(f.check == "dead_node" for f in found)


def test_reachable_catches_a_gate_input_with_no_path():
    kit = load_kit(ROOT)
    edges = tuple(e for e in kit.graph.edges if not (e.frm == "u01" and e.to == "u02"))
    found = failures(run_static(_kit_with(Graph(kit.graph.nodes, edges))))
    assert any(f.check == "reachable" and f.subject.startswith("E1") for f in found)
```

```python
# tests/test_cli_check_static.py
import pathlib

from rgraph.cli import main

ROOT = str(pathlib.Path(__file__).resolve().parents[1])


def test_static_check_on_the_reference_graph_exits_zero(capsys):
    assert main(["--root", ROOT, "--no-banner", "check", "--static"]) == 0
    out = capsys.readouterr().out
    assert "STATIC GRAPH CHECK" in out
    assert "PASS" in out
    assert "[----] Scientific correctness was not determined" in out


def test_static_check_on_a_broken_graph_exits_one(tmp_path, capsys):
    (tmp_path / "graph.yaml").write_text(
        "nodes:\n"
        "  - {id: a, kind: agent, stage: retrieve, produces: [evidence_matrix]}\n"
        "  - {id: b, kind: agent, stage: plan}\n"
        "edges:\n"
        "  - {from: a, to: b, kind: handoff, carries: [manuscript]}\n"
    )
    (tmp_path / "providers.yaml").write_text("codex: {kind: cli, invoke: codex}\n")
    assert main(["--root", str(tmp_path), "--no-banner", "check", "--static"]) == 1
    assert "FAIL" in capsys.readouterr().out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_lint.py tests/test_cli_check_static.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rgraph.lint'`

- [ ] **Step 3: Write `rgraph/lint.py`**

```python
"""Layer 1: static checks over graph.yaml and gates.yaml. No run directory needed."""

from __future__ import annotations

from dataclasses import dataclass

from rgraph.config import Kit

CHECKS = ("type_match", "acyclic", "bounded", "reachable", "dead_node")


@dataclass(frozen=True)
class Finding:
    check: str
    status: str
    subject: str
    detail: str
    fix: str = ""


def run_static(kit: Kit) -> list[Finding]:
    findings: list[Finding] = []
    for name in CHECKS:
        failures = _CHECKS[name](kit)
        findings.extend(failures or [Finding(name, "PASS", "graph.yaml", _CLEAN[name])])
    return findings


_CLEAN = {
    "type_match": "Every handoff carries an artifact its source declares.",
    "acyclic": "Handoff edges form a DAG; cycles occur only on return edges.",
    "bounded": "Every return edge has a revision budget.",
    "reachable": "Every gate input has a handoff path from its producer.",
    "dead_node": "No node produces an artifact nobody reads.",
}


def _type_match(kit: Kit) -> list[Finding]:
    out = []
    for edge in kit.graph.edges:
        if edge.kind != "handoff":
            continue
        source = kit.graph.node(edge.frm)
        if source.kind not in ("agent", "human"):
            continue
        for artifact in edge.carries:
            if artifact not in source.produces:
                out.append(Finding(
                    "type_match", "FAIL", f"{edge.frm} -> {edge.to}",
                    f"edge carries '{artifact}', which '{edge.frm}' does not produce",
                    f"add '{artifact}' to the produces list of '{edge.frm}', or drop it from carries",
                ))
    return out


def _acyclic(kit: Kit) -> list[Finding]:
    adjacency: dict[str, list[str]] = {node: [] for node in kit.graph.nodes}
    for edge in kit.graph.edges:
        if edge.kind == "handoff":
            adjacency[edge.frm].append(edge.to)
    state: dict[str, int] = {}
    out: list[Finding] = []

    def visit(node: str, path: list[str]) -> None:
        state[node] = 1
        for nxt in adjacency[node]:
            if state.get(nxt) == 1:
                cycle = " -> ".join(path[path.index(nxt):] + [nxt]) if nxt in path else f"{node} -> {nxt}"
                out.append(Finding(
                    "acyclic", "FAIL", nxt, f"handoff cycle: {cycle}",
                    "make the closing edge a 'return' edge with a budget",
                ))
            elif state.get(nxt) is None:
                visit(nxt, path + [nxt])
        state[node] = 2

    for node in kit.graph.nodes:
        if state.get(node) is None:
            visit(node, [node])
    return out


def _bounded(kit: Kit) -> list[Finding]:
    return [
        Finding(
            "bounded", "FAIL", f"{edge.frm} -> {edge.to}",
            "return edge has no budget (or a budget below 1)",
            "add 'budget: 3' to the edge",
        )
        for edge in kit.graph.edges
        if edge.kind == "return" and not (isinstance(edge.budget, int) and edge.budget >= 1)
    ]


def _handoff_ancestors(kit: Kit, target: str) -> set[str]:
    incoming: dict[str, list[str]] = {node: [] for node in kit.graph.nodes}
    for edge in kit.graph.edges:
        if edge.kind == "handoff":
            incoming[edge.to].append(edge.frm)
    seen, stack = set(), list(incoming[target])
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        stack.extend(incoming[node])
    return seen


def _reachable(kit: Kit) -> list[Finding]:
    out = []
    for gate in kit.gates.values():
        ancestors = _handoff_ancestors(kit, gate.id)
        for artifact in gate.inputs:
            producer = kit.graph.producer_of(artifact)
            if producer is None:
                out.append(Finding(
                    "reachable", "FAIL", f"{gate.id}/{artifact}",
                    f"no node produces '{artifact}'",
                    f"add '{artifact}' to some node's produces list",
                ))
            elif producer.id not in ancestors:
                out.append(Finding(
                    "reachable", "FAIL", f"{gate.id}/{artifact}",
                    f"'{artifact}' is produced by '{producer.id}', "
                    f"which has no handoff path to gate {gate.id}",
                    f"add a handoff edge chain from '{producer.id}' to '{gate.id}'",
                ))
    return out


def _dead_node(kit: Kit) -> list[Finding]:
    carried: set[str] = set()
    for edge in kit.graph.edges:
        if edge.kind == "handoff":
            carried.update(edge.carries)
    for gate in kit.gates.values():
        carried.update(gate.inputs)
    out = []
    for node in kit.graph.nodes.values():
        if node.kind not in ("agent", "human"):
            continue
        if not kit.graph.out_edges(node.id):
            out.append(Finding(
                "dead_node", "FAIL", node.id, "node has no outgoing edge",
                "connect it with a handoff or read_only edge, or remove it",
            ))
        for artifact in node.produces:
            if artifact not in carried:
                out.append(Finding(
                    "dead_node", "FAIL", f"{node.id}/{artifact}",
                    f"'{artifact}' is produced but never carried on a handoff "
                    f"and never read by a gate",
                    f"carry '{artifact}' on an outgoing handoff, or stop producing it",
                ))
    return out


_CHECKS = {
    "type_match": _type_match,
    "acyclic": _acyclic,
    "bounded": _bounded,
    "reachable": _reachable,
    "dead_node": _dead_node,
}
```

- [ ] **Step 4: Write `rgraph/commands/__init__.py` and `rgraph/commands/check.py`**

`check.py` grows a dynamic branch in Task 12; for now it handles `--static` only and
refuses a bare `rgraph check` with exit 2.

```python
# rgraph/commands/__init__.py
"""Subcommand modules. Each exposes register(subparsers) and handle(args)."""
```

```python
# rgraph/commands/check.py
from __future__ import annotations

import pathlib

from rgraph.config import ConfigError, load_kit
from rgraph.lint import run_static
from rgraph.render import render_static_report

CLAIM_BOUNDARY = "  [----] Scientific correctness was not determined"


def register(subparsers) -> None:
    parser = subparsers.add_parser("check", help="verify a gate, or lint the graph")
    parser.add_argument("gate", nargs="?", help="gate id, e.g. E1")
    parser.add_argument("--static", action="store_true", help="run Layer 1 only")
    parser.add_argument("--online", action="store_true", help="resolve DOIs over the network")
    parser.set_defaults(handler=handle)


def handle(args) -> int:
    try:
        kit = load_kit(pathlib.Path(args.root))
    except ConfigError as exc:
        print(f"error: {exc}")
        return 2
    if args.static or args.gate is None:
        findings = run_static(kit)
        render_static_report(findings)
        return 1 if any(f.status == "FAIL" for f in findings) else 0
    raise NotImplementedError("dynamic gate check lands in Task 12")
```

- [ ] **Step 5: Add a minimal `rgraph/render.py` and wire the subcommand into `rgraph/cli.py`**

`render.py` gains the remaining screens in later tasks. Start it with the static report
and the shared claim-boundary block.

```python
# rgraph/render.py
"""Every screen. Colour reinforces status; the status word always carries it."""

from __future__ import annotations

from rich.console import Console
from rich.text import Text

console = Console(highlight=False, soft_wrap=False)

STATUS_STYLE = {
    "PASS": "bold green", "FAIL": "bold red", "WAIT": "dim",
    "READY": "bold cyan", "STALE": "bold yellow", "BLOCKED": "bold red",
    "CAVEAT": "bold yellow", "----": "dim",
}
CLAIM_BOUNDARY_LINE = "  [----] Scientific correctness was not determined"


def rule(title: str, status: str | None = None, width: int = 49) -> None:
    head = title if status is None else f"{title}{' ' * max(1, width - len(title) - len(status))}{status}"
    console.print(Text(head, style="bold"))
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
        console.print(Text("  [", style="dim") + status_text(worst) + Text("] ", style="dim") + Text(check))
        for row in rows:
            if row.status == "FAIL":
                console.print(f"        {row.subject}")
                console.print(f"        {row.detail}")
                console.print(f"        Fix: {row.fix}")
    console.print()
    console.print("What this check covered")
    console.print("  [PASS] Graph structure")
    render_claim_boundary()
```

In `rgraph/cli.py`, replace the bare `add_subparsers` call with:

```python
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    from rgraph.commands import check as check_cmd

    check_cmd.register(subparsers)
    return parser
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_lint.py tests/test_cli_check_static.py -v`
Expected: 8 passed. Then `rgraph check --static` prints a clean report — this is done-criterion 1.

- [ ] **Step 7: Commit**

```bash
git add rgraph/lint.py rgraph/render.py rgraph/commands/ rgraph/cli.py tests/test_lint.py tests/test_cli_check_static.py
git commit -m "feat: Layer 1 static graph lint behind rgraph check --static"
```

---

### Task 6: Canonical hashing, the provenance envelope and the schema registry

Every artifact file is a JSON document with the same outer shape. `content_hash` covers
`body` only, so re-serialising or touching `produced_at` never changes it — that is what
makes staleness detection trustworthy.

**Files:**
- Create: `rgraph/hashing.py`, `rgraph/schemas.py`, `schemas/_envelope.schema.json`, `schemas/gate_record.schema.json`, `schemas/run_meta.schema.json`
- Test: `tests/test_hashing.py`, `tests/test_schemas.py`

**Interfaces:**
- Consumes: `jsonschema`, `referencing`.
- Produces:
  - `rgraph.hashing.canonical_bytes(obj) -> bytes` — `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)` encoded UTF-8.
  - `rgraph.hashing.content_hash(obj) -> str` — `"sha256:" + hexdigest`.
  - `rgraph.hashing.file_hash(path: pathlib.Path) -> str` — same prefix, chunked read.
  - `rgraph.hashing.HASH_RE: re.Pattern` — `^sha256:[0-9a-f]{64}$`.
  - `rgraph.schemas.registry(root: pathlib.Path) -> SchemaRegistry` with `validate(artifact_id: str, document: dict) -> list[SchemaError]` and `has(artifact_id) -> bool`.
  - `rgraph.schemas.SchemaError` — frozen dataclass `path: str`, `message: str`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_hashing.py
import pathlib

from rgraph.hashing import HASH_RE, canonical_bytes, content_hash, file_hash


def test_key_order_does_not_change_the_hash():
    assert content_hash({"a": 1, "b": 2}) == content_hash({"b": 2, "a": 1})


def test_value_change_does_change_the_hash():
    assert content_hash({"a": 1}) != content_hash({"a": 2})


def test_canonical_bytes_are_compact_and_sorted():
    assert canonical_bytes({"b": 1, "a": [1, 2]}) == b'{"a":[1,2],"b":1}'


def test_non_ascii_survives_unescaped():
    assert "ö".encode() in canonical_bytes({"a": "ö"})


def test_hash_shape():
    assert HASH_RE.match(content_hash({"a": 1}))


def test_file_hash_matches_content(tmp_path: pathlib.Path):
    target = tmp_path / "raw.jsonl"
    target.write_bytes(b'{"run":1}\n')
    first = file_hash(target)
    assert HASH_RE.match(first)
    target.write_bytes(b'{"run":2}\n')
    assert file_hash(target) != first
```

```python
# tests/test_schemas.py
import pathlib

from rgraph.hashing import content_hash
from rgraph.schemas import registry

ROOT = pathlib.Path(__file__).resolve().parents[1]


def envelope(artifact_id: str, body: dict, inputs=()) -> dict:
    return {
        "artifact_id": artifact_id,
        "version": 1,
        "produced_by": {"role": "retrieval", "identity": "codex/gpt-5.6",
                        "provider": "codex", "model": "gpt-5.6"},
        "produced_at": "2026-07-31T09:00:00Z",
        "inputs": list(inputs),
        "content_hash": content_hash(body),
        "body": body,
    }


def test_envelope_accepts_a_well_formed_document():
    reg = registry(ROOT)
    doc = envelope("problem_spec", {
        "question": "Does a learned channel estimator beat LMMSE at low SNR?",
        "scope": {"in_scope": ["OFDM pilot-aided estimation"], "out_of_scope": ["mmWave beamspace"]},
        "constraints": ["single workstation"],
        "success_criteria": ["paired comparison over matched SNR points"],
        "mode": "GUIDED",
    })
    assert reg.validate("problem_spec", doc) == []


def test_missing_provenance_field_is_reported_with_a_path():
    reg = registry(ROOT)
    doc = envelope("problem_spec", {"question": "q", "scope": {"in_scope": [], "out_of_scope": []},
                                    "constraints": [], "success_criteria": [], "mode": "GUIDED"})
    del doc["inputs"]
    errors = reg.validate("problem_spec", doc)
    assert any("inputs" in e.message for e in errors)


def test_wrong_artifact_id_is_rejected():
    reg = registry(ROOT)
    doc = envelope("evidence_matrix", {"question": "q", "scope": {"in_scope": [], "out_of_scope": []},
                                       "constraints": [], "success_criteria": [], "mode": "GUIDED"})
    assert reg.validate("problem_spec", doc) != []


def test_malformed_hash_is_rejected():
    reg = registry(ROOT)
    doc = envelope("problem_spec", {"question": "q", "scope": {"in_scope": [], "out_of_scope": []},
                                    "constraints": [], "success_criteria": [], "mode": "GUIDED"})
    doc["content_hash"] = "md5:abc"
    assert reg.validate("problem_spec", doc) != []


def test_gate_record_schema_round_trips():
    reg = registry(ROOT)
    record = {
        "gate_id": "E1", "outcome": "pass", "decided_at": "2026-07-31T10:00:00Z",
        "decided_by": {"role": "reviewer", "identity": "grok/grok-5"},
        "producer_identity": "codex/gpt-5.6",
        "separation_level": "separate_provider", "separation_caveat": False,
        "inputs": [{"artifact_id": "evidence_matrix", "content_hash": content_hash({"x": 1})}],
        "checks": [{"name": "source_support", "status": "PASS", "detail": "14 of 14 claims"}],
        "reason": None, "findings": [],
        "revision_budget": {"max": 3, "used": 0},
    }
    assert reg.validate("gate_record", record) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_hashing.py tests/test_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rgraph.hashing'`

- [ ] **Step 3: Write `rgraph/hashing.py`**

```python
"""Canonical JSON hashing. The whole staleness story rests on this file."""

from __future__ import annotations

import hashlib
import json
import pathlib
import re

HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_CHUNK = 1 << 20


def canonical_bytes(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def content_hash(obj) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(obj)).hexdigest()


def file_hash(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()
```

- [ ] **Step 4: Write `schemas/_envelope.schema.json`**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://research-graph.dev/schemas/_envelope.schema.json",
  "title": "Artifact envelope",
  "type": "object",
  "additionalProperties": false,
  "required": ["artifact_id", "version", "produced_by", "produced_at", "inputs", "content_hash", "body"],
  "properties": {
    "artifact_id": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
    "version": {"type": "integer", "minimum": 1},
    "produced_by": {"$ref": "#/$defs/actor"},
    "produced_at": {"type": "string", "format": "date-time"},
    "inputs": {"type": "array", "items": {"$ref": "#/$defs/input_ref"}},
    "content_hash": {"$ref": "#/$defs/hash"},
    "body": {"type": "object"}
  },
  "$defs": {
    "hash": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
    "actor": {
      "type": "object",
      "additionalProperties": false,
      "required": ["role", "identity"],
      "properties": {
        "role": {"enum": ["retrieval", "planning", "execution", "verification", "synthesis", "reviewer", "human"]},
        "identity": {"type": "string", "minLength": 1},
        "provider": {"type": "string"},
        "model": {"type": "string"},
        "session": {"type": "string"}
      }
    },
    "input_ref": {
      "type": "object",
      "additionalProperties": false,
      "required": ["artifact_id", "content_hash"],
      "properties": {
        "artifact_id": {"type": "string"},
        "content_hash": {"$ref": "#/$defs/hash"}
      }
    },
    "locator": {
      "type": "object",
      "additionalProperties": false,
      "required": ["kind", "value"],
      "properties": {
        "kind": {"enum": ["page", "section", "table", "figure", "passage"]},
        "value": {"type": "string", "minLength": 1}
      }
    }
  }
}
```

- [ ] **Step 5: Write `schemas/gate_record.schema.json` and `schemas/run_meta.schema.json`**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://research-graph.dev/schemas/gate_record.schema.json",
  "title": "Gate record",
  "type": "object",
  "additionalProperties": false,
  "required": ["gate_id", "outcome", "decided_at", "decided_by", "separation_level",
               "separation_caveat", "inputs", "checks", "revision_budget"],
  "properties": {
    "gate_id": {"type": "string", "pattern": "^[A-Z][A-Z0-9]*$"},
    "outcome": {"enum": ["pass", "revise", "block", "release", "narrow", "null-result", "stop"]},
    "decided_at": {"type": "string", "format": "date-time"},
    "decided_by": {"$ref": "https://research-graph.dev/schemas/_envelope.schema.json#/$defs/actor"},
    "producer_identity": {"type": ["string", "null"]},
    "separation_level": {"enum": ["context_only", "separate_model", "separate_provider", null]},
    "separation_caveat": {"type": "boolean"},
    "inputs": {"type": "array",
               "items": {"$ref": "https://research-graph.dev/schemas/_envelope.schema.json#/$defs/input_ref"}},
    "checks": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["name", "status"],
        "properties": {
          "name": {"type": "string"},
          "status": {"enum": ["PASS", "FAIL", "SKIP"]},
          "detail": {"type": "string"}
        }
      }
    },
    "reason": {"enum": ["evidence_gap", "hypothesis_defect", "scope_plan_defect",
                        "assumption_violation", "code_run_defect", "claim_support_gap",
                        "revision", null]},
    "findings": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["ref", "code", "detail"],
        "properties": {
          "ref": {"type": "string"},
          "code": {"type": "string"},
          "detail": {"type": "string"},
          "fix": {"type": "string"}
        }
      }
    },
    "revision_budget": {
      "type": "object",
      "additionalProperties": false,
      "required": ["max", "used"],
      "properties": {"max": {"type": "integer", "minimum": 0},
                     "used": {"type": "integer", "minimum": 0}}
    }
  }
}
```

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://research-graph.dev/schemas/run_meta.schema.json",
  "title": "Run metadata",
  "type": "object",
  "additionalProperties": false,
  "required": ["run_id", "question", "mode", "protocol", "revisions", "history"],
  "properties": {
    "run_id": {"type": "string", "pattern": "^rg-[0-9]{8}-[0-9]{3}$"},
    "question": {"type": "string", "minLength": 1},
    "mode": {"enum": ["GUIDED", "MANUAL"]},
    "protocol": {"enum": ["OPEN", "FROZEN"]},
    "frozen_at": {"type": ["string", "null"], "format": "date-time"},
    "revisions": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "additionalProperties": false,
        "required": ["max", "used"],
        "properties": {"max": {"type": "integer"}, "used": {"type": "integer"}}
      }
    },
    "history": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["at", "gate", "outcome"],
        "properties": {
          "at": {"type": "string", "format": "date-time"},
          "gate": {"type": "string"},
          "outcome": {"type": "string"},
          "reason": {"type": ["string", "null"]},
          "to": {"type": ["string", "null"]}
        }
      }
    }
  }
}
```

- [ ] **Step 6: Write `rgraph/schemas.py`**

```python
"""Schema registry. Loads schemas/*.schema.json once and validates against them."""

from __future__ import annotations

import functools
import json
import pathlib
from dataclasses import dataclass

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


@dataclass(frozen=True)
class SchemaError:
    path: str
    message: str


class SchemaRegistry:
    def __init__(self, directory: pathlib.Path) -> None:
        self._validators: dict[str, Draft202012Validator] = {}
        resources, documents = [], {}
        for path in sorted(directory.glob("*.schema.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            documents[path.stem.removesuffix(".schema")] = document
            resources.append((document["$id"], Resource.from_contents(document)))
        registry = Registry().with_resources(resources)
        for name, document in documents.items():
            if name.startswith("_"):
                continue
            self._validators[name] = Draft202012Validator(document, registry=registry)

    def has(self, artifact_id: str) -> bool:
        return artifact_id in self._validators

    def validate(self, artifact_id: str, document) -> list[SchemaError]:
        validator = self._validators.get(artifact_id)
        if validator is None:
            return [SchemaError(path="", message=f"no schema for '{artifact_id}'")]
        errors = []
        for error in sorted(validator.iter_errors(document), key=lambda e: list(e.absolute_path)):
            path = "/".join(str(part) for part in error.absolute_path) or "<root>"
            errors.append(SchemaError(path=path, message=error.message))
        return errors


@functools.lru_cache(maxsize=8)
def registry(root: pathlib.Path) -> SchemaRegistry:
    return SchemaRegistry(pathlib.Path(root) / "schemas")
```

Note: `path.stem` on `problem_spec.schema.json` yields `problem_spec.schema`, hence the
`removesuffix`. `_envelope` is loaded into the reference registry but gets no validator
of its own, which is why it is skipped by the leading-underscore test.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python -m pytest tests/test_hashing.py tests/test_schemas.py -v`
Expected: 6 passed in `test_hashing.py`; `test_schemas.py` fails on `problem_spec` until
Task 7 writes that schema. Write a temporary `schemas/problem_spec.schema.json` as part of
Task 7 and re-run — do not stub it here. Run `python -m pytest tests/test_hashing.py -v`
now (6 passed) and leave `test_schemas.py` red until Task 7 closes it.

- [ ] **Step 8: Commit**

```bash
git add rgraph/hashing.py rgraph/schemas.py schemas/ tests/test_hashing.py tests/test_schemas.py
git commit -m "feat: canonical hashing, provenance envelope and schema registry"
```

---

### Task 7: Artifact schemas 1–11 (`problem_spec` … `frozen_protocol`)

Every artifact schema file has the same shape. Only the `body` fragment differs, so this
task and Task 8 give the wrapper once and then the eleven / ten bodies.

**The wrapper.** For an artifact named `X`, `schemas/X.schema.json` is:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://research-graph.dev/schemas/X.schema.json",
  "title": "X",
  "allOf": [{"$ref": "https://research-graph.dev/schemas/_envelope.schema.json"}],
  "properties": {
    "artifact_id": {"const": "X"},
    "body": <BODY FRAGMENT>
  }
}
```

Two conventions hold in every body below: `"type": "object"`,
`"additionalProperties": false`, and an explicit `required` list. `$L` abbreviates
`{"$ref": "https://research-graph.dev/schemas/_envelope.schema.json#/$defs/locator"}` —
expand it literally when writing the file.

**Files:**
- Create: `schemas/{problem_spec,governance_record,search_protocol,corpus_snapshot,kg_snapshot,evidence_matrix,hypothesis_registry,design_protocol,frozen_protocol}.schema.json` (9 files; `environment_lock` and `data_manifest` belong to Task 8)
- Test: extend `tests/test_schemas.py`

**Interfaces:**
- Consumes: `rgraph.schemas.registry`, `schemas/_envelope.schema.json`.
- Produces: nine validators reachable as `registry(ROOT).validate("<artifact_id>", doc)`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_schemas.py
import pytest

BODIES = {
    "problem_spec": {
        "question": "Does a learned channel estimator beat LMMSE at low SNR?",
        "scope": {"in_scope": ["OFDM pilot-aided estimation"], "out_of_scope": ["mmWave"]},
        "constraints": ["one workstation"], "success_criteria": ["paired comparison"],
        "mode": "GUIDED",
    },
    "governance_record": {
        "ethics_applicable": False, "ethics_reference": None,
        "data_governance": ["synthetic channels only"], "legal_notes": [],
        "approvals": [{"name": "H. U. Yildiz", "date": "2026-07-31", "note": "scope approved"}],
    },
    "search_protocol": {
        "databases": ["Crossref", "arXiv"],
        "queries": [{"db": "Crossref", "query": "deep learning channel estimation OFDM",
                     "executed_at": "2026-07-31T08:00:00Z", "hits": 214}],
        "inclusion_criteria": ["reports SNR sweep"], "exclusion_criteria": ["no baseline"],
        "date_range": {"from": "2017-01-01", "to": "2026-07-31"},
    },
    "corpus_snapshot": {
        "count": 1,
        "sources": [{"source_id": "s-01", "doi": "10.1109/LWC.2017.2757490",
                     "title": "Power of Deep Learning for Channel Estimation and Signal Detection in OFDM Systems",
                     "authors": ["H. Ye", "G. Y. Li", "B. Juang"], "year": 2018,
                     "venue": "IEEE Wireless Communications Letters", "url": None,
                     "retracted": False, "retrieved_at": "2026-07-31T08:05:00Z"}],
    },
    "kg_snapshot": {
        "entities": [{"entity_id": "e-01", "type": "method", "label": "LMMSE estimator"}],
        "claims": [{"claim_id": "kc-01", "text": "Deep estimators degrade less at low SNR",
                    "entity_ids": ["e-01"]}],
        "edges": [{"edge_id": "ke-01", "from_claim": "kc-01", "relation": "supports",
                   "source_id": "s-01", "locator": {"kind": "section", "value": "IV-B"}}],
        "contradictions": [],
    },
    "evidence_matrix": {
        "rows": [{"claim_id": "c-01", "source_id": "s-01",
                  "locator": {"kind": "figure", "value": "Fig. 3"},
                  "method": "simulation", "result": "2.1 dB MSE gain at 0 dB SNR",
                  "strength": "moderate", "contradiction_of": []}],
        "gaps": [{"description": "no paired seeds reported", "blocking": False}],
    },
    "hypothesis_registry": {
        "hypotheses": [{"hypothesis_id": "h-01",
                        "statement": "A learned estimator lowers MSE below LMMSE at SNR <= 0 dB",
                        "falsifiable_prediction": "paired MSE difference CI excludes zero",
                        "novelty_status": "replication", "feasibility": "high",
                        "discriminating_evidence": ["c-01"], "decision": "accepted"}],
    },
    "design_protocol": {
        "objectives": ["quantify the low-SNR gap"], "methods": ["Monte Carlo over TDL-C"],
        "experiments": [{"experiment_id": "x-01", "hypothesis_id": "h-01",
                         "factors": ["snr_db", "estimator"], "metrics": ["mse"]}],
        "resources": {"compute": "1 CPU core", "data": "synthetic", "time": "10 minutes"},
        "risks": ["baseline mis-tuning"],
    },
    "frozen_protocol": {
        "frozen_at": "2026-07-31T11:00:00Z", "approved_by": "H. U. Yildiz",
        "hypotheses": ["h-01"],
        "outcomes": [{"metric": "mse", "direction": "lower_is_better", "threshold": None}],
        "exclusions": ["diverged runs"], "analysis_plan": "paired difference per seed",
        "multiplicity_plan": "Holm over 5 SNR points", "stopping_rule": "fixed 20 replications",
        "replications": 20, "seeds": list(range(41, 61)),
        "data_access": "generated locally", "compute_authorisation": "self",
    },
}


@pytest.mark.parametrize("artifact_id", sorted(BODIES))
def test_each_schema_accepts_its_reference_body(artifact_id):
    reg = registry(ROOT)
    assert reg.has(artifact_id)
    assert reg.validate(artifact_id, envelope(artifact_id, BODIES[artifact_id])) == []


def test_kg_edge_without_a_locator_is_rejected():
    body = {k: v for k, v in BODIES["kg_snapshot"].items()}
    body["edges"] = [{"edge_id": "ke-01", "from_claim": "kc-01",
                      "relation": "supports", "source_id": "s-01"}]
    assert registry(ROOT).validate("kg_snapshot", envelope("kg_snapshot", body)) != []


def test_kg_edge_with_an_empty_locator_value_is_rejected():
    body = {k: v for k, v in BODIES["kg_snapshot"].items()}
    body["edges"] = [{"edge_id": "ke-01", "from_claim": "kc-01", "relation": "supports",
                      "source_id": "s-01", "locator": {"kind": "page", "value": ""}}]
    assert registry(ROOT).validate("kg_snapshot", envelope("kg_snapshot", body)) != []


def test_frozen_protocol_needs_at_least_one_seed():
    body = {k: v for k, v in BODIES["frozen_protocol"].items()}
    body["seeds"] = []
    assert registry(ROOT).validate("frozen_protocol", envelope("frozen_protocol", body)) != []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_schemas.py -v`
Expected: FAIL — `no schema for 'problem_spec'` on every parametrised case.

- [ ] **Step 3: Write the nine body fragments**

`problem_spec`:

```json
{"type": "object", "additionalProperties": false,
 "required": ["question", "scope", "constraints", "success_criteria", "mode"],
 "properties": {
   "question": {"type": "string", "minLength": 1},
   "scope": {"type": "object", "additionalProperties": false,
             "required": ["in_scope", "out_of_scope"],
             "properties": {"in_scope": {"type": "array", "items": {"type": "string"}},
                            "out_of_scope": {"type": "array", "items": {"type": "string"}}}},
   "constraints": {"type": "array", "items": {"type": "string"}},
   "success_criteria": {"type": "array", "items": {"type": "string"}},
   "mode": {"enum": ["GUIDED", "MANUAL"]}}}
```

`governance_record`:

```json
{"type": "object", "additionalProperties": false,
 "required": ["ethics_applicable", "data_governance", "legal_notes", "approvals"],
 "properties": {
   "ethics_applicable": {"type": "boolean"},
   "ethics_reference": {"type": ["string", "null"]},
   "data_governance": {"type": "array", "items": {"type": "string"}},
   "legal_notes": {"type": "array", "items": {"type": "string"}},
   "approvals": {"type": "array", "items": {
     "type": "object", "additionalProperties": false,
     "required": ["name", "date"],
     "properties": {"name": {"type": "string"}, "date": {"type": "string", "format": "date"},
                    "note": {"type": "string"}}}}}}
```

`search_protocol`:

```json
{"type": "object", "additionalProperties": false,
 "required": ["databases", "queries", "inclusion_criteria", "exclusion_criteria", "date_range"],
 "properties": {
   "databases": {"type": "array", "items": {"type": "string"}, "minItems": 1},
   "queries": {"type": "array", "minItems": 1, "items": {
     "type": "object", "additionalProperties": false,
     "required": ["db", "query", "executed_at", "hits"],
     "properties": {"db": {"type": "string"}, "query": {"type": "string"},
                    "executed_at": {"type": "string", "format": "date-time"},
                    "hits": {"type": "integer", "minimum": 0}}}},
   "inclusion_criteria": {"type": "array", "items": {"type": "string"}},
   "exclusion_criteria": {"type": "array", "items": {"type": "string"}},
   "date_range": {"type": "object", "additionalProperties": false,
                  "required": ["from", "to"],
                  "properties": {"from": {"type": "string", "format": "date"},
                                 "to": {"type": "string", "format": "date"}}}}}
```

`corpus_snapshot`:

```json
{"type": "object", "additionalProperties": false,
 "required": ["count", "sources"],
 "properties": {
   "count": {"type": "integer", "minimum": 0},
   "sources": {"type": "array", "items": {
     "type": "object", "additionalProperties": false,
     "required": ["source_id", "doi", "title", "authors", "year", "venue", "retracted", "retrieved_at"],
     "properties": {
       "source_id": {"type": "string", "pattern": "^s-[0-9]{2,}$"},
       "doi": {"type": ["string", "null"], "pattern": "^10\\.[0-9]{4,9}/[^\\s]+$"},
       "title": {"type": "string", "minLength": 1},
       "authors": {"type": "array", "items": {"type": "string"}, "minItems": 1},
       "year": {"type": "integer", "minimum": 1900},
       "venue": {"type": "string"},
       "url": {"type": ["string", "null"]},
       "retracted": {"type": "boolean"},
       "retrieved_at": {"type": "string", "format": "date-time"}}}}}}
```

`kg_snapshot`:

```json
{"type": "object", "additionalProperties": false,
 "required": ["entities", "claims", "edges", "contradictions"],
 "properties": {
   "entities": {"type": "array", "items": {
     "type": "object", "additionalProperties": false,
     "required": ["entity_id", "type", "label"],
     "properties": {"entity_id": {"type": "string"},
                    "type": {"enum": ["method", "dataset", "metric", "concept", "author"]},
                    "label": {"type": "string", "minLength": 1}}}},
   "claims": {"type": "array", "items": {
     "type": "object", "additionalProperties": false,
     "required": ["claim_id", "text", "entity_ids"],
     "properties": {"claim_id": {"type": "string"}, "text": {"type": "string", "minLength": 1},
                    "entity_ids": {"type": "array", "items": {"type": "string"}}}}},
   "edges": {"type": "array", "items": {
     "type": "object", "additionalProperties": false,
     "required": ["edge_id", "from_claim", "relation", "source_id", "locator"],
     "properties": {"edge_id": {"type": "string"}, "from_claim": {"type": "string"},
                    "relation": {"enum": ["supports", "refutes", "qualifies", "replicates"]},
                    "source_id": {"type": "string"}, "locator": $L}}},
   "contradictions": {"type": "array", "items": {
     "type": "object", "additionalProperties": false,
     "required": ["claim_a", "claim_b", "note"],
     "properties": {"claim_a": {"type": "string"}, "claim_b": {"type": "string"},
                    "note": {"type": "string"}}}}}}
```

`evidence_matrix`:

```json
{"type": "object", "additionalProperties": false,
 "required": ["rows", "gaps"],
 "properties": {
   "rows": {"type": "array", "minItems": 1, "items": {
     "type": "object", "additionalProperties": false,
     "required": ["claim_id", "source_id", "locator", "method", "result", "strength", "contradiction_of"],
     "properties": {"claim_id": {"type": "string", "pattern": "^c-[0-9]{2,}$"},
                    "source_id": {"type": "string", "pattern": "^s-[0-9]{2,}$"},
                    "locator": $L, "method": {"type": "string"}, "result": {"type": "string"},
                    "strength": {"enum": ["strong", "moderate", "weak"]},
                    "contradiction_of": {"type": "array", "items": {"type": "string"}}}}},
   "gaps": {"type": "array", "items": {
     "type": "object", "additionalProperties": false,
     "required": ["description", "blocking"],
     "properties": {"description": {"type": "string"}, "blocking": {"type": "boolean"}}}}}}
```

`hypothesis_registry`:

```json
{"type": "object", "additionalProperties": false,
 "required": ["hypotheses"],
 "properties": {"hypotheses": {"type": "array", "minItems": 1, "items": {
   "type": "object", "additionalProperties": false,
   "required": ["hypothesis_id", "statement", "falsifiable_prediction", "novelty_status",
                "feasibility", "discriminating_evidence", "decision"],
   "properties": {"hypothesis_id": {"type": "string", "pattern": "^h-[0-9]{2,}$"},
                  "statement": {"type": "string", "minLength": 1},
                  "falsifiable_prediction": {"type": "string", "minLength": 1},
                  "novelty_status": {"enum": ["novel", "replication", "extension"]},
                  "feasibility": {"enum": ["high", "medium", "low"]},
                  "discriminating_evidence": {"type": "array", "items": {"type": "string"}},
                  "decision": {"enum": ["accepted", "deferred", "rejected"]}}}}}}
```

`design_protocol`:

```json
{"type": "object", "additionalProperties": false,
 "required": ["objectives", "methods", "experiments", "resources", "risks"],
 "properties": {
   "objectives": {"type": "array", "items": {"type": "string"}, "minItems": 1},
   "methods": {"type": "array", "items": {"type": "string"}, "minItems": 1},
   "experiments": {"type": "array", "minItems": 1, "items": {
     "type": "object", "additionalProperties": false,
     "required": ["experiment_id", "hypothesis_id", "factors", "metrics"],
     "properties": {"experiment_id": {"type": "string", "pattern": "^x-[0-9]{2,}$"},
                    "hypothesis_id": {"type": "string"},
                    "factors": {"type": "array", "items": {"type": "string"}},
                    "metrics": {"type": "array", "items": {"type": "string"}, "minItems": 1}}}},
   "resources": {"type": "object", "additionalProperties": false,
                 "required": ["compute", "data", "time"],
                 "properties": {"compute": {"type": "string"}, "data": {"type": "string"},
                                "time": {"type": "string"}}},
   "risks": {"type": "array", "items": {"type": "string"}}}}
```

`frozen_protocol`:

```json
{"type": "object", "additionalProperties": false,
 "required": ["frozen_at", "approved_by", "hypotheses", "outcomes", "exclusions",
              "analysis_plan", "multiplicity_plan", "stopping_rule", "replications",
              "seeds", "data_access", "compute_authorisation"],
 "properties": {
   "frozen_at": {"type": "string", "format": "date-time"},
   "approved_by": {"type": "string", "minLength": 1},
   "hypotheses": {"type": "array", "items": {"type": "string"}, "minItems": 1},
   "outcomes": {"type": "array", "minItems": 1, "items": {
     "type": "object", "additionalProperties": false,
     "required": ["metric", "direction", "threshold"],
     "properties": {"metric": {"type": "string"},
                    "direction": {"enum": ["lower_is_better", "higher_is_better"]},
                    "threshold": {"type": ["number", "null"]}}}},
   "exclusions": {"type": "array", "items": {"type": "string"}},
   "analysis_plan": {"type": "string", "minLength": 1},
   "multiplicity_plan": {"type": "string", "minLength": 1},
   "stopping_rule": {"type": "string", "minLength": 1},
   "replications": {"type": "integer", "minimum": 1},
   "seeds": {"type": "array", "items": {"type": "integer"}, "minItems": 1, "uniqueItems": true},
   "data_access": {"type": "string"},
   "compute_authorisation": {"type": "string"}}}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_schemas.py -v`
Expected: all `problem_spec` … `frozen_protocol` cases pass; the earlier
`test_gate_record_schema_round_trips` and envelope tests pass too.

- [ ] **Step 5: Commit**

```bash
git add schemas/ tests/test_schemas.py
git commit -m "feat: artifact schemas for scoping, retrieval and planning"
```

---

### Task 8: Artifact schemas 12–21 (`code_commit` … `release_manifest`)

Same wrapper as Task 7. Two of these are sidecars for payload files: `manuscript`
describes `manuscript.md`, `raw_results` describes `raw_results.jsonl`. Both carry
`payload_path` and `payload_sha256`, which is how the verifier hashes a non-JSON file
without parsing it.

**Files:**
- Create: `schemas/{environment_lock,data_manifest,code_commit,run_manifest,raw_results,reproduction_report,statistical_report,verification_report,claim_evidence_map,figure_registry,manuscript,release_manifest}.schema.json` (12 files)
- Test: extend `tests/test_schemas.py`

**Interfaces:**
- Consumes: `rgraph.schemas.registry`, `schemas/_envelope.schema.json`.
- Produces: twelve more validators; with Task 7 this completes all 21.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_schemas.py
from rgraph.config import ARTIFACTS

BODIES.update({
    "code_commit": {"repo": "https://github.com/huguryildiz/research-graph",
                    "commit": "9f2c1ab", "dirty": False,
                    "entrypoint": "code/estimator_bench.py",
                    "files": [{"path": "code/estimator_bench.py", "sha256": "0" * 64}]},
    "environment_lock": {"python": "3.11.9", "platform": "macOS-15.5-arm64",
                         "packages": [{"name": "numpy", "version": "2.1.0"}],
                         "lock_sha256": "1" * 64},
    "data_manifest": {"datasets": [{"dataset_id": "d-01", "path": "data/tdlc.npz",
                                    "sha256": "2" * 64, "bytes": 40960, "rows": 2000,
                                    "license": None, "generated": True}]},
    "run_manifest": {"replications": 2, "seeds": [41, 42],
                     "runs": [{"run_id": "run_20260731_041", "seed": 41, "config_sha256": "3" * 64,
                               "started_at": "2026-07-31T12:00:00Z",
                               "finished_at": "2026-07-31T12:00:04Z", "status": "ok"},
                              {"run_id": "run_20260731_042", "seed": 42, "config_sha256": "3" * 64,
                               "started_at": "2026-07-31T12:00:04Z",
                               "finished_at": "2026-07-31T12:00:08Z", "status": "ok"}],
                     "failures": 0},
    "raw_results": {"payload_path": "raw_results.jsonl", "payload_sha256": "4" * 64,
                    "records": 2, "run_ids": ["run_20260731_041", "run_20260731_042"],
                    "record_fields": [{"name": "run_id", "type": "string"},
                                      {"name": "mse", "type": "number"}]},
    "reproduction_report": {"reproduced": [{"run_id": "run_20260731_041",
                                            "original_sha256": "5" * 64,
                                            "reproduced_sha256": "5" * 64, "match": True}],
                            "environment_match": True, "reproduction_rate": 1.0, "notes": []},
    "statistical_report": {
        "estimates": [{"result_id": "r-01", "metric": "mse_delta_db", "estimate": 2.1,
                       "ci_lower": 1.4, "ci_upper": 2.8, "ci_level": 0.95, "n": 2,
                       "method": "paired bootstrap",
                       "assumptions_checked": [{"name": "pairing", "passed": True}]}],
        "multiplicity_correction": "Holm", "effect_sizes": [{"result_id": "r-01",
                                                             "name": "cohen_d", "value": 1.2}]},
    "verification_report": {
        "findings": [{"finding_id": "f-01", "severity": "minor", "text": "narrow SNR grid"}],
        "uncertainty": ["seed variance dominates below -5 dB"],
        "failures": {"total": 0, "accounted": 0},
        "limitations": ["synthetic channels only"], "recommendations": ["widen the grid"],
        "denominators": [{"name": "converged runs", "numerator": 2, "denominator": 2}]},
    "claim_evidence_map": {"claims": [{"claim_id": "c-03",
                                       "text": "Method X improved the target metric by 12 percent.",
                                       "location": {"file": "manuscript.md", "section": "Results"},
                                       "supported_by": {"result_ids": ["r-01"], "source_ids": []},
                                       "scope": "within_evidence"}]},
    "figure_registry": {"figures": [{"figure_id": "fig-01", "caption": "MSE versus SNR",
                                     "source_data": {"artifact_id": "statistical_report",
                                                     "selector": "estimates[0]"},
                                     "script": {"path": "code/plot_mse.py", "sha256": "6" * 64},
                                     "result_ids": ["r-01"]}]},
    "manuscript": {"payload_path": "manuscript.md", "payload_sha256": "7" * 64,
                   "title": "Learned channel estimation at low SNR",
                   "sections": [{"id": "sec-results", "heading": "Results", "claim_ids": ["c-03"]}],
                   "word_count": 3200, "references": ["s-01"]},
    "release_manifest": {"outcome": "release", "decided_by": "H. U. Yildiz",
                         "decided_at": "2026-07-31T18:00:00Z",
                         "revision_counts": {"E1": 1}, "scope_changes": [],
                         "separation_levels": {"M1": "separate_provider"},
                         "caveats": ["V1 decided at CONTEXT ONLY"],
                         "not_established": ["Scientific correctness was not determined"]},
})


def test_all_twenty_one_artifacts_have_a_schema():
    reg = registry(ROOT)
    assert len(ARTIFACTS) == 21
    missing = [a for a in ARTIFACTS if not reg.has(a)]
    assert missing == []


def test_run_manifest_rejects_duplicate_seeds():
    body = {**BODIES["run_manifest"], "seeds": [41, 41]}
    assert registry(ROOT).validate("run_manifest", envelope("run_manifest", body)) != []


def test_statistical_report_requires_a_confidence_interval():
    estimate = {k: v for k, v in BODIES["statistical_report"]["estimates"][0].items()
                if k not in ("ci_lower", "ci_upper")}
    body = {**BODIES["statistical_report"], "estimates": [estimate]}
    assert registry(ROOT).validate("statistical_report", envelope("statistical_report", body)) != []


def test_claim_scope_is_a_closed_enum():
    claim = {**BODIES["claim_evidence_map"]["claims"][0], "scope": "obviously_true"}
    body = {"claims": [claim]}
    assert registry(ROOT).validate("claim_evidence_map", envelope("claim_evidence_map", body)) != []


def test_release_manifest_keeps_the_claim_boundary_sentence():
    body = {**BODIES["release_manifest"], "not_established": []}
    assert registry(ROOT).validate("release_manifest", envelope("release_manifest", body)) != []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_schemas.py -v`
Expected: FAIL — `test_all_twenty_one_artifacts_have_a_schema` lists twelve missing.

- [ ] **Step 3: Write the twelve body fragments**

`$SHA` abbreviates `{"type": "string", "pattern": "^[0-9a-f]{64}$"}` — expand literally.

`code_commit`:

```json
{"type": "object", "additionalProperties": false,
 "required": ["repo", "commit", "dirty", "entrypoint", "files"],
 "properties": {"repo": {"type": "string"},
                "commit": {"type": "string", "pattern": "^[0-9a-f]{7,40}$"},
                "dirty": {"type": "boolean"}, "entrypoint": {"type": "string"},
                "files": {"type": "array", "minItems": 1, "items": {
                  "type": "object", "additionalProperties": false,
                  "required": ["path", "sha256"],
                  "properties": {"path": {"type": "string"}, "sha256": $SHA}}}}}
```

`environment_lock`:

```json
{"type": "object", "additionalProperties": false,
 "required": ["python", "platform", "packages", "lock_sha256"],
 "properties": {"python": {"type": "string"}, "platform": {"type": "string"},
                "packages": {"type": "array", "items": {
                  "type": "object", "additionalProperties": false,
                  "required": ["name", "version"],
                  "properties": {"name": {"type": "string"}, "version": {"type": "string"}}}},
                "lock_sha256": $SHA}}
```

`data_manifest`:

```json
{"type": "object", "additionalProperties": false,
 "required": ["datasets"],
 "properties": {"datasets": {"type": "array", "items": {
   "type": "object", "additionalProperties": false,
   "required": ["dataset_id", "path", "sha256", "bytes", "generated"],
   "properties": {"dataset_id": {"type": "string", "pattern": "^d-[0-9]{2,}$"},
                  "path": {"type": "string"}, "sha256": $SHA,
                  "bytes": {"type": "integer", "minimum": 0},
                  "rows": {"type": ["integer", "null"], "minimum": 0},
                  "license": {"type": ["string", "null"]},
                  "generated": {"type": "boolean"}}}}}}
```

`run_manifest`:

```json
{"type": "object", "additionalProperties": false,
 "required": ["replications", "seeds", "runs", "failures"],
 "properties": {"replications": {"type": "integer", "minimum": 1},
                "seeds": {"type": "array", "items": {"type": "integer"},
                          "minItems": 1, "uniqueItems": true},
                "runs": {"type": "array", "minItems": 1, "items": {
                  "type": "object", "additionalProperties": false,
                  "required": ["run_id", "seed", "config_sha256", "started_at", "finished_at", "status"],
                  "properties": {"run_id": {"type": "string"}, "seed": {"type": "integer"},
                                 "config_sha256": $SHA,
                                 "started_at": {"type": "string", "format": "date-time"},
                                 "finished_at": {"type": "string", "format": "date-time"},
                                 "status": {"enum": ["ok", "failed"]}}}},
                "failures": {"type": "integer", "minimum": 0}}}
```

`raw_results` (sidecar):

```json
{"type": "object", "additionalProperties": false,
 "required": ["payload_path", "payload_sha256", "records", "run_ids", "record_fields"],
 "properties": {"payload_path": {"const": "raw_results.jsonl"}, "payload_sha256": $SHA,
                "records": {"type": "integer", "minimum": 1},
                "run_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "record_fields": {"type": "array", "minItems": 1, "items": {
                  "type": "object", "additionalProperties": false,
                  "required": ["name", "type"],
                  "properties": {"name": {"type": "string"},
                                 "type": {"enum": ["string", "number", "integer", "boolean"]}}}}}}
```

`reproduction_report`:

```json
{"type": "object", "additionalProperties": false,
 "required": ["reproduced", "environment_match", "reproduction_rate", "notes"],
 "properties": {"reproduced": {"type": "array", "minItems": 1, "items": {
                  "type": "object", "additionalProperties": false,
                  "required": ["run_id", "original_sha256", "reproduced_sha256", "match"],
                  "properties": {"run_id": {"type": "string"}, "original_sha256": $SHA,
                                 "reproduced_sha256": $SHA, "match": {"type": "boolean"}}}},
                "environment_match": {"type": "boolean"},
                "reproduction_rate": {"type": "number", "minimum": 0, "maximum": 1},
                "notes": {"type": "array", "items": {"type": "string"}}}}
```

`statistical_report`:

```json
{"type": "object", "additionalProperties": false,
 "required": ["estimates", "multiplicity_correction", "effect_sizes"],
 "properties": {"estimates": {"type": "array", "minItems": 1, "items": {
                  "type": "object", "additionalProperties": false,
                  "required": ["result_id", "metric", "estimate", "ci_lower", "ci_upper",
                               "ci_level", "n", "method", "assumptions_checked"],
                  "properties": {"result_id": {"type": "string", "pattern": "^r-[0-9]{2,}$"},
                                 "metric": {"type": "string"}, "estimate": {"type": "number"},
                                 "ci_lower": {"type": "number"}, "ci_upper": {"type": "number"},
                                 "ci_level": {"const": 0.95}, "n": {"type": "integer", "minimum": 1},
                                 "method": {"type": "string"},
                                 "assumptions_checked": {"type": "array", "items": {
                                   "type": "object", "additionalProperties": false,
                                   "required": ["name", "passed"],
                                   "properties": {"name": {"type": "string"},
                                                  "passed": {"type": "boolean"}}}}}}},
                "multiplicity_correction": {"type": ["string", "null"]},
                "effect_sizes": {"type": "array", "items": {
                  "type": "object", "additionalProperties": false,
                  "required": ["result_id", "name", "value"],
                  "properties": {"result_id": {"type": "string"}, "name": {"type": "string"},
                                 "value": {"type": "number"}}}}}}
```

`verification_report`:

```json
{"type": "object", "additionalProperties": false,
 "required": ["findings", "uncertainty", "failures", "limitations", "recommendations", "denominators"],
 "properties": {"findings": {"type": "array", "items": {
                  "type": "object", "additionalProperties": false,
                  "required": ["finding_id", "severity", "text"],
                  "properties": {"finding_id": {"type": "string"},
                                 "severity": {"enum": ["info", "minor", "major"]},
                                 "text": {"type": "string", "minLength": 1}}}},
                "uncertainty": {"type": "array", "items": {"type": "string"}},
                "failures": {"type": "object", "additionalProperties": false,
                             "required": ["total", "accounted"],
                             "properties": {"total": {"type": "integer", "minimum": 0},
                                            "accounted": {"type": "integer", "minimum": 0}}},
                "limitations": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "recommendations": {"type": "array", "items": {"type": "string"}},
                "denominators": {"type": "array", "minItems": 1, "items": {
                  "type": "object", "additionalProperties": false,
                  "required": ["name", "numerator", "denominator"],
                  "properties": {"name": {"type": "string"},
                                 "numerator": {"type": "integer", "minimum": 0},
                                 "denominator": {"type": "integer", "minimum": 1}}}}}}
```

`claim_evidence_map`:

```json
{"type": "object", "additionalProperties": false,
 "required": ["claims"],
 "properties": {"claims": {"type": "array", "minItems": 1, "items": {
   "type": "object", "additionalProperties": false,
   "required": ["claim_id", "text", "location", "supported_by", "scope"],
   "properties": {"claim_id": {"type": "string", "pattern": "^c-[0-9]{2,}$"},
                  "text": {"type": "string", "minLength": 1},
                  "location": {"type": "object", "additionalProperties": false,
                               "required": ["file", "section"],
                               "properties": {"file": {"type": "string"},
                                              "section": {"type": "string"}}},
                  "supported_by": {"type": "object", "additionalProperties": false,
                                   "required": ["result_ids", "source_ids"],
                                   "properties": {"result_ids": {"type": "array",
                                                                 "items": {"type": "string"}},
                                                  "source_ids": {"type": "array",
                                                                 "items": {"type": "string"}}}},
                  "scope": {"enum": ["within_evidence", "extrapolation"]}}}}}}
```

`figure_registry`:

```json
{"type": "object", "additionalProperties": false,
 "required": ["figures"],
 "properties": {"figures": {"type": "array", "items": {
   "type": "object", "additionalProperties": false,
   "required": ["figure_id", "caption", "source_data", "script", "result_ids"],
   "properties": {"figure_id": {"type": "string", "pattern": "^fig-[0-9]{2,}$"},
                  "caption": {"type": "string", "minLength": 1},
                  "source_data": {"type": "object", "additionalProperties": false,
                                  "required": ["artifact_id", "selector"],
                                  "properties": {"artifact_id": {"type": "string"},
                                                 "selector": {"type": "string"}}},
                  "script": {"type": "object", "additionalProperties": false,
                             "required": ["path", "sha256"],
                             "properties": {"path": {"type": "string"}, "sha256": $SHA}},
                  "result_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1}}}}}}
```

`manuscript` (sidecar):

```json
{"type": "object", "additionalProperties": false,
 "required": ["payload_path", "payload_sha256", "title", "sections", "word_count", "references"],
 "properties": {"payload_path": {"const": "manuscript.md"}, "payload_sha256": $SHA,
                "title": {"type": "string", "minLength": 1},
                "sections": {"type": "array", "minItems": 1, "items": {
                  "type": "object", "additionalProperties": false,
                  "required": ["id", "heading", "claim_ids"],
                  "properties": {"id": {"type": "string"}, "heading": {"type": "string"},
                                 "claim_ids": {"type": "array", "items": {"type": "string"}}}}},
                "word_count": {"type": "integer", "minimum": 1},
                "references": {"type": "array", "items": {"type": "string"}}}}
```

`release_manifest`:

```json
{"type": "object", "additionalProperties": false,
 "required": ["outcome", "decided_by", "decided_at", "revision_counts", "scope_changes",
              "separation_levels", "caveats", "not_established"],
 "properties": {"outcome": {"enum": ["release", "revise", "narrow", "null-result", "stop"]},
                "decided_by": {"type": "string", "minLength": 1},
                "decided_at": {"type": "string", "format": "date-time"},
                "revision_counts": {"type": "object",
                                    "additionalProperties": {"type": "integer", "minimum": 0}},
                "scope_changes": {"type": "array", "items": {"type": "string"}},
                "separation_levels": {"type": "object", "additionalProperties": {
                  "enum": ["context_only", "separate_model", "separate_provider"]}},
                "caveats": {"type": "array", "items": {"type": "string"}},
                "not_established": {"type": "array", "minItems": 1,
                                    "contains": {"const": "Scientific correctness was not determined"},
                                    "items": {"type": "string"}}}}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_schemas.py -v`
Expected: all 21 artifacts resolve; every negative case is rejected.

- [ ] **Step 5: Commit**

```bash
git add schemas/ tests/test_schemas.py
git commit -m "feat: artifact schemas for execution, verification and writing"
```

---

### Task 9: The run directory — discovery, presence and schema validation

**Files:** Create `rgraph/run.py`, `template-run/meta.json`, `template-run/README.md`. Test `tests/test_run.py`, `tests/conftest.py`.

**Interfaces:**
- Produces: `rgraph.run.Artifact` (`id, path, document, payload_path, present, errors: list[SchemaError]`), `rgraph.run.Run` (`root, meta, artifacts: dict[str, Artifact]`, methods `get(id)`, `present_ids()`, `gate_record(gate_id)`, `write_gate_record(record)`, `save_meta()`), `rgraph.run.load_run(root, kit) -> Run`, `rgraph.run.RunError`.
- Consumes: `rgraph.schemas.registry`, `rgraph.hashing.file_hash`, `rgraph.config.PAYLOAD_ARTIFACTS`.

Layout, flat under the run root: `meta.json`, `<artifact_id>.json` ×19, `manuscript.md` + `manuscript.meta.json`, `raw_results.jsonl` + `raw_results.meta.json`, `gates/<GATE>.json`, `logs/`, `code/`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/conftest.py
import json
import pathlib
import shutil

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def example_run(tmp_path):
    """A writable copy of example-run. Never mutate the committed one."""
    target = tmp_path / "run"
    shutil.copytree(ROOT / "example-run", target)
    return target


def write_json(path: pathlib.Path, document) -> None:
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
```

```python
# tests/test_run.py
import pathlib

import pytest

from rgraph.config import load_kit
from rgraph.run import RunError, load_run

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_empty_run_reports_every_artifact_absent(tmp_path):
    (tmp_path / "meta.json").write_text(
        '{"run_id":"rg-20260731-001","question":"q","mode":"GUIDED",'
        '"protocol":"OPEN","revisions":{},"history":[]}'
    )
    run = load_run(tmp_path, load_kit(ROOT))
    assert run.present_ids() == []
    assert run.get("evidence_matrix").present is False


def test_missing_meta_is_a_run_error(tmp_path):
    with pytest.raises(RunError, match="meta.json"):
        load_run(tmp_path, load_kit(ROOT))


def test_example_run_is_fully_present_and_schema_clean(example_run):
    run = load_run(example_run, load_kit(ROOT))
    assert len(run.present_ids()) == 20  # every artifact except release_manifest
    assert [a.id for a in run.artifacts.values() if a.errors] == []


def test_payload_artifacts_expose_their_payload_path(example_run):
    run = load_run(example_run, load_kit(ROOT))
    assert run.get("manuscript").payload_path.name == "manuscript.md"
    assert run.get("raw_results").payload_path.name == "raw_results.jsonl"


def test_schema_violation_is_reported_not_raised(example_run):
    target = example_run / "evidence_matrix.json"
    target.write_text('{"artifact_id":"evidence_matrix"}')
    run = load_run(example_run, load_kit(ROOT))
    assert run.get("evidence_matrix").errors != []
```

- [ ] **Step 2: Run the tests** — `python -m pytest tests/test_run.py -v` → FAIL, no `rgraph.run`.

- [ ] **Step 3: Write `rgraph/run.py`**

```python
"""The run directory: what exists, what validates, what the gates recorded."""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field

from rgraph.config import ARTIFACTS, PAYLOAD_ARTIFACTS, Kit
from rgraph.schemas import SchemaError, registry


class RunError(Exception):
    pass


@dataclass
class Artifact:
    id: str
    path: pathlib.Path
    document: dict | None = None
    payload_path: pathlib.Path | None = None
    errors: list[SchemaError] = field(default_factory=list)

    @property
    def present(self) -> bool:
        return self.document is not None

    @property
    def body(self) -> dict:
        return (self.document or {}).get("body", {})

    @property
    def content_hash(self) -> str | None:
        return (self.document or {}).get("content_hash")

    @property
    def inputs(self) -> list[dict]:
        return (self.document or {}).get("inputs", [])

    @property
    def identity(self) -> str | None:
        return ((self.document or {}).get("produced_by") or {}).get("identity")


@dataclass
class Run:
    root: pathlib.Path
    meta: dict
    artifacts: dict[str, Artifact]

    def get(self, artifact_id: str) -> Artifact:
        return self.artifacts[artifact_id]

    def present_ids(self) -> list[str]:
        return [a.id for a in self.artifacts.values() if a.present]

    def gate_record(self, gate_id: str) -> dict | None:
        path = self.root / "gates" / f"{gate_id}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def write_gate_record(self, record: dict) -> pathlib.Path:
        directory = self.root / "gates"
        directory.mkdir(exist_ok=True)
        path = directory / f"{record['gate_id']}.json"
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        return path

    def save_meta(self) -> None:
        (self.root / "meta.json").write_text(
            json.dumps(self.meta, indent=2) + "\n", encoding="utf-8"
        )


def _artifact_paths(root: pathlib.Path, artifact_id: str):
    payload = PAYLOAD_ARTIFACTS.get(artifact_id)
    if payload is None:
        return root / f"{artifact_id}.json", None
    return root / f"{artifact_id}.meta.json", root / payload


def load_run(root: pathlib.Path | str, kit: Kit) -> Run:
    root = pathlib.Path(root)
    meta_path = root / "meta.json"
    if not meta_path.exists():
        raise RunError(f"not a run directory: {meta_path} is missing")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    reg = registry(kit.root)
    meta_errors = reg.validate("run_meta", meta)
    if meta_errors:
        raise RunError(f"meta.json is invalid: {meta_errors[0].path}: {meta_errors[0].message}")

    artifacts: dict[str, Artifact] = {}
    for artifact_id in ARTIFACTS:
        path, payload = _artifact_paths(root, artifact_id)
        artifact = Artifact(id=artifact_id, path=path, payload_path=payload)
        if path.exists():
            try:
                artifact.document = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                artifact.errors = [SchemaError(path="<file>", message=f"invalid JSON: {exc}")]
            else:
                artifact.errors = reg.validate(artifact_id, artifact.document)
        artifacts[artifact_id] = artifact
    return Run(root=root, meta=meta, artifacts=artifacts)
```

- [ ] **Step 4: Write `template-run/meta.json` and `template-run/README.md`**

```json
{
  "run_id": "rg-20260101-001",
  "question": "Replace this with the research question.",
  "mode": "GUIDED",
  "protocol": "OPEN",
  "frozen_at": null,
  "revisions": {},
  "history": []
}
```

`template-run/README.md`: five lines in English — copy this directory to `run/`, edit
`meta.json`, then `rgraph next`; artifacts land beside `meta.json`; gate records land in
`gates/`; never edit a file after the gate that read it has passed.

- [ ] **Step 5: Run the tests** — the `example_run` fixture stays red until Task 21. Run
`python -m pytest tests/test_run.py -k "not example" -v` → 2 passed.

- [ ] **Step 6: Commit** — `git add rgraph/run.py template-run/ tests/test_run.py tests/conftest.py && git commit -m "feat: run directory loading with schema reporting"`

---

### Task 10: Provenance, staleness and the trace chain

Staleness is the kit's sharpest catch: an artifact records the `content_hash` of each
input it consumed, so if an upstream file changes afterwards, every downstream artifact
and every gate that read it becomes STALE.

**Files:** Create `rgraph/provenance.py`. Test `tests/test_provenance.py`.

**Interfaces:**
- Produces: `rgraph.provenance.hash_mismatch(run, artifact) -> list[tuple[str, str, str]]` (artifact_id, recorded, actual); `stale_artifacts(run) -> dict[str, list[str]]`; `invalidated_gates(run, kit) -> dict[str, list[str]]` (gate → causes); `payload_mismatch(run, artifact) -> str | None`; `trace(run, kit, claim_id) -> TraceChain`; `TraceChain` with `claim, links: list[TraceLink], complete: bool, missing: list[str]`; `TraceLink` (`label, detail, status`).
- Consumes: `rgraph.run.Run`, `rgraph.hashing.file_hash`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_provenance.py
import json
import pathlib

from rgraph.config import load_kit
from rgraph.provenance import invalidated_gates, payload_mismatch, stale_artifacts, trace
from rgraph.run import load_run

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_untouched_run_has_no_stale_artifacts(example_run):
    run = load_run(example_run, load_kit(ROOT))
    assert stale_artifacts(run) == {}


def test_editing_data_manifest_after_the_freeze_staleness_cascades(example_run):
    kit = load_kit(ROOT)
    path = example_run / "data_manifest.json"
    document = json.loads(path.read_text())
    document["body"]["datasets"][0]["bytes"] += 1
    document["content_hash"] = __import__("rgraph.hashing", fromlist=["x"]).content_hash(document["body"])
    path.write_text(json.dumps(document, indent=2))
    run = load_run(example_run, kit)
    stale = stale_artifacts(run)
    assert "run_manifest" in stale
    invalidated = invalidated_gates(run, kit)
    assert set(invalidated) >= {"T2", "V1", "M1"}


def test_payload_edit_is_detected(example_run):
    (example_run / "manuscript.md").write_text("# tampered\n")
    run = load_run(example_run, load_kit(ROOT))
    assert payload_mismatch(run, run.get("manuscript")) is not None


def test_trace_walks_manuscript_to_raw_results(example_run):
    kit = load_kit(ROOT)
    chain = trace(load_run(example_run, kit), kit, "c-03")
    labels = [link.label for link in chain.links]
    assert labels[0] == "manuscript.md"
    assert "claim_evidence_map.json" in labels
    assert "statistical_report.json" in labels
    assert "raw_results.jsonl" in labels
    assert chain.complete is True


def test_trace_of_an_unknown_claim_is_incomplete(example_run):
    kit = load_kit(ROOT)
    chain = trace(load_run(example_run, kit), kit, "c-99")
    assert chain.complete is False
    assert "c-99" in " ".join(chain.missing)
```

- [ ] **Step 2: Run the tests** → FAIL, no `rgraph.provenance`.

- [ ] **Step 3: Write `rgraph/provenance.py`**

```python
"""Provenance: recorded input hashes versus what the files say today."""

from __future__ import annotations

from dataclasses import dataclass, field

from rgraph.config import Kit
from rgraph.hashing import file_hash
from rgraph.run import Artifact, Run


@dataclass(frozen=True)
class TraceLink:
    label: str
    detail: str
    status: str = ""


@dataclass
class TraceChain:
    claim: str
    links: list[TraceLink] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.missing


def hash_mismatch(run: Run, artifact: Artifact) -> list[tuple[str, str, str]]:
    out = []
    for reference in artifact.inputs:
        upstream = run.artifacts.get(reference["artifact_id"])
        if upstream is None or not upstream.present:
            out.append((reference["artifact_id"], reference["content_hash"], "absent"))
        elif upstream.content_hash != reference["content_hash"]:
            out.append((reference["artifact_id"], reference["content_hash"], upstream.content_hash))
    return out


def payload_mismatch(run: Run, artifact: Artifact) -> str | None:
    if artifact.payload_path is None or not artifact.present:
        return None
    if not artifact.payload_path.exists():
        return f"{artifact.payload_path.name} is missing"
    recorded = artifact.body.get("payload_sha256")
    actual = file_hash(artifact.payload_path).removeprefix("sha256:")
    return None if recorded == actual else (
        f"{artifact.payload_path.name} digest changed: recorded {recorded[:12]}…, "
        f"actual {actual[:12]}…"
    )


def stale_artifacts(run: Run) -> dict[str, list[str]]:
    stale: dict[str, list[str]] = {}
    for artifact in run.artifacts.values():
        if not artifact.present:
            continue
        causes = [f"{name} changed" for name, _, _ in hash_mismatch(run, artifact)]
        payload = payload_mismatch(run, artifact)
        if payload:
            causes.append(payload)
        if causes:
            stale[artifact.id] = causes
    # one propagation pass per artifact is enough: the graph is a DAG of depth < 21
    for _ in range(len(run.artifacts)):
        for artifact in run.artifacts.values():
            if not artifact.present or artifact.id in stale:
                continue
            upstream = [r["artifact_id"] for r in artifact.inputs if r["artifact_id"] in stale]
            if upstream:
                stale[artifact.id] = [f"{name} is stale" for name in upstream]
    return stale


def invalidated_gates(run: Run, kit: Kit) -> dict[str, list[str]]:
    stale = stale_artifacts(run)
    out: dict[str, list[str]] = {}
    for gate in kit.gates.values():
        record = run.gate_record(gate.id)
        if record is None or record.get("outcome") not in ("pass", "release"):
            continue
        causes = [f"{name} changed after {gate.id} passed" for name in gate.inputs if name in stale]
        for reference in record.get("inputs", []):
            current = run.artifacts.get(reference["artifact_id"])
            if current and current.present and current.content_hash != reference["content_hash"]:
                causes.append(f"{reference['artifact_id']} changed after {gate.id} passed")
        if causes:
            out[gate.id] = sorted(set(causes))
    return out


def trace(run: Run, kit: Kit, claim_id: str) -> TraceChain:
    chain = TraceChain(claim=claim_id)
    cem = run.get("claim_evidence_map")
    claim = next((c for c in cem.body.get("claims", []) if c["claim_id"] == claim_id), None)
    if claim is None:
        chain.missing.append(f"claim {claim_id} is not in claim_evidence_map")
        return chain

    manuscript = run.get("manuscript")
    section = next(
        (s for s in manuscript.body.get("sections", []) if claim_id in s.get("claim_ids", [])),
        None,
    )
    chain.links.append(TraceLink("manuscript.md", section["heading"] if section else "not located"))
    if section is None:
        chain.missing.append(f"{claim_id} appears in no manuscript section")
    chain.links.append(TraceLink("claim_evidence_map.json", f"{claim_id} -> "
                                 + ", ".join(claim["supported_by"]["result_ids"]) or "no result"))

    stats = run.get("statistical_report")
    for result_id in claim["supported_by"]["result_ids"]:
        estimate = next(
            (e for e in stats.body.get("estimates", []) if e["result_id"] == result_id), None
        )
        if estimate is None:
            chain.missing.append(f"{result_id} is not in statistical_report")
            continue
        chain.links.append(TraceLink(
            "statistical_report.json",
            f"estimate {estimate['estimate']} · 95% CI "
            f"[{estimate['ci_lower']}, {estimate['ci_upper']}] · n {estimate['n']}",
        ))

    raw = run.get("raw_results")
    run_ids = raw.body.get("run_ids", [])
    chain.links.append(TraceLink("raw_results.jsonl", f"{len(run_ids)} records"))
    if not run_ids:
        chain.missing.append("raw_results records no run")

    manifest = run.get("run_manifest")
    manifest_status = "HASH VALID" if not hash_mismatch(run, manifest) else "HASH CHANGED"
    chain.links.append(TraceLink("run_manifest.json", "", manifest_status))
    if manifest_status != "HASH VALID":
        chain.missing.append("run_manifest inputs changed")

    frozen = "FROZEN" if run.meta.get("protocol") == "FROZEN" else "OPEN"
    chain.links.append(TraceLink("frozen_protocol.json", "", frozen))
    if frozen != "FROZEN":
        chain.missing.append("protocol is not frozen")

    record = run.gate_record("M1")
    if record is None:
        chain.missing.append("M1 has no gate record")
    else:
        level = (record.get("separation_level") or "unknown").replace("_", "-").upper()
        chain.links.append(TraceLink("gates/M1.json", "", f"{level} {record['outcome'].upper()}"))
    return chain
```

- [ ] **Step 4: Run the tests** — red until Task 21 supplies `example-run/`. Re-run then.

- [ ] **Step 5: Commit** — `git add rgraph/provenance.py tests/test_provenance.py && git commit -m "feat: provenance chain, staleness cascade and claim tracing"`

---

### Task 11: Per-gate content checks

The six checks named in `gates.yaml` beyond the generic ones. Each takes `(run, kit, gate)`
and returns `list[CheckFinding]`.

| Check | Gate | Rule |
|---|---|---|
| `source_support` | E1 | every `kg_snapshot.edges[]` and `evidence_matrix.rows[]` references a `source_id` present in `corpus_snapshot`; that source has a syntactically valid DOI and `retracted == false`; the row carries a non-empty locator. With `--online`, each DOI resolves. |
| `design_traceability` | T1 | every `design_protocol.experiments[].hypothesis_id` exists in `hypothesis_registry` and its `decision == "accepted"` |
| `freeze_completeness` | H4 | `frozen_protocol.replications >= 1`, `len(seeds) == replications`, `stopping_rule` and `multiplicity_plan` non-empty |
| `run_integrity` | T2 | `run_manifest.replications == len(runs)`; seed set equals `frozen_protocol.seeds`; every `data_manifest.datasets[].sha256` matches the file on disk when present; `raw_results.records >= 1` |
| `statistical_support` | V1 | every estimate has `ci_lower < estimate < ci_upper`; `n` equals the count of `status == "ok"` runs; `reproduction_rate == 1.0` or a `verification_report` finding accounts for it |
| `claim_support` | M1 | every `claim_evidence_map.claims[]` has at least one `result_id` or `source_id`; every `result_id` exists in `statistical_report`; every `source_id` exists in `corpus_snapshot`; `scope == "extrapolation"` requires a matching `verification_report` limitation |

**Files:** Create `rgraph/checks.py`. Test `tests/test_checks.py`.

**Interfaces:**
- Produces: `rgraph.checks.CheckFinding` (`ref, code, detail, fix`), `rgraph.checks.CONTENT_CHECKS: dict[str, Callable]`, `rgraph.checks.DOI_RE`, `rgraph.checks.resolve_doi(doi) -> bool`.
- Codes used in output: `SOURCE NOT RESOLVED`, `SOURCE RETRACTED`, `SOURCE MISSING`, `SUPPORT LOCATOR MISSING`, `HYPOTHESIS NOT REGISTERED`, `FREEZE INCOMPLETE`, `SEED SET MISMATCH`, `DIGEST MISMATCH`, `CI MISSING`, `N MISMATCH`, `CLAIM UNSUPPORTED`, `RESULT NOT FOUND`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_checks.py
import json
import pathlib

from rgraph.checks import CONTENT_CHECKS
from rgraph.config import load_kit
from rgraph.run import load_run

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _run(path):
    kit = load_kit(ROOT)
    return load_run(path, kit), kit


def test_clean_example_passes_every_content_check(example_run):
    run, kit = _run(example_run)
    for gate in kit.gates.values():
        for name in gate.checks:
            check = CONTENT_CHECKS.get(name)
            if check:
                assert check(run, kit, gate, online=False) == [], (gate.id, name)


def test_fake_doi_fails_source_support(example_run):
    path = example_run / "corpus_snapshot.json"
    document = json.loads(path.read_text())
    document["body"]["sources"][0]["doi"] = "10.1234/fake.2024"
    path.write_text(json.dumps(document))
    run, kit = _run(example_run)
    findings = CONTENT_CHECKS["source_support"](run, kit, kit.gates["E1"], online=False)
    assert findings == [] or all(f.code != "SOURCE NOT RESOLVED" for f in findings)


def test_null_doi_fails_source_support(example_run):
    path = example_run / "corpus_snapshot.json"
    document = json.loads(path.read_text())
    document["body"]["sources"][0]["doi"] = None
    path.write_text(json.dumps(document))
    run, kit = _run(example_run)
    findings = CONTENT_CHECKS["source_support"](run, kit, kit.gates["E1"], online=False)
    assert any(f.code == "SOURCE NOT RESOLVED" for f in findings)


def test_retracted_source_fails_source_support(example_run):
    path = example_run / "corpus_snapshot.json"
    document = json.loads(path.read_text())
    document["body"]["sources"][0]["retracted"] = True
    path.write_text(json.dumps(document))
    run, kit = _run(example_run)
    findings = CONTENT_CHECKS["source_support"](run, kit, kit.gates["E1"], online=False)
    assert any(f.code == "SOURCE RETRACTED" for f in findings)


def test_seed_set_mismatch_fails_run_integrity(example_run):
    path = example_run / "run_manifest.json"
    document = json.loads(path.read_text())
    document["body"]["seeds"] = document["body"]["seeds"][:-1]
    path.write_text(json.dumps(document))
    run, kit = _run(example_run)
    findings = CONTENT_CHECKS["run_integrity"](run, kit, kit.gates["T2"], online=False)
    assert any(f.code in ("SEED SET MISMATCH", "N MISMATCH") for f in findings)


def test_unsupported_claim_fails_claim_support(example_run):
    path = example_run / "claim_evidence_map.json"
    document = json.loads(path.read_text())
    document["body"]["claims"][0]["supported_by"] = {"result_ids": [], "source_ids": []}
    path.write_text(json.dumps(document))
    run, kit = _run(example_run)
    findings = CONTENT_CHECKS["claim_support"](run, kit, kit.gates["M1"], online=False)
    assert any(f.code == "CLAIM UNSUPPORTED" for f in findings)
```

- [ ] **Step 2: Run the tests** → FAIL, no `rgraph.checks`.

- [ ] **Step 3: Write `rgraph/checks.py`**

```python
"""Per-gate content checks. Each returns findings; an empty list means PASS."""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from rgraph.config import Gate, Kit
from rgraph.hashing import file_hash
from rgraph.run import Run

DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")


@dataclass(frozen=True)
class CheckFinding:
    ref: str
    code: str
    detail: str
    fix: str = ""


def resolve_doi(doi: str, timeout: float = 5.0) -> bool:
    request = urllib.request.Request(f"https://doi.org/{doi}", method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 400
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        return False


def _source_support(run: Run, kit: Kit, gate: Gate, online: bool = False) -> list[CheckFinding]:
    corpus = {s["source_id"]: s for s in run.get("corpus_snapshot").body.get("sources", [])}
    findings: list[CheckFinding] = []
    referenced: set[str] = set()

    rows = [
        (row["claim_id"], row["source_id"], row.get("locator"))
        for row in run.get("evidence_matrix").body.get("rows", [])
    ] + [
        (edge["from_claim"], edge["source_id"], edge.get("locator"))
        for edge in run.get("kg_snapshot").body.get("edges", [])
    ]
    for claim_id, source_id, locator in rows:
        referenced.add(source_id)
        source = corpus.get(source_id)
        if source is None:
            findings.append(CheckFinding(
                claim_id, "SOURCE MISSING", f"source {source_id} is not in corpus_snapshot",
                f"add {source_id} to the corpus snapshot or drop the claim"))
            continue
        if not locator or not locator.get("value"):
            findings.append(CheckFinding(
                claim_id, "SUPPORT LOCATOR MISSING",
                "Source exists, but no page, section, table, or passage\nsupports this claim.",
                "add a direct locator or narrow the claim"))

    for source_id in sorted(referenced):
        source = corpus.get(source_id)
        if source is None:
            continue
        doi = source.get("doi")
        if not doi or not DOI_RE.match(doi):
            findings.append(CheckFinding(
                source_id, "SOURCE NOT RESOLVED", f"DOI: {doi}",
                f"replace or remove source {source_id}"))
        elif source.get("retracted"):
            findings.append(CheckFinding(
                source_id, "SOURCE RETRACTED", f"DOI: {doi}",
                f"remove source {source_id} and every claim that rests on it"))
        elif online and not resolve_doi(doi):
            findings.append(CheckFinding(
                source_id, "SOURCE NOT RESOLVED", f"DOI: {doi}",
                f"replace or remove source {source_id}"))
    return findings


def _design_traceability(run, kit, gate, online=False):
    accepted = {
        h["hypothesis_id"]
        for h in run.get("hypothesis_registry").body.get("hypotheses", [])
        if h["decision"] == "accepted"
    }
    return [
        CheckFinding(experiment["experiment_id"], "HYPOTHESIS NOT REGISTERED",
                     f"{experiment['hypothesis_id']} is not an accepted hypothesis",
                     "register the hypothesis, or point the experiment at an accepted one")
        for experiment in run.get("design_protocol").body.get("experiments", [])
        if experiment["hypothesis_id"] not in accepted
    ]


def _freeze_completeness(run, kit, gate, online=False):
    body = run.get("frozen_protocol").body
    findings = []
    if len(body.get("seeds", [])) != body.get("replications"):
        findings.append(CheckFinding(
            "frozen_protocol", "FREEZE INCOMPLETE",
            f"{len(body.get('seeds', []))} seeds recorded for "
            f"{body.get('replications')} replications",
            "list one seed per replication before freezing"))
    for field_name in ("stopping_rule", "multiplicity_plan", "analysis_plan"):
        if not (body.get(field_name) or "").strip():
            findings.append(CheckFinding(
                "frozen_protocol", "FREEZE INCOMPLETE", f"{field_name} is empty",
                f"record the {field_name.replace('_', ' ')} before freezing"))
    return findings


def _run_integrity(run, kit, gate, online=False):
    manifest = run.get("run_manifest").body
    frozen = run.get("frozen_protocol").body
    findings = []
    if manifest.get("replications") != len(manifest.get("runs", [])):
        findings.append(CheckFinding(
            "run_manifest", "N MISMATCH",
            f"declares {manifest.get('replications')} replications "
            f"but records {len(manifest.get('runs', []))} runs",
            "re-run the missing replications or correct the count"))
    if sorted(manifest.get("seeds", [])) != sorted(frozen.get("seeds", [])):
        findings.append(CheckFinding(
            "run_manifest", "SEED SET MISMATCH",
            "run seeds differ from the seeds fixed in frozen_protocol",
            "run exactly the frozen seeds, or return to H4 and re-freeze"))
    for dataset in run.get("data_manifest").body.get("datasets", []):
        path = run.root / dataset["path"]
        if path.exists() and file_hash(path).removeprefix("sha256:") != dataset["sha256"]:
            findings.append(CheckFinding(
                dataset["dataset_id"], "DIGEST MISMATCH",
                f"{dataset['path']} does not match its recorded digest",
                "restore the dataset or re-record the manifest and re-run"))
    if run.get("raw_results").body.get("records", 0) < 1:
        findings.append(CheckFinding(
            "raw_results", "N MISMATCH", "no records", "re-run the experiment"))
    return findings


def _statistical_support(run, kit, gate, online=False):
    manifest = run.get("run_manifest").body
    ok_runs = sum(1 for r in manifest.get("runs", []) if r["status"] == "ok")
    findings = []
    for estimate in run.get("statistical_report").body.get("estimates", []):
        if not estimate["ci_lower"] < estimate["estimate"] < estimate["ci_upper"]:
            findings.append(CheckFinding(
                estimate["result_id"], "CI MISSING",
                f"estimate {estimate['estimate']} lies outside its own interval "
                f"[{estimate['ci_lower']}, {estimate['ci_upper']}]",
                "recompute the interval from raw results"))
        if estimate["n"] != ok_runs:
            findings.append(CheckFinding(
                estimate["result_id"], "N MISMATCH",
                f"n = {estimate['n']} but {ok_runs} runs completed",
                "recompute from raw_results, or account for the excluded runs"))
    report = run.get("reproduction_report").body
    if report.get("reproduction_rate", 0) < 1.0 and not run.get("verification_report").body.get("findings"):
        findings.append(CheckFinding(
            "reproduction_report", "N MISMATCH",
            f"reproduction rate {report.get('reproduction_rate')} with no finding recorded",
            "record a verification_report finding that accounts for the gap"))
    return findings


def _claim_support(run, kit, gate, online=False):
    results = {e["result_id"] for e in run.get("statistical_report").body.get("estimates", [])}
    sources = {s["source_id"] for s in run.get("corpus_snapshot").body.get("sources", [])}
    limitations = " ".join(run.get("verification_report").body.get("limitations", []))
    findings = []
    for claim in run.get("claim_evidence_map").body.get("claims", []):
        support = claim["supported_by"]
        if not support["result_ids"] and not support["source_ids"]:
            findings.append(CheckFinding(
                claim["claim_id"], "CLAIM UNSUPPORTED",
                "no result and no source is mapped to this claim",
                "map the claim to a result, or remove it"))
        for result_id in support["result_ids"]:
            if result_id not in results:
                findings.append(CheckFinding(
                    claim["claim_id"], "RESULT NOT FOUND",
                    f"{result_id} is not in statistical_report",
                    "point at a computed result, or narrow the claim"))
        for source_id in support["source_ids"]:
            if source_id not in sources:
                findings.append(CheckFinding(
                    claim["claim_id"], "SOURCE MISSING",
                    f"{source_id} is not in corpus_snapshot",
                    "cite a snapshotted source"))
        if claim["scope"] == "extrapolation" and claim["claim_id"] not in limitations:
            findings.append(CheckFinding(
                claim["claim_id"], "CLAIM UNSUPPORTED",
                "claim is marked as an extrapolation but no limitation records it",
                "add the extrapolation to verification_report.limitations, or narrow the claim"))
    return findings


CONTENT_CHECKS = {
    "source_support": _source_support,
    "design_traceability": _design_traceability,
    "freeze_completeness": _freeze_completeness,
    "run_integrity": _run_integrity,
    "statistical_support": _statistical_support,
    "claim_support": _claim_support,
}
```

Note on `test_fake_doi_fails_source_support`: offline, a syntactically valid but
non-existent DOI passes — that is honest, and the test asserts exactly that. Scenario ②
of `rgraph demo` (Task 22) injects a **null** DOI so the catch is offline-detectable, and
`--online` covers the syntactically-valid-but-dead case.

- [ ] **Step 4: Run the tests** — red until Task 21. Re-run then.

- [ ] **Step 5: Commit** — `git add rgraph/checks.py tests/test_checks.py && git commit -m "feat: per-gate content checks"`

---

### Task 12: The gate engine and `rgraph check <GATE>`

**Files:** Create `rgraph/gates.py`. Modify `rgraph/commands/check.py`, `rgraph/render.py`. Test `tests/test_gates.py`, `tests/test_cli_check_gate.py`.

**Interfaces:**
- Produces: `rgraph.gates.GateResult` (`gate_id, status, checks: list[CheckResult], findings: list[CheckFinding], separation: SeparationVerdict, budget: tuple[int, int], reason: str | None, return_to: str | None`); `rgraph.gates.CheckResult` (`name, status, detail`); `rgraph.gates.evaluate_gate(run, kit, gate_id, *, online=False) -> GateResult`; `rgraph.gates.record_from(result, run, kit) -> dict`.
- Generic checks in evaluation order — `presence` (every `gate.inputs` artifact exists), `schema` (no `SchemaError`), `provenance` (no `hash_mismatch`, no `payload_mismatch`), `staleness` (gate id not in `invalidated_gates`), `separation` (`separation.evaluate`), `budget` (`used < max`), then the gate's content check.
- Status resolution: any FAIL → `FAIL`; staleness cause → `STALE`; budget exhausted → `BLOCKED`; separation CAVEAT and nothing else wrong → `CAVEAT`; otherwise `PASS`. Exit code is 0 for `PASS` and `CAVEAT`, 1 otherwise.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gates.py
import json
import pathlib

from rgraph.config import load_kit
from rgraph.gates import evaluate_gate, record_from
from rgraph.run import load_run

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _eval(path, gate_id, **kwargs):
    kit = load_kit(ROOT, assignment="assignment.example.yaml")
    return evaluate_gate(load_run(path, kit), kit, gate_id, **kwargs), kit


def test_every_gate_passes_on_the_example_run(example_run):
    for gate_id in ("H1", "E1", "H2", "H3", "T1", "H4", "T2", "V1", "M1"):
        result, _ = _eval(example_run, gate_id)
        assert result.status in ("PASS", "CAVEAT"), (gate_id, result.findings)


def test_missing_input_is_a_presence_failure(example_run):
    (example_run / "evidence_matrix.json").unlink()
    result, _ = _eval(example_run, "E1")
    assert result.status == "FAIL"
    assert any(c.name == "presence" and c.status == "FAIL" for c in result.checks)


def test_stale_upstream_marks_the_gate_stale(example_run):
    from rgraph.hashing import content_hash
    path = example_run / "data_manifest.json"
    document = json.loads(path.read_text())
    document["body"]["datasets"][0]["bytes"] += 1
    document["content_hash"] = content_hash(document["body"])
    path.write_text(json.dumps(document))
    result, _ = _eval(example_run, "V1")
    assert result.status == "STALE"


def test_exhausted_budget_blocks(example_run):
    run_meta = json.loads((example_run / "meta.json").read_text())
    run_meta["revisions"]["E1"] = {"max": 3, "used": 3}
    (example_run / "meta.json").write_text(json.dumps(run_meta))
    result, _ = _eval(example_run, "E1")
    assert result.status == "BLOCKED"


def test_gate_record_validates_against_its_schema(example_run):
    from rgraph.schemas import registry
    result, kit = _eval(example_run, "M1")
    run = load_run(example_run, kit)
    assert registry(ROOT).validate("gate_record", record_from(result, run, kit)) == []
```

```python
# tests/test_cli_check_gate.py
import json
import pathlib

from rgraph.cli import main

ROOT = str(pathlib.Path(__file__).resolve().parents[1])


def test_clean_gate_exits_zero_and_prints_the_boundary(example_run, capsys):
    assert main(["--root", ROOT, "--run", str(example_run), "--no-banner", "check", "E1"]) == 0
    out = capsys.readouterr().out
    assert "GATE E1" in out and "PASS" in out
    assert "[----] Scientific correctness was not determined" in out


def test_broken_doi_makes_e1_red_and_exits_one(example_run, capsys):
    path = example_run / "corpus_snapshot.json"
    document = json.loads(path.read_text())
    document["body"]["sources"][0]["doi"] = None
    path.write_text(json.dumps(document))
    assert main(["--root", ROOT, "--run", str(example_run), "--no-banner", "check", "E1"]) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out and "SOURCE NOT RESOLVED" in out
    assert "rgraph revise E1" in out
```

- [ ] **Step 2: Run the tests** → FAIL, no `rgraph.gates`.

- [ ] **Step 3: Write `rgraph/gates.py`**

```python
"""Gate evaluation. Generic checks first, then the gate's content check."""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field

from rgraph import separation as sep
from rgraph.checks import CONTENT_CHECKS, CheckFinding
from rgraph.config import Kit
from rgraph.provenance import hash_mismatch, invalidated_gates, payload_mismatch
from rgraph.run import Run

GENERIC = ("presence", "schema", "provenance", "staleness", "separation", "budget")


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str = ""


@dataclass
class GateResult:
    gate_id: str
    status: str
    checks: list[CheckResult] = field(default_factory=list)
    findings: list[CheckFinding] = field(default_factory=list)
    separation: sep.SeparationVerdict | None = None
    budget: tuple[int, int] = (0, 3)
    reason: str | None = None
    return_to: str | None = None
    proves: tuple[str, ...] = ()


def _assignment_for(kit: Kit, node_id: str | None):
    if node_id is None:
        return None
    if node_id in ("reviewer", "human"):
        return kit.assignment.get("reviewer")
    node = kit.graph.nodes.get(node_id)
    return kit.assignment.get(node.role_name) if node and node.role_name else None


def evaluate_gate(run: Run, kit: Kit, gate_id: str, *, online: bool = False) -> GateResult:
    gate = kit.gates[gate_id]
    result = GateResult(gate_id=gate_id, status="PASS", proves=gate.proves)

    missing = [a for a in gate.inputs if not run.get(a).present]
    result.checks.append(CheckResult(
        "presence", "FAIL" if missing else "PASS",
        f"missing: {', '.join(missing)}" if missing else f"{len(gate.inputs)} inputs present"))

    invalid = [a for a in gate.inputs if run.get(a).errors]
    result.checks.append(CheckResult(
        "schema", "FAIL" if invalid else "PASS",
        f"invalid: {', '.join(invalid)}" if invalid else "all inputs validate"))
    for artifact_id in invalid:
        for error in run.get(artifact_id).errors[:3]:
            result.findings.append(CheckFinding(
                artifact_id, "SCHEMA VIOLATION", f"{error.path}: {error.message}",
                f"correct {artifact_id}.json against schemas/{artifact_id}.schema.json"))

    provenance_problems = []
    for artifact_id in gate.inputs:
        artifact = run.get(artifact_id)
        provenance_problems += [f"{artifact_id}: {name} changed"
                                for name, _, _ in hash_mismatch(run, artifact)]
        payload = payload_mismatch(run, artifact)
        if payload:
            provenance_problems.append(f"{artifact_id}: {payload}")
    result.checks.append(CheckResult(
        "provenance", "FAIL" if provenance_problems else "PASS",
        "; ".join(provenance_problems) or "input hashes match"))

    invalidated = invalidated_gates(run, kit).get(gate_id, [])
    result.checks.append(CheckResult(
        "staleness", "FAIL" if invalidated else "PASS",
        "; ".join(invalidated) or "no upstream artifact changed"))

    if "separation" in gate.checks:
        verdict = sep.evaluate(gate, _assignment_for(kit, gate.producer),
                               _assignment_for(kit, gate.owner))
        result.separation = verdict
        result.checks.append(CheckResult("separation", verdict.status,
                                         sep.LABELS.get(verdict.level or "", "n/a")))

    budget = run.meta.get("revisions", {}).get(gate_id, {"max": gate.max_revisions, "used": 0})
    result.budget = (budget["used"], budget["max"])
    exhausted = budget["used"] >= budget["max"]
    result.checks.append(CheckResult(
        "budget", "FAIL" if exhausted else "PASS",
        f"{budget['max'] - budget['used']} of {budget['max']} attempts remain"))

    for name in gate.checks:
        check = CONTENT_CHECKS.get(name)
        if check is None or missing or invalid:
            continue
        findings = check(run, kit, gate, online=online)
        result.findings.extend(findings)
        result.checks.append(CheckResult(
            name, "FAIL" if findings else "PASS",
            f"{len(findings)} findings" if findings else "clean"))

    failed = [c for c in result.checks if c.status == "FAIL"]
    if exhausted and len(failed) == 1 and failed[0].name == "budget":
        result.status = "BLOCKED"
    elif any(c.name == "staleness" and c.status == "FAIL" for c in result.checks):
        result.status = "STALE"
    elif failed:
        result.status = "FAIL"
    elif result.separation and result.separation.status == "CAVEAT":
        result.status = "CAVEAT"

    if result.status in ("FAIL", "STALE"):
        result.reason = _reason_for(gate, result)
        routes = gate.routes.get("revise") or {}
        result.return_to = routes.get(result.reason, routes.get("default")) if isinstance(routes, dict) else routes
    return result


def _reason_for(gate, result: GateResult) -> str:
    codes = {f.code for f in result.findings}
    table = {
        "E1": "evidence_gap", "H2": "evidence_gap", "H3": "hypothesis_defect",
        "T2": "code_run_defect", "M1": "claim_support_gap",
    }
    if gate.id == "V1":
        if codes & {"DIGEST MISMATCH", "N MISMATCH", "SEED SET MISMATCH"}:
            return "code_run_defect"
        if codes & {"CI MISSING"}:
            return "assumption_violation"
        return "scope_plan_defect"
    return table.get(gate.id, "revision")


def record_from(result: GateResult, run: Run, kit: Kit) -> dict:
    gate = kit.gates[result.gate_id]
    reviewer = _assignment_for(kit, gate.owner)
    producer = _assignment_for(kit, gate.producer)
    outcome = {"PASS": "pass", "CAVEAT": "pass", "STALE": "revise",
               "FAIL": "revise", "BLOCKED": "block"}[result.status]
    return {
        "gate_id": result.gate_id,
        "outcome": outcome,
        "decided_at": _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "decided_by": {"role": "reviewer" if gate.kind == "challenge" else "human",
                       "identity": reviewer.identity(kit.providers) if reviewer else "human/manual"},
        "producer_identity": producer.identity(kit.providers) if producer else None,
        "separation_level": result.separation.level if result.separation else None,
        "separation_caveat": bool(result.separation and result.separation.status == "CAVEAT"),
        "inputs": [{"artifact_id": a, "content_hash": run.get(a).content_hash}
                   for a in gate.inputs if run.get(a).present],
        "checks": [{"name": c.name, "status": c.status, "detail": c.detail} for c in result.checks],
        "reason": result.reason,
        "findings": [{"ref": f.ref, "code": f.code, "detail": f.detail, "fix": f.fix}
                     for f in result.findings],
        "revision_budget": {"max": result.budget[1], "used": result.budget[0]},
    }
```

- [ ] **Step 4: Add `render_gate_result` to `rgraph/render.py`**

Reproduces spec §9.0.4 and §9.0.5 exactly, including the STALE block.

```python
def render_gate_result(result, gate, run=None, invalidated=None) -> None:
    rule(f"GATE {result.gate_id} / {gate.title.upper()}", result.status)
    console.print()
    if result.findings:
        subjects = len({f.ref for f in result.findings})
        console.print(f"{subjects} item(s) need revision.")
        console.print()
        for finding in result.findings:
            console.print(f"  {finding.ref:<6}{finding.code}")
            for line in finding.detail.splitlines():
                console.print(f"        {line}")
            if finding.fix:
                console.print(f"        Fix: {finding.fix}")
            console.print()
    if invalidated:
        console.print(Text("STALE CHAIN DETECTED", style=STATUS_STYLE["STALE"]))
        for cause in invalidated:
            console.print(f"  {cause}")
        console.print(f"  Invalidated: {', '.join(sorted(invalidated))}  "
                      f"(must re-run before they can pass)")
        console.print()
    if result.separation:
        console.print("Review separation")
        console.print(f"  Level : {SEP_LABELS.get(result.separation.level, 'n/a')}")
        if result.separation.note:
            first, *rest = result.separation.note.splitlines()
            console.print(f"  Note  : {first}")
            for line in rest:
                console.print(f"          {line}")
        console.print()
    console.print("What this gate checked")
    for check in result.checks:
        mark = {"PASS": "PASS", "FAIL": "FAIL", "CAVEAT": "CAVEAT", "SKIP": "----"}[check.status]
        console.print(Text("  [", style="dim") + status_text(mark) + Text("] ", style="dim")
                      + Text(check.name.replace("_", " ").capitalize()))
    render_claim_boundary()
    console.print()
    if result.return_to:
        console.print(f"Return to       {result.return_to}")
        console.print(f"Revision budget {result.budget[1] - result.budget[0]} -> "
                      f"{max(0, result.budget[1] - result.budget[0] - 1)}")
        console.print()
        console.print("Run next:")
        console.print(f"  rgraph revise {result.gate_id}")
```

Add `from rgraph.separation import LABELS as SEP_LABELS` at the top of `render.py`.

- [ ] **Step 5: Replace the `NotImplementedError` branch in `rgraph/commands/check.py`**

```python
    run = load_run(pathlib.Path(args.run), kit)
    if args.gate not in kit.gates:
        print(f"error: unknown gate '{args.gate}'; expected one of {', '.join(kit.gates)}")
        return 2
    result = evaluate_gate(run, kit, args.gate, online=args.online)
    render_gate_result(result, kit.gates[args.gate], run,
                       invalidated_gates(run, kit).get(args.gate))
    run.write_gate_record(record_from(result, run, kit))
    return 0 if result.status in ("PASS", "CAVEAT") else 1
```

- [ ] **Step 6: Run the tests** — red until Task 21; re-run then. **Step 7: Commit** —
`git add rgraph/gates.py rgraph/render.py rgraph/commands/check.py tests/test_gates.py tests/test_cli_check_gate.py && git commit -m "feat: gate engine and rgraph check <GATE>"`

---

### Task 13: `rgraph status`

Reproduces spec §9.0.2 exactly: header block, five-stage pipeline row with gate and human
rows aligned beneath it, then the four summary lines. `--verbose` expands the 12 units.

**Files:** Create `rgraph/commands/status.py`, add `render_status` to `rgraph/render.py`. Modify `rgraph/cli.py`. Test `tests/test_cli_status.py`.

**Interfaces:** `rgraph.commands.status.build_view(run, kit) -> StatusView` with fields
`run_id, question, mode, protocol, revision_line, stages: list[StageCell]`,
`gate_row: list[tuple[str, str]]`, `human_row: list[tuple[str, str]]`,
`units_complete: int`, `artifact_counts: tuple[int, int, int]` (valid, stale, pending),
`last_gate: str`, `next_unit: str | None`.

Stage status is the worst of its units: a unit is `PASS` when all its artifacts are
present, valid and not stale; `STALE` when any is stale; `READY` when every input
artifact is valid and the upstream gate passed; otherwise `WAIT`. Gate cells show the
recorded outcome or `----` when no record exists.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_status.py
import pathlib

from rgraph.cli import main

ROOT = str(pathlib.Path(__file__).resolve().parents[1])


def test_status_reproduces_the_spec_layout(example_run, capsys):
    assert main(["--root", ROOT, "--run", str(example_run), "--no-banner", "status"]) == 0
    out = capsys.readouterr().out
    assert "RESEARCH RUN" in out
    assert "RETRIEVE ---> PLAN ---> EXECUTE ---> VERIFY ---> WRITE" in out
    assert "gate:E1" in out and "human:H1" in out
    assert "Progress" in out and "12 units complete" in out
    assert "Artifacts" in out
    assert "contract-gated" not in out  # no banner on status


def test_verbose_status_lists_every_unit(example_run, capsys):
    main(["--root", ROOT, "--run", str(example_run), "--no-banner", "--verbose", "status"])
    out = capsys.readouterr().out
    for unit in ("u01", "u06", "u12"):
        assert unit in out
```

- [ ] **Step 2: Run it** → FAIL. **Step 3:** implement `build_view` + `render_status`,
register the subcommand. **Step 4:** re-run (red until Task 21). **Step 5:** commit
`feat: rgraph status pipeline summary`.

---

### Task 14: `rgraph trace <claim>`

Renders `provenance.trace` as the ASCII tree of spec §9.0.6, closing with the two-line
Assurance block: `Provenance chain is complete.` / `Scientific validity still requires
human review.` An incomplete chain prints the missing links and exits 1.

**Files:** Create `rgraph/commands/trace.py`, add `render_trace` to `rgraph/render.py`. Test `tests/test_cli_trace.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_trace.py
import pathlib

from rgraph.cli import main

ROOT = str(pathlib.Path(__file__).resolve().parents[1])


def test_trace_prints_an_unbroken_chain(example_run, capsys):
    assert main(["--root", ROOT, "--run", str(example_run), "--no-banner", "trace", "c-03"]) == 0
    out = capsys.readouterr().out
    assert "CLAIM c-03" in out
    assert "+-- manuscript.md" in out
    assert "`-- gates/M1.json" in out or "gates/M1.json" in out
    assert "Provenance chain is complete." in out
    assert "Scientific validity still requires human review." in out


def test_trace_of_a_missing_claim_exits_one(example_run, capsys):
    assert main(["--root", ROOT, "--run", str(example_run), "--no-banner", "trace", "c-99"]) == 1
    assert "not in claim_evidence_map" in capsys.readouterr().out
```

- [ ] **Steps 2–5:** implement, register, re-run, commit `feat: rgraph trace`.

---

### Task 15: `rgraph revise <GATE>`

Reads the gate record, increments `meta.json` `revisions[gate].used`, appends a `history`
entry, prints the return target, the typed reason and the remaining budget. Refuses with
exit 1 when the budget is spent (prints `BLOCKED`) or when the last record was a pass.

**Files:** Create `rgraph/commands/revise.py`, add `render_revise` to `rgraph/render.py`. Test `tests/test_cli_revise.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_revise.py
import json
import pathlib

from rgraph.cli import main

ROOT = str(pathlib.Path(__file__).resolve().parents[1])


def test_revise_after_a_failure_spends_one_attempt(example_run, capsys):
    path = example_run / "corpus_snapshot.json"
    document = json.loads(path.read_text())
    document["body"]["sources"][0]["doi"] = None
    path.write_text(json.dumps(document))
    main(["--root", ROOT, "--run", str(example_run), "--no-banner", "check", "E1"])
    assert main(["--root", ROOT, "--run", str(example_run), "--no-banner", "revise", "E1"]) == 0
    out = capsys.readouterr().out
    assert "evidence_gap" in out and "u01" in out
    meta = json.loads((example_run / "meta.json").read_text())
    assert meta["revisions"]["E1"]["used"] == 1
    assert meta["history"][-1]["gate"] == "E1"


def test_revise_on_a_passed_gate_exits_one(example_run, capsys):
    main(["--root", ROOT, "--run", str(example_run), "--no-banner", "check", "E1"])
    assert main(["--root", ROOT, "--run", str(example_run), "--no-banner", "revise", "E1"]) == 1
    assert "passed" in capsys.readouterr().out


def test_revise_beyond_the_budget_is_blocked(example_run, capsys):
    meta_path = example_run / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["revisions"]["E1"] = {"max": 3, "used": 3}
    meta_path.write_text(json.dumps(meta))
    assert main(["--root", ROOT, "--run", str(example_run), "--no-banner", "revise", "E1"]) == 1
    assert "BLOCKED" in capsys.readouterr().out
```

- [ ] **Steps 2–5:** implement, register, re-run, commit `feat: rgraph revise`.

---

### Task 16: `rgraph setup`

Detects each `providers.yaml` CLI with `shutil.which(invoke)`, probes `login_check` when
present (2-second timeout, non-zero means "found, not logged in"), then proposes the
assignment that maximises separation: with two CLIs, producers on one and the reviewer on
the other (`separate_provider`); with one, everything on it and the reviewer in a separate
session (`context_only`, printed with the §5.1 note). Refuses to assign `execution` or
`verification` to a `kind: web` provider and prints why. `--preset "producers=claude-code,reviewer=grok"`
applies a page-generated configuration; `--yes` skips the prompt. Writes `assignment.yaml`.

**Files:** Create `rgraph/commands/setup.py`, add `render_setup` to `rgraph/render.py`. Test `tests/test_cli_setup.py`.

**Interfaces:** `rgraph.commands.setup.detect(kit) -> dict[str, str]` (provider → `FOUND` / `FOUND (not logged in)` / `NOT INSTALLED` / `WEB`); `propose(kit, detected, preset=None) -> dict[str, Assignment]`; `parse_preset(text) -> dict[str, str]`; `capability_conflicts(kit, assignment) -> list[str]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_setup.py
import pathlib

from rgraph.config import load_kit
from rgraph.commands.setup import capability_conflicts, detect, parse_preset, propose

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_two_clis_maximise_separation():
    kit = load_kit(ROOT)
    plan = propose(kit, {"claude-code": "FOUND", "codex": "FOUND", "grok": "WEB"})
    assert plan["reviewer"].provider != plan["execution"].provider


def test_one_cli_keeps_everything_on_it():
    kit = load_kit(ROOT)
    plan = propose(kit, {"codex": "FOUND", "claude-code": "NOT INSTALLED"})
    assert {a.provider for a in plan.values()} == {"codex"}


def test_web_provider_cannot_take_execution():
    kit = load_kit(ROOT)
    plan = propose(kit, {"grok": "WEB", "codex": "FOUND"})
    assert plan["execution"].provider == "codex"
    assert plan["reviewer"].provider == "grok"


def test_capability_conflict_is_explained():
    kit = load_kit(ROOT)
    from rgraph.config import Assignment
    bad = {"execution": Assignment("execution", "grok", "grok-5")}
    messages = capability_conflicts(kit, bad)
    assert any("shell" in m and "grok" in m for m in messages)


def test_preset_parsing():
    assert parse_preset("producers=claude-code,reviewer=grok") == {
        "producers": "claude-code", "reviewer": "grok"}


def test_detect_marks_absent_binaries(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert set(detect(load_kit(ROOT)).values()) <= {"NOT INSTALLED", "WEB"}
```

- [ ] **Steps 2–5:** implement, register (banner prints for `setup`), re-run, commit
`feat: rgraph setup with capability-aware assignment`.

---

### Task 17: `rgraph next` and the single-shot approved runner

The only place the kit executes anything. It selects the first READY unit, prints the
inventory screen of spec §9.0.3 ending in `No command has been executed.`, then offers
`[E] Execute  [D] Dry run  [S] Stop`. `E` runs exactly one subprocess built from the
provider's `exec_argv` with the role file (plus a generated context header) on stdin,
streams to `run/logs/<unit>-<stamp>.log`, and on exit prints `Run next: rgraph check <GATE>`.
Web providers get the manual script instead: open a session, paste the role file, save the
output to the listed paths, run `rgraph check`.

**Files:** Create `rgraph/runner.py`, `rgraph/commands/next_.py`, add `render_next` to `rgraph/render.py`. Test `tests/test_runner.py`, `tests/test_cli_next.py`.

**Interfaces:** `rgraph.runner.Plan` (`unit, role_path, provider, model, argv: list[str], stdin_text, inputs, produces, gate, log_path`); `rgraph.runner.build_plan(run, kit, unit_id) -> Plan`; `rgraph.runner.execute(plan, *, verbose=False) -> int`; `rgraph.commands.next_.select_unit(run, kit) -> Node | None`.

The context header prepended to stdin:

```
# research-graph context
# run directory : <abs path>
# unit          : u06 Code generation & execution
# write these artifacts, each as JSON matching schemas/<id>.schema.json:
#   run/code_commit.json
#   run/environment_lock.json
#   run/data_manifest.json
# every artifact must carry produced_by.identity = "<identity>"
# and inputs[] with the content_hash of every artifact you read.
```

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_runner.py
import pathlib

from rgraph.config import load_kit
from rgraph.run import load_run
from rgraph.runner import build_plan, execute

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_plan_builds_the_verified_codex_call(example_run):
    kit = load_kit(ROOT, assignment="assignment.example.yaml")
    plan = build_plan(load_run(example_run, kit), kit, "u08")
    assert plan.argv == ["codex", "exec", "-c", "model=gpt-5.6", "-"]
    assert plan.stdin_text.startswith("# research-graph context")
    assert "run/reproduction_report.json" in plan.stdin_text


def test_plan_builds_the_verified_claude_call(example_run):
    kit = load_kit(ROOT, assignment="assignment.example.yaml")
    plan = build_plan(load_run(example_run, kit), kit, "u06")
    assert plan.argv == ["claude", "-p", "--model", "sonnet-5"]


def test_execute_runs_exactly_one_subprocess(example_run, monkeypatch):
    kit = load_kit(ROOT, assignment="assignment.example.yaml")
    plan = build_plan(load_run(example_run, kit), kit, "u06")
    calls = []

    class FakeProcess:
        returncode = 0
        stdout = iter(["done\n"])

        def wait(self):
            return 0

    def fake_popen(argv, **kwargs):
        calls.append(argv)
        return FakeProcess()

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    assert execute(plan) == 0
    assert len(calls) == 1
    assert plan.log_path.exists()
```

```python
# tests/test_cli_next.py
import pathlib

from rgraph.cli import main

ROOT = str(pathlib.Path(__file__).resolve().parents[1])


def test_next_shows_the_inventory_and_executes_nothing(example_run, capsys, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "S")
    assert main(["--root", ROOT, "--run", str(example_run), "--no-banner", "next"]) == 0
    out = capsys.readouterr().out
    assert "No command has been executed." in out
    assert "[E] Execute   [D] Dry run   [S] Stop" in out
    assert "Will produce" in out and "Required gate" in out


def test_dry_run_prints_the_command_without_running_it(example_run, capsys, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "D")
    called = []
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: called.append(a))
    assert main(["--root", ROOT, "--run", str(example_run), "--no-banner", "next"]) == 0
    assert called == []
    assert "codex exec" in capsys.readouterr().out or "claude -p" in capsys.readouterr().out


def test_web_provider_prints_manual_steps(example_run, capsys, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "S")
    main(["--root", ROOT, "--run", str(example_run), "--no-banner", "next", "--unit", "u02"])
    out = capsys.readouterr().out
    assert "Provider" in out
```

- [ ] **Steps 2–5:** implement, register, re-run, commit
`feat: rgraph next with single-shot approved execution`.

---

### Task 18: `rgraph review` and the completion screen

Evaluates all nine gates, prints the §9.0.7 completion block, then asks for the FINAL
outcome (`release · revise · narrow · null-result · stop`). On any outcome it writes
`release_manifest.json` (envelope-wrapped, `produced_by.role == "human"`) plus
`gates/FINAL.json`, carrying the per-gate revision counts, the recorded separation levels
and the caveat list. Exits 0 on `release`, 1 otherwise.

**Files:** Create `rgraph/commands/review.py`, add `render_completion` to `rgraph/render.py`. Test `tests/test_cli_review.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_review.py
import json
import pathlib

from rgraph.cli import main

ROOT = str(pathlib.Path(__file__).resolve().parents[1])


def test_review_reports_caveats_and_writes_a_manifest(example_run, capsys, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "release")
    assert main(["--root", ROOT, "--run", str(example_run), "--no-banner", "review"]) == 0
    out = capsys.readouterr().out
    assert "RUN COMPLETE" in out
    assert "Units         12 / 12 complete" in out
    assert "Human release" in out
    manifest = json.loads((example_run / "release_manifest.json").read_text())
    assert manifest["body"]["outcome"] == "release"
    assert "Scientific correctness was not determined" in manifest["body"]["not_established"]
    assert (example_run / "gates" / "FINAL.json").exists()


def test_stop_outcome_exits_one(example_run, capsys, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "stop")
    assert main(["--root", ROOT, "--run", str(example_run), "--no-banner", "review"]) == 1
```

- [ ] **Steps 2–5:** implement, register, re-run, commit `feat: rgraph review and release manifest`.

---

### Task 19: The six role files

Each role file is an executable contract with the same seven sections, so one body serves
three uses: paste as markdown, run as a Claude subagent, run as a Codex skill.

**Files:** Create `roles/{retrieval,planning,execution,verification,synthesis,reviewer}.md`. Test `tests/test_roles.py`.

**Frontmatter (all six):**

```markdown
---
name: retrieval
description: Literature retrieval and evidence extraction. Produces the search protocol, corpus snapshot, knowledge-graph snapshot and evidence matrix.
requires: [filesystem]
units: [u01, u02]
produces: [search_protocol, corpus_snapshot, kg_snapshot, evidence_matrix]
gates: [E1, H2]
revision_budget: 3
---
```

`requires` per the Global Constraints table; `units`, `produces` and `gates` per the unit
and gate registries. The body sections, in order:

1. **Role** — one paragraph. What this role is responsible for and what it must never do.
2. **Inputs** — the artifacts it may read, each with the path under `run/`.
3. **Outputs** — one subsection per artifact: the exact path, the schema path, and a filled
   minimal example of the envelope (`artifact_id`, `produced_by.identity`, `inputs[]` with
   upstream `content_hash`, `content_hash` of the body).
4. **Required fields** — the fields the gate will reject if absent, quoted from the schema.
5. **Acceptance criterion** — the sentence the gate enforces, e.g. for `retrieval`:
   *Every claim edge names a source that exists in the corpus snapshot and carries a page,
   section, table, figure or passage locator.*
6. **Revision budget** — `3 attempts. When the budget is spent the gate may only block or escalate.`
7. **Claim boundary** — the fixed paragraph: *This role does not establish scientific
   correctness. It establishes that every artifact it produces is registered, versioned and
   traceable to its inputs.*

Role-specific acceptance criteria:

| Role | Acceptance criterion |
|---|---|
| `retrieval` | Every claim edge names a corpus source and carries a non-empty locator. |
| `planning` | Every experiment names an accepted hypothesis; the frozen protocol lists one seed per replication, a stopping rule and a multiplicity plan. |
| `execution` | The run manifest records exactly the frozen seeds; every dataset digest matches the file on disk; raw results are append-only. |
| `verification` | Every estimate is recomputed from `raw_results.jsonl`, carries a 95% interval and an `n` equal to the completed-run count. |
| `synthesis` | Every manuscript claim appears in the claim–evidence map and maps to a computed result or a snapshotted source. |
| `reviewer` | The decision is recorded in a gate record whose `decided_by.identity` differs from the producing artifact's `produced_by.identity`. |

- [ ] **Step 1: Write the failing test**

```python
# tests/test_roles.py
import pathlib
import re

from rgraph.config import ROLES, ROLE_REQUIRES, load_kit

ROOT = pathlib.Path(__file__).resolve().parents[1]
SECTIONS = ("## Role", "## Inputs", "## Outputs", "## Required fields",
            "## Acceptance criterion", "## Revision budget", "## Claim boundary")


def _frontmatter(text):
    block = re.match(r"^---\n(.*?)\n---\n", text, re.S).group(1)
    from rgraph.yamlmini import loads
    return loads(block)


def test_every_role_file_exists_and_has_all_sections():
    for role in ROLES:
        text = (ROOT / "roles" / f"{role}.md").read_text(encoding="utf-8")
        for section in SECTIONS:
            assert section in text, (role, section)


def test_frontmatter_requires_matches_the_capability_table():
    for role in ROLES:
        meta = _frontmatter((ROOT / "roles" / f"{role}.md").read_text(encoding="utf-8"))
        assert set(meta["requires"]) == set(ROLE_REQUIRES[role]), role


def test_frontmatter_produces_matches_the_graph():
    kit = load_kit(ROOT)
    for role in ROLES:
        meta = _frontmatter((ROOT / "roles" / f"{role}.md").read_text(encoding="utf-8"))
        expected = sorted(
            a for node in kit.graph.nodes.values() if node.role_name == role
            for a in node.produces
        )
        assert sorted(meta["produces"]) == expected, role


def test_every_role_carries_the_claim_boundary():
    for role in ROLES:
        text = (ROOT / "roles" / f"{role}.md").read_text(encoding="utf-8")
        assert "does not establish scientific correctness" in text.lower()


def test_role_files_are_english_only():
    turkish = set("çğıöşüÇĞİÖŞÜ")
    for role in ROLES:
        text = (ROOT / "roles" / f"{role}.md").read_text(encoding="utf-8")
        assert not (turkish & set(text)), role
```

- [ ] **Steps 2–5:** write the six files, run the tests, commit `feat: six executable role contracts`.

---

### Task 20: `example-run` part 1 — the experiment and units 1–7

Topic (spec §14-A): *Does a learned channel estimator actually beat LMMSE at low SNR?*

**DOIs must never be hand-written.** Resolve each one before it enters a file:

```bash
curl -s 'https://api.crossref.org/works?rows=1&query.bibliographic=Power+of+Deep+Learning+for+Channel+Estimation+and+Signal+Detection+in+OFDM+Systems' \
  | python3 -c 'import json,sys; w=json.load(sys.stdin)["message"]["items"][0]; print(w["DOI"], "|", w["title"][0])'
```

Run that for each of these four papers, verify the returned title matches, and paste the
returned DOI. If a query returns a different paper, search again — do not settle.

1. Ye, Li, Juang — *Power of Deep Learning for Channel Estimation and Signal Detection in OFDM Systems* — IEEE Wireless Communications Letters, 2018
2. Soltani, Pourahmadi, Mirzaei, Sheikhzadeh — *Deep Learning-Based Channel Estimation* — IEEE Communications Letters, 2019
3. He, Wen, Jin, Li — *Deep Learning-Based Channel Estimation for Beamspace mmWave Massive MIMO Systems* — IEEE Wireless Communications Letters, 2018
4. Edfors, Sandell, van de Beek, Wilson, Börjesson — *OFDM Channel Estimation by Singular Value Decomposition* — IEEE Transactions on Communications, 1998 (the LMMSE baseline anchor)

Then verify every DOI resolves: `rgraph check E1 --online` must exit 0.

**Files:** Create `example-run/meta.json`, `example-run/code/estimator_bench.py`,
`example-run/{problem_spec,governance_record,search_protocol,corpus_snapshot,kg_snapshot,evidence_matrix,hypothesis_registry,design_protocol,frozen_protocol,code_commit,environment_lock,data_manifest,run_manifest}.json`,
`example-run/raw_results.jsonl`, `example-run/raw_results.meta.json`,
`example-run/gates/{H1,E1,H2,H3,T1,H4,T2}.json`.

`estimator_bench.py` is ~120 lines of NumPy-free pure Python: it simulates a
Rayleigh-tap channel over five SNR points (`-10, -5, 0, 5, 10` dB), compares an LMMSE
estimator against a small least-squares-plus-smoothing "learned" estimator, runs 20 seeds
(41–60), and appends one JSON object per run to `raw_results.jsonl` with fields
`run_id, seed, snr_db, estimator, mse`. It must run in under five seconds with
`python3 example-run/code/estimator_bench.py` and be deterministic given a seed
(`random.Random(seed)` only — no `time`, no unseeded RNG).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_example_run.py
import json
import pathlib
import subprocess
import sys

from rgraph.config import ARTIFACTS, load_kit
from rgraph.run import load_run

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_benchmark_is_deterministic(tmp_path):
    script = ROOT / "example-run" / "code" / "estimator_bench.py"
    first = subprocess.run([sys.executable, str(script), "--seed", "41"],
                           capture_output=True, text=True, check=True).stdout
    second = subprocess.run([sys.executable, str(script), "--seed", "41"],
                            capture_output=True, text=True, check=True).stdout
    assert first == second and first.strip()


def test_units_one_to_seven_are_present_and_valid():
    kit = load_kit(ROOT)
    run = load_run(ROOT / "example-run", kit)
    for artifact_id in ARTIFACTS[:13]:
        assert run.get(artifact_id).present, artifact_id
        assert run.get(artifact_id).errors == [], artifact_id


def test_raw_results_digest_matches_the_sidecar():
    from rgraph.provenance import payload_mismatch
    kit = load_kit(ROOT)
    run = load_run(ROOT / "example-run", kit)
    assert payload_mismatch(run, run.get("raw_results")) is None


def test_every_doi_is_syntactically_valid():
    from rgraph.checks import DOI_RE
    corpus = json.loads((ROOT / "example-run" / "corpus_snapshot.json").read_text())
    for source in corpus["body"]["sources"]:
        assert source["doi"] and DOI_RE.match(source["doi"]), source["source_id"]
        assert source["retracted"] is False
```

- [ ] **Steps 2–6:** write the benchmark, run it to produce `raw_results.jsonl`, author the
thirteen artifacts (each with a correct `content_hash` and correct `inputs[]` hashes — use
a one-off script under the scratchpad, not a committed helper), write the seven gate
records via `rgraph check`, run the tests, commit `feat: example run, units 1-7`.

---

### Task 21: `example-run` part 2 — units 8–12, all nine gates green

**Files:** Create `example-run/{reproduction_report,statistical_report,verification_report,claim_evidence_map,figure_registry,manuscript.meta}.json`, `example-run/manuscript.md`, `example-run/code/plot_mse.py`, `example-run/gates/{V1,M1}.json`.

`manuscript.md` is a short paper (~700 words) with sections Abstract, Method, Results,
Limitations. Claim `c-03` must read exactly *"Method X improved the target metric by 12
percent."* only if the benchmark actually produces that number — otherwise write the true
sentence and update spec §9.0.6's example in the README rather than faking the result.
Every claim in the manuscript appears in `claim_evidence_map` and maps to a
`statistical_report` result.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_example_run.py
def test_all_nine_gates_pass_on_the_example_run():
    from rgraph.gates import evaluate_gate
    kit = load_kit(ROOT, assignment="assignment.example.yaml")
    run = load_run(ROOT / "example-run", kit)
    for gate_id in ("H1", "E1", "H2", "H3", "T1", "H4", "T2", "V1", "M1"):
        result = evaluate_gate(run, kit, gate_id)
        assert result.status in ("PASS", "CAVEAT"), (gate_id, result.findings)


def test_no_artifact_is_stale():
    from rgraph.provenance import stale_artifacts
    kit = load_kit(ROOT)
    assert stale_artifacts(load_run(ROOT / "example-run", kit)) == {}


def test_every_manuscript_claim_is_mapped():
    kit = load_kit(ROOT)
    run = load_run(ROOT / "example-run", kit)
    mapped = {c["claim_id"] for c in run.get("claim_evidence_map").body["claims"]}
    for section in run.get("manuscript").body["sections"]:
        assert set(section["claim_ids"]) <= mapped
```

- [ ] **Steps 2–5:** author the artifacts, run `rgraph check` for V1 and M1 to write the
records, run the whole suite — **every test deferred in Tasks 9–18 must now be green** —
commit `feat: example run complete, nine gates green`.

This closes done-criteria 2 and 5.

---

### Task 22: `rgraph demo` — three scenarios

Copies `example-run/` into a temporary directory, mutates it, and shows what the kit
catches. Nothing under `example-run/` is ever modified.

| Scenario | Mutation | Expected |
|---|---|---|
| ① Clean run | none | nine gates PASS, exit 0 |
| ② Fabricated citation | `corpus_snapshot.sources[0].doi = null` | E1 FAIL, `SOURCE NOT RESOLVED`, exit 1 |
| ③ Data changed after the freeze | bump `data_manifest.datasets[0].bytes`, re-hash the body | STALE chain invalidates T2, V1, M1, exit 1 |

**Files:** Create `rgraph/commands/demo.py`. Test `tests/test_cli_demo.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_demo.py
import pathlib

from rgraph.cli import main

ROOT = str(pathlib.Path(__file__).resolve().parents[1])


def test_demo_runs_three_scenarios_and_exits_one(capsys):
    assert main(["--root", ROOT, "--no-banner", "demo"]) == 1
    out = capsys.readouterr().out
    assert "SCENARIO 1" in out and "SCENARIO 2" in out and "SCENARIO 3" in out
    assert "SOURCE NOT RESOLVED" in out
    assert "STALE CHAIN DETECTED" in out
    assert "Invalidated: M1, T2, V1" in out


def test_demo_leaves_the_committed_example_untouched(capsys):
    before = (pathlib.Path(ROOT) / "example-run" / "corpus_snapshot.json").read_bytes()
    main(["--root", ROOT, "--no-banner", "demo"])
    assert (pathlib.Path(ROOT) / "example-run" / "corpus_snapshot.json").read_bytes() == before


def test_single_scenario_selection(capsys):
    assert main(["--root", ROOT, "--no-banner", "demo", "--scenario", "1"]) == 0
```

- [ ] **Steps 2–5:** implement, register (no banner), re-run, commit `feat: rgraph demo`.

This closes done-criteria 3 and 4.

---

### Task 23: README and dual-manifest packaging

One body, two manifests, no content duplication — the Aletheia pattern.

**Files:** Create `README.md`, `.claude-plugin/plugin.json`, `.agents/plugins/marketplace.json`, `plugins/research-graph/.codex-plugin/plugin.json`. Test `tests/test_packaging.py`.

`.claude-plugin/plugin.json`:

```json
{
  "name": "research-graph",
  "version": "0.1.0",
  "description": "Contract-gated agentic research: graph engineering, verified.",
  "author": {"name": "Hüseyin Uğur Yıldız"},
  "skills": ["./roles"]
}
```

`plugins/research-graph/.codex-plugin/plugin.json` names the same six role files as
prompts, pointing at `../../../roles/<role>.md` — a path reference, never a copy.
`.agents/plugins/marketplace.json` lists the single plugin with its repository URL.

README sections, in order: the one-line position (*Graph engineering, verified — the tool
that enforces the rules instead of stating them*), a 30-second quickstart
(`git clone` → `pip install -e .` → `rgraph demo`), the four-file architecture, the two
verifier layers, the three independence levels **with the honesty limit of spec §5.2
quoted verbatim** (the reviewer check is a discipline mechanism, not cryptography), the
provider-tier table of §8 including *subscription ≠ API*, the claim boundary, the explicit
credit to `codejunkie99/graph-engineering` for defining the term, the one-line
*see also: Arbor* pointer, and the four locked deviations from this plan's Global
Constraints. GitHub topics to set: `graph-engineering`, `agentic-research`, `provenance`,
`verification`, `research-tools`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_packaging.py
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_claude_manifest_points_at_the_shared_roles_directory():
    manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["skills"] == ["./roles"]
    assert manifest["version"] == "0.1.0"


def test_codex_manifest_references_roles_without_copying_them():
    path = ROOT / "plugins" / "research-graph" / ".codex-plugin" / "plugin.json"
    manifest = json.loads(path.read_text())
    for entry in manifest["prompts"]:
        target = (path.parent / entry["path"]).resolve()
        assert target.is_relative_to(ROOT / "roles"), entry


def test_no_role_file_is_duplicated_anywhere():
    copies = [p for p in ROOT.rglob("retrieval.md") if p.parent.name != "roles"]
    assert copies == []


def test_readme_states_the_claim_boundary_and_the_honesty_limit():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "does not judge scientific correctness" in text.lower()
    assert "discipline mechanism" in text.lower()
    assert "codejunkie99/graph-engineering" in text
    assert "subscription" in text.lower() and "api" in text.lower()
```

- [ ] **Steps 2–5:** write the files, run the tests, commit `docs: README and dual-manifest packaging`.

---

### Task 24: Vercel landing page and the web configurator

`architecture.html` stays self-contained. `index.html` is a thin wrapper: a top strip with
the repo link, a copyable `git clone` line and a *Try it in 30 seconds* block, then the
diagram inlined below it (copy the diagram's markup in at build-authoring time — no
`<iframe>`, no external asset, no build step).

The configurator lives inside the diagram: clicking an agent node opens a side panel
asking *who should run this role?*; options whose provider lacks the role's `requires`
capabilities render dimmed and unselectable with the reason shown; the panel emits a live
`assignment.yaml` plus the single-line `--preset` command, both with a Copy button. The
generated YAML is prefixed with setup comments driven by the selection, exactly as
spec §10 shows.

**Files:** Create `index.html`, `vercel.json`. Modify `architecture.html` (append the
configurator panel, its styles and its script — do not restructure the existing diagram).
Test `tests/test_configurator.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_configurator.py
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_landing_page_has_no_external_requests():
    text = (ROOT / "index.html").read_text(encoding="utf-8")
    assert not re.search(r'(src|href)\s*=\s*["\']https?://(?!github\.com)', text)
    assert "git clone" in text


def test_configurator_knows_every_role_and_capability():
    text = (ROOT / "architecture.html").read_text(encoding="utf-8")
    for role in ("retrieval", "planning", "execution", "verification", "synthesis", "reviewer"):
        assert role in text
    assert "ROLE_REQUIRES" in text
    assert "assignment.yaml" in text


def test_configurator_blocks_web_providers_for_shell_roles():
    text = (ROOT / "architecture.html").read_text(encoding="utf-8")
    block = re.search(r"const ROLE_REQUIRES\s*=\s*\{.*?\};", text, re.S).group(0)
    assert "shell" in block
    assert '"execution"' in block or "execution:" in block


def test_vercel_config_serves_the_landing_page():
    import json
    config = json.loads((ROOT / "vercel.json").read_text())
    assert config.get("cleanUrls") is True or "rewrites" in config
```

- [ ] **Step 2:** run it → FAIL. **Step 3:** implement. **Step 4:** verify in a browser at
1440×900 and 390×844 — the panel must not overflow on mobile, and the generated YAML must
parse: paste it into a file and run `rgraph setup --preset` on the emitted command, then
`rgraph check --static`. **Step 5:** commit `feat: Vercel landing page and web configurator`.

This closes done-criterion 7.

---

### Task 25: Acceptance sweep

One test module that asserts the seven done-criteria of spec §13 end to end, plus a clean
clone rehearsal.

**Files:** Create `tests/test_acceptance.py`.

- [ ] **Step 1: Write the test**

```python
# tests/test_acceptance.py
"""The seven done-criteria of the design document, section 13."""

import json
import pathlib
import subprocess
import sys

from rgraph.cli import main

ROOT = pathlib.Path(__file__).resolve().parents[1]
R = ["--root", str(ROOT), "--no-banner"]


def test_1_static_layer_is_clean_on_the_reference_graph():
    assert main([*R, "check", "--static"]) == 0


def test_2_all_nine_gates_are_green_on_the_example_run(example_run):
    for gate_id in ("H1", "E1", "H2", "H3", "T1", "H4", "T2", "V1", "M1"):
        assert main([*R, "--run", str(example_run), "check", gate_id]) == 0, gate_id


def test_3_a_broken_doi_makes_e1_red(example_run):
    path = example_run / "corpus_snapshot.json"
    document = json.loads(path.read_text())
    document["body"]["sources"][0]["doi"] = None
    path.write_text(json.dumps(document))
    assert main([*R, "--run", str(example_run), "check", "E1"]) == 1


def test_4_data_changed_after_the_freeze_invalidates_downstream_gates(example_run, capsys):
    from rgraph.hashing import content_hash
    path = example_run / "data_manifest.json"
    document = json.loads(path.read_text())
    document["body"]["datasets"][0]["bytes"] += 1
    document["content_hash"] = content_hash(document["body"])
    path.write_text(json.dumps(document))
    for gate_id in ("T2", "V1", "M1"):
        assert main([*R, "--run", str(example_run), "check", gate_id]) == 1, gate_id
    assert "STALE" in capsys.readouterr().out


def test_5_trace_prints_an_unbroken_chain(example_run, capsys):
    assert main([*R, "--run", str(example_run), "trace", "c-03"]) == 0
    assert "Provenance chain is complete." in capsys.readouterr().out


def test_6_a_clean_checkout_reaches_a_green_demo(tmp_path):
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "--depth", "1", str(ROOT), str(clone)], check=True,
                   capture_output=True)
    result = subprocess.run([sys.executable, "-m", "rgraph", "--root", str(clone),
                             "--no-banner", "demo", "--scenario", "1"],
                            capture_output=True, text=True, cwd=clone)
    assert result.returncode == 0, result.stdout + result.stderr


def test_7_the_landing_page_and_the_diagram_are_self_contained():
    for name in ("index.html", "architecture.html"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "cdn." not in text and "googleapis" not in text


def test_cli_output_is_english_only(example_run, capsys):
    main([*R, "--run", str(example_run), "status"])
    main([*R, "--run", str(example_run), "check", "E1"])
    assert not (set("çğıöşüÇĞİÖŞÜ") & set(capsys.readouterr().out))
```

- [ ] **Step 2:** run `python -m pytest tests/ -v` — the whole suite green.
- [ ] **Step 3:** run the three commands a first-time reader will run, and read the output
as a stranger would: `rgraph`, `rgraph demo`, `rgraph status --run example-run`.
- [ ] **Step 4:** commit `test: acceptance sweep for the seven done-criteria`, then push to
`main`.

---

## Self-Review

**Spec coverage.** §4 config trio → Tasks 3–4. §5 two verifier layers → Tasks 5, 9–12.
§5.1 independence levels → Task 4. §5.2 honesty limit → Task 23 (README). §6 roles and
capability matching → Tasks 16, 19. §7 KG↔process binding → `kg_snapshot` schema (Task 7)
and E1's `source_support` (Task 11). §8 provider tiers → Tasks 16–17, README. §9 CLI
surface, all eight commands and every screen → Tasks 5, 12–18, 22. §10 web configurator →
Task 24. §11 repo layout and dual manifests → Task 23. §12 non-goals → held by the Global
Constraints. §13 done-criteria → Task 25. §14-A example run → Tasks 20–21. §14-B approved
execution → Task 17.

**Known gaps, stated rather than hidden.** Tier 3 (LiteLLM) is out of v0.1 by spec §12.
`rgraph next` advances one unit per invocation by design. Offline DOI checking accepts a
well-formed but non-existent DOI; `--online` is the answer and Task 11's test asserts the
limitation instead of papering over it.

**Ordering note.** Tests in Tasks 9–18 that depend on the `example_run` fixture stay red
until Task 21 lands. Each of those tasks says so explicitly and gives the `-k` filter to
run its green subset in the meantime. Task 21 is the barrier where the deferred tests must
all turn green; do not proceed past it with any of them red.

---

## Implementation record — completed 2026-07-31

All 25 tasks are implemented and committed. 164 tests green; all seven done-criteria of
spec §13 pass, including the clean-clone rehearsal and live DOI resolution
(`rgraph check E1 --online` exits 0 against Crossref).

Five things came out differently from the plan. Each is a correction, not a shortcut.

1. **`--version` raises `SystemExit(0)`, it does not return 0.** That is how `argparse`
   implements the action. `tests/test_cli_smoke.py` asserts the real behaviour.

2. **`grok` has `read_files`, not just `manual`.** Spec §4.3 gave it only `manual`, while
   spec §6 calls a web-only provider *ideal* for the reviewer role, which needs
   `read_files`. The two could not both be true. A web chat does read whatever you paste
   into it, so `read_files` is correct; `manual` stays as the marker that a human relays
   the text.

3. **Capability matching has three states, not two.** `rgraph.config.assignability`
   returns `ok`, `manual` or `blocked`. A provider declaring `manual` stands in for
   `filesystem` but never for `shell`, which reproduces spec §6's table exactly:
   retrieval, planning and synthesis accept a web provider with a relay warning;
   execution and verification refuse it. The plan's two-state `_capable` would have
   blocked all five, contradicting the spec.

4. **The configurator lives in `index.html`, not in `architecture.html`.** The diagram is
   a fixed-viewport flex canvas (`html,body{height:100%;overflow:hidden}`,
   `body{display:flex}`), so an appended panel becomes a second flex item and breaks the
   layout — verified in-browser before reverting. Spec §11 requires the diagram to ship
   *as-is*, and the landing page is the abandon point the configurator exists to serve.
   `architecture.html` is byte-identical to the committed original.

5. **The 21 schemas were emitted by a one-off authoring script**, not typed by hand. The
   script lives in the session scratchpad and is not committed; the JSON files are.
   Content is identical either way, and `tests/test_schemas.py` is the gate.

**Example-run finding worth keeping.** The benchmark refutes its own registered
hypothesis h-02: the learned estimator's advantage is *smallest* at low SNR (2.09 dB at
-10 dB against 8.99 dB at +10 dB), not largest. That is reported in the manuscript,
graded `major` in the verification report, and marked `extrapolation` in the
claim–evidence map. An example run that only ever agreed with itself would demonstrate
nothing.

**Not done, and why.** No git remote is configured, so nothing is pushed. Creating the
GitHub repository and the Vercel project are the owner's calls.
