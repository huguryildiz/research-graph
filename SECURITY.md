# Security

## What this tool is not

`research-graph` is a discipline mechanism, not a security control, and the
README says so where it matters. Two limits are worth restating here because
they shape what counts as a vulnerability.

**The reviewer/producer check is not cryptographic.** A gate compares identity
strings. Anyone who writes their own `produced_by.identity` can make a run claim
whatever separation they like — and would be deceiving only themselves. Reports
that amount to "a user can lie in their own artifacts" describe the design, not a
defect.

**Digests establish integrity, not authenticity.** `content_hash` proves a body
has not changed since it was sealed. It does not prove who sealed it, and there
are no signatures. If you need authenticity, sign the run directory with
something built for it.

## What does count

Please do report:

- A tampered artifact that passes a gate it should have failed — in particular
  any way to edit a body without the staleness cascade firing.
- Command injection through `providers.yaml`, `assignment.yaml`, `graph.yaml`,
  `gates.yaml`, or an artifact. `rgraph` builds an argv list and never uses a
  shell; a way around that is a real finding.
- Path traversal that reads or writes outside the run directory or the kit root.
- Anything that makes `rgraph` transmit run contents anywhere. The only network
  call in the codebase is a HEAD request to `doi.org` under `check --online`.
- A crash that leaves a run directory in a state no command can recover.

## Reporting

Open a [security advisory](https://github.com/huguryildiz/research-graph/security/advisories/new)
rather than a public issue for anything in the list above. For everything else, a
normal issue is fine and usually faster.

Include the command, its exit code, and the run directory or config that
reproduces it. A minimal `run/` that triggers the behaviour is worth more than a
description of it.

There is no bounty, and no fixed response window — this is a single-maintainer
research tool. Expect an acknowledgement rather than a schedule.

## Supported versions

`main` is the supported version. `0.1.x` is pre-1.0: fixes land on `main` and
there are no backports.
