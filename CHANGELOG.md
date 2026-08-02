# Changelog

Notable changes, newest first. This project is pre-1.0; until it isn't, the CLI
surface may still move.

## [Unreleased]

### Fixed

- `rgraph trace` now derives protocol-freeze status from the current, valid H4
  decision instead of the unchanged `meta.protocol` template flag. Real runs
  created as `OPEN` no longer produce a false incomplete-chain result after H4
  passes.

## [0.2.1] — 2026-08-02

Public-beta hardening for technical users: provider preflight, a shorter
empty-repository path, portable terminal behaviour, and tag-pinned release
installation checks. The release does not add orchestration or make a claim of
scientific correctness.

### Fixed — challenge decisions require an actual reviewer invocation

- **`rgraph check` is read-only for every gate.** It previously wrote challenge
  records and copied the configured reviewer identity into them even when no
  reviewer process had run. A missing challenge decision now remains
  `AWAITING`.
- **`rgraph challenge <GATE>` performs one attributable review call.** It
  launches exactly one assigned CLI, captures prompt and response logs, and
  binds their digests, argv, provider, model, exit code, invocation ID and
  current artifact hashes into the gate record. Malformed output or provider
  failure is an actionable exit `2`, with no gate record.
- **Reviewer writes are rejected.** A challenge reviewer receives a read-only
  contract, and an artifact, metadata or gate-file change during its invocation
  prevents the decision from being recorded.
- **A running producer cannot cross a decision boundary by default.** Unit
  subprocesses carry an active-invocation marker; nested `challenge`, `decide`
  and final `review` commands return control to the host. This is a workflow
  guard, not a security boundary against a process deliberately removing its
  own environment.
- Existing non-synthetic challenge records without invocation provenance must
  be re-run. The bundled synthetic fixture retains its explicit exception and
  is never described as a real provider call.
- **Unit subprocesses now leave host execution receipts.** Each accepted or
  rejected call records its provider/model assignment, argv, unique log digest,
  current input and output hashes, exit code and validation problems. A rejected
  call therefore cannot advance `status` merely because it left files behind.
- **Providers seal with the active installation.** The current Python
  environment is placed first on the provider `PATH`, and the unit prompt names
  the exact artifact-only seal command. Hand-computed `content_hash` values are
  explicitly forbidden and fail normal output validation.
- **Data-manifest sidecars are first-class bounded outputs.** A dataset below
  `run/data/` is accepted only when the manifest records its digest and byte
  count. Missing, mismatched or escaping paths fail both unit acceptance and T2.

### Added — provider and release preflight

- **`rgraph doctor`.** The command checks the effective assignment, CLI presence
  on `PATH`, non-interactive login state, role capabilities, and assignments that
  make T2 or M1 impossible to pass. Model names are `UNVERIFIED` unless
  `--probe-models` makes one small real provider call per distinct model; a
  rejection or timeout is an actionable exit `2`, not a traceback.
- **Release-install gates.** Normal CI now installs the built wheel through both
  `uv tool` and `uvx`, and its newcomer job starts from an empty Git repository.
  A tag workflow separately installs the exact GitHub tag through both paths.
- **Manual PyPI Trusted Publishing workflow.** It builds and checks the wheel and
  sdist, then requires the `pypi` GitHub environment and OIDC publisher setup.
  It is dispatch-only and is not triggered by a GitHub release.

### Fixed — portable terminal contracts

- Final `rgraph review` decisions now require a TTY even when `--outcome` and
  `--as` are supplied. The flags may preselect and name a decision for a person
  at a terminal; they no longer create a non-interactive approval path.
- The enforcement boundary is now explicit: a TTY check refuses pipes but
  cannot authenticate a person or detect software controlling a pseudo-terminal.
  Agent command policy and run-directory access remain the operator's
  responsibility.
- Windows output no longer assumes a UTF-8 console when Rich selects Unicode
  decoration, and executable/path tests assert behaviour rather than Unix mode
  bits on Windows.
