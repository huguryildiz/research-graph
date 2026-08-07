/* The execution console.

   Provider output arrives as newline-delimited JSON over a fetch stream, with a
   sequence number on every event. Reconnecting asks for everything after the
   last sequence seen, so a refresh recovers the job and a flaky connection does
   not duplicate a line. Nothing here is inserted as HTML: every byte a provider
   produced is written through `textContent`. */

const consoleState = {
  jobId: null,
  after: 0,
  seen: new Set(),
  controller: null,
  tab: "output",
  job: null,
  timer: null,
  elapsedTimer: null,
};

function stopConsoleStream() {
  if (consoleState.controller) {
    consoleState.controller.abort();
    consoleState.controller = null;
  }
  clearTimeout(consoleState.timer);
  clearInterval(consoleState.elapsedTimer);
  consoleState.timer = null;
  consoleState.elapsedTimer = null;
  consoleState.jobId = null;
}

function consoleShell(job) {
  const tabs = [
    ["output", "Live output"],
    ["summary", "Summary"],
    ["inputs", "Inputs"],
    ["outputs", "Expected outputs"],
    ["result", "Validation"],
  ];
  return `
    <h2 id="drawer-title">${esc(job.target)} · ${esc(job.title || "")}</h2>
    <div class="drawer-meta" id="console-meta"></div>
    <div class="tabs" role="tablist" aria-label="Execution detail">
      ${tabs.map(([key, label]) => `
        <button class="tab" role="tab" type="button" data-tab="${key}"
                aria-selected="${key === consoleState.tab}">${label}</button>`).join("")}
    </div>
    <div class="tab-panel" id="console-panel"></div>
    <div class="drawer-section" id="console-actions"></div>`;
}

/* Elapsed time is the one field that changes without an event, so it ticks on
   its own rather than waiting for the provider to say something. */
function startElapsedTicker() {
  clearInterval(consoleState.elapsedTimer);
  consoleState.elapsedTimer = setInterval(() => {
    const job = consoleState.job;
    const node = $("#console-elapsed");
    if (!node || !job?.active || job.started_at == null) return;
    const seconds = Math.max(0, Math.round(
      (Date.now() - Date.parse(job.started_at)) / 1000));
    node.textContent = `elapsed ${seconds}s`;
  }, 1000);
}

function renderConsoleMeta(job) {
  const elapsed = job.elapsed_seconds == null ? "—" : `${Math.round(job.elapsed_seconds)}s`;
  $("#console-meta").innerHTML = `
    ${statusPill(job.state)}
    <span class="gate-kind">${esc(job.provider)} / ${esc(job.model)}</span>
    <span class="gate-kind" id="console-elapsed">elapsed ${esc(elapsed)}</span>
    <span class="gate-kind">${job.kind === "unit" ? "work unit" : "reviewer"} ${esc(job.target)}</span>`;
  const actions = $("#console-actions");
  const canCancel = job.active;
  actions.innerHTML = `
    ${canCancel ? `<button class="button danger" id="cancel-job" type="button">Stop this execution</button>` : ""}
    <button class="button" id="console-refresh" type="button">Refresh study state</button>
    <p class="muted-line">${esc(job.redaction_note || "")}</p>`;
  const cancel = $("#cancel-job");
  if (cancel) cancel.addEventListener("click", () => cancelJob(job.id, cancel));
  $("#console-refresh").addEventListener("click", () => loadState());
  if (job.active) startElapsedTicker();
  else clearInterval(consoleState.elapsedTimer);
}

function renderConsolePanel(job) {
  const panel = $("#console-panel");
  if (consoleState.tab === "output") {
    if (!panel.querySelector("#console-log")) {
      panel.innerHTML = `<pre class="console-log" id="console-log" tabindex="0"
        aria-label="Provider output"></pre>`;
      consoleState.seen.forEach(() => {});
      (consoleState.lines || []).forEach(line => appendConsoleLine(line));
    }
    return;
  }
  if (consoleState.tab === "summary") {
    panel.innerHTML = `<dl class="handoff-facts">
      ${[
        ["Job", job.id],
        ["Unit or checkpoint", job.target],
        ["Role", job.role || "—"],
        ["Provider / model", `${job.provider} / ${job.model}`],
        ["State", `${job.state}`],
        ["Started", job.started_at || "not started"],
        ["Last event", job.last_event_at || "—"],
        ["Elapsed", job.elapsed_seconds == null ? "—" : `${Math.round(job.elapsed_seconds)}s`],
        ["Exit code", job.exit_code == null ? "still running" : String(job.exit_code)],
        ["Provider log", job.log || "—"],
        ["Process id", job.pid == null ? "—" : String(job.pid)],
      ].map(([term, value]) => `<div><dt>${esc(term)}</dt><dd>${esc(value)}</dd></div>`).join("")}
    </dl>
    <p class="muted-line">${esc(job.log_note || "")}</p>
    ${job.interrupted_note ? `<p class="finding">${esc(job.interrupted_note)}</p>` : ""}`;
    return;
  }
  if (consoleState.tab === "inputs") {
    panel.innerHTML = `<div class="plan-list">${job.inputs.map(item => `
      <div>${esc(item.artifact_id)}<br>${statusPill(item.state)}
        <small>${esc((item.content_hash || "not sealed").slice(0, 23))}</small></div>`).join("")
      || "<p class='muted-line'>No upstream artifact is bound to this execution.</p>"}</div>`;
    return;
  }
  if (consoleState.tab === "outputs") {
    panel.innerHTML = `<ul class="plain-list">${job.expected_outputs.map(
      name => `<li>${esc(name)}</li>`).join("")}</ul>
      <p class="muted-line">A provider exit code of 0 does not make these valid. They are
      checked separately, and the result appears under Validation.</p>`;
    return;
  }
  const validation = job.validation;
  if (!validation) {
    panel.innerHTML = `<p class="muted-line">The process has not finished, so nothing
      has been validated yet.</p>`;
    return;
  }
  panel.innerHTML = `
    <div class="finding-list">
      ${(validation.stages || []).map(stage => `
        <div class="finding-row">${statusPill(stage.status)}
          <div><b>${esc(stage.name)}</b><span>${esc(stage.detail)}</span></div></div>`).join("")}
    </div>
    ${validation.problems.length ? `<ul class="plain-list">${validation.problems.map(
      line => `<li class="finding">${esc(line)}</li>`).join("")}</ul>` : ""}
    ${validation.produced?.length ? `<p>Artifacts now present: ${
      validation.produced.map(esc).join(", ")}.</p>` : ""}
    ${validation.gate_status ? `<p>Checkpoint ${esc(validation.gate)} now reads
      <b>${esc(validation.gate_status)}</b>.</p>` : ""}
    <p class="muted-line">${esc(validation.boundary || "")}</p>`;
}

