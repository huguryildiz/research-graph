/* The control room over one open study.

   The first screen answers one question — what should I do next — and every
   code it shows carries its plain-English title. Detail is one click away in
   the drawer, never dumped on arrival. */

function renderHeader(state) {
  document.title = `Research Graph · ${state.run.id}`;
  $("#run-id-rail").textContent = state.run.id;
  $("#rail-question").textContent = state.run.question;
  $("#run-question").textContent = state.run.question;
  $("#responsible").textContent = state.run.responsible || "not recorded";
  $("#protocol").textContent = state.run.protocol;
  $("#mode").textContent = state.run.mode;
  $("#provenance").textContent = state.run.provenance;
  $("#overview-eyebrow").textContent = state.demo
    ? "Demo study / bundled teaching data, read-only"
    : `Current study / stage: ${state.summary.stage}`;
  $("#unit-count").textContent = `${state.summary.units_complete}/${state.summary.units_total}`;
  const ratio = state.summary.units_total ? state.summary.units_complete / state.summary.units_total : 0;
  $("#seal-progress").style.strokeDashoffset = String(351.86 * (1 - ratio));
}

function renderNext(state) {
  const action = state.next_action;
  $("#next-kind").textContent = action.kind.replaceAll("_", " ");
  $("#next-title").textContent = action.title || action.detail;
  $("#next-detail").textContent = action.command
    ? `Equivalent terminal command: ${action.command}`
    : "No command is required for this state.";
  const controls = $("#next-controls");
  controls.replaceChildren();
  const add = (label, handler, primary = false) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `button${primary ? " primary" : ""}`;
    button.textContent = label;
    button.addEventListener("click", handler);
    controls.append(button);
  };
  const running = state.jobs.find(job => job.active);
  if (running) {
    add("Watch the running execution", () => openConsole(running.id), true);
  } else if (action.kind === "unit") add("Preview this work", () => previewUnit(action.target), true);
  else if (action.kind === "check") add("Run this check", () => runCheck(action.target), true);
  else if (action.kind === "decide") add("How to record this decision", () => openGate(action.target), true);
  else if (action.kind === "challenge") add("Preview the reviewer", () => previewChallenge(action.target), true);
  else if (action.kind === "revise") add("Preview the return", () => previewRevision(action.target), true);
  else if (action.kind === "review") add("Open the release checkpoint", () => openGate(action.target || "FINAL"), true);
  add("Refresh", loadState, false);
}

function renderHandoff(state) {
  const panel = $("#human-handoff");
  const handoff = state.human_decision;
  if (!handoff) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  panel.innerHTML = `
    <div class="handoff-mark">HUMAN<br>DECISION</div>
    <div class="handoff-copy">
      <h3>${esc(handoff.gate)} — ${esc(handoff.title)}</h3>
      <p>${esc(handoff.criterion)}</p>
      <dl class="handoff-facts">
        <div><dt>Responsible</dt><dd>${esc(handoff.responsible || "not recorded")}</dd></div>
        <div><dt>Current state</dt><dd>${esc(handoff.state)}</dd></div>
      </dl>
      ${commandBlock(handoff.command)}
      <p class="muted-line">${esc(handoff.why_terminal)}</p>
      <button class="text-button" type="button" id="handoff-detail">What was checked, and what was not</button>
    </div>`;
  bindCopyButtons(panel);
  $("#handoff-detail").addEventListener("click", () => openGate(handoff.gate));
}

function renderJobStrip(state) {
  const strip = $("#job-strip");
  const jobs = state.jobs.slice(0, 3);
  if (!jobs.length) {
    strip.hidden = true;
    return;
  }
  strip.hidden = false;
  strip.innerHTML = `<h3>Executions</h3>` + jobs.map(job => `
    <button class="job-row" type="button" data-job="${esc(job.id)}">
      ${statusPill(job.state)}
      <span class="job-target"><b>${esc(job.target)}</b> ${esc(job.title)}</span>
      <span class="job-meta">${esc(job.provider)}/${esc(job.model)}</span>
      <span class="job-meta">${job.elapsed_seconds != null
        ? `${Math.round(job.elapsed_seconds)}s` : "—"}</span>
    </button>`).join("");
  $$("[data-job]", strip).forEach(node =>
    node.addEventListener("click", () => openConsole(node.dataset.job)));
}

