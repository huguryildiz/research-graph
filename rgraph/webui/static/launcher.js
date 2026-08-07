/* Launcher, demo and the new-study wizard.

   The wizard holds answers in memory and asks the server to judge them. Every
   rule it enforces — a required field, a refused destination, a provider that
   cannot take a role — comes back from the same Python service `rgraph setup`
   and `rgraph init` use, so this file contains no contract of its own. */

const wizard = {
  step: 0,
  study: {
    question: "",
    in_scope: "",
    out_of_scope: "",
    constraints: "",
    success_criteria: "",
    ethics_applicable: false,
    ethics_reference: "",
    data_governance: "",
    legal_notes: "No known additional legal restrictions.",
    approver: "",
  },
  detection: null,
  assignment: {},
  scope: "study",
  destination: "",
  preflight: null,
  probe: null,
  created: null,
};

const STEPS = [
  { id: "question", title: "Research question",
    lede: "One sentence. This is what every later checkpoint is judged against." },
  { id: "scope", title: "Scope and exclusions",
    lede: "What this study covers, and what it deliberately leaves out." },
  { id: "constraints", title: "Constraints and success",
    lede: "The limits you are working under, and what would count as an answer." },
  { id: "governance", title: "Governance, ethics and data",
    lede: "Where the data comes from, what governs it, and any licence limits." },
  { id: "responsible", title: "Responsible person",
    lede: "Human checkpoints are recorded against a named person." },
  { id: "providers", title: "Available providers",
    lede: "What is installed on this computer. Detecting calls no model." },
  { id: "assignment", title: "Who does what",
    lede: "Each role reads a role file and produces artifacts. Two of them must differ." },
  { id: "preflight", title: "Preflight",
    lede: "Whether the assignment can actually be invoked, before anything runs." },
  { id: "preview", title: "What will be written",
    lede: "The exact destination and the exact files. Nothing has been written yet." },
  { id: "create", title: "Create the study",
    lede: "This is the first material write in the whole wizard." },
];

const splitItems = (value) => value.split(";").map(s => s.trim()).filter(Boolean);

/* ── launcher ──────────────────────────────────────────────────────────── */

function renderLauncher(app) {
  document.title = "Research Graph · Studies";
  const entries = [
    {
      key: "demo",
      kicker: "Two minutes, no setup",
      title: "Try the demo",
      body: "Three handoffs over bundled teaching data: one clean, one with an "
        + "untraceable source, one where the data changed after a freeze. "
        + "No model is called and no study file is changed.",
      primary: true,
    },
    {
      key: "new",
      kicker: "Guided",
      title: "Start a new study",
      body: `Ten short questions, then a governed run directory at `
        + `${app.default_destination}. Providers are detected for you; you never `
        + `type a provider identifier.`,
      primary: !app.here.exists,
    },
  ];
  if (app.here.exists) {
    entries.splice(1, 0, {
      key: "here",
      kicker: "In this folder",
      title: "Open the study here",
      body: app.here.path,
      primary: true,
    });
  }
  $("#entry-list").innerHTML = entries.map((entry, index) => `
    <li class="entry${entry.primary ? " primary" : ""}">
      <span class="entry-index">${String(index + 1).padStart(2, "0")}</span>
      <div class="entry-copy">
        <span class="entry-kicker">${esc(entry.kicker)}</span>
        <h2>${esc(entry.title)}</h2>
        <p>${esc(entry.body)}</p>
      </div>
      <button class="button${entry.primary ? " primary" : ""}" type="button"
              data-entry="${entry.key}">${entry.key === "demo" ? "Open the demo"
                : entry.key === "here" ? "Open study" : "Start"}</button>
    </li>`).join("");
  $$("[data-entry]").forEach(button => button.addEventListener("click", () => {
    if (button.dataset.entry === "demo") openDemo();
    else if (button.dataset.entry === "here") openStudy(app.here.path);
    else startWizard(app);
  }));

  renderRecent(app.recent);
  renderAbout(app.install, app);
  $("#open-path-button").onclick = () => openStudy($("#open-path").value);
}

