---
name: Bug report
about: A command did something other than what it says it does
labels: bug
---

## What you ran

```
$ rgraph ...
```

## Exit code

Exit codes are a contract: `0` pass, `1` a gate or lint failed, `2` usage or
configuration error. A traceback is always a bug, whatever caused it.

## What it printed

```
paste the output
```

## What you expected instead

## Environment

- `rgraph --version`:
- `python3 --version`:
- OS:
- Installed with: `pip install -e .` / wheel / other

## The run, if there was one

If a gate behaved wrongly, the run directory is worth more than a description of
it. `run/meta.json` plus the artifacts the gate reads is usually enough. Say so
if it contains anything you cannot share.