/* ── the study map ─────────────────────────────────────────────────────────

   One spine, in the order the graph itself produces: every work unit and every
   checkpoint, banded by stage. The order arrives from the server, derived from
   graph.yaml — nothing here is a hand-written list of nodes.

   A row says only what was observed. The row the workflow points at is opened;
   the rest stay compact, so "where am I" survives a glance. Return edges are
   drawn only when a revision was actually spent; the ones a checkpoint could
   still take appear on hover, because a path nobody has walked is not history. */

const RETURN_NOTE = "sends work back to";

function mapRow(state, entry) {
  const current = state.next_action.target === entry.id;
  if (entry.kind === "unit") {
    const unit = state.units.find(item => item.id === entry.id);
    if (!unit) return "";
    const held = ["BLOCKED", "STALE", "FAILED", "CANCELLED", "INTERRUPTED"].includes(unit.state);
    return `
      <button class="node unit-node${current ? " is-current" : ""}" type="button"
              data-unit="${esc(unit.id)}" data-state="${esc(unit.state)}"
              data-row="${esc(unit.id)}">
        <span class="node-mark" aria-hidden="true"></span>
        <span class="node-id">${esc(unit.id)}</span>
        <span class="node-body">
          <b>${esc(unit.title)}</b>
          ${current || held ? `<small>${esc(unit.state_meaning)}</small>` : ""}
        </span>
        <span class="node-state">${esc(unit.state)}</span>
      </button>`;
  }
  const gate = state.gates.find(item => item.id === entry.id);
  if (!gate) return "";
  const budget = state.revisions[gate.id] || gate.budget;
  const spent = (budget && budget.used) || 0;
  const targets = (state.map.returns || []).filter(edge => edge.from === gate.id);
  const returnLine = targets.length ? `
    <small class="node-returns">${RETURN_NOTE}
      ${targets.map(edge =>
        `${esc(edge.to)}<i>${esc(edge.carries || "revision")}</i>`).join(", ")}
      · ${spent} of ${esc(budget ? budget.max : "—")} used</small>` : "";
  return `
    <button class="node gate-node${current ? " is-current" : ""}${spent ? " is-returned" : ""}"
            type="button" data-gate="${esc(gate.id)}" data-status="${esc(gate.status)}"
            data-row="${esc(gate.id)}">
      <span class="node-mark" aria-hidden="true"></span>
      <span class="node-id">${esc(gate.id)}</span>
      <span class="node-body">
        <b>${esc(gate.title)}</b>
        ${current || gate.status !== "PASS" ? `<small>${esc(gate.status_meaning)}</small>` : ""}
        ${returnLine}
      </span>
      <span class="node-state">${esc(gate.status)}</span>
    </button>`;
}

function renderMap(state) {
  const titles = Object.fromEntries(state.stages.map(stage => [stage.id, stage]));
  const bands = [];
  state.map.spine.forEach(entry => {
    const last = bands[bands.length - 1];
    if (!last || last.stage !== entry.stage) bands.push({ stage: entry.stage, entries: [entry] });
    else last.entries.push(entry);
  });
  $("#map-spine").innerHTML = bands.map(band => {
    const stage = titles[band.stage] || { title: band.stage, status: "WAIT" };
    return `
      <section class="band ${statusClass(stage.status)}" data-stage="${esc(band.stage)}">
        <h3 class="band-head">
          <span>${esc(band.stage)}</span><b>${esc(stage.title)}</b>
          <em>${esc(stage.status)}</em>
        </h3>
        ${band.entries.map(entry => mapRow(state, entry)).join("")}
      </section>`;
  }).join("");
  $$("[data-unit]", $("#map-spine")).forEach(node =>
    node.addEventListener("click", () => openUnit(node.dataset.unit)));
  $$("[data-gate]", $("#map-spine")).forEach(node => {
    node.addEventListener("click", () => openGate(node.dataset.gate));
    const reveal = (on) => $$(`[data-arc-gate="${CSS.escape(node.dataset.gate)}"]`, $("#map-arcs"))
      .forEach(arc => arc.classList.toggle("is-shown", on));
    node.addEventListener("mouseenter", () => reveal(true));
    node.addEventListener("mouseleave", () => reveal(false));
    node.addEventListener("focus", () => reveal(true));
    node.addEventListener("blur", () => reveal(false));
  });
  watchMap(state);
  drawReturnArcs(state);
}