- Narrow-terminal tests assert that status stays attached to its artifact rather
  than depending on one platform's exact wrapping decision.
- The human-gate CI rig allocates a real pseudo-terminal on Unix while the
  application continues to reject piped approval.

### Fixed — six ways a gate could pass while a check was not looking

An audit of the verifier against deliberately broken runs found five checks that
returned PASS on evidence they should have refused, and one ordering bug behind
them. Each is now closed with a regression test that fails without the fix.

- **`content_hash` now covers the whole artifact, not just its body.** The
  envelope — `produced_by`, `inputs[]`, `produced_at`, `version` — sat outside
  the digest, so the identity that reviewer separation rests on could be
  rewritten, and an input reference unlinking an artifact from its chain could
  be deleted, with every recorded hash still agreeing. This changes every
  digest: run `rgraph seal` once on an existing run.
- **Reviewer separation reads every artifact a unit produced.** It stopped at
  the first entry of `produces`, so on M1 (`manuscript`, `claim_evidence_map`)
  and T2 (`run_manifest`, `raw_results`) the reviewer could author the second
  artifact — on M1, the claim–evidence map itself — and the gate still passed.
  A gate is now reported at the weakest separation level across the unit.
- **An unknown check name in `gates.yaml` fails at load.** `evaluate_gate` skips
  a name it does not recognise, so one dropped letter silently disabled that
  gate's content check while the gate reported PASS, and neither
  `check --static` nor the suite noticed.
- **`meta.json` carries its own digest.** It holds the revision budget, so an
  exhausted gate could be reopened by editing `used` back to zero. Editing it by
  hand is now a `META EDITED AFTER HASHING` finding; `rgraph seal` stamps it.
- **`rgraph seal` converges in one pass.** `figure_registry` sat after
  `claim_evidence_map` in `ARTIFACTS`, which consumes it, so a single pass
  sealed the consumer against a digest its producer had not taken yet.
- **M1 checks that the manuscript and the evidence map name the same claims.** A
  section could cite a claim the map had never registered, and a mapped claim
  could appear in no section at all.

### Documented

- **What the verifier cannot see in a manuscript.** It reads the artifact
  registry, not the prose, so a number quoted from raw data but never registered
  as an estimate is outside every gate. `README.md` now says so and names the
  place the shipped example does it.

### Added

- **The first-run journey no longer requires hand-written JSON or internal
  IDs.** In a terminal, `rgraph init` now asks a short set of plain-language
  study and governance questions, previews the answer, and writes three valid,
  sealed setup files. `--from FILE` provides the equivalent JSON/YAML automation
  path and `--edit` safely updates an existing run without deleting later work.
  `setup` uses role/provider/model menus, while `decide`, `revise`, and `trace`
  offer contextual menus when their IDs are omitted. `status` ends with one
  recommended command; `next` and `review` use explained numbered decisions.
  Explicit flags remain available for non-interactive operation.
- **`next` now enforces the graph it displays.** It cannot run a unit before its
  upstream gate passes, cannot use `--unit` to jump over unresolved work, and
  stops at each checkpoint with the correct `check`, `decide`, or `revise`
  action. Intermediate units return to `status`; they no longer incorrectly
  tell users to check a stage gate whose remaining inputs do not exist yet.
- **Release now respects unresolved gates.** `rgraph review --outcome release`
  refuses to write a release decision while any required gate is not passed;
  an EOF no longer silently records `stop` as if a human chose it.

- **`rgraph setup` asks which model takes which role.** The model for each role
  was a constant in `setup.py`, applied per-role only for `claude-code`, and the
  only way to change one was to open `assignment.yaml` by hand — which the README
  did not mention. `setup` now walks the six roles with the proposal as the
  default and accepts any `provider/model` the registry can name, or a bare model
  name to keep the CLI. A provider whose capabilities cannot carry the role is
  refused on the spot, and the separation level is recomputed from the choice.
  `--yes` and a non-terminal stdin keep the old non-interactive behaviour.
