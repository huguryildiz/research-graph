<br>

<p align="center">
  <a href="https://github.com/huguryildiz/research-graph">
    <img src="assets/icon.svg" width="144" height="144" alt="research-graph icon">
  </a>
</p>

<h1 align="center">research-graph</h1>

<p align="center"><strong>Contract-gated research verification</strong></p>

<p align="center">
  Trace every artifact, verify every handoff, and bound every revision.<br>
  A provider-neutral integrity layer for multi-agent research pipelines.
</p>

<p align="center">
  <a href="https://github.com/huguryildiz/research-graph/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/huguryildiz/research-graph/ci.yml?branch=main&amp;style=flat-square&amp;label=CI&amp;labelColor=243449&amp;color=25c08c" alt="CI status"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.11%2B-4d97f2?style=flat-square&amp;labelColor=243449" alt="Python 3.11 or newer"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/Licence-MIT-e0a83d?style=flat-square&amp;labelColor=243449" alt="MIT licence"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/validation-JSON_Schema-25c08c?style=flat-square&amp;labelColor=111a24" alt="JSON Schema validation">
  <img src="https://img.shields.io/badge/provenance-SHA--256-e0629b?style=flat-square&amp;labelColor=111a24" alt="SHA-256 provenance">
  <img src="https://img.shields.io/badge/runtime-offline--first-7fa9b5?style=flat-square&amp;labelColor=111a24" alt="Offline-first runtime">
</p>

<p align="center">
  <a href="#30-seconds"><strong>Quickstart</strong></a>
  &nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="https://research-graph-kit.vercel.app/architecture.html"><strong>Architecture</strong></a>
  &nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="#the-eleven-commands"><strong>Commands</strong></a>
  &nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="#what-it-does-not-do"><strong>Scope</strong></a>
  &nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="https://research-graph-kit.vercel.app"><strong>Live site</strong></a>
</p>

<br>

---

**Graph engineering, verified.** Most graph engineering material states rules.
This one enforces them.

`research-graph` is a contract-gated verification layer for multi-agent research
pipelines. It reads a directory of versioned artifacts, validates every one
against a JSON Schema, walks the provenance hash chain, checks that the reviewer
was not the producer, and returns an exit code. It orchestrates nothing and calls
no model API.

## 30 seconds

```bash
uv tool install git+https://github.com/huguryildiz/research-graph
rgraph demo
```