function renderRecent(recent) {
  const list = $("#recent-list");
  if (!recent.length) {
    list.innerHTML = `<p class="muted-line">No studies have been opened on this
      computer yet. The list records only where a study is, never what it found.</p>`;
    return;
  }
  list.innerHTML = recent.map(item => `
    <div class="recent-row">
      <button class="recent-open" type="button" data-open="${esc(item.path)}">
        <b>${esc(item.question || item.run_id || item.path)}</b>
        <span>${esc(item.path)}</span>
      </button>
      <span class="recent-when">${esc((item.opened_at || "").slice(0, 10))}</span>
      <button class="text-button" type="button" data-forget="${esc(item.path)}">Remove</button>
    </div>`).join("");
  $$("[data-open]").forEach(node =>
    node.addEventListener("click", () => openStudy(node.dataset.open)));
  $$("[data-forget]").forEach(node =>
    node.addEventListener("click", () => forgetStudy(node.dataset.forget)));
}

function renderAbout(install, app) {
  $("#about-body").innerHTML = `
    <dl class="about-list">
      ${[
        ["Version", install.version],
        ["Installation", `${install.install_kind} — ${install.install_detail}`],
        ["Python", `${install.python} (${install.python_version})`],
        ["Package", install.package],
        ["Contract kit", install.kit_root],
        ["Working directory", install.cwd],
        ["Selected study", install.run || "none"],
        ["Assignment in force", install.assignment || "none written yet"],
      ].map(([term, value]) =>
        `<div><dt>${esc(term)}</dt><dd>${esc(value)}</dd></div>`).join("")}
    </dl>
    <p class="muted-line">${esc(install.update_note)}</p>`;
  if (app) $("#about-block").open = false;
}

async function openStudy(path) {
  try {
    await post("/api/run/open", { path });
    await loadState();
    setMode("workspace");
    announce("Study opened.");
  } catch (error) {
    toast(error.message);
  }
}

async function forgetStudy(path) {
  try {
    const body = await post("/api/recent/forget", { path });
    renderRecent(body.recent);
    toast(body.note);
  } catch (error) {
    toast(error.message);
  }
}

/* ── demo ──────────────────────────────────────────────────────────────── */

async function openDemo() {
  setMode("demo");
  $("#demo-cases").innerHTML = `<p class="muted-line">Running the three cases over a
    throwaway copy…</p>`;
  try {
    const body = await post("/api/demo/scenarios");
    $("#demo-note").textContent = body.note;
    $("#demo-boundary").textContent = body.boundary;
    $("#demo-cases").innerHTML = body.scenarios.map(item => `
      <article class="demo-case">
        <header>
          <span class="entry-index">${esc(item.id)}</span>
          <h2>${esc(item.title)}</h2>
          ${statusPill(item.behaved_as_documented ? "AS DOCUMENTED" : "UNEXPECTED")}
        </header>
        <p>${esc(item.consequence)}</p>
        <details class="disclosure">
          <summary>What the checks reported</summary>
          <div class="disclosure-body">
            <div class="gate-mini">${item.gates.map(gate => `
              <div><span>${esc(gate.id)} · ${esc(gate.title)}</span>${statusPill(gate.status)}</div>`).join("")}</div>
            ${(item.findings || []).map(finding => `
              <p class="finding"><b>${esc(finding.code)}</b> ${esc(finding.detail)}<br>
              <em>Correction: ${esc(finding.fix)}</em></p>`).join("")}
            ${(item.causes || []).length ? `<p class="finding">${item.causes.map(esc).join("<br>")}</p>` : ""}
            ${(item.invalidated || []).length
              ? `<p class="finding">Approvals retired: ${item.invalidated.map(esc).join(", ")}</p>` : ""}
            ${(item.detail || []).length
              ? `<ul class="plain-list">${item.detail.map(line => `<li>${esc(line)}</li>`).join("")}</ul>` : ""}
          </div>
        </details>
      </article>`).join("");
    announce("The demo finished running its three cases.");
  } catch (error) {
    $("#demo-cases").innerHTML = `<p class="error-note">${esc(error.message)}</p>`;
  }
  $("#demo-open").onclick = async () => {
    try {
      const body = await post("/api/demo/open");
      toast(body.note);
      await loadState();
      setMode("workspace");
    } catch (error) {
      toast(error.message);
    }
  };
  $("#demo-home").onclick = goHome;
}