- **`setup` reports CLIs on `PATH` that `providers.yaml` does not describe.**
  Detection only ever answered "which of the providers I know about are
  installed". Naming the rest is not endorsing them: `rgraph` invents no call
  form, so an unregistered CLI is reported and left for you to describe.
- **A role can be given a reasoning depth.** `assignment.yaml` takes an optional
  `effort`, and `setup` accepts it as an `@effort` suffix — `@xhigh` on its own
  changes the depth and nothing else. `providers.yaml` says where the flags go
  with an `{effort_argv}` slot, which expands to nothing when no effort is
  asked for, so every existing invocation is byte-for-byte what it was. Effort
  stays out of the identity: a gate demanding separation wants a second opinion,
  and the same model thinking longer is not one. An effort named for a provider
  that has nowhere to put it, or one outside the levels that provider lists, is
  refused at load rather than silently dropped.
- **`sakana` is in the registry.** Fugu is not a CLI of its own; it is a model
  provider reached through codex, so the entry calls `codex exec -p fugu` and
  carries its own identity prefix. Draft entries for `qwen`, `kimi` and
  `deepseek` are marked as such — their call forms come from documentation, not
  from a machine.

### Fixed

- **`setup` reported two things it had not established.** `NOT INSTALLED` was a
  claim about the machine that `shutil.which` cannot make: it establishes only
  that the CLI is absent from this process's PATH, and both `claude` and `codex`
  routinely live in directories (`~/.local/bin`, `~/.npm-global/bin`) that reach
  the PATH through shell startup. A missed lookup now says `NOT ON PATH — found
  at …` when the binary is sitting in one of the conventional install
  directories, `NOT FOUND` only when it is nowhere, and the screen explains that
  an absolute path has to go in both `invoke` and `exec_argv[0]`. Separately, a
  `login_check` that timed out or would not start was reported as `FOUND (not
  logged in)`; a question that went unanswered is now `FOUND (login unknown)`.
  `which` still decides whether a provider is usable — `Popen` resolves the same
  PATH — so the search only ever explains a miss, never overrides it. A provider
  that was found now names the copy that answered, which is how two installs of
  one CLI on a single PATH stop being invisible, and how `sakana` shows on screen
  that it borrows codex's binary rather than shipping one.
- **claude-code's login check tested nothing.** It ran `claude --version`, which
  exits 0 whether or not you are signed in, so `FOUND (not logged in)` could
  never appear for that provider and the check only repeated what `which` had
  already answered. It now runs `claude auth status`.
- **Half the model identifiers in this repository were not real.** `claude`
  rejects `sonnet-5`, `opus-5`, `fable-5` and `haiku-4.5`; it wants
  `claude-sonnet-5` and the like. Codex has no `gpt-5.6` at all — only
  `gpt-5.6-sol`, `-terra` and `-luna`. Those strings were the defaults in
  `setup.py`, the whole of `assignment.example.yaml`, the examples in every role
  contract, and the call forms README claimed had been "run against the installed
  CLIs", so `rgraph setup --yes` wrote an assignment that failed on first
  invocation. All of them are corrected and the three call forms in README were
  re-run on 2026-08-02. The identities recorded inside `example-run/` are left
  alone: that fixture is a record of what was produced, and its README now says
  why the strings in it do not match.

- **A retired human gate had no move left.** Editing an artifact after its gate
  passed, then resealing, put `check` and `revise` at odds: `check` reported
  `STALE` and printed `Run next: rgraph revise H1`, while `revise` read the
  frozen gate record, saw `pass`, and answered `gate H1 passed; there is nothing
  to revise`. A newcomer following the screens reached a dead end in the exact
  scenario the README describes. `check` now sends a stale human gate to
  `rgraph decide`, and `revise` names the cause and the command that reopens the
  gate instead of denying the situation.
- **`rgraph status` reported a retired decision as passed.** It read gate records
  without rechecking the digests those records were written against, so it
  printed `Last gate H1 PASS` and an `APPROVED` human row while `check` was
  calling the same gate `STALE` in the same directory. Both now recompute.