You do not need a Python of your own: [`uv`](https://docs.astral.sh/uv/) fetches
an interpreter that satisfies the kit and keeps both it and the dependencies
away from whatever else is installed on your machine. If you do not have `uv`
yet:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh    # Windows: irm https://astral.sh/uv/install.ps1 | iex
```

To try it without installing anything at all, run
`uvx --from git+https://github.com/huguryildiz/research-graph rgraph demo`
instead. Every command below then needs the same `uvx --from ...` prefix, which
is why `uv tool install` is the shorter road past the demo.

### From a checkout

For working on the kit itself, or reading the sources while you run them:

```bash
python3 --version                  # 3.11 or newer; older will fail confusingly
git clone https://github.com/huguryildiz/research-graph
cd research-graph
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
rgraph demo
```

If your shell answers `command not found: rgraph` immediately after that
install, it is reading a stale command table rather than missing the file:
`rehash` in zsh, `hash -r` in bash. A conda `base` environment can also keep its
own `bin` ahead of the venv's, in which case `conda deactivate` before
activating the venv.

> `rgraph demo` **exits 1 on purpose.** Scenarios 2 and 3 are failures staged to
> show what the verifier catches, and the exit code reports the worst of the
> three. A non-zero exit here means the demo worked.

`rgraph demo` runs three scenarios on a throwaway copy of the bundled example:

1. **A clean run** — nine gates pass.
2. **A fabricated citation** — a source with no resolvable DOI. Gate E1 goes red,
   names the source, says how to fix it, and exits 1.
3. **Data changed after the freeze** — `data_manifest.json` rewritten after the
   protocol was frozen, digest and downstream references included, the way a
   re-run would. The stale chain invalidates T2, V1 and M1.

Scenarios 2 and 3 are the point. Neither can be prevented by a prompt; both are
caught by a file digest.

## Your own run, in four commands

The demo shows the verifier working on somebody else's evidence. This starts
yours:

```bash
rgraph init          # run/ from the template, plus the two artifacts you write
rgraph seal          # stamp each content_hash from the body it belongs to
rgraph decide H1     # answer what the gate proves — this part is yours
rgraph check H1      # verify the answer, the files and the digests agree
```

`rgraph init` writes `run/problem_spec.json` and `run/governance_record.json` as
filled-in skeletons, because gate H1 needs both and no agent produces them —
they are yours. Edit them, run `rgraph seal`, and check H1 again. From there
`rgraph next` walks the twelve units in order.

### A human gate needs a human

Four of the nine gates are human gates, and `check` cannot decide one. It reads
files, recomputes digests and compares strings — all of which it can do while
nobody is watching. So a human gate stays `AWAITING` until somebody answers it:

```
GATE H1 / SCOPE, CONSTRAINTS & RESEARCH INTENT   AWAITING

  [PASS] Presence
  [PASS] Schema
  [FAIL] Decision
         no human decision recorded

  Run next:  rgraph decide H1
```

`rgraph decide` asks what the gate declares it proves, one line at a time, and
records the answers and who gave them. The questions are not invented: they are
the `proves` entries already written in `gates.yaml`.

```
This gate proves 2 thing(s). It cannot prove them for you.

  1/2  Scope and constraints recorded
       Have you read problem_spec, governance_record and does this hold?
       [y] yes  [n] no  [s] stop > y
```

A `no` sends the gate back rather than opening it. Walking away records nothing.
And because the attestation is pinned to the digests that were on the table, a
later edit retires it — resealing repairs the hash, which is mechanical, but it
cannot repair the reading, so the gate asks again.

A canonical SHA-256 is not something anyone types by hand, so `rgraph seal`
computes it. Everything else the kit does rests on those digests being true, so
editing a body and leaving its hash behind is itself a finding:

```
  problem_spec  BODY EDITED AFTER HASHING
        body no longer matches its content_hash: declared sha256:257e24be...,
        actual sha256:b58612699...
        Fix: re-run the unit that produces problem_spec, or `rgraph seal
             problem_spec` if you edited it on purpose
```

## The four files

Separation of concerns is the backbone of the kit.

| File | Answers |
|---|---|
| `graph.yaml` | Which nodes, which edges, which gates — the architecture |
| `assignment.yaml` | Who runs which role — your subscriptions |
| `providers.yaml` | Which providers exist and what they can do — the registry |
| `gates.yaml` | What each gate requires, at what separation level, with what budget |

The same graph runs on anyone's combination of subscriptions. Adding a provider
is a few lines in `providers.yaml`; **no code changes**, because `rgraph` knows no
provider — it only carries identity strings.

Three of the four describe the architecture and ship with the kit.
`assignment.yaml` is yours, so it lives with you rather than with the install:
`rgraph setup` writes `~/.config/rgraph/assignment.yaml` once, and every study on
the machine uses it. A study that needs a different pair of providers gets its
own copy with `rgraph setup --here`, which wins over the machine default for that
directory.

## The verifier: two layers

### Layer 1 — static, no run required

```bash
rgraph check --static
```

| Check | Catches |
|---|---|
| Type match | a stage expecting an output nobody produces |
| Acyclic | a hidden infinite loop (cycles are legal only on `return` edges) |
| Bounded | an unbounded correction spiral |
| Reachable | a gate that can never be passed |
| Dead node | a decorative box — a "fake edge" |

### Layer 2 — dynamic, over a `run/` directory

Existence, JSON Schema, provenance (`produced_by`, `inputs[]` upstream hashes,
`content_hash`), **staleness**, **reviewer separation**, and the revision budget.

The last two are the kit's reason to exist. Neither can be prevented by
instructions, and both fall out of a file digest:

- **Staleness** — every artifact carries the digest of its own body and the
  `content_hash` of each input it consumed. Both are recomputed on every read,
  so a file edited after a gate passed invalidates that gate and everything
  downstream, whether or not whoever edited it updated the hashes.
- **Reviewer separation** — a challenge gate records who decided it and who
  produced what was decided on.

## Independence, without the word "independent"

"Independent" promises more than a separate session delivers, so the CLI never
prints it — no `rgraph` screen, in any command, contains the word. It prints a
level you can verify instead:

| Level | Rule | Costs |
|---|---|---|
| `CONTEXT ONLY` | separate session, same model and provider | one subscription |
| `SEPARATE MODEL` | same provider, different model | one subscription, multi-model |
| `SEPARATE PROVIDER` | different provider | two subscriptions |

`CONTEXT ONLY` always prints with its caveat:

```
Review separation
  Level : CONTEXT ONLY
  Note  : Reviewer uses a separate session, but the same model
          and provider. Correlated errors may remain.
```

`rgraph` never hides which level was actually achieved; it writes it into the
release manifest. `tests/test_separation.py` holds the CLI to it.

The reference diagram is the exception, and deliberately: `architecture.html`
labels the audit role "independent review role", because there the word names a
design intention rather than something the kit measured. The rule binds what
`rgraph` reports, not what a drawing aspires to.

### The honesty limit

The `reviewer_id != producer_id` check is **not cryptographic.**
It is a **discipline mechanism.**
A determined user can write whatever identity they like — and would
only be deceiving themselves. The kit is built to make the honest path the easy
one, not to make the dishonest path impossible.

## What it does not do

**research-graph does not judge scientific correctness.** It establishes that
every artifact behind a claim is registered, versioned and traceable to its
inputs. Every gate screen repeats this, in the same words, whether the gate
passed or failed:

```
  [----] Scientific correctness was not determined
```

Also deliberately absent: no runtime or orchestrator, no model API calls, no
multi-provider abstraction layer, no web UI, no database, no server.

## Running it: four tiers

| Tier | Needs | Separation | Status |
|---|---|---|---|
| **0 · Manual** | nothing — a web chat and copy-paste | separate session | works today |
| **1 · One CLI** | Claude Code **or** Codex | separate session | works today |
| **2 · Two CLIs** | Claude Code **and** Codex | **separate provider** | works today |
| **3 · API** | API keys | separate provider, full automation | **not implemented** |

Tier 3 is a design intention, not a feature: `providers.yaml` has no API-backed
provider kind, `rgraph` contains no HTTP client, and nothing here calls a model.
It is listed so the ceiling of the design is visible, not to suggest you can run
it. Tiers 0–2 are what the kit does today.

Tier 2 is the kit's most distinctive configuration: real cross-provider auditing
for the price of two subscriptions and no API spend. These call forms were run
against the installed CLIs on 2026-07-31 and are what `providers.yaml` records:

```bash
codex exec -c model="gpt-5.6" - < roles/reviewer.md   # codex-cli 0.144.6
claude -p --model opus-5 < roles/planning.md          # Claude Code 2.1.220
```

What has *not* happened is an end-to-end study driven this way. `example-run/` is
a fixture with authored provenance, `template-run/` is empty, and no run in this
repository was produced by the identities it names. The verifier is exercised;
the multi-agent loop around it is not yet evidenced.

### A subscription is not an API key

| | Gives you | Does not give you |
|---|---|---|
| Claude Pro/Max | claude.ai and the Claude Code CLI | Anthropic API credit |
| ChatGPT Plus/Pro | chatgpt.com and the Codex CLI | OpenAI API credit |
| An API key | programmatic calls | — (billed separately) |

Subscription CLIs carry rate limits, and orchestration is not automatic: you move
between steps yourself. Full automation is tier 3.

## The eleven commands

| Command | When |
|---|---|
| `rgraph demo` | once, out of curiosity — three scenarios |
| `rgraph setup` | once, at install — detect providers and assign roles (`--here` for one study) |
| `rgraph init` | once per study — create `run/` and the two artifacts you write |
| `rgraph status` | "where am I" — the summary pipeline (`--verbose` opens all 12 units) |
| `rgraph next` | the next unit — inventory, then one approved command |
| `rgraph seal` | after editing an artifact by hand — recompute its digests |
| `rgraph decide <GATE>` | answer a human gate — H1, H2, H3, H4 |
| `rgraph check <GATE>` | gate verification, or `--static` for the graph lint |
| `rgraph revise <GATE>` | the return path after a FAIL |
| `rgraph trace <claim>` | from a claim down to raw data |
| `rgraph review` | the human release decision |

`check` verifies and `decide` decides, and the split is deliberate: a command
that could write its own attestation could forge one, so `check` never writes a
human gate's record.

Global flags (`--run`, `--root`, `--verbose`, `--no-banner`) are accepted on
either side of the command name.

`rgraph next` shows exactly what it would run, prints `No command has been
executed.`, and waits for `[E] Execute`. It runs **one** subprocess and returns
control. There is no scheduler and no loop.

## The example run

`example-run/` is a **fixture, and it says so**: its `meta.json` carries
`"provenance": "synthetic"`, and every `rgraph` screen that reads it prints that
before anything else. The experiment, the statistics, the DOIs and the hash chain
are real; the `produced_by.identity` fields are illustrative, because no provider
was ever invoked and no reviewer ever decided a gate.
[`example-run/README.md`](example-run/README.md) lists exactly what is real and
what is not. A kit about honest provenance does not get to be vague about its own.

It answers a real question — *does a learned channel estimator actually beat
LMMSE at low SNR?* — over twenty seed-matched replications with a protocol frozen
before execution.

The estimator it labels *learned* is **not a neural network.** It is a tuned
delay-domain filter: the structure a learned estimator recovers in this setting,
written out explicitly so the benchmark stays deterministic and reviewable. The
result therefore bounds the value of that structure, not of any architecture.
The code says so, the manuscript says so in its Method and Limitations, and it is
said here too, because a reader who stops at this README should not leave with
the wrong picture.

All four DOIs in its corpus were resolved against Crossref and verified by direct
lookup. None was hand-written. If they had been, the kit's own E1 gate would fail
on the kit's own example.

The run reports an honest negative. Registered hypothesis h-02 said the advantage
would be largest at the lowest SNR. It is not: 2.09 dB at -10 dB against 8.99 dB
at +10 dB. The manuscript says so, the verification report grades it `major`, and
the claim–evidence map marks the trend claim as an extrapolation. That is what
the kit is for.

## Credit and neighbours

[`codejunkie99/graph-engineering`](https://github.com/codejunkie99/graph-engineering)
defined the term and wrote its textbook: *knowledge graphs are what agents
remember, task graphs are what agents run*. Its four rules — delete fake edges,
verify at every stage, separate verifier contexts, keep a stop rule and a human
gate — are the rules this repository turns into code. They wrote the textbook; we
wrote the compiler. Complementary, not competing.

See also [Arbor](https://github.com/RUC-NLPIR/Arbor) (arXiv 2606.11926), which
solves a different problem: finding a better result through autonomous
optimisation. *Arbor runs; research-graph audits.*

## Deviations from the design document

`docs/2026-07-31-research-graph-design.md` is the Turkish design document. Four
points were resolved during implementation and are recorded here rather than
buried:

1. **21 artifact schemas, not 18.** The reference diagram's artifact registry
   holds 20 entries, and `kg_snapshot` is the 21st. Every gate input now has a
   schema, so the reachability lint has no blind spot. `architecture.html` is
   drawn by hand rather than rendered from `graph.yaml`, so
   `tests/test_diagram_matches_graph.py` diffs the plate against the executed
   configuration on every run — gates, gate inputs, artifact registry and typed
   revision reasons. `kg_snapshot` is the one divergence it permits, and it
   fails if a second one appears.
2. **Graph nodes are the 12 work units, not the 5 pipeline stages.** The CLI
   output requires unit granularity; each unit carries a `stage` field and
   `rgraph status` aggregates the five-stage row from it.
3. **Run artifacts are JSON; only the four config files are YAML.** The kit ships
   a deliberately small YAML-subset parser (no PyYAML dependency) and that parser
   should not be the one reading your evidence.
4. **Gate decisions are gate records, not an artifact.** They live in
   `run/gates/<GATE>.json` under their own schema and are not among the 21.

## Requirements

Python ≥ 3.11, tested on 3.11, 3.12 and 3.13 across Linux, macOS and Windows.
Installing with `uv` covers that requirement for you; a checkout install expects
you to have the interpreter already. Two runtime dependencies: `jsonschema` and
`rich`. Nothing else.

Everything runs offline. The single exception is `rgraph check E1 --online`,
which resolves each DOI against `doi.org`; without a network it reports which
DOIs it could not reach and judges the rest, rather than calling them
fabricated.

Installing from a wheel works the same as from a checkout — the graph, gates,
schemas, role contracts and both example runs ship inside the package, and
`rgraph` falls back to them whenever you are not standing in a checkout.

To remove it: `uv tool uninstall research-graph`, or `pip uninstall
research-graph` from a checkout, then delete your `run/` directory and
`~/.config/rgraph/assignment.yaml` if you want the state gone too.

## Contributing

```bash
pip install -e '.[dev]'
pytest -q
```

Details, including what CI checks and why, are in
[`CONTRIBUTING.md`](CONTRIBUTING.md). What counts as a security issue — and
the two limits that mean most reports are not one — is in
[`SECURITY.md`](SECURITY.md). Release notes live in
[`CHANGELOG.md`](CHANGELOG.md).

## Licence

MIT — see [`LICENSE`](LICENSE).