/* The arcs are painted from the rendered rows rather than from a layout guess,
   so they keep pointing at the right row when the text wraps or the pane
   narrows. A row the map never rendered simply gets no arc.

   The observer matters more than it looks: the map is rendered while the
   workspace is still hidden, where every row measures zero, so a one-shot draw
   at render time would paint nothing. */
let mapObserver = null;

function watchMap(state) {
  const map = $("#map");
  if (!map || mapObserver) return;
  mapObserver = new ResizeObserver(() => ui.state && drawReturnArcs(ui.state));
  mapObserver.observe(map);
}

function drawReturnArcs(state) {
  const map = $("#map");
  const svg = $("#map-arcs");
  if (!map || !svg) return;
  const frame = map.getBoundingClientRect();
  if (!frame.height) return;
  svg.setAttribute("viewBox", `0 0 ${frame.width} ${frame.height}`);
  svg.style.height = `${frame.height}px`;
  const centre = (id) => {
    const mark = $(`[data-row="${CSS.escape(id)}"] .node-mark`, map);
    if (!mark) return null;
    const box = mark.getBoundingClientRect();
    return { y: box.top - frame.top + box.height / 2, left: box.left - frame.left };
  };
  const arcs = (state.map.returns || []).map(edge => {
    const from = centre(edge.from);
    const to = centre(edge.to);
    if (!from || !to) return "";
    const spent = (state.revisions[edge.from] || {}).used || 0;
    const lane = Math.max(6, from.left - 12);
    const bow = Math.min(30, Math.max(12, Math.abs(from.y - to.y) / 6));
    const style = `class="arc${spent ? " is-spent" : ""}" data-arc-gate="${esc(edge.from)}"`;
    return `
      <path ${style} d="M ${from.left - 1} ${from.y}
        C ${lane - bow} ${from.y}, ${lane - bow} ${to.y}, ${to.left - 1} ${to.y}"/>
      <path ${style} d="M ${to.left - 7} ${to.y - 4} L ${to.left - 1} ${to.y}
        L ${to.left - 7} ${to.y + 4}" stroke-dasharray="none"/>`;
  }).join("");
  svg.innerHTML = arcs;
}

function renderGates(state) {
  $("#gate-ledger").innerHTML = state.gates.map(gate => `
    <button class="gate-row" data-gate="${esc(gate.id)}" type="button">
      <span class="gate-code">${esc(gate.id)}</span>
      <span><span class="gate-title">${esc(gate.title)}</span><span class="gate-kind">${
        gate.human ? "decided by a person" : "decided by the assigned reviewer"}</span></span>
      ${statusPill(gate.status, gate.status_meaning)}
      <span class="gate-proof">${esc(gate.status_meaning)}</span>
      <span class="gate-arrow">→</span>
    </button>`).join("");
  $$("[data-gate]").forEach(node => node.addEventListener("click", () => openGate(node.dataset.gate)));
}

function renderArtifacts(state) {
  const counts = state.artifacts.reduce((acc, item) => {
    acc[item.state] = (acc[item.state] || 0) + 1;
    return acc;
  }, {});
  $("#artifact-summary").innerHTML = ["VALID", "STALE", "INVALID", "PENDING"].map(key =>
    `<span><b>${counts[key] || 0}</b>${key.toLowerCase()}</span>`).join("");
  $("#artifact-table").innerHTML = state.artifacts.map(item => `
    <div class="artifact-row" data-artifact-state="${esc(item.state)}">
      <span class="artifact-name">${esc(item.id)}</span>
      ${statusPill(item.state)}
      <span class="artifact-owner" title="${esc(item.identity || item.path)}">${esc(item.identity || item.path)}</span>
    </div>`).join("");
  applyArtifactFilter();
}

