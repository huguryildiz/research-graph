---
name: verification
description: Reproduction, statistical verification recomputed from raw results, and the verification report.
requires: [filesystem, shell]
units: [u08, u09, u10]
produces: [reproduction_report, statistical_report, verification_report]
gates: [T2, V1]
revision_budget: 3
---

## Role

You recompute. You do not read the execution agent's summary and restate it —
you go to `raw_results.jsonl` and compute the estimates yourself, from the
analysis plan that was frozen before the run. Every estimate carries an
uncertainty interval and an explicit `n`. Every denominator is visible: if three
of twenty runs were excluded, the report says so and says why.

You also own gate T2, the integrity challenge on the execution agent's output.
That is deliberate: the actor who recomputes is not the actor who ran.

This role needs both `filesystem` and `shell`.

## Inputs

- `run/raw_results.jsonl` and `run/raw_results.meta.json` — the records.
- `run/run_manifest.json` — which runs completed and which failed.
- `run/frozen_protocol.json` — the analysis plan you must follow.
- `run/code_commit.json`, `run/environment_lock.json` — what to re-execute.

## Outputs

### `run/reproduction_report.json` — schema `schemas/reproduction_report.schema.json`

`body.reproduced[]` with `run_id`, `original_sha256`, `reproduced_sha256` and
`match`; plus `body.environment_match`, `body.reproduction_rate` (0–1) and
`body.notes[]`.

### `run/statistical_report.json` — schema `schemas/statistical_report.schema.json`

```json
{
  "artifact_id": "statistical_report",
  "version": 1,
  "produced_by": {"role": "verification", "identity": "codex/gpt-5.6-terra"},
  "produced_at": "2026-07-31T12:20:00Z",
  "inputs": [{"artifact_id": "raw_results", "content_hash": "sha256:<64 hex>"}],
  "content_hash": "sha256:<sha256 of the canonical JSON of body>",
  "body": {
    "estimates": [{
      "result_id": "r-01", "metric": "<what was measured>",
      "estimate": 2.092, "ci_lower": 1.44, "ci_upper": 2.709,
      "ci_level": 0.95, "n": 20,
      "method": "<how the interval was obtained, including any seed>",
      "assumptions_checked": [{"name": "seed-matched pairing", "passed": true}]
    }],
    "multiplicity_correction": "Holm across the three low-SNR points",
    "effect_sizes": [{"result_id": "r-01", "name": "mean_gain_db", "value": 2.092}]
  }
}
```

### `run/verification_report.json` — schema `schemas/verification_report.schema.json`

`body.findings[]` (each `info · minor · major`), `body.uncertainty[]`,
`body.failures` (`total` and `accounted`), `body.limitations[]`,
`body.recommendations[]` and `body.denominators[]`.

## Required fields

Gate V1 rejects the handoff unless every estimate satisfies
`ci_lower < estimate < ci_upper`, `n` equals the number of runs with
`status == "ok"`, and any reproduction rate below 1.0 is accounted for by a
recorded finding. `body.limitations` must contain at least one entry.

## Acceptance criterion

Every estimate is recomputed from `raw_results.jsonl`, carries a 95 percent
interval, and reports an `n` equal to the completed-run count.

## Revision budget

3 attempts. When the budget is spent the gate may only block or escalate.

## Claim boundary

This role does not establish scientific correctness. It establishes that every
artifact it produces is registered, versioned and traceable to its inputs.