/* ── wizard ────────────────────────────────────────────────────────────── */

function startWizard(app) {
  wizard.step = 0;
  wizard.destination = app.default_destination;
  wizard.created = null;
  setMode("wizard");
  document.title = "Research Graph · New study";
  renderWizard();
}

function wizardError(message) {
  const node = $("#wizard-error");
  node.hidden = !message;
  node.textContent = message || "";
  if (message) announce(message);
}

function renderWizard() {
  const step = STEPS[wizard.step];
  $("#wizard-steps").innerHTML = STEPS.map((item, index) => `
    <li class="${index === wizard.step ? "current" : index < wizard.step ? "done" : ""}">
      <span>${String(index + 1).padStart(2, "0")}</span>${esc(item.title)}</li>`).join("");
  $("#wizard-title").textContent = step.title;
  $("#wizard-lede").textContent = step.lede;
  $("#wizard-back").disabled = wizard.step === 0;
  $("#wizard-next").textContent =
    step.id === "create" ? "Create this study" :
    step.id === "preview" ? "I have read the destination" : "Continue";
  wizardError("");
  $("#wizard-body").innerHTML = STEP_BODIES[step.id]();
  bindCopyButtons($("#wizard-body"));
  if (STEP_BINDINGS[step.id]) STEP_BINDINGS[step.id]();
  const first = $("#wizard-body input, #wizard-body textarea, #wizard-body select");
  if (first) first.focus();
}

const textField = (name, label, hint, { multiline = false, value = "" } = {}) => `
  <div class="field">
    <label for="w-${name}">${esc(label)}</label>
    ${multiline
      ? `<textarea id="w-${name}" rows="3" data-field="${name}">${esc(value)}</textarea>`
      : `<input id="w-${name}" type="text" data-field="${name}" value="${esc(value)}">`}
    ${hint ? `<p class="field-hint">${esc(hint)}</p>` : ""}
  </div>`;

const STEP_BODIES = {
  question: () => textField("question", "Research question",
    "Plain language, one sentence.", { multiline: true, value: wizard.study.question }),
  scope: () =>
    textField("in_scope", "In scope",
      "Separate several items with semicolons.", { multiline: true, value: wizard.study.in_scope })
    + textField("out_of_scope", "Deliberately out of scope",
      "Optional, but it is what stops scope creep later.",
      { multiline: true, value: wizard.study.out_of_scope }),
  constraints: () =>
    textField("constraints", "Constraints",
      "Data, compute, time, policy. Semicolons separate items.",
      { multiline: true, value: wizard.study.constraints })
    + textField("success_criteria", "What would count as an answer",
      "Semicolons separate items.", { multiline: true, value: wizard.study.success_criteria }),
  governance: () => `
    <div class="field checkbox-field">
      <label><input type="checkbox" id="w-ethics" ${wizard.study.ethics_applicable ? "checked" : ""}>
        This study needs an ethics approval or a recorded exemption</label>
    </div>
    <div id="ethics-reference" ${wizard.study.ethics_applicable ? "" : "hidden"}>
      ${textField("ethics_reference", "Approval or exemption reference", "",
        { value: wizard.study.ethics_reference })}
    </div>
    ${textField("data_governance", "Where the data comes from and what governs it",
      "Semicolons separate items.", { multiline: true, value: wizard.study.data_governance })}
    ${textField("legal_notes", "Licence or third-party restrictions", "",
      { multiline: true, value: wizard.study.legal_notes })}`,
  responsible: () =>
    textField("approver", "Responsible person",
      "This name is recorded on the study's governance record. Human checkpoints "
      + "are answered at a terminal by a person, never by this browser.",
      { value: wizard.study.approver }),
  providers: () => `<div id="detection-body"><p class="muted-line">Looking for installed
    provider CLIs…</p></div>`,
  assignment: () => `<div id="assignment-body"></div>`,
  preflight: () => `<div id="preflight-body"><p class="muted-line">Checking the
    assignment…</p></div>`,
  preview: () => `<div id="preview-body"><p class="muted-line">Preparing the
    write preview…</p></div>`,
  create: () => `<div id="create-body"></div>`,
};

