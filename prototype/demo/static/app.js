/* text2answer graph analysis: demo front end (no framework). */
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fmt = (n) => typeof n === "number" ? (Number.isInteger(n) ? n.toLocaleString() : (Math.abs(n) < 0.01 && n !== 0 ? n.toExponential(3) : n.toLocaleString(undefined, { maximumFractionDigits: 4 }))) : String(n);
  const bytes = (b) => b > 1e9 ? (b / 1e9).toFixed(1) + " GB" : b > 1e6 ? (b / 1e6).toFixed(1) + " MB" : (b / 1e3).toFixed(0) + " kB";
  const TYPE_COLORS = { Graph: "var(--t-graph)", NodeMap: "var(--t-nodemap)", NodeSet: "var(--t-nodeset)", Partition: "var(--t-partition)", Scalar: "var(--t-scalar)", Table: "var(--t-table)", Bool: "var(--t-bool)", Path: "var(--t-path)" };
  const typeOf = (r) => (Object.keys(TYPE_COLORS).find((t) => String(r || "").startsWith(t)) || "Scalar");

  const state = { datasets: [], ds: null, system: "full", card: null, scenes: [], replay: null, static: !!window.T2A_STATIC };

  // ------------------------------------------------------------------ steps ribbon
  function setStep(n) {
    $$(".step").forEach((li) => { const k = +li.dataset.step; li.classList.toggle("current", k === n); li.classList.toggle("done", k < n); });
  }

  // ------------------------------------------------------------------ datasets
  async function loadDatasets() {
    if (state.static) { state.datasets = window.T2A_DATASETS || []; }
    else { state.datasets = await (await fetch("/api/datasets")).json(); }
    const list = $("#ds-list"); list.innerHTML = "";
    const order = { hard: 0, base: 1, upload: 2, scale: 3 };
    state.datasets.sort((a, b) => order[a.tier] - order[b.tier] || a.name.localeCompare(b.name));
    for (const d of state.datasets) {
      const b = document.createElement("button"); b.className = "ds"; b.dataset.path = d.path;
      b.innerHTML = `<span class="n">${esc(d.name)}</span><span class="tier">${esc(d.tier)}</span><span class="f">${esc(d.file)} <span class="sz">· ${bytes(d.bytes)}</span></span>`;
      b.title = d.head.join("\n");
      b.onclick = () => pickDataset(d);
      list.appendChild(b);
    }
  }

  async function pickDataset(d, { silent } = {}) {
    state.ds = d; state.replay = null;
    $$(".ds").forEach((b) => b.classList.toggle("active", b.dataset.path === d.path));
    $("#description").value = d.description || "";
    $("#examples").innerHTML = (d.examples || []).map((q) => `<button class="chip">${esc(q)}</button>`).join("");
    $$("#examples .chip").forEach((c) => c.onclick = () => { $("#question").value = c.textContent; $("#question").focus(); setStep(3); });
    $("#run").disabled = false;
    if (!silent) { $("#result").classList.add("hidden"); }
    setStep(2);
    $("#profile").className = "profile empty"; $("#profile").textContent = "Loading and profiling the file…";
    try {
      let card;
      if (state.static) card = d.card;
      else card = await (await fetch(`/api/profile?path=${encodeURIComponent(d.path)}&name=${encodeURIComponent(d.name)}&description=${encodeURIComponent(d.description || "")}`)).json();
      if (card.error) throw new Error(card.error);
      state.card = card; renderProfile(card);
    } catch (e) { $("#profile").innerHTML = `<div class="error">Could not profile this file: ${esc(e.message)}</div>`; }
  }

  function renderProfile(c) {
    const el = $("#profile"); el.className = "profile";
    const s = c.semantics || {}; const f = c.facts || {};
    const conf = (k) => Math.round(((s.confidence || {})[k] || 0) * 100);
    const bar = (k) => `<div class="conf"><i style="width:${conf(k)}%"></i></div>`;
    const row = (k, label, val, ev) => `<div class="sem-row"><span class="k">${label}</span><div><span class="val">${val}</span>${bar(k)}<div class="ev">${esc(ev || "")} <span class="muted">· confidence ${conf(k)}%</span></div></div></div>`;
    const stats = [["nodes", fmt(c.n_nodes)], ["edges", fmt(c.n_edges)], ["components", fmt(c.n_components_weak)],
      ["max degree", fmt(c.degree?.max)], ["median degree", fmt(c.degree?.median)], ["density", c.density < 0.0005 ? c.density.toExponential(1) : c.density.toFixed(4)]];
    let html = `<div class="stat-row">${stats.map(([l, v]) => `<div class="stat"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("")}</div>`;
    html += `<div class="sem">`;
    html += row("directed", "direction", s.directed ? "directed" : "undirected", s.evidence?.directed);
    html += row("weighted", "weights", s.weighted ? `weighted (${s.weight_semantics || "unknown kind"})` : "none", s.evidence?.weighted || s.evidence?.weight_semantics);
    html += row("multigraph", "repeats", s.multigraph ? "multigraph: repeated rows kept" : "simple graph", s.evidence?.multigraph);
    if (c.is_bipartite) html += `<div class="sem-row"><span class="k">shape</span><div><span class="val">bipartite</span><div class="ev">two disjoint node sets</div></div></div>`;
    if (c.columns) html += `<div class="sem-row"><span class="k">columns</span><div><span class="val mono">${esc(c.columns.header ? c.columns.header.join(", ") : c.columns.note)}</span></div></div>`;
    html += `</div>`;
    if ((s.needs_clarification || []).length) html += `<div class="ask-badge">Would ask: ${esc(s.needs_clarification.join("; "))}</div>`;
    const sample = (f.sample_rows || []).map((r) => r.join(f.header ? "," : " ")).join("\n");
    html += `<details class="more"><summary>raw file facts</summary><div class="head-sample">${esc(sample)}</div>
      <div class="kv" style="margin-top:8px;font-size:12.5px">
        <span class="k">rows</span><span class="v">${fmt(f.rows)}</span>
        <span class="k">distinct pairs</span><span class="v">${fmt(f.distinct_pairs_directed)} directed · ${fmt(f.distinct_pairs_undirected)} undirected</span>
        <span class="k">reciprocity of rows</span><span class="v">${f.reciprocity_of_rows}</span>
        <span class="k">self loops</span><span class="v">${fmt(f.self_loops)}</span>
        ${f.weight_column ? `<span class="k">weight column</span><span class="v">${esc(f.weight_column)} in [${f.weight_range?.map(fmt).join(", ")}]${f.weight_has_fractions ? ", fractional" : ", integer"}</span>` : ""}
        ${f.row_index_column ? `<span class="k">row index</span><span class="v">first column is a running row number (ignored)</span>` : ""}
        <span class="k">ids</span><span class="v">${f.ids_numeric ? "integers" : "string labels"} · e.g. ${esc((c.sample_node_ids || []).slice(0, 4).join(", "))}</span>
      </div></details>`;
    el.innerHTML = html;
  }

  // ------------------------------------------------------------------ ask / run
  let timer = null;
  async function ask() {
    const q = $("#question").value.trim(); if (!q || !state.ds) return;
    if (state.static) { alert("This is a static preview: it replays recorded scenes only. Run demo/server.py for live questions."); return; }
    setStep(4);
    $("#result").classList.add("hidden"); $("#progress-card").classList.remove("hidden");
    $("#prog-title").textContent = `Asking the ${labelOf(state.system)} executor…`;
    const req = { path: state.ds.path, name: state.ds.name, description: $("#description").value.trim(), question: q, system: state.system, model: $("#model").value };
    const r = await (await fetch("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(req) })).json();
    if (r.error) { $("#progress-card").classList.add("hidden"); showError(r.error); return; }
    const stages = r.stages || []; $("#stages").innerHTML = stages.map((s) => `<li>${esc(s)}</li>`).join("");
    const t0 = Date.now(); let i = 0;
    clearInterval(timer);
    timer = setInterval(async () => {
      const el = (Date.now() - t0) / 1000; $("#prog-time").textContent = el.toFixed(0) + " s";
      // the server reports no per-stage progress; advance the indicator on elapsed time as a rough guide
      const guess = Math.min(stages.length - 1, Math.floor(el / 6)); i = Math.max(i, guess);
      $$("#stages li").forEach((li, k) => { li.classList.toggle("done", k < i); li.classList.toggle("active", k === i); });
      const job = await (await fetch(`/api/job/${r.job}`)).json();
      if (job.status === "done") { clearInterval(timer); $("#progress-card").classList.add("hidden"); render(job.result); }
      else if (job.status === "error") { clearInterval(timer); $("#progress-card").classList.add("hidden"); showError(job.error + "\n" + (job.traceback || "")); }
    }, 1000);
  }
  function showError(msg) { $("#result").classList.remove("hidden"); $("#answer").innerHTML = `<div class="error mono">${esc(msg)}</div>`; }
  const labelOf = (s) => ({ full: "typed plan", flat: "tool agent", codegen: "code generation", no_verify: "typed plan (no verifier)", no_interp: "typed plan (no interpretation)", codegen_nofacts: "code generation without facts" }[s] || s);

  // ------------------------------------------------------------------ render a result
  function render(r) {
    $("#result").classList.remove("hidden"); setStep(4);
    renderAnswer(r); renderInterp(r); renderPlan(r); renderFindings(r); renderCost(r);
    $("#result").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function answerHtml(a, kind) {
    if (a === null || a === undefined) return `<div class="big small muted">no answer</div>`;
    if (Array.isArray(a)) {
      if (a.length && typeof a[0] === "object" && a[0] && "node" in a[0]) return `<div class="list">${a.slice(0, 20).map((x, i) => `<span class="pill"><b>${i + 1}</b>${esc(x.node)}<span class="v">${fmt(x.value)}</span></span>`).join("")}</div>`;
      if (a.every((x) => typeof x !== "object")) return `<div class="list">${a.slice(0, 30).map((x, i) => `<span class="pill"><b>${i + 1}</b>${esc(x)}</span>`).join("")}${a.length > 30 ? `<span class="pill">+${a.length - 30} more</span>` : ""}</div>`;
      return `<pre class="code">${esc(JSON.stringify(a, null, 1).slice(0, 2000))}</pre>`;
    }
    if (typeof a === "object") {
      const ents0 = Object.entries(a);
      if (ents0.length && ents0.length <= 6 && ents0.some(([, v]) => typeof v === "object" && v !== null)) {
        return ents0.map(([k, v]) => `<div class="sub"><div class="sub-l">${esc(k.replace(/_/g, " "))}</div>${answerHtml(v)}</div>`).join("");
      }
      if ("path" in a && Array.isArray(a.path)) return `<div class="big small">${a.path.map(esc).join(" → ")}</div><div class="kv">${Object.entries(a).filter(([k]) => k !== "path").map(([k, v]) => `<span class="k">${esc(k)}</span><span class="v">${fmt(v)}</span>`).join("")}</div>`;
      const ents = Object.entries(a);
      if (ents.length <= 6 && ents.every(([, v]) => typeof v !== "object")) return `<div class="stat-row" style="grid-template-columns:repeat(${Math.min(3, ents.length)},1fr)">${ents.map(([k, v]) => `<div class="stat"><div class="v">${typeof v === "boolean" ? (v ? "yes" : "no") : fmt(v)}</div><div class="l">${esc(k)}</div></div>`).join("")}</div>`;
      return `<pre class="code">${esc(JSON.stringify(a, null, 1).slice(0, 2000))}</pre>`;
    }
    if (typeof a === "boolean") return `<div class="big">${a ? "Yes" : "No"}</div>`;
    return `<div class="big">${esc(fmt(a))}</div>`;
  }

  function renderAnswer(r) {
    const el = $("#answer");
    const head = state.replay ? `<div class="replay-banner"><span>Recorded run · ${esc(labelOf(r.system))} · ${esc(r.model || "")}</span><span class="mono">${esc(r.question || "")}</span></div>` : "";
    if (r.error && r.answer == null) { el.innerHTML = head + `<div class="error">${esc(r.error)}</div>`; }
    else el.innerHTML = head + answerHtml(r.answer, r.plan?.answer?.kind);
    const cl = $("#clarification");
    if (r.clarification) { cl.classList.remove("hidden"); cl.innerHTML = `<b>The system asks:</b> ${esc(r.clarification)}`; } else cl.classList.add("hidden");
    $("#explanation").innerHTML = r.explanation ? esc(r.explanation).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>") : "";
    const vs = r.variants || [];
    $("#variants").innerHTML = vs.length ? `<div class="muted" style="font-size:12.5px">Also computed, under other readings of the question:</div>` + vs.map((v) => `<div class="variant"><b>${esc(v.label || "variant")}</b>: ${esc(JSON.stringify(v.answer).slice(0, 300))}</div>`).join("") : "";
  }

  function renderInterp(r) {
    const a = r.assumptions || {}; const el = $("#interp");
    const flag = (v) => typeof v === "boolean" ? `<span class="flag ${v ? "yes" : "no"}">${v ? "yes" : "no"}</span>` : esc(typeof v === "object" ? JSON.stringify(v) : String(v));
    const keys = Object.keys(a).filter((k) => !["tier_notes", "verifier_note"].includes(k));
    el.innerHTML = keys.map((k) => `<span class="k">${esc(k.replace(/_/g, " "))}</span><span class="v">${flag(a[k])}</span>`).join("") || `<span class="muted">none stated</span>`;
    if (a.verifier_note) el.innerHTML += `<span class="k">verifier</span><span class="v">${esc(a.verifier_note)}</span>`;
  }

  function renderPlan(r) {
    const el = $("#plan"); const hint = $("#plan-hint");
    if (r.plan_graph && r.plan_graph.nodes.length) {
      hint.textContent = "typed dataflow the executor ran";
      el.innerHTML = planSvg(r.plan_graph, r.trace || []) + legend() + planNotes(r);
    } else if (typeof r.plan === "string" && r.system.startsWith("codegen")) {
      hint.textContent = "the script the model wrote (no plan to inspect)";
      el.innerHTML = `<pre class="code">${esc(r.plan)}</pre>` + (r.trace?.stdout ? `<details class="more"><summary>script output</summary><pre class="code">${esc(r.trace.stdout)}</pre></details>` : "") + (r.trace?.stderr ? `<details class="more"><summary>stderr</summary><pre class="code">${esc(r.trace.stderr)}</pre></details>` : "");
    } else if (typeof r.trace === "string") {
      hint.textContent = "tool-calling transcript (no plan to inspect)";
      el.innerHTML = transcript(r.trace);
    } else if (r.clarification) {
      hint.textContent = ""; el.innerHTML = `<div class="absent">No plan was executed: the system asked for clarification instead of guessing.</div>`;
    } else { hint.textContent = ""; el.innerHTML = `<div class="absent">No plan available.</div>`; }
  }

  function planNotes(r) {
    const steps = r.plan?.steps || [];
    const notes = steps.filter((s) => s.note).map((s) => `<li><b>${esc(s.id)}</b>${esc(s.note)}</li>`).join("");
    return (notes ? `<ul class="notes">${notes}</ul>` : "") + (r.plan?.rationale ? `<div class="rationale">${esc(r.plan.rationale)}</div>` : "");
  }

  function legend() {
    return `<div class="legend">${Object.entries(TYPE_COLORS).map(([t, c]) => `<span><i style="background:${c}"></i>${t}</span>`).join("")}<span style="margin-left:auto">outlined = answer step</span></div>`;
  }

  // layered dataflow layout
  function planSvg(pg, trace) {
    const nodes = pg.nodes; const edges = pg.edges;
    const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
    const level = {}; const indeg = Object.fromEntries(nodes.map((n) => [n.id, 0]));
    const preds = Object.fromEntries(nodes.map((n) => [n.id, []]));
    for (const e of edges) if (byId[e.from] && byId[e.to]) { preds[e.to].push(e.from); }
    const lv = (id, seen = new Set()) => { if (level[id] != null) return level[id]; if (seen.has(id)) return 0; seen.add(id); const l = preds[id].length ? 1 + Math.max(...preds[id].map((p) => lv(p, seen))) : 0; level[id] = l; return l; };
    nodes.forEach((n) => lv(n.id));
    const cols = {}; nodes.forEach((n) => { (cols[level[n.id]] ||= []).push(n); });
    const W = 184, H = 62, GX = 70, GY = 18, PAD = 8;
    const nCols = Object.keys(cols).length; const maxRows = Math.max(...Object.values(cols).map((c) => c.length));
    const width = nCols * W + (nCols - 1) * GX + PAD * 2; const height = maxRows * H + (maxRows - 1) * GY + PAD * 2;
    const pos = {};
    Object.entries(cols).forEach(([c, ns]) => { const offset = (height - (ns.length * H + (ns.length - 1) * GY)) / 2; ns.forEach((n, i) => { pos[n.id] = { x: PAD + c * (W + GX), y: offset + i * (H + GY) }; }); });
    const t = Object.fromEntries(trace.map((s) => [s.step, s]));
    const argStr = (n) => Object.entries(n.args || {}).filter(([k]) => k !== "graph" || n.args.graph !== "G").map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`).join(" ");
    const trunc = (s, n) => s.length > n ? s.slice(0, n - 1) + "…" : s;
    let svg = `<svg viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="plan dataflow">`;
    svg += `<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="var(--muted)"/></marker></defs>`;
    for (const e of edges) {
      const a = pos[e.from], b = pos[e.to]; if (!a || !b) continue;
      const x1 = a.x + W, y1 = a.y + H / 2, x2 = b.x, y2 = b.y + H / 2; const mx = (x1 + x2) / 2;
      svg += `<path class="edge" marker-end="url(#arr)" d="M${x1} ${y1} C${mx} ${y1}, ${mx} ${y2}, ${x2 - 2} ${y2}"/>`;
      svg += `<text class="edge-label" x="${mx}" y="${(y1 + y2) / 2 - 4}" text-anchor="middle">${esc(e.arg)}</text>`;
    }
    for (const n of nodes) {
      const p = pos[n.id]; const ty = typeOf(n.returns); const col = TYPE_COLORS[ty]; const tr = t[n.id];
      const isAns = (pg.answer_steps || []).includes(n.id);
      svg += `<g class="node ${isAns ? "answer" : ""}" transform="translate(${p.x},${p.y})"><title>${esc(n.op)}: ${esc(n.doc || "")}\n${esc(argStr(n))}\ncost ${esc(n.cost)}</title>`;
      svg += `<rect width="${W}" height="${H}" rx="10"/>`;
      svg += `<rect x="0" y="0" width="6" height="${H}" rx="3" fill="${col}"/>`;
      svg += `<text class="op" x="14" y="20">${esc(n.id)} · ${esc(n.op)}</text>`;
      svg += `<text class="args" x="14" y="36">${esc(trunc(argStr(n), 30))}</text>`;
      svg += `<rect x="${W - 66}" y="${H - 20}" width="58" height="14" rx="7" fill="${col}"/><text class="type" x="${W - 37}" y="${H - 9.5}" text-anchor="middle">${esc(ty.toUpperCase())}</text>`;
      if (tr) svg += `<text class="time" x="14" y="${H - 9}">${tr.seconds >= 1 ? tr.seconds.toFixed(1) + " s" : Math.round(tr.seconds * 1000) + " ms"}${tr.cached ? " · cached" : ""}</text>`;
      svg += `</g>`;
    }
    return svg + `</svg>`;
  }

  function transcript(txt) {
    const parts = txt.split(/\n(?=ASSISTANT:|TOOL:|USER:)/);
    return `<div class="transcript">` + parts.map((p) => {
      const m = p.match(/^(ASSISTANT|TOOL|USER):\s*/); const who = m ? m[1].toLowerCase() : "user"; const body = m ? p.slice(m[0].length) : p;
      return `<div class="bubble ${who}"><div class="who">${who === "assistant" ? "model" : who}</div>${esc(body.trim().slice(0, 1800))}</div>`;
    }).join("") + `</div>`;
  }

  function renderFindings(r) {
    const el = $("#findings"); const f = r.findings;
    if (!Array.isArray(f)) {
      el.innerHTML = `<div class="absent">${r.system === "flat" ? "The tool agent returns an answer with no verification: nothing here can be checked against the question." : r.system?.startsWith("codegen") ? "A script that runs is indistinguishable from a script that is right: there is no verification stage." : "No verification was run."}</div>`;
      return;
    }
    const bad = f.filter((x) => !x.ok && x.severity === "error").length, warn = f.filter((x) => !x.ok && x.severity === "warn").length;
    const verdict = bad ? ["var(--bad)", `${bad} check${bad > 1 ? "s" : ""} failed`] : warn ? ["var(--warn)", `${warn} warning${warn > 1 ? "s" : ""}, no failures`] : ["var(--ok)", `all ${f.length} checks passed`];
    el.innerHTML = `<div class="verdict"><span class="dot" style="background:${verdict[0]}"></span>${verdict[1]}</div><div class="findings">` + f.map((x) => {
      const cls = x.ok ? (x.severity === "info" && /approximate|lower bound|pivots/.test(x.check) ? "info" : "ok") : x.severity;
      const ic = cls === "ok" ? "✓" : cls === "info" ? "i" : "!";
      return `<div class="finding ${cls}"><span class="ic">${ic}</span><div><div>${esc(x.check)}</div><div class="d">${esc(x.detail)}</div></div></div>`;
    }).join("") + `</div>`;
  }

  function renderCost(r) {
    const tiles = [["LLM calls", r.llm_calls ?? 0], ["tokens in", fmt(r.tokens_in ?? 0)], ["tokens out", fmt(r.tokens_out ?? 0)], ["USD", "$" + (r.cost_usd ?? 0).toFixed(3)], ["seconds", (r.seconds ?? 0).toFixed(1)]];
    $("#cost").innerHTML = tiles.map(([l, v]) => `<div class="stat"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");
    const notes = (r.assumptions || {}).tier_notes || [];
    $("#tiers").innerHTML = notes.length ? `<div class="muted" style="background:none;color:var(--muted);padding:0;font-size:12.5px">Cost model decisions:</div>` + notes.map((n) => `<div>${esc(n)}</div>`).join("") : "";
  }

  // ------------------------------------------------------------------ scenes
  async function loadScenes() {
    try { state.scenes = state.static ? (window.T2A_SCENES || []) : await (await fetch("/api/scenes")).json(); } catch { state.scenes = []; }
    const el = $("#scene-list");
    el.innerHTML = state.scenes.length ? state.scenes.map((s, i) => `<div class="scene" data-i="${i}"><span class="sys">${esc(labelOf(s.result?.system || ""))}</span><div class="t">${esc(s.title)}</div><div class="s">${esc(s.subtitle || "")}</div><div class="q">${esc(s.result?.question || "")}</div></div>`).join("") : `<p class="muted">No recorded scenes yet. Run <span class="mono">python3 demo/make_scenes.py</span>.</p>`;
    $$(".scene", el).forEach((d) => d.onclick = () => playScene(state.scenes[+d.dataset.i]));
  }
  function playScene(s) {
    $("#scenes").classList.add("hidden");
    state.replay = s;
    const ds = state.datasets.find((d) => d.name === s.result.dataset) || { name: s.result.dataset, path: "", file: s.result.dataset, examples: [], description: "" };
    $$(".ds").forEach((b) => b.classList.toggle("active", b.dataset.path === ds.path));
    state.ds = ds; $("#run").disabled = !ds.path;
    $("#question").value = s.result.question || ""; $("#description").value = s.description || "";
    $("#examples").innerHTML = "";
    setSystem(s.result.system);
    if (s.card) { state.card = s.card; renderProfile(s.card); } else if (ds.path && !state.static) pickDataset(ds, { silent: true });
    render(s.result);
    if (s.note) $("#answer").insertAdjacentHTML("afterbegin", `<div class="replay-banner" style="margin-bottom:8px"><span>${esc(s.note)}</span></div>`);
  }

  function setSystem(sys) {
    state.system = sys;
    $$(".mode").forEach((b) => b.classList.toggle("active", b.dataset.system === sys));
    const known = $$(".mode").some((b) => b.dataset.system === sys);
    if (!known) $$(".mode").forEach((b) => b.classList.remove("active"));
  }

  // ------------------------------------------------------------------ wiring
  $$(".mode").forEach((b) => b.onclick = () => { setSystem(b.dataset.system); if (state.replay) { const alt = state.scenes.find((s) => s.result.question === state.replay.result.question && s.result.system === b.dataset.system); if (alt) playScene(alt); } });
  $("#run").onclick = ask;
  $("#question").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); } });
  $("#question").addEventListener("focus", () => setStep(3));
  $("#btn-scenes").onclick = () => { $("#scenes").classList.toggle("hidden"); };
  $("#scenes-close").onclick = () => $("#scenes").classList.add("hidden");
  $("#btn-help").onclick = () => $("#help").classList.remove("hidden");
  $("#help-close").onclick = () => { $("#help").classList.add("hidden"); try { localStorage.setItem("t2a_help_seen", "1"); } catch {} };
  $("#help").addEventListener("click", (e) => { if (e.target === $("#help")) $("#help-close").click(); });
  // upload
  const up = $("#upload"), file = $("#file");
  $("#upload-link").onclick = (e) => { e.preventDefault(); file.click(); };
  file.onchange = () => file.files[0] && upload(file.files[0]);
  up.addEventListener("dragover", (e) => { e.preventDefault(); up.classList.add("over"); });
  up.addEventListener("dragleave", () => up.classList.remove("over"));
  up.addEventListener("drop", (e) => { e.preventDefault(); up.classList.remove("over"); if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]); });
  async function upload(f) {
    if (state.static) { alert("Uploads need the live server (python3 demo/server.py)."); return; }
    const r = await (await fetch("/api/upload", { method: "POST", headers: { "X-Filename": f.name }, body: f })).json();
    await loadDatasets(); const d = state.datasets.find((x) => x.path === r.path); if (d) pickDataset(d);
  }

  (async () => {
    await loadDatasets(); await loadScenes();
    let seen = false; try { seen = !!localStorage.getItem("t2a_help_seen"); } catch {}
    if (!seen && !state.static) $("#help").classList.remove("hidden");
    if (state.static && state.scenes.length) playScene(state.scenes[0]);
  })();
})();