- **`rgraph decide` accepted its answers from a pipe.** `yes y | rgraph decide
  H1` opened a human gate with nobody reading anything, which is the one thing
  the command exists to prevent. A stdin that is not a terminal is now refused;
  `rgraph setup` already did this, and human gates get no `--yes` escape.
- **`architecture.html` disagreed with itself.** The mobile "Required audit
  trail" listed 19 artifacts against the plate's own registry of 20:
  `design_protocol` was missing from the prose while the same file's T1 contract
  read it as an input. `tests/test_diagram_matches_graph.py` now diffs the phone
  view against the registry, not only the registry against the kit.

## [0.2.0] — 2026-08-02

Human gates stop opening on their own, and the example run's statistics are
computed rather than asserted.

### Added

- **`tests/test_diagram_matches_graph.py`** — `architecture.html` is drawn by
  hand rather than rendered from `graph.yaml`, so the two could drift unchecked
  in a repository whose first static check is "delete the fake edge". The gate
  set, every gate's inputs, the artifact registry and every typed revision
  reason on the plate are now diffed against the configuration the CLI executes.
  The one deliberate divergence, `kg_snapshot`, is named in the test.
- **`rgraph decide <GATE>`, and human gates that need a human.** A human gate
  used to pass on file presence alone, and the record it wrote named a *model*
  as the person who decided it — `decided_by: {role: human, identity:
  codex/gpt-5.6}` — while nobody had been asked anything. Human gates now stay
  `AWAITING` until somebody answers them. `rgraph decide` puts each claim the
  gate declares it `proves` to a person one at a time, and records the answers
  and who gave them under `attestation`. The questions are not new: they are the
  `proves` entries that were already in `gates.yaml` and had never been read.

### Changed

- **Breaking: a human gate no longer passes on file presence alone.** It stays
  `AWAITING` until somebody answers it, so a pipeline that ran `rgraph check H1`
  and expected `0` now needs `rgraph decide H1` in front of it. The four human
  gates are H1, H2, H3 and H4; challenge gates are unaffected.
- **`check` no longer writes a human gate's record.** A command that can write
  its own attestation can forge one, so the two verbs are split: `decide`
  decides, `check` verifies. The shipped `example-run/` is now read-only to
  every writing command rather than to `check` alone — `rgraph review` had been
  quietly creating `release_manifest.json` and `gates/FINAL.json` inside it.
- **An attestation is pinned to what was on the table.** It covers the digests
  that existed when it was given, so editing an artifact afterwards retires it.
  Resealing repairs the hash; it cannot repair the reading, so the gate asks
  again.

### Fixed

- **A multiplicity correction that was named but never computed.** The example
  run's `statistical_report.json` declared Holm, and the manuscript claimed the
  intervals survived it, while no p-value existed anywhere to correct. The
  procedure is now computed: `example-run/code/analyze.py` derives every number
  in the report from `raw_results.jsonl`, including an exact two-sided sign-flip
  permutation test over all 2^20 assignments and Holm across the three
  registered low-SNR points. `statistical_report.schema.json` gained optional
  `p_value` and `p_adjusted` fields, and the downstream chain was re-sealed.
- **A tier that did not exist.** The README listed a fourth running tier as
  "API keys, via LiteLLM". No API-backed provider kind exists in
  `providers.yaml`, no HTTP client exists in `rgraph`, and LiteLLM appeared
  nowhere but that sentence. Tier 3 is now marked *not implemented* and the
  README says plainly that no end-to-end multi-agent run has been evidenced.
- **An over-broad claim about the word "independent".** The README said `rgraph`
  never prints it; the reference diagram and `graph.yaml` both used it. The
  claim is now scoped to the CLI, `tests/test_separation.py` holds the CLI to
  it, `graph.yaml` calls the node a *separate* review role, and the diagram's
  usage is named as the deliberate exception it is.
- **A README that under-described its own example.** The estimator the example
  labels *learned* is a tuned delay-domain filter, not a neural network. The
  code and the manuscript always said so; the README now does too.