const STEP_BINDINGS = {
  governance() {
    $("#w-ethics").addEventListener("change", (event) => {
      wizard.study.ethics_applicable = event.target.checked;
      $("#ethics-reference").hidden = !event.target.checked;
    });
  },
  providers: loadDetection,
  assignment: renderAssignmentStep,
  preflight: runPreflight,
  preview: renderWritePreview,
  create: renderCreateStep,
};

function collectFields() {
  $$("[data-field]").forEach(node => { wizard.study[node.dataset.field] = node.value; });
  const ethics = $("#w-ethics");
  if (ethics) wizard.study.ethics_applicable = ethics.checked;
}

function studyPayload() {
  return {
    question: wizard.study.question,
    mode: "GUIDED",
    scope: {
      in_scope: splitItems(wizard.study.in_scope),
      out_of_scope: splitItems(wizard.study.out_of_scope),
    },
    constraints: splitItems(wizard.study.constraints),
    success_criteria: splitItems(wizard.study.success_criteria),
    governance: {
      ethics_applicable: wizard.study.ethics_applicable,
      ethics_reference: wizard.study.ethics_reference || null,
      data_governance: splitItems(wizard.study.data_governance),
      legal_notes: splitItems(wizard.study.legal_notes),
      approver: wizard.study.approver,
    },
  };
}

async function loadDetection() {
  try {
    wizard.detection = await post("/api/providers/detect");
  } catch (error) {
    $("#detection-body").innerHTML = `<p class="error-note">${esc(error.message)}</p>`;
    return;
  }
  const found = wizard.detection.providers.filter(item => item.available);
  $("#detection-body").innerHTML = `
    <p class="muted-line">${esc(wizard.detection.note)}</p>
    <div class="provider-table">
      ${wizard.detection.providers.map(item => `
        <div class="provider-row">
          <b>${esc(item.id)}</b>
          ${statusPill(item.available ? "AVAILABLE" : "NOT FOUND", item.state)}
          <span>${esc(item.state)}</span>
        </div>`).join("")}
    </div>
    ${wizard.detection.unregistered.length ? `<p class="finding">Also on this
      computer, with no entry in providers.yaml:
      ${wizard.detection.unregistered.map(esc).join(", ")}. Adding one is a few
      lines of configuration, not a code change.</p>` : ""}
    ${found.length ? "" : `<p class="finding">No provider CLI was found. You can still
      create the study and configure providers later.</p>`}`;
  if (!Object.keys(wizard.assignment).length) seedAssignment();
}

function seedAssignment() {
  const available = wizard.detection.providers.filter(
    item => item.available && item.kind === "cli");
  const producer = available[0] || wizard.detection.providers[0];
  const second = available.find(item => item.id !== producer?.id) || producer;
  const pick = (provider, role) => ({
    provider: provider?.id || "",
    model: (provider?.models || [])[0] || "",
    effort: null,
  });
  wizard.detection.roles.forEach(role => {
    const provider = ["reviewer", "verification"].includes(role.id) ? second : producer;
    wizard.assignment[role.id] = pick(provider, role.id);
  });
}

