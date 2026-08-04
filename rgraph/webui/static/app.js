const sessionToken = document.querySelector('meta[name="rgraph-token"]').content;
const ui = {
  state: null,
  artifactFilter: "ALL",
  drawerTrigger: null,
  toastTimer: null,
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = (value) => String(value ?? "")
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
const statusClass = (value) => String(value || "WAIT").toLowerCase().replace(/[^a-z]/g, "");

async function api(path, options = {}) {
  const init = { ...options, headers: { ...(options.headers || {}) } };
  if (init.method === "POST") {
    init.headers["Content-Type"] = "application/json";
    init.headers["X-RGraph-Token"] = sessionToken;
  }
  const response = await fetch(path, init);
  const body = await response.json().catch(() => ({ error: "The local UI returned an unreadable response." }));
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status}).`);
  return body;
}

function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.add("show");
  clearTimeout(ui.toastTimer);
  ui.toastTimer = setTimeout(() => node.classList.remove("show"), 3200);
}

function statusPill(status) {
  return `<span class="status ${statusClass(status)}">${esc(status)}</span>`;
}

function renderHeader(state) {
  $("#run-id-rail").textContent = state.run.id;
  $("#rail-question").textContent = state.run.question;
  $("#run-question").textContent = state.run.question;
  $("#protocol").textContent = state.run.protocol;
  $("#mode").textContent = state.run.mode;
  $("#provenance").textContent = state.run.provenance;
  $("#unit-count").textContent = `${state.summary.units_complete}/${state.summary.units_total}`;
  const ratio = state.summary.units_total ? state.summary.units_complete / state.summary.units_total : 0;
  $("#seal-progress").style.strokeDashoffset = String(351.86 * (1 - ratio));
}

function renderNext(state) {
  const action = state.next_action;
  $("#next-kind").textContent = action.kind.replaceAll("_", " ");
  $("#next-title").textContent = action.target
    ? `${action.target} · ${action.detail}` : action.detail;
  $("#next-detail").textContent = action.command
    ? `Permitted route: ${action.command}` : "No command is required for this state.";
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
  if (action.kind === "unit") add("Preview work", () => previewUnit(action.target), true);
  else if (action.kind === "check") add("Run check", () => runCheck(action.target), true);
  else if (action.kind === "decide") add("Review gate", () => openGate(action.target), true);
  else if (action.kind === "challenge") add("Preview reviewer", () => previewChallenge(action.target), true);
  else if (action.kind === "revise") add("Preview revision", () => previewRevision(action.target), true);
  else if (action.kind === "review") {
    add("Inspect gate", () => openGate(action.target || "FINAL"), true);
  }
  add("Refresh", loadState, false);
}

function renderStages(state) {
  $("#stage-rule").innerHTML = state.stages.map(stage => `
    <div class="stage ${statusClass(stage.status)}">
      <span>${esc(stage.status)}</span><b>${esc(stage.id)}</b>
    </div>`).join("");
  const byStage = Object.fromEntries(state.stages.map(stage => [stage.id, []]));
  state.units.forEach(unit => (byStage[unit.stage] ||= []).push(unit));
  $("#workflow").innerHTML = state.stages.map(stage => `
    <div class="stage-column" data-stage="${esc(stage.id)}">
      ${(byStage[stage.id] || []).map(unit => `
        <button class="unit" data-unit="${esc(unit.id)}" data-state="${esc(unit.state)}" type="button">
          <span class="unit-id">${esc(unit.id)}</span>
          <b>${esc(unit.title)}</b>
          <small>${esc(unit.role)} · ${esc(unit.produces.length)} output${unit.produces.length === 1 ? "" : "s"}</small>
          <span class="unit-state" aria-label="${esc(unit.state)}"></span>
        </button>`).join("")}
    </div>`).join("");
  $$("[data-unit]").forEach(node => node.addEventListener("click", () => openUnit(node.dataset.unit)));
}

function renderGates(state) {
  $("#gate-ledger").innerHTML = state.gates.map(gate => `
    <button class="gate-row" data-gate="${esc(gate.id)}" type="button">
      <span class="gate-code">${esc(gate.id)}</span>
      <span><span class="gate-title">${esc(gate.title)}</span><span class="gate-kind">${esc(gate.kind)} gate</span></span>
      ${statusPill(gate.status)}
      <span class="gate-proof">${esc(gate.proves.join(" · "))}</span>
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

function renderState(state) {
  ui.state = state;
  renderHeader(state);
  renderNext(state);
  renderStages(state);
  renderGates(state);
  renderArtifacts(state);
  renderClaims(state);
  document.body.classList.remove("loading");
}

async function loadState() {
  document.body.classList.add("loading");
  try {
    renderState(await api("/api/state"));
  } catch (error) {
    document.body.classList.remove("loading");
    $("#next-title").textContent = "The run could not be loaded.";
    $("#next-detail").textContent = error.message;
    toast(error.message);
  }
}