function applyArtifactFilter() {
  $$("[data-artifact-state]").forEach(row => {
    const attention = ["STALE", "INVALID"].includes(row.dataset.artifactState);
    row.hidden = ui.artifactFilter !== "ALL"
      && row.dataset.artifactState !== ui.artifactFilter
      && !(ui.artifactFilter === "STALE" && attention);
  });
}

function renderClaims(state) {
  const list = $("#claim-list");
  if (!state.claims.length) {
    list.innerHTML = '<div class="empty-trace"><p>No claims are registered yet.</p></div>';
    return;
  }
  list.innerHTML = state.claims.map(claim => `
    <button class="claim-button" data-claim="${esc(claim.id)}" type="button">
      <b>${esc(claim.id)}</b><span>${esc(claim.text)}</span>
    </button>`).join("");
  $$("[data-claim]").forEach(node => node.addEventListener("click", () => loadTrace(node.dataset.claim)));
}

function renderSetup(state) {
  const install = state.install;
  const revisions = Object.entries(state.revisions || {});
  $("#setup-grid").innerHTML = `
    <section>
      <h3>Role assignment</h3>
      <div class="assignment-readout">
        ${state.assignment.filter(Boolean).map(item => `
          <div><b>${esc(item.role)}</b><span>${esc(item.identity || "not assigned")}</span></div>`).join("")}
      </div>
      ${state.separation ? `<p class="muted-line">Producer / reviewer separation between
        ${esc(state.separation.between)}: <b>${esc(state.separation.label)}</b>.</p>` : ""}
    </section>
    <section>
      <h3>Revision budgets</h3>
      ${revisions.length ? `<div class="assignment-readout">${revisions.map(([gate, budget]) => `
        <div><b>${esc(gate)}</b><span>${budget.used} of ${budget.max} attempts used</span></div>`).join("")}</div>`
        : `<p class="muted-line">No checkpoint has spent a revision attempt yet.</p>`}
    </section>
    <section>
      <h3>This installation</h3>
      <div class="assignment-readout">
        ${[["Version", install.version], ["Installation", install.install_kind],
           ["Python", install.python], ["Contract kit", install.kit_root],
           ["Study", install.run], ["Assignment", install.assignment || "none"]]
          .map(([term, value]) => `<div><b>${esc(term)}</b><span>${esc(value)}</span></div>`).join("")}
      </div>
    </section>`;
}

function renderState(state) {
  ui.state = state;
  renderHeader(state);
  renderNext(state);
  renderHandoff(state);
  renderJobStrip(state);
  renderMap(state);
  renderGates(state);
  renderArtifacts(state);
  renderClaims(state);
  renderSetup(state);
  document.body.classList.remove("loading");
}

async function loadState() {
  document.body.classList.add("loading");
  try {
    renderState(await api("/api/state"));
  } catch (error) {
    document.body.classList.remove("loading");
    $("#next-title").textContent = "The study could not be loaded.";
    $("#next-detail").textContent = error.message;
    toast(error.message);
  }
}

/* ── gate detail ───────────────────────────────────────────────────────── */

