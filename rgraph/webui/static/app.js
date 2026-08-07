/* Shared shell: transport, escaping, the detail drawer, and which mode is on
   screen. Everything that touches the server goes through `api`, and every
   string that came from disk or from a provider goes through `esc`. */

const sessionToken = document.querySelector('meta[name="rgraph-token"]').content;
const ui = {
  app: null,
  state: null,
  artifactFilter: "ALL",
  drawerTrigger: null,
  toastTimer: null,
  mode: "loading",
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
  if (path.startsWith("/api/jobs")) init.headers["X-RGraph-Token"] = sessionToken;
  const response = await fetch(path, init);
  const body = await response.json().catch(() => ({ error: "The local UI returned an unreadable response." }));
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status}).`);
  return body;
}

const post = (path, body) =>
  api(path, { method: "POST", body: JSON.stringify(body || {}) });

function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.add("show");
  clearTimeout(ui.toastTimer);
  ui.toastTimer = setTimeout(() => node.classList.remove("show"), 4200);
}

/* State changes are announced separately from the toast, so a screen reader
   hears them even when the visual notice has already faded. */
function announce(message) {
  const region = $("#live-region");
  region.textContent = "";
  setTimeout(() => { region.textContent = message; }, 30);
}

function statusPill(status, meaning) {
  const title = meaning ? ` title="${esc(meaning)}"` : "";
  return `<span class="status ${statusClass(status)}"${title}>${esc(status)}</span>`;
}

function commandBlock(command) {
  const id = `copy-${Math.random().toString(36).slice(2, 9)}`;
  return `<div class="command-row">
    <div class="plan-command" id="${id}">${esc(command)}</div>
    <button class="button copy-button" type="button" data-copy="${id}">Copy command</button>
  </div>`;
}

function bindCopyButtons(root = document) {
  $$("[data-copy]", root).forEach((button) => {
    button.addEventListener("click", async () => {
      const text = $(`#${button.dataset.copy}`).textContent;
      try {
        await navigator.clipboard.writeText(text);
        button.textContent = "Copied";
        announce("Command copied to the clipboard.");
        setTimeout(() => { button.textContent = "Copy command"; }, 1800);
      } catch {
        toast("The browser refused clipboard access. Select the command and copy it.");
      }
    });
  });
}

function setMode(mode) {
  ui.mode = mode;
  document.body.dataset.mode = mode;
  const panels = { launcher: "#launcher", wizard: "#wizard", demo: "#demo", workspace: "#workspace" };
  Object.entries(panels).forEach(([name, selector]) => {
    const node = $(selector);
    if (node) node.hidden = name !== mode;
  });
  $("#rail").hidden = mode !== "workspace";
  $("#home-button").hidden = mode === "launcher";
  $("#refresh-button").hidden = mode === "wizard";
  $("#brand-sub").textContent = mode === "workspace" ? "local control room" : "local application";
  const panel = $(panels[mode]);
  if (panel) panel.focus({ preventScroll: true });
}

/* ── detail drawer ─────────────────────────────────────────────────────── */

function openDrawer(label, content) {
  const drawer = $("#drawer");
  if (!drawer.classList.contains("open")) ui.drawerTrigger = document.activeElement;
  $("#drawer-label").textContent = label;
  $("#drawer-body").innerHTML = content;
  drawer.inert = false;
  drawer.classList.add("open");
  drawer.setAttribute("aria-hidden", "false");
  $(".skip-link").inert = true;
  $(".page-shell").inert = true;
  $("#scrim").classList.add("open");
  $("#drawer-close").focus();
  bindCopyButtons(drawer);
}

function closeDrawer() {
  const drawer = $("#drawer");
  if (!drawer.classList.contains("open")) return;
  if (typeof stopConsoleStream === "function") stopConsoleStream();
  drawer.classList.remove("open");
  drawer.setAttribute("aria-hidden", "true");
  drawer.inert = true;
  $(".skip-link").inert = false;
  $(".page-shell").inert = false;
  $("#scrim").classList.remove("open");
  const trigger = ui.drawerTrigger;
  ui.drawerTrigger = null;
  if (trigger?.isConnected && typeof trigger.focus === "function") trigger.focus();
}

function keepDrawerFocus(event) {
  const drawer = $("#drawer");
  if (event.key !== "Tab" || !drawer.classList.contains("open")) return;
  const focusable = $$('button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])', drawer)
    .filter(node => !node.inert && node.getClientRects().length);
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  } else if (!drawer.contains(document.activeElement)) {
    event.preventDefault();
    first.focus();
  }
}

/* ── boot ──────────────────────────────────────────────────────────────── */

async function boot() {
  try {
    ui.app = await api("/api/app");
  } catch (error) {
    setMode("launcher");
    $("#entry-list").innerHTML =
      `<li class="entry error-note">${esc(error.message)}</li>`;
    return;
  }
  if (ui.app.mode === "workspace") {
    await loadState();
    setMode("workspace");
  } else {
    renderLauncher(ui.app);
    setMode("launcher");
  }
}

async function goHome() {
  try {
    await post("/api/run/close");
  } catch (error) {
    toast(error.message);
  }
  ui.state = null;
  ui.app = await api("/api/app");
  renderLauncher(ui.app);
  setMode("launcher");
  announce("Returned to the study list.");
}

async function refreshCurrent() {
  if (ui.mode === "workspace") return loadState();
  if (ui.mode === "launcher") {
    ui.app = await api("/api/app");
    renderLauncher(ui.app);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  $("#refresh-button").addEventListener("click", () => refreshCurrent());
  $("#home-button").addEventListener("click", goHome);
  $("#drawer-close").addEventListener("click", closeDrawer);
  $("#scrim").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") closeDrawer();
    else keepDrawerFocus(event);
  });
  $$(`[data-filter]`).forEach(button => button.addEventListener("click", () => {
    ui.artifactFilter = button.dataset.filter;
    $$(`[data-filter]`).forEach(item => item.classList.toggle("active", item === button));
    applyArtifactFilter();
  }));
  boot();
});
