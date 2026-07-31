# template-run

Copy this directory to `run/`, edit `meta.json`, then start with `rgraph next`.

- Artifacts land beside `meta.json`, one JSON file per artifact id.
- Two artifacts carry a payload plus a sidecar: `manuscript.md` with
  `manuscript.meta.json`, and `raw_results.jsonl` with `raw_results.meta.json`.
- Gate records land in `gates/`. Provider logs land in `logs/`.
- Never edit a file after the gate that read it has passed. If you must, the
  staleness check will invalidate that gate and everything downstream, which is
  the intended behaviour, not a bug.
