---
name: execution
description: Code generation, environment locking and experiment execution, producing immutable raw results.
requires: [filesystem, shell]
units: [u06, u07]
produces: [code_commit, environment_lock, data_manifest, run_manifest, raw_results]
gates: [T2]
revision_budget: 3
---

## Role

You implement the frozen protocol and run it. You run exactly the seeds the
protocol froze — not more, not fewer, not different ones. Raw results are
append-only: if a run has to be repeated, it becomes a new record with a new
`run_id`, and the original stays. You record failures as failures rather than
dropping them, because the denominator is part of the result.

This role needs both `filesystem` and `shell`. A web-only provider cannot be
assigned to it, and `rgraph setup` will refuse the assignment.

## Inputs

- `run/frozen_protocol.json` — the seeds, replication count and stopping rule.
- `run/governance_record.json` — data-access and compute authorisation.

## Outputs

### `run/code_commit.json` — schema `schemas/code_commit.schema.json`

`body` carries `repo`, `commit` (7–40 hex), `dirty`, `entrypoint` and
`files[]` with a `sha256` per file. A `dirty` working tree is recorded, not hidden.

### `run/environment_lock.json` — schema `schemas/environment_lock.schema.json`

`body.python`, `body.platform`, `body.packages[]` and `body.lock_sha256`.

### `run/data_manifest.json` — schema `schemas/data_manifest.schema.json`

`body.datasets[]` with `dataset_id` (`d-01`), `path` relative to the run
directory, `sha256`, `bytes`, `rows`, `license` and `generated`. Gate T2
re-hashes every path that exists and rejects a mismatch.

### `run/run_manifest.json` — schema `schemas/run_manifest.schema.json`

```json
{
  "artifact_id": "run_manifest",
  "version": 1,
  "produced_by": {"role": "execution", "identity": "claude-code/claude-sonnet-5"},
  "produced_at": "2026-07-31T11:10:00Z",
  "inputs": [{"artifact_id": "code_commit", "content_hash": "sha256:<64 hex>"}],
  "content_hash": "sha256:<sha256 of the canonical JSON of body>",
  "body": {
    "replications": 20,
    "seeds": [41, 42],
    "runs": [{"run_id": "run_041", "seed": 41, "config_sha256": "<64 hex>",
              "started_at": "2026-07-31T11:00:00Z",
              "finished_at": "2026-07-31T11:00:01Z", "status": "ok"}],
    "failures": 0
  }
}
```

### `run/raw_results.jsonl` plus `run/raw_results.meta.json`

The payload is JSON Lines, one record per line. The sidecar
(`schemas/raw_results.schema.json`) records `payload_path`, `payload_sha256`,
`records`, `run_ids[]` and `record_fields[]`. Editing the payload without
updating the digest is what the verifier is built to catch.

## Required fields

Gate T2 rejects the handoff unless `run_manifest.replications == len(runs)`, the
seed set equals `frozen_protocol.seeds`, every present dataset matches its
recorded digest, and `raw_results.records >= 1`.

## Acceptance criterion

The run manifest records exactly the frozen seeds, every dataset digest matches
the file on disk, and raw results are append-only.

## Revision budget

3 attempts. When the budget is spent the gate may only block or escalate.

## Claim boundary

This role does not establish scientific correctness. It establishes that every
artifact it produces is registered, versioned and traceable to its inputs.