async function renderAssignmentStep() {
  if (!wizard.detection) await loadDetection();
  const body = $("#assignment-body");
  const providers = wizard.detection.providers;
  body.innerHTML = `
    <div class="assignment-table">
      ${wizard.detection.roles.map(role => {
        const current = wizard.assignment[role.id] || {};
        const usable = providers.filter(p => p.roles[role.id] !== "blocked");
        const chosen = providers.find(p => p.id === current.provider);
        return `
        <div class="assignment-row">
          <div class="assignment-role"><b>${esc(role.title)}</b>
            <span>${esc(role.id)}</span></div>
          <div class="field">
            <label for="p-${role.id}">Provider</label>
            <select id="p-${role.id}" data-role-provider="${role.id}">
              ${usable.map(p => `<option value="${esc(p.id)}"
                ${p.id === current.provider ? "selected" : ""}>${esc(p.id)}${
                  p.available ? "" : " (not installed)"}</option>`).join("")}
            </select>
          </div>
          <div class="field">
            <label for="m-${role.id}">Model</label>
            <input id="m-${role.id}" type="text" list="models-${esc(role.id)}"
                   data-role-model="${role.id}" value="${esc(current.model || "")}">
            <datalist id="models-${esc(role.id)}">
              ${(chosen?.models || []).map(m => `<option value="${esc(m)}"></option>`).join("")}
            </datalist>
          </div>
        </div>`; }).join("")}
    </div>
    <details class="disclosure">
      <summary>Advanced — reasoning effort</summary>
      <div class="disclosure-body">
        <p>Leave these alone unless you know a provider charges for depth.</p>
        ${wizard.detection.roles.map(role => {
          const current = wizard.assignment[role.id] || {};
          const chosen = providers.find(p => p.id === current.provider);
          if (!chosen?.efforts?.length) return "";
          return `<div class="field">
            <label for="e-${role.id}">${esc(role.title)}</label>
            <select id="e-${role.id}" data-role-effort="${role.id}">
              <option value="">Provider default</option>
              ${chosen.efforts.map(value => `<option value="${esc(value)}"
                ${value === current.effort ? "selected" : ""}>${esc(value)}</option>`).join("")}
            </select></div>`;
        }).join("")}
      </div>
    </details>
    <div id="assignment-verdict"></div>`;
  $$("[data-role-provider]").forEach(node => node.addEventListener("change", () => {
    const role = node.dataset.roleProvider;
    const provider = providers.find(p => p.id === node.value);
    wizard.assignment[role] = {
      provider: node.value,
      model: (provider?.models || [])[0] || "",
      effort: null,
    };
    renderAssignmentStep();
  }));
  $$("[data-role-model]").forEach(node => node.addEventListener("input", () => {
    wizard.assignment[node.dataset.roleModel].model = node.value;
  }));
  $$("[data-role-model]").forEach(node => node.addEventListener("change", previewAssignment));
  $$("[data-role-effort]").forEach(node => node.addEventListener("change", () => {
    wizard.assignment[node.dataset.roleEffort].effort = node.value || null;
    previewAssignment();
  }));
  previewAssignment();
}

async function previewAssignment() {
  const verdict = $("#assignment-verdict");
  if (!verdict) return;
  try {
    const body = await post("/api/providers/preview", { assignment: wizard.assignment });
    const view = body.assignment;
    verdict.innerHTML = `
      <div class="verdict">
        <div><span class="verdict-label">Producer / reviewer separation</span>
          <b>${esc(view.separation.label)}</b></div>
        ${view.separation.note ? `<p class="finding">${esc(view.separation.note)}</p>` : ""}
        ${view.warnings.map(line => `<p class="finding">${esc(line)}</p>`).join("")}
        ${view.manual.map(line => `<p class="finding">${esc(line)}</p>`).join("")}
        ${view.conflicts.map(line => `<p class="error-note">${esc(line)}</p>`).join("")}
      </div>`;
    wizard.assignmentValid = !view.conflicts.length;
    wizardError("");
  } catch (error) {
    verdict.innerHTML = `<p class="error-note">${esc(error.message)}</p>`;
    wizard.assignmentValid = false;
  }
}

