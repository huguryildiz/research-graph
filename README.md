# research-graph

**Graph engineering, verified** — the tool that enforces the rules instead of stating them.

A contract-gated verification layer for agentic research pipelines. It reads a run
directory of versioned artifacts, validates every one against a JSON Schema, walks the
provenance hash chain, and returns an exit code.

```bash
git clone https://github.com/huguryildiz/research-graph
cd research-graph
pip install -e .
rgraph demo
```

> This README is the v0.1 stub. The full text lands with Task 23 of
> `docs/superpowers/plans/2026-07-31-research-graph-v0.1.md`.

## Claim boundary

research-graph **does not judge scientific correctness.** It establishes that every
artifact behind a claim is registered, versioned and traceable to its inputs. Every gate
output repeats this on screen.
