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

If a completed campaign is returned after its results were visible, do not
silently overwrite it or reuse its run IDs. The host must preserve the rejected
campaign and obtain any human re-attestation required by the frozen protocol;
the replacement campaign uses a distinct run-ID prefix and records its own
actual invocation/configuration evidence.

For a replacement campaign, u06 must expose that distinct prefix as an explicit
entrypoint argument (for example `--run-prefix t2r1`) rather than hard-coding or
post-processing it. Verify one output record with the replacement prefix before
sealing. u07 must place that exact argument in its hash-bound configuration and
invocation; every emitted `run_id` must differ from the archived campaign IDs.
Before a repeated u07 invocation, the host archives the current campaign and
binds all of its run IDs into signed run metadata. Reusing even one retired ID
causes host rejection; choose a new explicit prefix by inspecting the retained
campaign history, not by assuming that an earlier prefix is still available.
For a provenance-only correction, the host may explicitly invoke u07 in
payload-preservation mode. In that mode do not execute the experiment or change
the payload, artifact bodies, run IDs, run records, configurations, or argv;
only repair the required envelope input links, set both envelopes' `produced_at`
to their actual current UTC production instant, and reseal both envelopes.

This role needs both `filesystem` and `shell`. A web-only provider cannot be
assigned to it, and `rgraph setup` will refuse the assignment.

## Inputs

- `run/frozen_protocol.json` — the seeds, replication count and stopping rule.
- `run/governance_record.json` — data-access and compute authorisation.

## Outputs

### `run/code_commit.json` — schema `schemas/code_commit.schema.json`

Write version 2. `body` carries `repo`, a full 40-hex `commit`, `dirty: false`,
`entrypoint`, `bundle_path`, `bundle_sha256`, and `files[]` with the run-side
`path`, committed `repo_path`, and `sha256` per file. Source sidecars and the
host-provided Git bundle stay below `run/code/`; the entrypoint must be listed.
`bundle_sha256`, envelope `content_hash`, and `inputs[].content_hash` use the
algorithm-labelled `sha256:<64 lowercase hex>` form. Existing `files[].sha256`
and `lock_sha256` fields use exactly 64 lowercase hex characters without that
prefix.
Do not alter that bundle, initialise a nested repository, create a virtual
environment or install packages inside the run directory. The retained bundle
must contain the clean commit and the exact executed bytes, so another user can
verify code provenance offline. Do not commit or push user work. Record every
envelope's `produced_at` as the actual current UTC instant with a `Z` suffix;
never label local wall-clock time as UTC.

### `run/environment_lock.json` — schema `schemas/environment_lock.schema.json`

Write version 2. `body` carries `python`, `platform`, `packages[]`, `lock_path`
and `lock_sha256`. Write the immutable dependency-lock material below
`run/environment/`; `lock_path` names that relative file and `lock_sha256`
must match its bytes. A digest with no retained lock payload is not a lock.

### `run/data_manifest.json` — schema `schemas/data_manifest.schema.json`

`body.datasets[]` with `dataset_id` (`d-01`), `path` relative to the run
directory, `sha256`, `bytes`, `rows`, `license` and `generated`. Gate T2
requires every path to stay below `run/data/`, requires the file to exist, and
rejects digest or byte-count mismatches.

### `run/run_manifest.json` — schema `schemas/run_manifest.schema.json`

Write version 2. Put every immutable execution configuration below
`run/config/`. `body.configurations[]` binds each `config_id`, relative `path`,
file `sha256`, and the exact `argv` used. Every `runs[].config_sha256` must equal
one of those configuration hashes; an opaque digest with no snapshot and no
invocation is not reproducible. The envelope `inputs[]` must bind all three u06
outputs used for execution: `code_commit`, `environment_lock`, and
`data_manifest`. Binding only the source does not establish which environment
or declared dataset state produced the runs.

```json
{
  "artifact_id": "run_manifest",
  "version": 2,
  "produced_by": {"role": "execution", "identity": "claude-code/claude-sonnet-5"},
  "produced_at": "2026-07-31T11:10:00Z",
  "inputs": [
    {"artifact_id": "code_commit", "content_hash": "sha256:<64 hex>"},
    {"artifact_id": "environment_lock", "content_hash": "sha256:<64 hex>"},
    {"artifact_id": "data_manifest", "content_hash": "sha256:<64 hex>"}
  ],
  "content_hash": "sha256:<sha256 of the canonical JSON of body>",
  "body": {
    "replications": 20,
    "seeds": [41, 42],
    "configurations": [{
      "config_id": "evaluation",
      "path": "config/evaluation.json",
      "sha256": "<64 hex>",
      "argv": ["python", "code/estimator_bench.py", "--config", "config/evaluation.json"]
    }],
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
The digest-bound `code_commit.body.entrypoint` must directly emit all declared
`record_fields`, including `run_id`; do not add or rewrite fields through an
unrecorded post-processing script.

For u06, inspect one entrypoint output record before sealing `code_commit` and
verify that `run_id` is already present. If an existing source omits it, correct
the source in u06 and update its recorded digest. It is not sufficient to defer
that field to u07, because u07 may not alter code or use an unrecorded helper.

## Required fields

Gate T2 rejects the handoff unless `run_manifest.replications == len(runs)`, the
seed set equals `frozen_protocol.seeds`, every present dataset matches its
recorded digest, the v2 environment/configuration sidecars match their recorded
digests, every run configuration resolves to an exact invocation, and
`raw_results.records >= 1`.

## Acceptance criterion

The run manifest records exactly the frozen seeds, every dataset digest matches
the file on disk, and raw results are append-only.

## Revision budget

3 attempts. When the budget is spent the gate may only block or escalate.

## Claim boundary

This role does not establish scientific correctness. It establishes that every
artifact it produces is registered, versioned and traceable to its inputs.
