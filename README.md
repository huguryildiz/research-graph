# research-graph

**Graph engineering, verified.** Most graph engineering material states rules.
This one enforces them.

`research-graph` is a contract-gated verification layer for multi-agent research
pipelines. It reads a directory of versioned artifacts, validates every one
against a JSON Schema, walks the provenance hash chain, checks that the reviewer
was not the producer, and returns an exit code. It orchestrates nothing and calls
no model API.

## 30 seconds

```bash
git clone https://github.com/huguryildiz/research-graph
cd research-graph
pip install -e .
rgraph demo
```

`rgraph demo` runs three scenarios on a throwaway copy of the bundled example:

1. **A clean run** — nine gates pass.
2. **A fabricated citation** — a source with no resolvable DOI. Gate E1 goes red,
   names the source, says how to fix it, and exits 1.
3. **Data changed after the freeze** — one byte edited in `data_manifest.json`
   after the protocol was frozen. The stale chain invalidates T2, V1 and M1.

Scenarios 2 and 3 are the point. Neither can be prevented by a prompt; both are
caught by a file digest.

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

- **Staleness** — every artifact records the `content_hash` of each input it
  consumed. Change an upstream file after a gate passed and the gate is
  invalidated, along with everything downstream.
- **Reviewer separation** — a challenge gate records who decided it and who
  produced what was decided on.

## Independence, without the word "independent"

"Independent" promises more than a separate session delivers, so `rgraph` never
prints it. It prints a level you can verify:

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
release manifest.

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
multi-provider abstraction layer of our own (tier 3 delegates to LiteLLM), no web
UI, no database, no server.

## Running it: four tiers

| Tier | Needs | Separation | For |
|---|---|---|---|
| **0 · Manual** | nothing — a web chat and copy-paste | separate session | anyone |
| **1 · One CLI** | Claude Code **or** Codex | separate session | one subscription |
| **2 · Two CLIs** | Claude Code **and** Codex | **separate provider** | two subscriptions, no API |
| **3 · API** | API keys, via LiteLLM | separate provider, full automation | advanced |

Tier 2 is the kit's most distinctive configuration: real cross-provider auditing
for the price of two subscriptions and no API spend. The verified call forms, as
of 2026-07-31:

```bash
codex exec -c model="gpt-5.6" - < roles/reviewer.md   # codex-cli 0.144.6
claude -p --model opus-5 < roles/planning.md          # Claude Code 2.1.220
```

### A subscription is not an API key

| | Gives you | Does not give you |
|---|---|---|
| Claude Pro/Max | claude.ai and the Claude Code CLI | Anthropic API credit |
| ChatGPT Plus/Pro | chatgpt.com and the Codex CLI | OpenAI API credit |
| An API key | programmatic calls | — (billed separately) |

Subscription CLIs carry rate limits, and orchestration is not automatic: you move
between steps yourself. Full automation is tier 3.

## The eight commands

| Command | When |
|---|---|
| `rgraph demo` | once, out of curiosity — three scenarios |
| `rgraph setup` | once, at install — detect providers and assign roles |
| `rgraph status` | "where am I" — the summary pipeline (`--verbose` opens all 12 units) |
| `rgraph next` | the next unit — inventory, then one approved command |
| `rgraph check <GATE>` | gate verification, or `--static` for the graph lint |
| `rgraph revise <GATE>` | the return path after a FAIL |
| `rgraph trace <claim>` | from a claim down to raw data |
| `rgraph review` | the human release decision |

`rgraph next` shows exactly what it would run, prints `No command has been
executed.`, and waits for `[E] Execute`. It runs **one** subprocess and returns
control. There is no scheduler and no loop.

## The example run

`example-run/` answers a real question — *does a learned channel estimator
actually beat LMMSE at low SNR?* — over twenty seed-matched replications with a
protocol frozen before execution.

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
   schema, so the reachability lint has no blind spot.
2. **Graph nodes are the 12 work units, not the 5 pipeline stages.** The CLI
   output requires unit granularity; each unit carries a `stage` field and
   `rgraph status` aggregates the five-stage row from it.
3. **Run artifacts are JSON; only the four config files are YAML.** The kit ships
   a deliberately small YAML-subset parser (no PyYAML dependency) and that parser
   should not be the one reading your evidence.
4. **Gate decisions are gate records, not an artifact.** They live in
   `run/gates/<GATE>.json` under their own schema and are not among the 21.

## Requirements

Python ≥ 3.11. Two runtime dependencies: `jsonschema` and `rich`. Nothing else.

## Licence

MIT.
