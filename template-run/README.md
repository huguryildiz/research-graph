# template-run

`rgraph init` copies this directory to `run/`, asks the study and governance
questions in plain language, and adds the two artifacts no agent produces —
`problem_spec.json` and `governance_record.json`, both of which gate H1 needs.
It also updates `meta.json` and seals the artifacts. Run `rgraph decide` next.

For automation use `rgraph init --from study.yaml`. Copying the template by hand
still works, but then H1 has nothing to read until those two files are supplied.

- Artifacts land beside `meta.json`, one JSON file per artifact id.
- Two artifacts carry a payload plus a sidecar: `manuscript.md` with
  `manuscript.meta.json`, and `raw_results.jsonl` with `raw_results.meta.json`.
- Gate records land in `gates/`. Provider logs land in `logs/`.
- Never edit a file after the gate that read it has passed. If you must, the
  staleness check will invalidate that gate and everything downstream, which is
  the intended behaviour, not a bug.