function gateContent(gate) {
  const checks = gate.checks.map(check => `
    <div class="check-row"><span>${esc(check.name)}</span><b>${esc(check.status)}</b><span>${esc(check.detail)}</span></div>`).join("");
  const findings = gate.findings.length ? gate.findings.map(item => `
    <div class="drawer-section"><h3>${esc(item.code)} · ${esc(item.artifact)}</h3><p>${esc(item.detail)}</p><p><b>Correction:</b> ${esc(item.fix)}</p></div>`).join("") : "";
  const canDecide = gate.kind === "human" && ["AWAITING", "STALE", "FAIL"].includes(gate.status);
  const canChallenge = gate.kind === "challenge" && !["PASS", "CAVEAT", "BLOCKED"].includes(gate.status) && !ui.state.read_only;
  const canRevise = gate.outcome === "revise" && !ui.state.read_only;
  const decision = canDecide ? `
    <div class="drawer-section"><h3>Continue in the terminal</h3><p>Human attestations are recorded only at a real terminal prompt. This handoff is deliberate: a button cannot attest that somebody read the files.</p><div class="plan-command">rgraph decide ${esc(gate.id)}</div></div>` : "";
  const challenge = canChallenge ? `<div class="drawer-section"><h3>Separate reviewer</h3><p>Preview the assigned reviewer identity, model, exact command, and current gate inputs before one invocation is allowed.</p><button id="preview-challenge" class="button primary" type="button">Preview reviewer</button></div>` : "";
  const revision = canRevise ? `<div class="drawer-section"><h3>Bounded return</h3><p>Preview the target work unit and remaining budget before spending one revision attempt.</p><button id="preview-revision" class="button primary" type="button">Preview revision</button></div>` : "";
  const review = gate.kind === "release" ? `
    <div class="drawer-section"><h3>Continue in the terminal</h3><p>Passing gates do not approve publication. A named researcher records the final decision at a real terminal prompt.</p><div class="plan-command">rgraph review</div></div>` : "";
  return `
    <h2 id="drawer-title">${esc(gate.id)} · ${esc(gate.title)}</h2>
    <div class="drawer-meta">${statusPill(gate.status)}<span class="gate-kind">${esc(gate.kind)} / ${esc(gate.owner)}</span><span class="gate-kind">budget ${gate.budget.used}/${gate.budget.max}</span></div>
    <div class="drawer-section"><h3>What this state means</h3><p>${esc(gate.status_meaning)}</p></div>
    <div class="drawer-section"><h3>Declared reading</h3><p>${esc(gate.proves.join(" · "))}</p></div>
    <div class="drawer-section"><h3>Mechanical checks</h3>${checks}</div>
    ${findings}${challenge}${revision}
    <div class="drawer-section"><h3>Boundary</h3><p><em>${esc(gate.mechanical_limit)} ${esc(ui.state.boundary)}</em></p></div>
    ${decision}${review}`;
}

function openGate(id) {
  const gate = ui.state.gates.find(item => item.id === id);
  if (!gate) return toast(`Checkpoint ${id} is not available.`);
  openDrawer("CHECKPOINT", gateContent(gate));
  const challenge = $("#preview-challenge");
  if (challenge) challenge.addEventListener("click", () => previewChallenge(gate.id));
  const revision = $("#preview-revision");
  if (revision) revision.addEventListener("click", () => previewRevision(gate.id));
}

/* ── work unit detail ──────────────────────────────────────────────────── */

