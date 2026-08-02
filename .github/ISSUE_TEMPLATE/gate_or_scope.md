---
name: A gate, a check, or the scope
about: Propose a change to what a gate requires, or ask where the boundary is
labels: design
---

## Which gate or check

## What it does today

## What you think it should do instead

## Why the current behaviour is wrong rather than inconvenient

A gate that fails your run is often working. The interesting cases are the other
two: a gate that passes something it should catch, or a gate whose requirement
does not follow from what it claims to prove.

## Scope check

`research-graph` verifies provenance. It does not judge scientific correctness,
orchestrate anything, or call a model API. If your proposal needs one of those,
say so — it may still be right, but it is a different project boundary and worth
naming up front.
