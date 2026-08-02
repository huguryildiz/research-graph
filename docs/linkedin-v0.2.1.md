# LinkedIn draft — not published

I am preparing `research-graph` v0.2.1 as an open-source public beta for
technical users working with multi-agent research workflows.

It is a provider-neutral verification layer: versioned artifact contracts,
SHA-256 provenance links, explicit gate conditions, bounded revision routes,
and measured producer/reviewer separation. It does not orchestrate agents and
does not determine whether a scientific claim is true.

This release focuses on the less glamorous work that makes a technical preview
defensible: provider and login preflight, explicit `UNVERIFIED` model status
unless a real probe is requested, terminal-only named human decisions, a
Python 3.11–3.13 matrix across Linux/macOS/Windows, clean-wheel installation,
and GitHub-tag-pinned `uv tool`/`uvx` checks.

The bundled demo is synthetic and labelled as such. The useful question is not
whether a green screen makes research correct; it is whether every handoff can
show what was checked, against which files, by whom, and with which limits.

Repository: https://github.com/huguryildiz/research-graph
