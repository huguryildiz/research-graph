## What this changes

## Why

## How it was verified

```
$ pytest -q
```

If the change touches a gate, a check, or the hash chain, say which test would
have failed before it and passes after. A behavioural test is worth more here
than a unit one — `tests/test_onboarding.py` is the pattern.

## House rules touched?

- [ ] Digests are still recomputed, never trusted from the file
- [ ] Every gate screen still prints `Scientific correctness was not determined`
- [ ] Separation is still printed as a level, never as the word "independent"
- [ ] The committed `example-run/` is unchanged, or changed deliberately and resealed
- [ ] A new provider needed no Python (`providers.yaml` only)

Details in [CONTRIBUTING.md](../CONTRIBUTING.md).