async function openUnit(id) {
  let unit;
  try {
    unit = (await api(`/api/unit?id=${encodeURIComponent(id)}`)).unit;
  } catch (error) {
    return toast(error.message);
  }
  const rows = (items, empty) => items.length
    ? `<div class="plan-list">${items.join("")}</div>` : `<p class="muted-line">${empty}</p>`;
  openDrawer("WORK UNIT", `
    <h2 id="drawer-title">${esc(unit.id)} · ${esc(unit.title)}</h2>
    <div class="drawer-meta">${statusPill(unit.state, unit.state_meaning)}
      <span class="gate-kind">${esc(unit.stage_title)}</span>
      <span class="gate-kind">${esc(unit.assignment?.identity || unit.role || "unassigned")}</span></div>
    <div class="drawer-section"><h3>What this state means</h3><p>${esc(unit.state_meaning)}</p>
      ${unit.blocked_reason ? `<p class="finding">${esc(unit.blocked_reason)}</p>` : ""}</div>
    <div class="drawer-section"><h3>Reads</h3>
      ${rows(unit.inputs.map(item => `<div>${esc(item.id)}<br>${statusPill(item.state)}
        <small>${esc((item.content_hash || "not sealed").slice(0, 23))}</small></div>`),
        "This unit reads no upstream artifact.")}</div>
    <div class="drawer-section"><h3>Expected outputs</h3>
      ${rows(unit.outputs.map(item => `<div>${esc(item.id)}<br>
        ${statusPill(item.present ? "PRESENT" : "PENDING")}<small>${esc(item.path)}</small></div>`),
        "No declared output.")}</div>
    ${unit.downstream_gate ? `<div class="drawer-section"><h3>Next checkpoint</h3>
      <p>${esc(unit.downstream_gate.id)} — ${esc(unit.downstream_gate.title)}</p></div>` : ""}
    ${unit.last_execution ? `<div class="drawer-section"><h3>Last recorded execution</h3>
      <p>${esc(unit.last_execution.outcome)} · exit ${esc(unit.last_execution.exit_code)}
      · ${esc(unit.last_execution.finished_at || "")}</p>
      ${unit.last_execution.problems.length ? `<ul class="plain-list">${
        unit.last_execution.problems.map(line => `<li>${esc(line)}</li>`).join("")}</ul>` : ""}
      <p class="muted-line">Provider logs are written to ${esc(unit.logs_directory)}. They are
        not redacted and are readable by anyone with access to this computer.</p></div>` : ""}
    <div class="drawer-section"><h3>Execution</h3>
      <p>The server rechecks upstream checkpoints and recomputes every input digest
         before it prepares a provider command.</p>
      ${unit.job ? `<button id="open-console" class="button" type="button">Open the execution console</button>` : ""}
      ${unit.state === "BLOCKED" || ui.state.read_only
        ? `<p class="muted-line">${ui.state.read_only
            ? "This study is read-only, so no provider can be launched against it."
            : "Finish the earlier step first."}</p>`
        : `<button id="preview-unit" class="button primary" type="button">Preview the exact plan</button>`}
    </div>`);
  const preview = $("#preview-unit");
  if (preview) preview.addEventListener("click", () => previewUnit(id));
  const console_ = $("#open-console");
  if (console_) console_.addEventListener("click", () => openConsole(unit.job.id));
}

/* ── approvals ─────────────────────────────────────────────────────────── */

async function previewUnit(id) {
  try {
    const body = await post("/api/next/preview", { unit: id });
    const plan = body.plan;
    openDrawer("EXECUTION PREVIEW", `
      <h2 id="drawer-title">Approve ${esc(plan.unit)}</h2>
      <div class="drawer-meta"><span class="gate-kind">${esc(plan.provider)} / ${esc(plan.model)}</span>${plan.manual ? statusPill("MANUAL") : statusPill("APPROVAL REQUIRED")}</div>
      <div class="drawer-section"><h3>Exact provider command</h3><div class="plan-command">${esc(plan.command.join(" "))}</div></div>
      <div class="drawer-section"><h3>Inputs</h3><div class="plan-list">${plan.inputs.map(item => `<div>${esc(item.id)}<br>${statusPill(item.state)}</div>`).join("")}</div></div>
      <div class="drawer-section"><h3>Expected outputs</h3><p>${esc(plan.produces.join(" · "))}</p></div>
      <div class="drawer-section"><h3>Approval boundary</h3><p>This approval is single-use and bound to the exact command, prompt, inputs, and expected outputs shown here. The command runs as a child process of this application; it is not a terminal you can type into.</p>
      ${plan.manual || !plan.approval_token ? '<p class="error-note">This provider is manual and cannot be launched here.</p>' : '<button id="execute-plan" class="button primary" type="button">Run this exact plan</button>'}</div>`);
    const execute = $("#execute-plan");
    if (execute) execute.addEventListener("click", () => startJob("unit", plan.unit, plan.approval_token, execute));
  } catch (error) {
    toast(error.message);
  }
}

