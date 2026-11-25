/* Session view: follow-up questions on one graph. Live against demo/server.py, or replaying a recorded session. */
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fmt = (n) => typeof n === "number" ? (Number.isInteger(n) ? n.toLocaleString() : (Math.abs(n) < 0.01 && n !== 0 ? n.toExponential(2) : n.toLocaleString(undefined, { maximumFractionDigits: Math.abs(n) >= 1000 ? 1 : 4 }))) : String(n);
  const secs = (s) => s == null ? "" : s === 0 ? "0 s" : s >= 10 ? s.toFixed(0) + " s" : s >= 1 ? s.toFixed(1) + " s" : s >= 0.0995 ? s.toFixed(2) + " s" : Math.max(1, Math.round(s * 1000)) + " ms";
  const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
  const S = { sid: null, rec: null, recIdx: 0, turns: new Map(), ledger: null, card: null, busy: false, datasets: [], name: "", file: "" };

  // ------------------------------------------------------------------ server
  const post = async (path, body) => (await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })).json();
  async function job(path, body, label) {
    setBusy(true, label);
    const t0 = Date.now();
    try {
      const r = await post(path, body);
      if (r.error) throw new Error(r.error);
      for (;;) {
        await new Promise((res) => setTimeout(res, 700));
        const j = await (await fetch(`/api/job/${r.job}`)).json();
        setBusy(true, `${label} · ${((Date.now() - t0) / 1000).toFixed(0)} s`);
        if (j.status === "done") return j.result;
        if (j.status === "error") throw new Error(j.error);
      }
    } finally { setBusy(false); }
  }
  function setBusy(b, label) {
    S.busy = b; $("#run").disabled = b || (!S.sid && !S.rec);
    const st = $("#status"); st.classList.toggle("hidden", !b && !st.dataset.keep);
    if (b) { st.dataset.keep = ""; st.innerHTML = `<span class="spin"></span>${esc(label || "Working")}`; }
  }
  function note(html) { const st = $("#status"); if (html) { st.dataset.keep = "1"; st.classList.remove("hidden"); st.innerHTML = html; } else { st.dataset.keep = ""; st.classList.add("hidden"); } }

  // ------------------------------------------------------------------ graph and ledger
  function renderGraph() {
    const c = S.card; if (!c) return;
    const attrs = Object.entries(c.node_attributes?.attributes || {});
    const s = c.semantics || {};
    $("#graph-info").className = "profile";
    $("#graph-info").innerHTML = `<div class="gi-name">${esc(S.name)}</div><div class="gi-file">${esc(S.file)}</div>
      <div class="stat-row" style="grid-template-columns:repeat(2,1fr)"><div class="stat"><div class="v">${fmt(c.n_nodes)}</div><div class="l">nodes</div></div><div class="stat"><div class="v">${fmt(c.n_edges)}</div><div class="l">${s.directed ? "directed edges" : "edges"}</div></div></div>
      ${attrs.length ? `<div class="muted" style="font-size:12.5px">Node attributes the planner can use</div><div class="attrs">${attrs.map(([k, v]) => `<span class="attr">${esc(k)}<small>${v.type === "categorical" ? fmt(v.n_distinct) + " values" : "numeric"}</small></span>`).join("")}</div>` : `<div class="muted" style="font-size:12.5px">No node attribute table next to this file.</div>`}`;
  }
  function renderLedger() {
    const L = S.ledger, el = $("#ledger"); if (!L || !L.turns) { el.className = "profile empty"; el.textContent = "Nothing asked yet."; return; }
    const tot = L.steps_reused + L.steps_executed || 1;
    const sem = L.accepted_semantics;
    el.className = "profile ledger";
    el.innerHTML = `<div class="ledger-bar" role="img" aria-label="${L.steps_reused} steps reused, ${L.steps_executed} executed"><div class="r" style="width:${100 * L.steps_reused / tot}%"></div><div class="x" style="width:${100 * L.steps_executed / tot}%"></div></div>
      <div class="ledger-cap"><span><b>${L.steps_reused}</b> steps reused</span><span><b>${L.steps_executed}</b> executed</span></div>
      <div class="stat-row">
        <div class="stat saved"><div class="v">${secs(L.seconds_saved)}</div><div class="l">computation not repeated</div></div>
        <div class="stat"><div class="v">${secs(L.execute_seconds)}</div><div class="l">computation run</div></div>
        <div class="stat"><div class="v">${L.answered}</div><div class="l">turns answered</div></div>
        <div class="stat"><div class="v">$${(L.cost_usd || 0).toFixed(L.cost_usd < 0.1 ? 3 : 2)}</div><div class="l">${plural(L.llm_calls, "model call")}</div></div>
      </div>
      <div class="inforce">
        ${sem ? `<div>Reading of the graph: <b>${sem.directed ? "directed" : "undirected"}${sem.weighted ? ", weighted" : ""}</b></div>` : ""}
        ${L.scope_choice ? `<div>Group restrictions: <b>reading ${esc(L.scope_choice.reading)}</b>, chosen in turn ${L.scope_choice.turn}</div>` : ""}
        <div><b>${fmt(L.stored_results)}</b> results kept for reuse</div>
        ${L.turns_replayed ? `<div><b>${plural(L.turns_replayed, "turn")}</b> replayed without asking the model</div>` : ""}
        ${L.tokens_cache_read ? `<div><b>${Math.round(100 * L.tokens_cache_read / Math.max(1, L.tokens_in))}%</b> of the tokens read came from the prompt cache</div>` : ""}
        ${(L.data_changes || []).map((c) => `<div class="chg">Before turn ${c.before_turn} the ${esc((c.changed || []).join(" and "))} changed${c.edges ? `: ${fmt(c.edges[0])} to ${fmt(c.edges[1])} edges` : ""}; earlier results were dropped</div>`).join("")}
        ${L.outcomes && L.outcomes["answer by code"] ? `<div><b>${plural(L.outcomes["answer by code"], "answer")}</b> by generated code</div>` : ""}
        ${L.outcomes && (L.outcomes.unsupported || L.outcomes.unconfirmed) ? `<div><b>${plural((L.outcomes.unsupported || 0) + (L.outcomes.unconfirmed || 0), "request")}</b> declined, with the reason</div>` : ""}
        ${(L.conventions || []).map((c) => `<div class="chg">${esc(c)}</div>`).join("")}
      </div>`;
    $("#btn-audit").disabled = false;
  }

  // ------------------------------------------------------------------ answers
  function answerHtml(a) {
    if (a === null || a === undefined) return `<div class="muted">no answer yet</div>`;
    if (Array.isArray(a)) {
      if (a.length && typeof a[0] === "object" && a[0] && "node" in a[0]) {
        const pill = (x, i) => `<span class="pill"><b>${i + 1}.</b>${esc(x.node)}<span class="v">${esc(typeof x.value === "number" ? fmt(x.value) : x.value)}</span></span>`;
        const head = a.slice(0, 10).map(pill).join(""), rest = a.slice(10, 50).map((x, i) => pill(x, i + 10)).join("");
        return `<div class="list">${head}${rest ? `<details class="rest"><summary>${a.length - 10} more</summary>${rest}</details>` : ""}</div>`;
      }
      if (a.length && typeof a[0] === "object" && a[0] && "value" in a[0]) {
        const cols = Object.keys(a[0]);
        return `<table class="audit"><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr>${a.slice(0, 12).map((r) => `<tr>${cols.map((c) => `<td>${esc(typeof r[c] === "number" ? fmt(r[c]) : r[c])}</td>`).join("")}</tr>`).join("")}</table>`;
      }
      if (a.every((x) => typeof x !== "object")) return `<div class="list">${a.slice(0, 30).map((x, i) => `<span class="pill"><b>${i + 1}.</b>${esc(x)}</span>`).join("")}</div>`;
      return `<pre class="code">${esc(JSON.stringify(a, null, 1).slice(0, 1500))}</pre>`;
    }
    if (typeof a === "object") {
      const ents = Object.entries(a);
      if (ents.some(([, v]) => typeof v === "object" && v !== null)) return ents.map(([k, v]) => `<div class="sub"><div class="sub-l">${esc(k.replace(/_/g, " "))}</div>${answerHtml(v)}</div>`).join("");
      return `<div class="list">${ents.map(([k, v]) => `<span class="pill"><b>${esc(k)}</b>${esc(typeof v === "number" ? fmt(v) : v)}</span>`).join("")}</div>`;
    }
    return `<div class="big">${esc(typeof a === "boolean" ? (a ? "Yes" : "No") : fmt(a))}</div>`;
  }

  // ------------------------------------------------------------------ plan drawing: reused versus executed
  function planSvg(pg, status) {
    const nodes = pg.nodes, byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
    const preds = Object.fromEntries(nodes.map((n) => [n.id, []]));
    for (const e of pg.edges) if (byId[e.from] && byId[e.to]) preds[e.to].push(e.from);
    const level = {}; const lv = (id) => level[id] ?? (level[id] = preds[id].length ? 1 + Math.max(...preds[id].map(lv)) : 0);
    nodes.forEach((n) => lv(n.id));
    const cols = {}; nodes.forEach((n) => (cols[level[n.id]] ||= []).push(n));
    const W = 190, H = 64, GX = 54, GY = 12, PAD = 6;
    const nC = Object.keys(cols).length, maxR = Math.max(...Object.values(cols).map((c) => c.length));
    const width = nC * W + (nC - 1) * GX + PAD * 2, height = maxR * H + (maxR - 1) * GY + PAD * 2;
    const pos = {};
    Object.entries(cols).forEach(([c, ns]) => { const off = (height - (ns.length * H + (ns.length - 1) * GY)) / 2; ns.forEach((n, i) => { pos[n.id] = { x: PAD + c * (W + GX), y: off + i * (H + GY) }; }); });
    const argStr = (n) => Object.entries(n.args || {}).filter(([k, v]) => !(k === "graph" && v === "G")).map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`).join(" ");
    const trunc = (s, k) => s.length > k ? s.slice(0, k - 1) + "…" : s;
    const uid = "a" + Math.random().toString(36).slice(2, 8);
    let svg = `<svg viewBox="0 0 ${width} ${height}" width="${width}" style="max-width:none" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="plan: reused and executed steps">`;
    svg += `<defs><marker id="${uid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="var(--muted)"/></marker></defs>`;
    for (const e of pg.edges) {
      const a = pos[e.from], b = pos[e.to]; if (!a || !b) continue;
      const x1 = a.x + W, y1 = a.y + H / 2, x2 = b.x, y2 = b.y + H / 2, mx = (x1 + x2) / 2;
      svg += `<path class="pedge" marker-end="url(#${uid})" d="M${x1} ${y1} C${mx} ${y1}, ${mx} ${y2}, ${x2 - 2} ${y2}"/><text class="pedge-l" x="${mx}" y="${(y1 + y2) / 2 - 4}" text-anchor="middle">${esc(e.arg)}</text>`;
    }
    for (const n of nodes) {
      const p = pos[n.id], st = status[n.id] || { cls: "", text: "" };
      const ans = (pg.answer_steps || []).includes(n.id);
      svg += `<g class="pnode ${st.cls} ${ans ? "answer" : ""}" transform="translate(${p.x},${p.y})"><title>${esc(n.op)}: ${esc(n.doc || "")}\n${esc(argStr(n))}${st.key ? "\nlineage key " + st.key : ""}</title>
        <rect class="box" width="${W}" height="${H}" rx="10"/>
        <text class="op" x="12" y="20">${esc(trunc(n.op, 22))}</text><text class="ty" x="${W - 10}" y="20" text-anchor="end">${esc(n.returns)}</text>
        <text class="args" x="12" y="36">${esc(trunc(argStr(n) || "whole graph", 31))}</text>
        <text class="st" x="12" y="54">${esc(st.text)}</text></g>`;
    }
    return svg + `</svg>`;
  }
  const traceStatus = (t) => Object.fromEntries((t.trace || []).map((r) => [r.step, r.cached
    ? { cls: "reused", key: r.key, text: `reused${r.from_turn ? " from turn " + r.from_turn : ""} · saved ${secs(r.seconds_saved)}` }
    : { cls: "ran", key: r.key, text: `executed · ${secs(r.seconds)}` }]));
  const previewStatus = (c) => Object.fromEntries((c.preview?.steps || []).map((r) => [r.step, r.reuse
    ? { cls: "reused", key: r.key, text: `would be reused · saves ${secs(r.seconds_saved)}` } : { cls: "pending", key: r.key, text: "would be executed" }]));

  // ------------------------------------------------------------------ a turn
  const OUT = { "exact reuse": ["exact", "Exact reuse"], "partial reuse": ["partial", "Partial reuse"], recompute: ["recompute", "Computed"], clarify: ["clarify", "Needs your choice"], error: ["error", "Error"], "both readings shown": ["partial", "Both readings"],
    unsupported: ["unsupported", "Not supported"], "answer by code": ["bycode", "Answered by code"], unconfirmed: ["unsupported", "Not confirmed"] };
  const INTENT = { new: "new analysis", patch: "plan patch", drill_down: "drill-down", ambiguous: "ambiguous" };
  const READING = { A: "whole-graph scores, group members kept", B: "recomputed inside the group" };

  function turnHtml(t) {
    const [ocls, olabel] = OUT[t.outcome] || ["recompute", t.outcome];
    const meta = [];
    if (t.intent) meta.push(`<span class="tag2"><b>${esc(INTENT[t.intent] || t.intent)}</b>${t.patch?.type && t.intent !== "new" ? " · " + esc(t.patch.type) : ""}</span>`);
    if (t.based_on) meta.push(`<span class="tag2">builds on turn <b>${t.based_on}</b></span>`);
    if (t.reading) meta.push(`<span class="tag2">reading <b>${t.reading}</b>: ${READING[t.reading]}</span>`);
    let body = "";
    const refs = Object.entries(t.references || {});
    if (refs.length) body += `<div class="refs">${refs.map(([k, v]) => `<q>${esc(k)}</q> is read as ${esc(v)}`).join("<br>")}</div>`;
    if (t.error) body += `<div class="error">${esc(t.error)}</div>`;
    const code = t.code && t.code.scripts ? t.code : null;
    if (t.pending) body += contractsHtml(t);
    else if (t.outcome === "unsupported") body += `<div class="grade none"><b>No answer was computed.</b> No combination of the operators computes exactly what was asked, and the system does not answer an easier question in its place.<div class="why">${esc(t.unsupported || "")}</div></div>`;
    else if (t.trace) {
      if (code) body += codeGrade(t, code);
      if (t.outcome !== "unconfirmed") body += `<div class="answer">${answerHtml(t.answer)}</div>`;
      if (t.explanation && t.outcome !== "unconfirmed") body += `<div class="explanation">${esc(t.explanation).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")}</div>`;
      if (t.contracts && !t.pending) body += chosenHtml(t);
      body += `<div class="reuse-line">
        <span class="seg"><span class="key reused"></span><b>${t.steps_reused}</b> reused${t.steps_reused ? `, <b>${secs(t.seconds_saved)}</b> of computation not repeated` : ""}</span>
        <span class="seg"><span class="key ran"></span><b>${t.steps_executed}</b> executed${t.steps_executed ? ` in <b>${secs(t.execute_seconds)}</b>` : ""}</span></div>`;
      if (t.plan_graph) body += `${code ? `<div class="plan-cap">Inputs prepared by checked operators, then handed to the generated code</div>` : ""}<div class="plan-wrap">${planSvg(t.plan_graph, traceStatus(t))}</div>`;
      if ((t.conventions || []).length) body += `<div class="convention"><b>How the file was read</b>${t.conventions.map(esc).join("<br>")}</div>`;
    } else if (t.clarification) body += `<div class="clarify-q">${esc(t.clarification)}</div>`;
    const rules = (t.reuse_findings || []);
    if (rules.length) body += `<div class="rules">${rules.map((f) => `<div class="rule ${f.ok ? "" : "warn"}"><span class="ic">${f.ok ? "i" : "!"}</span><div><b>${esc(f.check.replace(/_/g, " "))}</b>${esc(f.detail)}</div></div>`).join("")}</div>`;
    const f = t.findings || [], bad = f.filter((x) => !x.ok && x.severity === "error").length, warn = f.filter((x) => !x.ok && x.severity === "warn").length;
    const ver = !t.trace ? "" : code ? `<span class="${code.agree ? "warn" : "bad"}">${code.agree ? "answer by code: cross-checked, not verified by operators" : "the two functions disagree"}</span>` : bad ? `<span class="bad">${plural(bad, "check")} failed</span>` : warn ? `<span class="warn">${plural(warn, "verifier warning")}</span>` : `<span class="ok">verified: ${plural(f.length, "check")} passed</span>`;
    const other = t.reading === "A" ? "B" : t.reading === "B" ? "A" : null;
    const foot = `<div class="turn-foot">${ver}${t.trace && !t.steps_executed ? `<span>checked again although nothing was executed</span>` : ""}
      ${t.seconds != null ? `<span>planning and run ${secs(t.seconds)} · ${plural(t.llm_calls || 0, "model call")}</span>` : ""}<span class="sp"></span>
      ${other && t.trace ? `<button class="link" data-act="reading" data-reading="${other}">Show reading ${other} instead</button>` : ""}
      ${t.plan?.steps?.length && t.trace && !code ? `<button class="link" data-act="edit">Edit plan</button>` : ""}
      ${code ? `<button class="link" data-act="code">Generated code</button>` : ""}
      ${t.trace ? `<button class="link" data-act="steps">Step record</button>` : ""}</div>`;
    return `<div class="turn-head"><div class="turn-no">${t.turn}</div><div><div class="turn-q">${esc(t.question)}</div><div class="turn-meta">${meta.join("")}</div></div><span class="outcome ${ocls}">${olabel}</span></div>
      <div class="turn-body">${body}</div>${foot}`;
  }

  // a turn outside the catalogue: what was checked, and the grade of the answer
  function codeGrade(t, c) {
    const n = (t.trace || []).length;
    if (c.agree) return `<div class="grade code"><b>Answer by code.</b> No operator computes this, so the value comes from generated code. ${n ? `Its inputs were prepared by ${plural(n, "checked step")}; the code did not read the file.` : ""} Two functions written separately gave the same value. A wrong reading of the question would pass this check: treat it as a lower grade than an operator answer.<div class="why">${esc(t.unsupported || "")}</div></div>`;
    const cands = c.scripts.map((r, i) => `<div class="cand"><span>function ${i + 1}</span>${r.ok ? `<code>${esc(JSON.stringify(r.value).slice(0, 160))}</code>` : `<i>${esc(r.error || "no result")}</i>`}</div>`).join("");
    return `<div class="grade none"><b>No answer is given.</b> No operator computes this, and the two functions written for it did not give the same value, so neither is shown as the answer.<div class="cands">${cands}</div><div class="why">${esc(t.unsupported || "")}</div></div>`;
  }
  function codeRecord(t) {
    const c = t.code;
    modal(`Turn ${t.turn}: generated code`, `<p class="muted">The task below was written by the planner and handed to two writers that did not see each other. Each function ran in its own process on the same prepared inputs.</p>
      <h4>Task statement</h4><p>${esc(c.task || "")}</p>
      <h4>Inputs</h4><div class="mono small">${(c.input_lines || []).map(esc).join("<br>")}</div>
      ${c.scripts.map((r, i) => `<h4>Function ${i + 1} <small class="muted">${r.ok ? "value " + esc(JSON.stringify(r.value).slice(0, 120)) : "failed"} · ${secs(r.seconds)}${r.repaired ? " · repaired once" : ""}</small></h4>
        <div class="muted small">${esc(r.method || r.error || "")}</div><pre class="code">${esc(r.code)}</pre>`).join("")}`);
  }

  function contractCard(t, c, i, pending) {
    const p = c.preview || {};
    const recorded = S.rec && pending ? S.rec.steps[S.recIdx]?.index : null;
    const chosen = !pending && t.reading === c.reading;
    return `<div class="contract ${chosen ? "chosen" : !pending ? "dim" : ""}">
      <h4><span class="letter">${esc(c.reading)}</span>${esc(READING[c.reading] || "")}<small>${c.source === "planner" ? "as the planner wrote it" : "derived by the engine"}</small></h4>
      <p>${esc(c.contract)}</p>
      <div class="cwhat">${pending ? "If chosen" : "At the time of the choice"}: ${plural(p.reused ?? 0, "step")} reused, ${plural(p.to_execute ?? 0, "step")} executed</div>
      <div class="csteps">${(p.steps || []).map((r) => `<div class="cstep ${r.reuse ? "reuse" : ""}"><span>${r.reuse ? "reuse" : "execute"}</span><span>${esc(r.op)}</span><span>${r.reuse ? "saves " + secs(r.seconds_saved) : ""}</span></div>`).join("")}</div>
      ${pending ? `<button class="primary" data-act="choose" data-i="${i}" ${S.rec && recorded !== i ? `disabled title="The recorded session continues with the other reading"` : ""}>Use reading ${esc(c.reading)}</button>` : chosen ? `<div class="cwhat" style="color:var(--accent-ink)">Chosen</div>` : ""}
    </div>`;
  }
  const contractsHtml = (t) => `<div class="clarify-q">This request has two readings that give different answers. Nothing has been computed for it yet: pick one.</div><div class="contracts">${t.contracts.map((c, i) => contractCard(t, c, i, true)).join("")}</div>`;
  const chosenHtml = (t) => `<details class="more"><summary>The two readings that were offered</summary><div class="contracts" style="margin-top:8px">${t.contracts.map((c, i) => contractCard(t, c, i, false)).join("")}</div></details>`;

  function showTurn(t) {
    S.turns.set(t.turn, t);
    $("#intro")?.remove();
    let el = $(`#turn-${t.turn}`);
    if (!el) { el = document.createElement("section"); el.className = "card turn"; el.id = `turn-${t.turn}`; $("#timeline").appendChild(el); }
    el.innerHTML = turnHtml(t);
    $$("[data-act]", el).forEach((b) => b.onclick = () => act(t.turn, b.dataset));
    el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
  function apply(r) { S.ledger = r.ledger; showTurn(r.turn); renderLedger(); if (r.turn.reading && r.turn.contracts) compareNote(r.turn); }

  // the turn that reruns a request under the other reading: say how far the two answers differ
  function compareNote(t) { /* placeholder for symmetric notes on choose; the comparison is added when the other reading is shown */ }
  function compareWith(t, of) {
    const nodesOf = (x) => Array.isArray(x) ? (x.length && x[0] && typeof x[0] === "object" && "node" in x[0] ? x.map((r) => r.node) : null) : x && typeof x === "object" ? Object.values(x).map(nodesOf).find(Boolean) || null : null;
    const a = nodesOf(S.turns.get(of)?.answer) || [], b = nodesOf(t.answer) || []; const k = Math.min(a.length, b.length); if (!k) return;
    const shared = a.slice(0, k).filter((x) => b.slice(0, k).includes(x)).length;
    const el = $(`#turn-${t.turn} .turn-body`);
    el.insertAdjacentHTML("afterbegin", `<div class="compare">Compared with turn ${of} (reading ${esc(S.turns.get(of).reading)}): the two top-${k} lists${t.answer && !Array.isArray(t.answer) ? " (first part of the answer)" : ""} share <b>${shared} of ${k}</b> nodes${shared === k ? (JSON.stringify(a.slice(0, k)) === JSON.stringify(b.slice(0, k)) ? ", in the same order" : ", in a different order") : ""}. Reusing one for the other would have returned a different answer.</div>`);
  }

  // ------------------------------------------------------------------ actions
  async function act(turnNo, d) {
    if (S.busy) return;
    const t = S.turns.get(turnNo);
    if (d.act === "steps") return stepRecord(t);
    if (d.act === "code") return codeRecord(t);
    if (d.act === "edit") return editPlan(t);
    try {
      if (S.rec) {
        const st = S.rec.steps[S.recIdx];
        if (!st || !((d.act === "choose" && st.kind === "choose") || (d.act === "reading" && st.kind === "reading" && st.of_turn === turnNo))) { note("The recorded session does not include this step. Start a live session to try it."); return; }
        return advance();
      }
      if (d.act === "choose") apply(await job("/api/session/choose", { sid: S.sid, turn: turnNo, index: +d.i }, "Running the chosen reading"));
      if (d.act === "reading") { const r = await job("/api/session/reading", { sid: S.sid, turn: turnNo, reading: d.reading }, `Running reading ${d.reading}`); apply(r); compareWith(r.turn, turnNo); }
    } catch (e) { note(`<span class="error">${esc(e.message)}</span>`); }
  }

  async function ask() {
    if (S.busy) return;
    if (S.rec) return advance();
    const q = $("#question").value.trim(); if (!q || !S.sid) return;
    $("#question").value = "";
    try { apply(await job("/api/session/ask", { sid: S.sid, question: q, explain: true }, "Planning against the session, then running")); }
    catch (e) { note(`<span class="error">${esc(e.message)}</span>`); }
  }

  // ------------------------------------------------------------------ recorded session
  async function advance() {
    const st = S.rec.steps[S.recIdx]; if (!st) return;
    setBusy(true, st.kind === "ask" ? "Replaying the recorded turn" : "Replaying"); await new Promise((r) => setTimeout(r, 350)); setBusy(false);
    S.recIdx++;
    if (st.kind === "event") { showEvent(st); return recPrompt(); }
    apply({ turn: st.turn, ledger: st.ledger });
    if (st.kind === "reading") compareWith(st.turn, st.of_turn);
    recPrompt();
  }
  function showEvent(st) {
    $("#intro")?.remove();
    const el = document.createElement("section"); el.className = "card event";
    el.innerHTML = `<span class="ev-ic" aria-hidden="true">+</span><div><b>The data changed</b><div>${esc(st.text)}</div></div>`;
    $("#timeline").appendChild(el); el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
  function recPrompt() {
    const st = S.rec.steps[S.recIdx], q = $("#question"), run = $("#run");
    q.readOnly = true; $("#examples").innerHTML = "";
    const say = (x) => x ? `<div class="say">${esc(x)}</div>` : "";
    const prev = S.rec.steps[S.recIdx - 1];
    if (!st) { q.value = ""; q.placeholder = "End of the recorded session. Pick a graph on the left to ask your own questions."; run.disabled = true; note(S.rec.close ? say(S.rec.close) : ""); return; }
    run.disabled = false;
    const where = `<div class="where">Recorded session · step ${S.recIdx + 1} of ${S.rec.steps.length} · model ${esc(S.rec.model)}</div>`;
    if (st.kind === "event") { q.value = ""; q.placeholder = "Next: the edge file changes"; run.textContent = "Next"; note(where + say(prev?.say)); return; }
    if (st.kind === "ask") { q.value = st.question; run.textContent = "Ask"; note(where + say(prev && prev.kind !== "ask" && prev.kind !== "event" ? "" : prev?.say)); }
    else if (st.kind === "choose") { q.value = ""; q.placeholder = "Choose a reading on the card above"; run.textContent = "Next"; note(`The recorded user picks reading <b>${esc(st.turn.reading)}</b>: use the button on the card above, or Next.`); }
    else { q.value = ""; q.placeholder = `Then: show reading ${st.reading} for the same request`; run.textContent = "Next"; note(`The recorded user then looks at reading <b>${esc(st.reading)}</b> of the same request, to see how far the answers differ.`); }
  }
  async function loadRecorded() {
    let recs = [];
    try { recs = window.T2A_SESSIONS || await (await fetch("/api/session/recorded")).json(); if (!Array.isArray(recs)) recs = []; } catch { recs = []; }
    if (!recs.length) { try { const idx = await (await fetch("../sessions/index.json")).json(); recs = await Promise.all(idx.map(async (f) => (await fetch("../sessions/" + f)).json())); } catch { recs = []; } }
    return recs;
  }
  function playRecorded(rec) {
    S.rec = rec; S.recIdx = 0; S.sid = null; S.turns.clear(); S.card = rec.card; S.name = rec.name; S.file = rec.file; S.ledger = null;
    $("#timeline").innerHTML = `<section class="card intro" id="intro"><h2>${esc(rec.title)}</h2><p>A recorded session, replayed without calling a model. Every plan, timing and result on this page is what the system produced on the real graph; press <b>Ask</b> to step through it.</p></section>`;
    $$(".ds").forEach((b) => b.classList.remove("active"));
    renderGraph(); renderLedger(); recPrompt();
  }

  // ------------------------------------------------------------------ live session
  async function loadDatasets() {
    try { S.datasets = await (await fetch("/api/datasets")).json(); } catch { S.datasets = []; }
    if (!Array.isArray(S.datasets)) S.datasets = [];
    $("#ds-list").innerHTML = S.datasets.map((d, i) => `<button class="ds" data-i="${i}"><span class="n">${esc(d.name)}</span><span class="tier">${esc(d.tier)}</span><span class="f">${esc(d.file)}</span></button>`).join("");
    $$("#ds-list .ds").forEach((b) => b.onclick = () => startLive(S.datasets[+b.dataset.i], b));
    return S.datasets.length > 0;
  }
  async function startLive(d, btn) {
    if (S.busy) return;
    $$(".ds").forEach((b) => b.classList.toggle("active", b === btn));
    try {
      const r = await job("/api/session/start", { path: d.path, name: d.name, description: d.description || "", model: $("#model").value }, `Loading ${d.name} and starting a session`);
      S.rec = null; S.sid = r.sid; S.card = r.card; S.name = d.name; S.file = d.file; S.ledger = r.ledger; S.turns.clear();
      $("#timeline").innerHTML = ""; renderGraph(); renderLedger();
      const q = $("#question"); q.readOnly = false; q.value = ""; q.placeholder = "Ask about this graph, then follow up"; $("#run").textContent = "Ask"; $("#run").disabled = false; note("");
      const attrs = Object.entries(r.card.node_attributes?.attributes || {}).filter(([, v]) => v.type === "categorical" && v.n_distinct > 2);
      const a = attrs[0]?.[0], v = attrs[0]?.[1]?.top_values?.[0]?.value;
      const ex = ["Who are the 10 most influential nodes?", "Show the top 20 instead.", ...(a ? [`Which ${a} is each of them from?`, `Who is most influential within ${a} "${v}"?`] : ["How many communities are there?"])];
      // a scripted graph: its questions in order, and its file changes as a button (the session itself is not told)
      S.script = r.script?.length ? r.script : ex.map((x) => ({ ask: x }));
      $("#examples").innerHTML = S.script.map((x) => x.event ? `<button class="chip change">Change the data file</button>` : `<button class="chip">${esc(x.ask)}</button>`).join("");
      $$("#examples .chip").forEach((c) => c.onclick = () => c.classList.contains("change") ? changeData(c) : (q.value = c.textContent, q.focus()));
    } catch (e) { note(`<span class="error">${esc(e.message)}</span>`); }
  }

  async function changeData(btn) {
    if (S.busy || !S.sid) return;
    try { const r = await job("/api/session/event", { sid: S.sid }, "Changing the edge file on disk"); showEvent(r.event); btn.remove(); note(""); }
    catch (e) { note(`<span class="error">${esc(e.message)}</span>`); }
  }

  // ------------------------------------------------------------------ modals: step record, plan editor, audit record
  function modal(title, html) { $("#modal-title").textContent = title; $("#modal-body").innerHTML = html; $("#modal").classList.remove("hidden"); }
  const stepRows = (t) => (t.trace || []).map((r) => `<tr><td class="m">${esc(r.step)}</td><td>${esc(r.op)}</td><td class="m">${esc(JSON.stringify(r.args))}</td>
      <td><span class="pill2 ${r.cached ? "reuse" : "ran"}">${r.cached ? "reused" + (r.from_turn ? " · turn " + r.from_turn : "") : "executed"}</span></td>
      <td class="m">${r.cached ? "saved " + secs(r.seconds_saved) : secs(r.seconds)}</td><td class="m">${esc(r.key)}</td></tr>`).join("");
  const stepHead = `<tr><th>step</th><th>operator</th><th>arguments</th><th>decision</th><th>time</th><th>lineage key</th></tr>`;
  function stepRecord(t) {
    modal(`Turn ${t.turn}: step record`, `<p class="muted">A step is reused only when its lineage key matches a stored result: the key covers the operator, its arguments, the seed, and the keys of every input back to the graph as loaded.</p>
      <table class="audit">${stepHead}${stepRows(t)}</table>
      <h4>Verifier</h4><div class="findings">${(t.findings || []).map((x) => `<div class="finding ${x.ok ? "ok" : x.severity}"><span class="ic">${x.ok ? "✓" : "!"}</span><div><div>${esc(x.check)}</div><div class="d">${esc(x.detail)}</div></div></div>`).join("") || `<span class="muted">no checks apply to this plan</span>`}</div>`);
  }
  function editPlan(t) {
    const steps = t.plan.steps;
    modal(`Turn ${t.turn}: edit the plan and run it`, `<p class="muted">Change any argument and run the plan as a new turn. Steps you leave untouched keep their lineage key and are reused; a changed step and everything downstream of it is executed. The edited plan goes through the same validation, reuse rules and verifier.</p>
      ${steps.map((s, i) => `<div class="edit-step"><div class="h"><span>${esc(s.id)}</span>${esc(s.op)}</div><div class="edit-args">${Object.entries(s.args || {}).map(([k, v]) => `<label>${esc(k)}</label><input data-s="${i}" data-k="${esc(k)}" value="${esc(JSON.stringify(v))}">`).join("") || `<span class="muted">no arguments</span>`}</div></div>`).join("")}
      <div class="modal-actions"><span class="muted" id="edit-msg"></span><button class="primary" id="edit-run" ${S.rec ? "disabled title=\"Needs a live session\"" : ""}>Run edited plan</button></div>`);
    if (S.rec) $("#edit-msg").textContent = "Editing is shown here; running it needs a live session.";
    $("#edit-run").onclick = async () => {
      const plan = JSON.parse(JSON.stringify(t.plan));
      try { $$("#modal-body input").forEach((inp) => { plan.steps[+inp.dataset.s].args[inp.dataset.k] = JSON.parse(inp.value); }); }
      catch { $("#edit-msg").textContent = "An argument is not valid JSON (text needs quotes)."; return; }
      $("#modal").classList.add("hidden");
      try { apply(await job("/api/session/submit", { sid: S.sid, plan, question: `${t.question} (plan edited by hand)` }, "Running the edited plan")); }
      catch (e) { note(`<span class="error">${esc(e.message)}</span>`); }
    };
  }
  async function auditRecord() {
    let a;
    if (S.rec) { const turns = [...S.turns.values()]; a = { ...S.rec.audit, ledger: S.ledger, turns }; }
    else a = await (await fetch(`/api/session/audit?sid=${S.sid}`)).json();
    const L = a.ledger;
    modal("Audit record", `<p class="muted">Everything needed to check this session: the graph's content hash, the reading in force, and for every turn the plan, the reuse decision per step with its lineage key, and the checks that ran.</p>
      <div class="kv" style="margin-bottom:10px"><span class="k">graph</span><span class="v mono">${esc(a.graph.file)} · sha1 ${esc(String(a.graph.sha1).slice(0, 16))}…</span>
      <span class="k">model</span><span class="v">${esc(a.model || "")}</span>
      <span class="k">totals</span><span class="v">${L.steps_reused} steps reused, ${L.steps_executed} executed · ${secs(L.seconds_saved)} not repeated · ${plural(L.llm_calls, "model call")} · $${(L.cost_usd || 0).toFixed(3)}</span>
      <span class="k">choices</span><span class="v">${(a.clarifications || []).filter((c) => c.answered).map((c) => `turn ${c.turn}: ${esc(c.answered)}`).join("; ") || "none"}</span></div>
      <table class="audit">${a.turns.map((t) => `<tr class="t"><td colspan="6">Turn ${t.turn} · ${esc(t.question)} · ${esc(t.outcome)}${t.reading ? " · reading " + t.reading : ""}</td></tr>${t.trace ? stepHead + stepRows(t) : ""}`).join("")}</table>
      <div class="modal-actions"><button class="primary" id="audit-dl">Download as JSON</button></div>`);
    $("#audit-dl").onclick = () => { const u = URL.createObjectURL(new Blob([JSON.stringify(a, null, 1)], { type: "application/json" })); const l = document.createElement("a"); l.href = u; l.download = `audit-${S.name}.json`; l.click(); URL.revokeObjectURL(u); };
  }

  // ------------------------------------------------------------------ wiring
  function applyTheme(t) { document.documentElement.setAttribute("data-theme", t); try { localStorage.setItem("t2a_theme", t); } catch {} }
  const isDark = () => { const t = document.documentElement.getAttribute("data-theme"); return t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches; };
  try { const t = localStorage.getItem("t2a_theme"); if (t) applyTheme(t); } catch {}
  $("#btn-theme").onclick = () => applyTheme(isDark() ? "light" : "dark");
  $("#run").onclick = ask;
  $("#question").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); } });
  $("#modal-close").onclick = () => $("#modal").classList.add("hidden");
  $("#modal").addEventListener("click", (e) => { if (e.target === $("#modal")) $("#modal").classList.add("hidden"); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("#modal").classList.add("hidden"); });
  $("#btn-audit").onclick = auditRecord;
  let RECS = [];
  $("#btn-recorded").onclick = () => {
    if (RECS.length === 1) return playRecorded(RECS[0]);
    modal("Recorded sessions", RECS.length ? RECS.map((r, i) => `<div class="rec" data-i="${i}"><b>${esc(r.title)}</b><div class="muted">${esc(r.file)} · ${r.steps.length} steps · ${esc(r.model)}</div></div>`).join("") : `<p class="muted">No recorded session found. Record one with <span class="mono">demo/make_session.py</span>.</p>`);
    $$("#modal-body .rec").forEach((d) => d.onclick = () => { $("#modal").classList.add("hidden"); playRecorded(RECS[+d.dataset.i]); });
  };
  (async () => {
    const live = await loadDatasets();
    RECS = await loadRecorded();
    if (!live) { $("#ds-list").innerHTML = ""; $("#model").closest("label").classList.add("hidden"); }
    if (RECS.length && !live) playRecorded(RECS[0]);
    else if (!live) $("#graph-info").textContent = "No server and no recorded session found.";
  })();
})();
