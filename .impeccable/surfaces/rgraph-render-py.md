---
version: 1
slug: "rgraph-render-py"
primary_target: "rgraph/render.py"
related_targets: ["rgraph/banner.py","rgraph/cli.py"]
---

## Scope and mode

The `rgraph` terminal interface is an Operate surface spanning the bare-command
home screen, setup and init, status, next, gate and review flows, trace and
revision output, interactive prompts, and narrow-terminal fallbacks.

## Audience, job, and constraints

Researchers and research software developers must identify the active run,
read verification state, and copy the next safe command within seconds. Output
must stay meaningful without color, at 40 columns, in CI logs, and through
`--no-banner`. Gate scope, synthetic-fixture disclosure, and scientific-
correctness limitations remain visible.

## Direction and memorable moment

The direction is a release-proof ledger: wide, banner-enabled openings use the
supplied white-and-emerald tiled circuit wordmark, while narrow terminals keep
a one-line identity. Quiet section labels establish scan order, semantic status
words carry state, and one emerald shell command closes each operational screen.
The memorable moment is the transition from the strong brand mark directly
into a single `NEXT ACTION`.

## Interaction boundary

Interactive prompts adopt the same hierarchy without changing their question
meaning, defaults, accepted shortcuts, cancellation behavior, or mutation
safeguards.