function openDrawer(label, content) {
  if (!$("#drawer").classList.contains("open")) ui.drawerTrigger = document.activeElement;
  $("#drawer-label").textContent = label;
  $("#drawer-body").innerHTML = content;
  $("#drawer").classList.add("open");
  $("#drawer").setAttribute("aria-hidden", "false");
  $("#scrim").classList.add("open");
  $("#drawer-close").focus();
}

function closeDrawer() {
  $("#drawer").classList.remove("open");
  $("#drawer").setAttribute("aria-hidden", "true");
  $("#scrim").classList.remove("open");
  const trigger = ui.drawerTrigger;
  ui.drawerTrigger = null;
  if (trigger?.isConnected && typeof trigger.focus === "function") trigger.focus();
}

function gateContent(gate) {
  const checks = gate.checks.map(check => `
    <div class="check-row"><span>${esc(check.name)}</span><b>${esc(check.status)}</b><span>${esc(check.detail)}</span></div>`).join("");
  const findings = gate.findings.length ? gate.findings.map(item => `
    <div class="drawer-section"><h3>${esc(item.code)} · ${esc(item.artifact)}</h3><p>${esc(item.detail)}</p><p><b>Correction:</b> ${esc(item.fix)}</p></div>`).join("") : "";
  const canDecide = gate.kind === "human" && ["AWAITING", "STALE", "FAIL"].includes(gate.status);
  const canChallenge = gate.kind === "challenge" && !["PASS", "CAVEAT", "BLOCKED"].includes(gate.status) && !ui.state.read_only;
  const canRevise = gate.outcome === "revise" && !ui.state.read_only;
  const decision = canDecide ? `
    <div class="drawer-section"><h3>Continue in the terminal</h3><p>Human attestations are recorded only at a real terminal prompt.</p><div class="plan-command">rgraph decide ${esc(gate.id)}</div></div>` : "";
  const challenge = canChallenge ? `<div class="drawer-section"><h3>Separate reviewer</h3><p>Preview the assigned reviewer identity, model, exact command, and current gate inputs before one invocation is allowed.</p><button id="preview-challenge" class="button primary" type="button">Preview reviewer</button></div>` : "";
  const revision = canRevise ? `<div class="drawer-section"><h3>Bounded return</h3><p>Preview the target work unit and remaining budget before spending one revision attempt.</p><button id="preview-revision" class="button primary" type="button">Preview revision</button></div>` : "";
  const review = gate.kind === "release" ? `
    <div class="drawer-section"><h3>Continue in the terminal</h3><p>Passing gates do not approve publication. A named researcher records the final decision at a real terminal prompt.</p><div class="plan-command">rgraph review</div></div>` : "";
  return `
    <h2 id="drawer-title">${esc(gate.id)} · ${esc(gate.title)}</h2>
    <div class="drawer-meta">${statusPill(gate.status)}<span class="gate-kind">${esc(gate.kind)} / ${esc(gate.owner)}</span><span class="gate-kind">budget ${gate.budget.used}/${gate.budget.max}</span></div>
    <div class="drawer-section"><h3>Declared reading</h3><p>${esc(gate.proves.join(" · "))}</p></div>
    <div class="drawer-section"><h3>Mechanical checks</h3>${checks}</div>
    ${findings}${challenge}${revision}
    <div class="drawer-section"><h3>Boundary</h3><p><em>${esc(ui.state.boundary)}</em></p></div>
    ${decision}${review}`;
}

function openGate(id) {
  const gate = ui.state.gates.find(item => item.id === id);
  if (!gate) return toast(`Gate ${id} is not available.`);
  openDrawer("GATE RECORD", gateContent(gate));
  const challenge = $("#preview-challenge");
  if (challenge) challenge.addEventListener("click", () => previewChallenge(gate.id));
  const revision = $("#preview-revision");
  if (revision) revision.addEventListener("click", () => previewRevision(gate.id));
}

function openUnit(id) {
  const unit = ui.state.units.find(item => item.id === id);
  if (!unit) return;
  openDrawer("WORK UNIT", `
    <h2 id="drawer-title">${esc(unit.id)} · ${esc(unit.title)}</h2>
    <div class="drawer-meta">${statusPill(unit.state)}<span class="gate-kind">${esc(unit.stage)} / ${esc(unit.role)}</span></div>
    <div class="drawer-section"><h3>Produces</h3><p>${esc(unit.produces.join(" · ") || "No artifacts")}</p></div>
    <div class="drawer-section"><h3>Execution</h3><p>The server rechecks upstream gates before it prepares any provider command.</p><button id="preview-unit" class="button primary" type="button">Preview exact plan</button></div>`);
  $("#preview-unit").addEventListener("click", () => previewUnit(id));
}