function appendConsoleLine(text) {
  const log = $("#console-log");
  if (!log) return;
  const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
  const line = document.createElement("div");
  line.textContent = text;          // never innerHTML: provider output is untrusted
  log.append(line);
  while (log.childElementCount > 1200) log.firstElementChild.remove();
  if (atBottom) log.scrollTop = log.scrollHeight;
}

function handleConsoleEvent(event) {
  if (consoleState.seen.has(event.seq) && event.channel !== "job") return;
  consoleState.seen.add(event.seq);
  if (event.seq > consoleState.after) consoleState.after = event.seq;
  consoleState.lines = consoleState.lines || [];
  if (event.channel === "job" && event.job) {
    consoleState.job = event.job;
    renderConsoleMeta(event.job);
    if (consoleState.tab !== "output") renderConsolePanel(event.job);
    announce(`Execution ${event.job.target} is now ${event.job.state}.`);
    loadState();
    return;
  }
  const prefix = event.channel === "output" ? "" : "· ";
  const text = prefix + event.text;
  consoleState.lines.push(text);
  if (consoleState.lines.length > 1200) consoleState.lines.shift();
  appendConsoleLine(text);
  if (event.channel === "state") announce(`Execution state: ${event.text}`);
}

async function openConsole(jobId) {
  stopConsoleStream();
  consoleState.jobId = jobId;
  consoleState.after = 0;
  consoleState.seen = new Set();
  consoleState.lines = [];
  consoleState.tab = "output";
  let job;
  try {
    job = (await api(`/api/jobs/${encodeURIComponent(jobId)}`)).job;
  } catch (error) {
    return toast(error.message);
  }
  consoleState.job = job;
  openDrawer("EXECUTION", consoleShell(job));
  renderConsoleMeta(job);
  renderConsolePanel(job);
  $$("[data-tab]").forEach(button => button.addEventListener("click", () => {
    consoleState.tab = button.dataset.tab;
    $$("[data-tab]").forEach(other =>
      other.setAttribute("aria-selected", String(other === button)));
    $("#console-panel").innerHTML = "";
    renderConsolePanel(consoleState.job);
    if (consoleState.tab === "output") consoleState.lines.forEach(appendConsoleLine);
  }));
  if (job.active) {
    streamConsole(jobId);
  } else {
    const body = await api(`/api/jobs/${encodeURIComponent(jobId)}/events?after=0&stream=0`);
    body.events.forEach(handleConsoleEvent);
  }
}

async function streamConsole(jobId) {
  consoleState.controller = new AbortController();
  try {
    const response = await fetch(
      `/api/jobs/${encodeURIComponent(jobId)}/events?after=${consoleState.after}`,
      { headers: { "X-RGraph-Token": sessionToken }, signal: consoleState.controller.signal },
    );
    if (!response.ok || !response.body) throw new Error(`Stream failed (${response.status}).`);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          handleConsoleEvent(JSON.parse(line));
        } catch {
          /* a partial line is simply retried on the next chunk */
        }
      }
    }
  } catch (error) {
    if (error.name === "AbortError") return;
  }
  if (consoleState.jobId !== jobId) return;
  const job = consoleState.job;
  if (job && job.active) {
    // The server closes a long stream on purpose; resume from where we were.
    consoleState.timer = setTimeout(() => streamConsole(jobId), 400);
  } else {
    try {
      const refreshed = (await api(`/api/jobs/${encodeURIComponent(jobId)}`)).job;
      consoleState.job = refreshed;
      renderConsoleMeta(refreshed);
      if (consoleState.tab !== "output") renderConsolePanel(refreshed);
    } catch {
      /* the study may have been closed */
    }
  }
}

async function startJob(kind, target, approvalToken, button) {
  button.disabled = true;
  button.textContent = "Starting…";
  try {
    const body = await post("/api/jobs", {
      kind, target, approval_token: approvalToken,
    });
    await loadState();
    openConsole(body.job.id);
    announce(`${target} was accepted and queued.`);
  } catch (error) {
    button.disabled = false;
    button.textContent = "Run this exact plan";
    toast(error.message);
  }
}

async function cancelJob(jobId, button) {
  button.disabled = true;
  button.textContent = "Stopping…";
  try {
    const body = await post(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, {});
    consoleState.job = body.job;
    renderConsoleMeta(body.job);
    announce("Cancellation requested.");
  } catch (error) {
    button.disabled = false;
    button.textContent = "Stop this execution";
    toast(error.message);
  }
}
