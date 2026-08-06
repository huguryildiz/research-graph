---
name: planning
description: Hypothesis registration, research planning and experiment design, ending in a frozen protocol.
requires: [filesystem]
units: [u03, u04, u05]
produces: [hypothesis_registry, design_protocol, frozen_protocol]
gates: [H3, T1, H4]
revision_budget: 3
---

## Role

You turn an evidence matrix into falsifiable hypotheses, a research plan, and a
protocol that is frozen before any code runs. Freezing is the point: the seeds,
the replication count, the analysis plan, the multiplicity plan and the stopping
rule are all fixed in advance, so nothing downstream can be chosen after seeing
the data. You register hypotheses you expect to fail alongside the ones you
expect to hold — a registry that only contains winners is a registry written
after the fact.

## Inputs

- `run/evidence_matrix.json` — what the literature supports and where it is silent.
- `run/kg_snapshot.json` — the claim graph and its recorded contradictions.
- `run/governance_record.json` — what is permitted.

## Outputs

### `run/hypothesis_registry.json` — schema `schemas/hypothesis_registry.schema.json`

```json
{
  "artifact_id": "hypothesis_registry",
  "version": 1,
  "produced_by": {"role": "planning", "identity": "claude-code/claude-opus-5"},
  "produced_at": "2026-07-31T09:10:00Z",
  "inputs": [{"artifact_id": "evidence_matrix", "content_hash": "sha256:<64 hex>"}],
  "content_hash": "sha256:<sha256 of the canonical JSON of body>",
  "body": {
    "hypotheses": [{
      "hypothesis_id": "h-01",
      "statement": "<what you assert>",
      "falsifiable_prediction": "<the measurement that would refute it>",
      "novelty_status": "novel | replication | extension",
      "feasibility": "high | medium | low",
      "discriminating_evidence": ["c-01"],
      "decision": "accepted | deferred | rejected"
    }]
  }
}
```

### `run/design_protocol.json` — schema `schemas/design_protocol.schema.json`

`body.objectives[]`, `body.methods[]`, `body.experiments[]` (each with
`experiment_id` `x-01`, a `hypothesis_id`, `factors[]` and `metrics[]`),
`body.resources` and `body.risks[]`.

### `run/frozen_protocol.json` — schema `schemas/frozen_protocol.schema.json`

`body` carries `frozen_at`, `approved_by`, `hypotheses[]`, `outcomes[]`,
`exclusions[]`, `analysis_plan`, `multiplicity_plan`, `stopping_rule`,
`replications`, `seeds[]`, `data_access` and `compute_authorisation`.

## Required fields

Gate T1 reads both the design and its frozen protocol. It rejects the handoff if
`design_protocol.experiments[].hypothesis_id` does not name a hypothesis whose
`decision` is `accepted`, and exposes the frozen reproduction fields to the
reviewer at the same hash-bound decision boundary. Gate H4 rejects the freeze if
`len(seeds) != replications`, or if `stopping_rule`, `multiplicity_plan` or
`analysis_plan` is empty.

## Acceptance criterion

Every experiment names an accepted hypothesis; the frozen protocol lists one seed
per replication, a stopping rule and a multiplicity plan, all recorded before
execution begins.

## Revision budget

3 attempts. When the budget is spent the gate may only block or escalate.

## Claim boundary

This role does not establish scientific correctness. It establishes that every
artifact it produces is registered, versioned and traceable to its inputs.