async function previewUnit(id) {
  try {
    const body = await api("/api/next/preview", { method: "POST", body: JSON.stringify({ unit: id }) });
    const plan = body.plan;
    openDrawer("EXECUTION PREVIEW", `
      <h2 id="drawer-title">Approve ${esc(plan.unit)}</h2>
      <div class="drawer-meta"><span class="gate-kind">${esc(plan.provider)} / ${esc(plan.model)}</span>${plan.manual ? statusPill("MANUAL") : statusPill("READY")}</div>
      <div class="drawer-section"><h3>Exact provider command</h3><div class="plan-command">${esc(plan.command.join(" "))}</div></div>
      <div class="drawer-section"><h3>Inputs</h3><div class="plan-list">${plan.inputs.map(item => `<div>${esc(item.id)}<br>${statusPill(item.state)}</div>`).join("")}</div></div>
      <div class="drawer-section"><h3>Expected outputs</h3><p>${esc(plan.produces.join(" · "))}</p></div>
      <div class="drawer-section"><h3>Approval boundary</h3><p>This approval is single-use and bound to the exact command, prompt, inputs, and expected outputs shown here.</p>
      ${plan.manual || !plan.approval_token ? '<p class="error-note">This provider is manual and cannot be launched here.</p>' : '<button id="execute-plan" class="button primary" type="button">Run this exact plan</button>'}</div>`);
    const execute = $("#execute-plan");
    if (execute) execute.addEventListener("click", () => executePlan(plan, execute));
  } catch (error) {
    toast(error.message);
  }
}

async function previewChallenge(gateId) {
  try {
    const body = await api("/api/challenge/preview", {
      method: "POST", body: JSON.stringify({ gate: gateId }),
    });
    const plan = body.plan;
    openDrawer("REVIEWER PREVIEW", `
      <h2 id="drawer-title">Challenge ${esc(gateId)}</h2>
      <div class="drawer-meta">${statusPill("READY")}<span class="gate-kind">${esc(plan.provider)} / ${esc(plan.model)}</span></div>
      <div class="drawer-section"><h3>Exact reviewer command</h3><div class="plan-command">${esc(plan.command.join(" "))}</div></div>
      <div class="drawer-section"><h3>Bound gate inputs</h3><div class="plan-list">${plan.inputs.map(item => `<div>${esc(item.id)}<br>${statusPill(item.state)}</div>`).join("")}</div></div>
      <div class="drawer-section"><h3>Approval boundary</h3><p>One reviewer invocation will run. The captured decision and provider log must validate before a gate record can be written.</p><button id="execute-challenge" class="button primary" type="button">Run this reviewer</button></div>`);
    $("#execute-challenge").addEventListener("click", () => executeChallenge(plan, gateId));
  } catch (error) {
    toast(error.message);
  }
}

async function executeChallenge(plan, gateId) {
  const button = $("#execute-challenge");
  button.disabled = true;
  button.textContent = "Reviewer running…";
  try {
    const body = await api("/api/challenge/execute", {
      method: "POST",
      body: JSON.stringify({ gate: gateId, approval_token: plan.approval_token }),
    });
    closeDrawer();
    toast(`${gateId}: ${body.execution.status}`);
    await loadState();
    openGate(gateId);
  } catch (error) {
    button.disabled = false;
    button.textContent = "Run this reviewer";
    toast(error.message);
  }
}

async function previewRevision(gateId) {
  try {
    const body = await api("/api/revise/preview", {
      method: "POST", body: JSON.stringify({ gate: gateId }),
    });
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
    const body = await api("/api/revise/execute", {
      method: "POST", body: JSON.stringify({ gate: gateId, approval_token: plan.approval_token }),
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

async function executePlan(plan, button) {
  button.disabled = true;
  button.textContent = "Provider running…";
  try {
    const body = await api("/api/next/execute", {
      method: "POST",
      body: JSON.stringify({ unit: plan.unit, approval_token: plan.approval_token }),
    });
    const result = body.execution;
    openDrawer("EXECUTION RESULT", `
      <h2 id="drawer-title">${esc(plan.unit)} finished</h2>
      <div class="drawer-meta">${statusPill(result.exit_code === 0 ? "PASS" : "FAIL")}<span class="gate-kind">exit ${esc(result.exit_code)}</span></div>
      <div class="drawer-section"><h3>Provider log</h3><p class="artifact-name">${esc(result.log)}</p></div>
      <div class="drawer-section"><h3>Recent output</h3><pre class="plan-command">${esc(result.output || "No output")}</pre></div>`);
    await loadState();
  } catch (error) {
    button.disabled = false;
    button.textContent = "Run this exact plan";
    toast(error.message);
  }
}

async function runCheck(gateId) {
  try {
    const body = await api("/api/check", { method: "POST", body: JSON.stringify({ gate: gateId }) });
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

$("#refresh-button").addEventListener("click", loadState);
$("#drawer-close").addEventListener("click", closeDrawer);
$("#scrim").addEventListener("click", closeDrawer);
document.addEventListener("keydown", event => { if (event.key === "Escape") closeDrawer(); });
$$(`[data-filter]`).forEach(button => button.addEventListener("click", () => {
  ui.artifactFilter = button.dataset.filter;
  $$(`[data-filter]`).forEach(item => item.classList.toggle("active", item === button));
  applyArtifactFilter();
}));

loadState();