- **A data manifest that sealed the wrong file.** `example-run/data/channels.jsonl`
  was written by a `--channels` path seeded on the seed alone, while the
  benchmark draws its channel from `seed*1000 + snr_db`. The committed file
  therefore held twenty channels no run ever saw, and `data_manifest.json`
  sealed them as the study's dataset — a true digest of an irrelevant file,
  which gate T2 passed because a digest check cannot tell the difference. The
  two paths now share a generator, the file holds the 100 channels the runs
  actually drew, and `tests/test_example_statistics.py` redraws every one of
  them.
- **`rgraph seal` left payload artifacts stale.** `manuscript` and `raw_results`
  keep their bodies in a companion file and carry only its digest. `seal` hashed
  the body without refreshing that digest first, so editing the manuscript by
  hand and sealing produced a true hash of a stale pointer: the gate stayed red
  and `seal` reported "already sealed". It now re-digests the payload first.
- **The landing page listed three config files, not four.** `gates.yaml` was
  missing from `index.html` while the README described all four.
- **`rgraph setup` wrote inside the installed package.** Off a checkout, the kit
  root is the packaged copy, so the assignment landed in `site-packages` — where
  the user could not see it and the next `uv tool upgrade` would delete it. It
  now writes `~/.config/rgraph/assignment.yaml` (`$XDG_CONFIG_HOME` honoured) as
  the machine default, and `rgraph setup --here` writes `./assignment.yaml` for a
  single study. Every command reads the study copy first, then the machine
  default, then the kit root.

## [0.1.0] — 2026-08-02

First public release. The verifier, the reference graph, the nine gates and a
worked example that exercises all of them.

### Added

- **`rgraph` CLI, ten commands** — `demo`, `setup`, `init`, `status`, `next`,
  `seal`, `check`, `revise`, `trace`, `review`. Global flags are accepted on
  either side of the command name.
- **Layer 1, static** — `rgraph check --static` lints the graph for type
  mismatches, cycles outside `return` edges, unbounded correction loops,
  unreachable gates and dead nodes.
- **Layer 2, dynamic** — existence, JSON Schema, provenance, staleness, reviewer
  separation and the revision budget over a `run/` directory.
- **Integrity that recomputes** — every artifact is checked against its own
  `content_hash` on read, so a body edited without resealing invalidates its
  gate and everything downstream.
- **`rgraph init` and `rgraph seal`** — a run directory with the two artifacts no
  agent produces, and the canonical SHA-256 nobody types by hand. `init`, `seal`,
  `check H1` reaches a green gate from nothing.
- **Separation levels** — `CONTEXT ONLY`, `SEPARATE MODEL`, `SEPARATE PROVIDER`,
  always printed with the caveat when the level is weak. The word "independent"
  is never used.
- **21 artifact schemas** plus the gate record and envelope schemas.
- **Six role contracts** in `roles/`, shared by the Claude Code and Codex plugin
  manifests without being copied.
- **`example-run/`** — a synthetic-provenance fixture with real data, real
  statistics and four Crossref-resolvable DOIs, reporting an honest negative.
- **Packaged runtime** — the graph, gates, schemas, roles and both example runs
  ship inside the wheel, so `pip install` works away from a checkout.
- **CI** — tests on Python 3.11–3.13 across Linux, macOS and Windows; a wheel
  installed into a clean environment and run from outside the repository; and the
  newcomer command sequence itself.

### Known limits

- The reviewer/producer check compares strings. It is a discipline mechanism, not
  a cryptographic one — see [SECURITY.md](SECURITY.md).
- `rgraph` judges provenance, never scientific correctness. Every gate screen
  says so, passing or failing.
- Offline by default. `check E1 --online` is the only command that touches the
  network; without one it reports which DOIs it could not reach instead of
  calling them fabricated.

[Unreleased]: https://github.com/huguryildiz/research-graph/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/huguryildiz/research-graph/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/huguryildiz/research-graph/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/huguryildiz/research-graph/releases/tag/v0.1.0
