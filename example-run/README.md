# example-run — what is real here, and what is not

This directory is a **fixture**. `meta.json` declares `"provenance": "synthetic"`, and
every `rgraph` screen that reads this run prints that fact before anything else. A kit
whose subject is honest provenance does not get to be vague about its own.

## Real

- **The experiment.** [`code/estimator_bench.py`](code/estimator_bench.py) runs in about
  0.3 s with no dependencies and is deterministic per seed. `raw_results.jsonl` is its
  actual output: 300 records, 20 seeds × 5 SNR points × 3 estimators.
- **The statistics.** Every number in `statistical_report.json` was computed from those
  records — paired per-seed differences, percentile bootstrap, 5000 draws, seed 20260731.
  Re-derive them yourself from `raw_results.jsonl`; they will match.
- **The citations.** All four DOIs were resolved against the Crossref API and verified by
  direct lookup. `rgraph check E1 --online` resolves them live and exits 0.
- **The hash chain.** Every `content_hash` is the real SHA-256 of its body, and every
  `inputs[]` entry really points at the upstream hash. Edit one byte anywhere and the
  staleness cascade fires — that is what scenario 3 of `rgraph demo` shows.
- **The finding.** The refutation of hypothesis h-02 is what the data says.

## Not real

- **No provider ran.** `produced_by.identity` fields name `claude-code/sonnet-5`,
  `codex/gpt-5.6` and so on because that is what `assignment.example.yaml` configures,
  but no model was ever invoked. The artifacts were authored.
- **No reviewer decided anything.** The gate records under `gates/` were written by
  `rgraph check`, which evaluates the files. `grok/grok-5` did not read the manuscript.
  The `separate_provider` levels are what the recorded identities *imply*, not an audit
  that took place.
- **The human attestations were written, not answered.** `gates/H1.json` through
  `H4.json` carry an `attestation` naming the author, because the author did write
  and freeze these files. Nobody sat at the `rgraph decide` prompt and answered the
  questions one at a time, which is what the same record means in a real run.
- **`reproduction_report.json` did not re-execute anything.** It records digests that
  match because they are the same file.
- **The timestamps are synthetic.** They order the units plausibly; they are not clock
  readings.

## Why keep it anyway

A verifier needs a corpus to verify. This one exercises all nine gates, all 21 artifact
schemas, the staleness cascade and the trace chain, and it does so with real data and real
citations so the checks have something true to bite on. What it cannot demonstrate is a
real multi-agent run — that requires running one, which is what
[`template-run/`](../template-run/) is for.

To produce a run whose provenance is recorded rather than authored: copy `template-run/`
to `run/`, set `"provenance": "recorded"`, and drive it with `rgraph next`.

## The finding, stated plainly

Registered hypothesis **h-01** — a learned estimator lowers MSE below scalar-Wiener LMMSE
at SNR ≤ 0 dB — is **supported**. All three intervals exclude zero.

Registered hypothesis **h-02** — the advantage is largest at the lowest SNR — is
**refuted by its own data**: 2.09 dB at −10 dB against 8.99 dB at +10 dB. The manuscript
reports it, `verification_report.json` grades it `major`, and `claim_evidence_map.json`
marks the trend claim as an `extrapolation`.