async function runPreflight() {
  const body = $("#preflight-body");
  try {
    await post("/api/providers/apply", {
      assignment: wizard.assignment,
      scope: wizard.scope,
      destination: wizard.destination,
    });
    wizard.preflight = await post("/api/preflight", {});
  } catch (error) {
    body.innerHTML = `<p class="error-note">${esc(error.message)}</p>`;
    return;
  }
  body.innerHTML = `
    <p class="muted-line">${esc(wizard.preflight.note)}</p>
    <div class="finding-list">
      ${wizard.preflight.findings.map(item => `
        <div class="finding-row">${statusPill(item.status)}
          <div><b>${esc(item.label)}</b><span>${esc(item.detail)}</span></div>
        </div>`).join("")}
    </div>
    <p class="summary-line">${esc(wizard.preflight.summary)}</p>
    <details class="disclosure" id="probe-block">
      <summary>Advanced — verify the model names with a real call</summary>
      <div class="disclosure-body" id="probe-body">
        <p>A model name is UNVERIFIED until a provider actually accepts it. Verifying
           costs one real call per distinct provider/model, billed to your own
           subscription.</p>
        <button class="button" id="probe-preview" type="button">Show the exact calls</button>
      </div>
    </details>`;
  $("#probe-preview").addEventListener("click", showProbePlan);
}

async function showProbePlan() {
  const body = $("#probe-body");
  try {
    wizard.probe = await post("/api/probe/preview", {});
  } catch (error) {
    body.innerHTML = `<p class="error-note">${esc(error.message)}</p>`;
    return;
  }
  body.innerHTML = `
    <p>${esc(wizard.probe.note)}</p>
    <div class="finding-list">
      ${wizard.probe.calls.map(call => `
        <div class="finding-row"><b>${esc(call.provider)}/${esc(call.model)}</b>
          <div><span>${esc(call.roles.join(", "))}</span>
          <div class="plan-command">${esc(call.command.join(" ") || "manual provider")}</div></div>
        </div>`).join("")}
    </div>
    <p class="summary-line">${wizard.probe.budget} call${wizard.probe.budget === 1 ? "" : "s"}
      will be made. Nothing else will run.</p>
    <button class="button primary" id="probe-run" type="button">
      Approve ${wizard.probe.budget} call${wizard.probe.budget === 1 ? "" : "s"} and probe</button>`;
  $("#probe-run").addEventListener("click", async (event) => {
    event.target.disabled = true;
    event.target.textContent = "Probing…";
    try {
      const result = await post("/api/probe/run", { approved_calls: wizard.probe.budget });
      body.innerHTML = `<div class="finding-list">${result.findings.map(item => `
        <div class="finding-row">${statusPill(item.status)}
          <div><b>${esc(item.label)}</b><span>${esc(item.detail)}</span></div>
        </div>`).join("")}</div>
        <p class="summary-line">${esc(result.summary)}</p>`;
    } catch (error) {
      body.innerHTML = `<p class="error-note">${esc(error.message)}</p>`;
    }
  });
}

async function renderWritePreview() {
  const body = $("#preview-body");
  body.innerHTML = `
    <div class="field">
      <label for="w-destination">Destination folder</label>
      <input id="w-destination" type="text" value="${esc(wizard.destination)}" spellcheck="false">
      <p class="field-hint">The study is created here. An existing run is never
        overwritten, and broad destinations such as a home or repository root are refused.</p>
    </div>
    <div id="preview-result"><p class="muted-line">Checking this destination…</p></div>`;
  $("#w-destination").addEventListener("change", (event) => {
    wizard.destination = event.target.value;
    refreshWritePreview();
  });
  refreshWritePreview();
}

