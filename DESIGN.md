---
name: research-graph
description: A release-proof ledger for contract-gated research verification.
colors:
  verification-emerald: "#6ee7b7"
  command-emerald: "#4fa98b"
  revision-pink: "#f472b6"
  ledger-slate: "#94a3b8"
  main-text: "#e5e7eb"
  body-text: "#d1d5db"
  muted-text: "#8a8a8a"
  status-pass: "green"
  status-fail: "red"
  status-caution: "yellow"
  status-ready: "cyan"
  wordmark: "white"
---

# Design System: research-graph Terminal

## Overview

**Creative North Star: "The Release-Proof Ledger"**

The terminal interface behaves like an engineering release record: traceable
and arranged around decisions. On wide, banner-enabled openings, a tiled
white-and-emerald circuit wordmark makes the identity explicit. Quiet section
labels then establish a stable reading order, while exact status words and one
paste-ready next command carry the operational weight.

The interface is deliberately flat and native to the user's terminal. It does
not simulate a graphical dashboard, cover the screen with boxes, or turn the
brand into a splash screen.

**Key Characteristics:**

- Full cell-grid wordmark only on wide, banner-enabled openings
- State before decoration
- One primary next action per operational screen
- Exact meaning without color
- Stable hierarchy from 40 columns upward

## Colors

The palette is restrained: a cool neutral hierarchy carries content while
color is reserved for verification, caution, revision, and action.

### Primary

- **Verification Emerald:** Identifies the verification diamond.
- **Command Emerald:** Identifies the single shell command the user should run
  next and detected providers that are ready to invoke.

### Secondary

- **Revision Pink:** Marks the bounded return path in the wordmark; it is not a
  general-purpose accent.
- **Ledger Slate:** Carries section labels and supporting structure without
  competing with content.

### Tertiary

- **Semantic Status Colors:** Pass, fail, caution, and ready colors reinforce
  the literal `PASS`, `FAIL`, `CAVEAT`, and `READY` words.

### Neutral

- **Main Text:** Near-white (`#e5e7eb`) carries current objects and primary
  values.
- **Body Text:** Cool light gray (`#d1d5db`) carries normal operational copy.
- **Muted Text:** Neutral gray (`#8a8a8a`) carries metadata, caveats, and prompt
  syntax. The wordmark remains white.

**The Meaning Survives Color Rule.** Removing ANSI color must leave every
status, warning, relationship, and next action unambiguous.

## Typography

The interface inherits the user's terminal monospace face and does not impose a
font. Weight and the main/body/muted neutral ladder distinguish the product
wordmark, current objects, ordinary copy, metadata, state words, and
paste-ready commands.

Section labels are concise uppercase operational nouns. Commands retain shell
case and syntax. Paragraphs use sentence case and avoid promotional language.

**The Native Terminal Rule.** Monospace is the medium, not a costume: hierarchy
comes from wording, whitespace, alignment, and sparing weight changes.

## Layout

Screens follow the same scan order: identity or caveat, current object,
pipeline or evidence, compact run state, then the next action. Related lines
stay tight; distinct sections receive one blank line. Section labels stay on
the left edge while their values, descriptions, and actions share a four-cell
content indent.

Wide status screens use a five-column pipeline. Below 68 columns, the pipeline
becomes a vertical sequence whose gate and human-review rows remain nested
under their stage. All prose uses hanging indentation. Paste-ready commands
wrap with shell continuation characters when they exceed the available width.

Regular screens target 80 columns and must remain intact at 40 columns. The
banner collapses from the full cell-grid identity to a one-line verification
diamond and wordmark below 64 columns.

## Elevation & Depth

The system has no shadows, simulated panels, gradients, or terminal background
fills. Depth is structural: indentation expresses ownership, blank space
separates decisions, and dim text recedes behind current state and action.

**The Flat Ledger Rule.** Add hierarchy by grouping and semantic emphasis, not
by drawing another container.

## Shapes

The verification diamond (`◆`) is the signature terminal shape. Filled circles
and thin horizontal strokes form the provenance spine; the return hook (`↺`)
signals bounded revision. Thin rules divide result headers from evidence.
Brackets around status words remain the canonical state marker in lists.

## Components

### Wordmark

The full wordmark uses white `RESEARCH` and emerald `GRAPH` cell-grid lettering,
followed by the provenance/revision spine and factual tagline. The compact form
is one verification diamond plus `research-graph`.

### Section label

A short uppercase phrase in ledger slate begins a new operational group. It is
never placed above a group that already has a stronger gate or scenario header.

### Status marker

List states use `[STATUS] Label`. Pipeline summaries may align the same literal
status word in a column. Color reinforces the word and never substitutes for
it.

### Primary command

The next safe shell action begins with `$`, uses verification emerald, and is
the only primary command in its section. Long commands wrap with `\` and a
stable continuation indent.

### Body row

Labels and values share the four-cell content indent. Metadata labels use the
muted neutral; values use body or main text according to importance. Wrapped
values hang under the value column.

### Interactive prompt

Interactive menus use the same slate section label, four-cell rows, main-text
question, muted default or shortcut hint, and explicit punctuation. Prompt
styling never changes defaults, accepted shortcuts, cancellation, or mutation
safeguards.

### Gate result header

The gate identity and title lead; the literal outcome aligns to the right when
space permits. A thin rule separates the verdict from findings. Every gate
result retains the scientific-correctness limitation.

## Do's and Don'ts

### Do:

- **Do** lead operational screens with current state and end with one next
  action.
- **Do** preserve hanging indentation for every wrapped finding, caveat, and
  command.
- **Do** test both 80-column and 40-column output with `NO_COLOR=1`.
- **Do** keep `PASS`, `FAIL`, `WAIT`, `STALE`, `BLOCKED`, and `CAVEAT` visible
  as text.

### Don't:

- **Don't** show the multi-line wordmark in narrow terminals, CI output, or
  screens invoked with `--no-banner`.
- **Don't** use color, icons, or alignment as the only carrier of meaning.
- **Don't** wrap every section in a box or imitate a graphical dashboard.
- **Don't** hide synthetic provenance or the scientific-correctness boundary
  to make a successful run appear stronger.