async function previewChallenge(gateId) {
  try {
    const body = await post("/api/challenge/preview", { gate: gateId });
    const plan = body.plan;
    openDrawer("REVIEWER PREVIEW", `
      <h2 id="drawer-title">Challenge ${esc(gateId)}</h2>
      <div class="drawer-meta">${statusPill("APPROVAL REQUIRED")}<span class="gate-kind">${esc(plan.provider)} / ${esc(plan.model)}</span></div>
      <div class="drawer-section"><h3>Exact reviewer command</h3><div class="plan-command">${esc(plan.command.join(" "))}</div></div>
      <div class="drawer-section"><h3>Bound gate inputs</h3><div class="plan-list">${plan.inputs.map(item => `<div>${esc(item.id)}<br>${statusPill(item.state)}</div>`).join("")}</div></div>
      <div class="drawer-section"><h3>Approval boundary</h3><p>One reviewer invocation will run. The captured decision and provider log must validate before a gate record can be written.</p><button id="execute-challenge" class="button primary" type="button">Run this reviewer</button></div>`);
    $("#execute-challenge").addEventListener("click", (event) =>
      startJob("challenge", gateId, plan.approval_token, event.target));
  } catch (error) {
    toast(error.message);
  }
}

async function previewRevision(gateId) {
  try {
    const body = await post("/api/revise/preview", { gate: gateId });
    const plan = body.plan;
    const remaining = plan.budget.max - plan.budget.used;
    openDrawer("REVISION PREVIEW", `
      <h2 id="drawer-title">Return ${esc(gateId)}</h2>
      <div class="drawer-meta">${statusPill("REVISION")}<span class="gate-kind">${esc(remaining)} attempt${remaining === 1 ? "" : "s"} available</span></div>
      <div class="drawer-section"><h3>Declared route</h3><p>This decision returns work to <b>${esc(plan.return_to)}</b> and increments the signed revision counter.</p></div>
      <div class="drawer-section"><h3>Material write</h3><div class="plan-command">rgraph revise ${esc(gateId)}</div><p><code>meta.json</code> history and content hash will change. No research artifact is rewritten.</p></div>
      <div class="drawer-section"><button id="execute-revision" class="button primary" type="button">Use one revision attempt</button></div>`);
    $("#execute-revision").addEventListener("click", () => executeRevision(plan, gateId));
  } catch (error) {
    toast(error.message);
  }
}

async function executeRevision(plan, gateId) {
  const button = $("#execute-revision");
  button.disabled = true;
  button.textContent = "Recording return…";
  try {
    const body = await post("/api/revise/execute", {
      gate: gateId, approval_token: plan.approval_token,
    });
    closeDrawer();
    toast(`${gateId} returned to ${body.revision.return_to}`);
    await loadState();
  } catch (error) {
    button.disabled = false;
    button.textContent = "Use one revision attempt";
    toast(error.message);
  }
}

async function runCheck(gateId) {
  try {
    const body = await post("/api/check", { gate: gateId });
    const index = ui.state.gates.findIndex(item => item.id === gateId);
    if (index >= 0) ui.state.gates[index] = body.gate;
    renderGates(ui.state);
    openGate(gateId);
    toast(`${gateId}: ${body.gate.status}`);
  } catch (error) {
    toast(error.message);
  }
}

async function loadTrace(claimId) {
  $$("[data-claim]").forEach(node => node.classList.toggle("active", node.dataset.claim === claimId));
  const paper = $("#trace-paper");
  paper.classList.add("loading");
  try {
    const trace = await api(`/api/trace?claim=${encodeURIComponent(claimId)}`);
    paper.innerHTML = `
      <h3 class="trace-heading">${esc(trace.claim_id)} · ${esc(trace.text || "Unregistered claim")}</h3>
      <div class="trace-chain">${trace.links.map(link => `
        <div class="trace-link"><span class="trace-dot"></span><span class="trace-label">${esc(link.label)}</span><span class="trace-detail">${esc([link.detail, link.status].filter(Boolean).join(" · "))}</span></div>`).join("")}</div>
      <div class="trace-verdict">${trace.complete ? "The registered provenance chain is complete." : `Incomplete: ${esc(trace.missing.join(" · "))}`}<br>${esc(trace.boundary)}</div>`;
  } catch (error) {
    paper.innerHTML = `<p class="error-note">${esc(error.message)}</p>`;
  } finally {
    paper.classList.remove("loading");
  }
}
