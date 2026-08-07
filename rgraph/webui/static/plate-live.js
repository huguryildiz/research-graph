/* "You are here", drawn onto the reference plate.

   The plate is a hand-drawn reference architecture and stays one: this file
   adds marks on top of it and changes nothing it says. The application injects
   the script when it serves the page, so the committed document — and the copy
   published as a site — remains a drawing with no study behind it.

   Every mark is read from /api/state, the same view the control room reads. If
   there is no study open, or the page was opened outside the application, the
   fetch fails and the plate is left exactly as it was drawn. A plate that
   cannot see a study must not imply one. */

(function () {
  "use strict";

  /* The plate numbers its work plates c1…c12; the graph names the same units
     u01…u12. Checkpoints carry the same code in both, and are drawn on the
     plate as the small pill on the edge they gate. */
  const plateId = (id) => `c${Number(id.slice(1))}`;

  const MARKS = {
    done: { fill: "#2fd39a", ring: null, word: "recorded" },
    now: { fill: "#e5ae45", ring: "#e5ae45", word: "this is the next step" },
    ready: { fill: "#e5ae45", ring: null, word: "waiting on you" },
    problem: { fill: "#e0629b", ring: null, word: "needs attention" },
    wait: { fill: "#55677d", ring: null, word: "not reached yet" },
  };

  /* Position decides as much as status does. A checkpoint at the end of the
     study is AWAITING because nothing has reached it, not because it is waiting
     on the reader — reading those two the same way would put "your turn" on ten
     checkpoints at once. So anything past the current step is "not reached yet"
     unless it is carrying a problem of its own. */
  const place = (index, here) => (index < here ? "before" : index > here ? "after" : "at");

  const unitMark = (unit, where) => {
    if (where === "at") return "now";
    if (unit.state === "COMPLETE") return "done";
    if (["STALE", "FAILED", "CANCELLED", "INTERRUPTED"].includes(unit.state)) return "problem";
    if (where === "after" || unit.state === "BLOCKED") return "wait";
    return "ready";
  };

  const gateMark = (gate, where) => {
    if (where === "at") return "now";
    if (["PASS", "CAVEAT"].includes(gate.status)) return "done";
    if (["FAIL", "STALE", "BLOCKED", "REVISION"].includes(gate.status)) return "problem";
    return where === "after" ? "wait" : "ready";
  };

  const SVGNS = "http://www.w3.org/2000/svg";
  const svgEl = (tag, attrs, parent) => {
    const node = document.createElementNS(SVGNS, tag);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
    if (parent) parent.append(node);
    return node;
  };

  /* The one node the reader is looking for gets more than a dot: a halo the eye
     lands on from across the plate, and the words in full, because a colour
     alone is a legend lookup. */
  function here(box, layer) {
    svgEl("rect", {
      x: box.x - 9, y: box.y - 9, width: box.width + 18, height: box.height + 18,
      rx: 15, fill: MARKS.now.fill, "fill-opacity": .10,
      stroke: MARKS.now.fill, "stroke-width": 2, "stroke-dasharray": "6 4",
      class: "live-halo",
    }, layer);
    const above = box.y > 34;
    const y = above ? box.y - 17 : box.y + box.height + 15;
    const tag = svgEl("g", {}, layer);
    svgEl("rect", {
      x: box.x + box.width / 2 - 42, y: y - 9, width: 84, height: 16, rx: 8,
      fill: "#04060a", stroke: MARKS.now.fill, "stroke-width": 1,
    }, tag);
    const label = svgEl("text", {
      x: box.x + box.width / 2, y: y + 3, "text-anchor": "middle", "font-size": 9,
      fill: MARKS.now.fill, "letter-spacing": ".12em", class: "mono",
    }, tag);
    label.textContent = "YOU ARE HERE";
  }

  function markUnits(state, layer, at) {
    state.units.forEach((unit) => {
      const node = document.querySelector(`[data-node-id="${plateId(unit.id)}"]`);
      if (!node) return;
      const kind = unitMark(unit, place(state.map.spine.findIndex(
        (entry) => entry.id === unit.id), at));
      const box = node.getBBox();
      node.setAttribute("data-live", kind);
      if (kind === "now") here(box, layer);
      svgEl("circle", {
        cx: box.x + box.width - 7, cy: box.y + 8, r: 5.2,
        fill: MARKS[kind].fill, stroke: "#04060a", "stroke-width": 1.6,
      }, layer);
    });
  }

  /* A checkpoint is a pill on the edge it gates, so its mark recolours the pill
     rather than floating beside it — the eye should land on the gate, not on a
     dot that could belong to either end of the arrow. */
  function markGates(state, layer, at) {
    const pills = new Map();
    document.querySelectorAll("#edgelabels .edge-label").forEach((label) => {
      const text = label.querySelector("text");
      if (text) pills.set(text.textContent.trim(), label);
    });
    state.gates.forEach((gate) => {
      const label = pills.get(gate.id);
      if (!label) return;
      const kind = gateMark(gate, place(state.map.spine.findIndex(
        (entry) => entry.id === gate.id), at));
      /* Recoloured from a stylesheet rather than by rewriting the pill's own
         attributes, so hiding the marks restores the drawing exactly. */
      label.setAttribute("data-live", kind);
      if (kind === "now") here(label.getBBox(), layer);
    });
  }

  /* What the study has not reached yet recedes, so the drawing reads as a path
     that stops where the reader stands. Nothing is hidden: this is a dimming,
     and "Hide marks" puts the plate back exactly as it was drawn. */
  const PLATE_CSS = `
    #plate.has-live #nodes>[data-live="wait"]{opacity:.34}
    #plate.has-live #edgelabels>[data-live="wait"]{opacity:.42}
    #plate.has-live #nodes>[data-live="now"]{filter:brightness(1.18)}
    .live-halo{animation:live-breathe 2.6s ease-in-out infinite}
    @keyframes live-breathe{50%{stroke-opacity:.45;fill-opacity:.04}}
    #plate:not(.has-live) #live-marks{display:none}
    #plate:not(.has-live) #nodes>[data-live],
    #plate:not(.has-live) #edgelabels>[data-live]{opacity:1;filter:none}
    @media (prefers-reduced-motion:reduce){.live-halo{animation:none}}
    ${Object.entries(MARKS).map(([kind, mark]) => `
      #plate.has-live #edgelabels>[data-live="${kind}"] rect{stroke:${mark.fill};
        stroke-opacity:.95;stroke-width:${kind === "now" ? 1.8 : 1.2}}
      #plate.has-live #edgelabels>[data-live="${kind}"] text{fill:${mark.fill};
        fill-opacity:1}`).join("")}`;

  const CARD_CSS = `
    #live-card{position:fixed;left:16px;bottom:16px;z-index:5;max-width:330px;
      font-family:var(--sans);color:#e9eef6;background:#05090e;
      border:1px solid #26394d;border-radius:10px;padding:.85rem .95rem;
      box-shadow:0 10px 30px rgba(0,0,0,.65);line-height:1.45}
    #live-card[data-collapsed="true"] .live-body{display:none}
    #live-card h2{font:600 .74rem/1.3 var(--mono);letter-spacing:.13em;
      text-transform:uppercase;color:#8494a8;margin:0 0 .1rem;padding-right:6rem}
    #live-card .live-now{font:600 .95rem/1.3 var(--sans);color:#e5ae45;margin:.35rem 0 .2rem}
    #live-card p{font-size:.76rem;color:#a9b6c6;margin:.3rem 0 0}
    #live-card .live-legend{display:flex;flex-wrap:wrap;gap:.55rem;margin-top:.6rem;
      font:.64rem/1 var(--mono);letter-spacing:.04em;color:#8494a8}
    #live-card .live-legend span{display:flex;align-items:center;gap:.3rem}
    #live-card .live-legend i{width:7px;height:7px;border-radius:50%;display:block}
    /* The next step and a checkpoint merely waiting share a colour on the plate;
       the ring is what separates them there, so it separates them here too. */
    #live-card .live-legend i.is-now{outline:1.4px dashed currentColor;outline-offset:2.4px}
    #live-card .live-limit{font-style:normal;color:#8494a8;font-size:.7rem;
      border-top:1px solid #1b2635;padding-top:.5rem;margin-top:.6rem}
    #live-card button{position:absolute;top:.5rem;right:.55rem;background:none;border:0;
      color:#8494a8;cursor:pointer;font:.62rem/1 var(--mono);letter-spacing:.1em;
      text-transform:uppercase;padding:.35rem}
    #live-card button:hover{color:#e9eef6}
    @media (max-width:767px){#live-card{position:static;max-width:none;margin:1rem;
      box-shadow:none}}`;

  function card(state, plate) {
    const style = document.createElement("style");
    style.textContent = CARD_CSS;
    document.head.append(style);

    const node = document.createElement("aside");
    node.id = "live-card";
    node.dataset.collapsed = "false";
    const legend = ["now", "done", "ready", "problem", "wait"].map((kind) =>
      `<span style="color:${MARKS[kind].fill}"><i class="${kind === "now" ? "is-now" : ""}"
        style="background:${MARKS[kind].fill}"></i><b style="color:#8494a8;font-weight:400"
        >${MARKS[kind].word}</b></span>`).join("");
    node.innerHTML = `
      <h2>Your study on this drawing</h2>
      <button type="button">Hide marks</button>
      <div class="live-body">
        <div class="live-now"></div>
        <p class="live-question"></p>
        <div class="live-legend">${legend}</div>
        <p class="live-limit"></p>
      </div>`;
    node.querySelector(".live-now").textContent =
      `${state.run.id} · ${state.next_action.title || state.next_action.detail}`;
    node.querySelector(".live-question").textContent =
      `${state.summary.units_complete} of ${state.summary.units_total} units recorded. ` +
      `${state.run.question}`;
    node.querySelector(".live-limit").textContent =
      "The drawing is the reference architecture, including a model routing this " +
      "study may not use. Only the marks come from your study. " + state.boundary;
    /* One control, because the marks and the card are one claim: either the
       reader is being shown their study on the plate, or they are looking at
       the reference drawing untouched. */
    const toggle = node.querySelector("button");
    toggle.addEventListener("click", () => {
      const on = plate.classList.toggle("has-live");
      node.dataset.collapsed = on ? "false" : "true";
      toggle.textContent = on ? "Hide marks" : "Show marks";
    });
    document.body.append(node);
  }

  async function paint() {
    let state;
    try {
      const response = await fetch("/api/state", { headers: { Accept: "application/json" } });
      if (!response.ok) return;
      state = await response.json();
    } catch (error) {
      return;
    }
    if (!state || !state.units || !state.run || !state.map) return;
    const nodes = document.getElementById("nodes");
    const plate = document.getElementById("plate");
    if (!nodes || !plate) return;
    const style = document.createElement("style");
    style.textContent = PLATE_CSS;
    document.head.append(style);
    const layer = svgEl("g", { id: "live-marks", "pointer-events": "none" });
    nodes.after(layer);
    const at = state.map.spine.findIndex((entry) => entry.id === state.next_action.target);
    markUnits(state, layer, at);
    markGates(state, layer, at);
    plate.classList.add("has-live");
    card(state, plate);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", paint);
  } else {
    paint();
  }
})();