async function refreshWritePreview() {
  const result = $("#preview-result");
  try {
    const body = await post("/api/study/preview", {
      study: studyPayload(), destination: wizard.destination,
    });
    const preview = body.preview;
    wizard.previewOk = true;
    result.innerHTML = `
      <div class="verdict">
        <div><span class="verdict-label">Destination</span><b>${esc(preview.destination)}</b></div>
        <div><span class="verdict-label">Run identity</span><b>${esc(preview.run_id)}</b></div>
        <div><span class="verdict-label">Responsible</span><b>${esc(preview.responsible)}</b></div>
      </div>
      <p class="muted-line">${esc(preview.note)}</p>
      <details class="disclosure"><summary>Files this will create</summary>
        <div class="disclosure-body"><ul class="plain-list">
          ${preview.files.map(name => `<li>${esc(name)}</li>`).join("")}
          ${preview.stamped.map(name => `<li>${esc(name)} <em>(stamped with your answers)</em></li>`).join("")}
        </ul></div></details>`;
  } catch (error) {
    wizard.previewOk = false;
    result.innerHTML = `<p class="error-note">${esc(error.message)}</p>`;
  }
}

function renderCreateStep() {
  $("#create-body").innerHTML = `
    <div class="verdict">
      <div><span class="verdict-label">Destination</span><b>${esc(wizard.destination)}</b></div>
      <div><span class="verdict-label">Question</span><b>${esc(wizard.study.question)}</b></div>
    </div>
    <p>Creating writes the template, stamps your answers into the problem
       statement and governance record, and seals each of them with its own digest.
       No model is called. The first checkpoint will then be waiting for a human
       decision, which is recorded at a terminal — not here.</p>`;
}

async function createStudy() {
  try {
    const body = await post("/api/study/create", {
      study: studyPayload(),
      destination: wizard.destination,
    });
    wizard.created = body;
    await loadState();
    setMode("workspace");
    toast(`Study created at ${body.run}.`);
    announce("The study was created and is open.");
  } catch (error) {
    wizardError(error.message);
  }
}

async function advanceWizard() {
  const step = STEPS[wizard.step];
  collectFields();
  if (["question", "scope", "constraints", "governance", "responsible"].includes(step.id)) {
    try {
      await post("/api/study/validate", { study: studyPayload() });
    } catch (error) {
      if (!isLaterFieldError(step.id, error.message)) {
        wizardError(error.message);
        return;
      }
    }
  }
  if (step.id === "assignment" && wizard.assignmentValid === false) {
    wizardError("Fix the assignment conflict above before continuing.");
    return;
  }
  if (step.id === "preview" && wizard.previewOk === false) {
    wizardError("Choose a destination this study can be written to.");
    return;
  }
  if (step.id === "create") {
    await createStudy();
    return;
  }
  wizard.step = Math.min(wizard.step + 1, STEPS.length - 1);
  renderWizard();
}

/* The validator judges a whole study, so an early step must not be blocked by a
   field two screens away. Only the messages naming this step's own fields stop
   the user here. */
function isLaterFieldError(stepId, message) {
  const owned = {
    question: ["question"],
    scope: ["scope."],
    constraints: ["constraints", "success_criteria"],
    governance: ["governance.ethics", "governance.data_governance", "governance.legal"],
    responsible: ["governance.approver"],
  }[stepId] || [];
  return !owned.some(fragment => message.includes(fragment));
}

document.addEventListener("DOMContentLoaded", () => {
  $("#wizard-next").addEventListener("click", advanceWizard);
  $("#wizard-back").addEventListener("click", () => {
    collectFields();
    wizard.step = Math.max(0, wizard.step - 1);
    renderWizard();
  });
  $("#wizard-cancel").addEventListener("click", () => {
    goHome();
    toast("Cancelled. Nothing was written.");
  });
});
