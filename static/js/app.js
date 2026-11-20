/**
 * Zero-Leak Enterprise RAG & Connector Lab — Interactive Frontend Controller
 */

let personas = [];
let llmProfiles = [];
let corpus = [];
let runSeq = 0;

const $ = (id) => document.getElementById(id);

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// Escape, then turn `backtick spans` from the data files into real <code> elements.
function fmt(s) {
  return esc(s).replace(/`([^`\n]+)`/g, "<code>$1</code>");
}

async function fetchJson(url, options) {
  let resp;
  try {
    resp = await fetch(url, options);
  } catch (err) {
    throw new Error("Cannot reach the lab server. Is it still running on this port?");
  }
  let data = null;
  try {
    data = await resp.json();
  } catch (err) {
    throw new Error(`Server returned an unreadable response (HTTP ${resp.status}).`);
  }
  if (!resp.ok) throw new Error((data && data.error) || `Request failed (HTTP ${resp.status}).`);
  return data;
}

/* ---------- Tabs ---------- */

function activateTab(tabId, updateHash) {
  const panel = $(tabId);
  if (!panel || !panel.classList.contains("tab-panel")) return;
  document.querySelectorAll(".tab-btn").forEach((b) => {
    const on = b.dataset.tab === tabId;
    b.classList.toggle("active", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
  });
  document.querySelectorAll(".tab-panel").forEach((p) => {
    const on = p.id === tabId;
    p.classList.toggle("active", on);
    p.hidden = !on;
  });
  if (updateHash) history.replaceState(null, "", `#${tabId}`);
}

/* ---------- Tab 1: Security lab ---------- */

function renderChunkCard(chunk, isNaiveCol) {
  const leaked = !chunk.caller_authorized;
  const noSignal = Number(chunk.dense_score) === 0 && Number(chunk.bm25_score) === 0;
  const cls = leaked ? "chunk-card chunk-leaked" : "chunk-card chunk-safe";
  const statusBadge = leaked
    ? `<span class="badge badge-rose">🚨 Unauthorized (${esc(chunk.sensitivity)})</span>`
    : `<span class="badge badge-emerald">✓ Authorized (${esc(chunk.sensitivity)})</span>`;

  return `
    <div class="${cls}">
      <div class="chunk-head">
        <strong><code>${esc(chunk.id)}</code> — ${esc(chunk.title)}</strong>
        ${statusBadge}
      </div>
      <div class="text-muted">Connector: ${esc(chunk.connector)}</div>
      <div class="chunk-body">${fmt(chunk.content)}</div>
      <div class="score-pills">
        <span title="Reciprocal Rank Fusion score">RRF <strong>${esc(chunk.rrf_score)}</strong></span>
        <span title="Dense (semantic) similarity and its rank">Dense <strong>${esc(chunk.dense_score)}</strong> (#${esc(chunk.dense_rank)})</span>
        <span title="BM25 keyword score and its rank">BM25 <strong>${esc(chunk.bm25_score)}</strong> (#${esc(chunk.bm25_rank)})</span>
      </div>
      ${noSignal ? `<div class="chunk-note">No relevance signal for this query: it is only here as nearest-neighbour filler, the way a vector index always returns its top-K.</div>` : ""}
      ${isNaiveCol && leaked ? `<div class="chunk-note chunk-note-leak">Why it leaked: ${esc(chunk.acl_decision_reason)}. The shared service account fetched it anyway.</div>` : ""}
    </div>
  `;
}

function renderAnswerMeta(res) {
  const secs = (Number(res.latency_ms) / 1000).toFixed(1);
  const lines = [];
  if (res.llm_fallback_used) {
    lines.push(
      `<div class="meta-warn">⚠️ No model answer. The text above is the top retrieved chunk shown verbatim, not model output.` +
      `${res.llm_error ? ` Reason: ${esc(res.llm_error)}` : ""}</div>`
    );
  } else {
    lines.push(`<div>Answered by <strong>${esc(res.llm_provider)}</strong> · <code>${esc(res.llm_model)}</code> · ${esc(secs)}s</div>`);
  }
  if (res.valid_citations && res.valid_citations.length) {
    lines.push(`<div>Citations found in the retrieved chunks: ${res.valid_citations.map((c) => `<code>${esc(c)}</code>`).join(" ")}</div>`);
  } else if (!res.llm_fallback_used && res.retrieved_chunks.length) {
    lines.push(`<div>The answer cites no chunk IDs.</div>`);
  }
  if (res.invalid_citations && res.invalid_citations.length) {
    lines.push(`<div class="meta-warn">⚠️ Cites IDs that were not retrieved: ${res.invalid_citations.map((c) => `<code>${esc(c)}</code>`).join(" ")}</div>`);
  }
  return lines.join("");
}

function updatePersonaBanner() {
  const p = personas.find((x) => x.id === $("persona-select").value) || personas[0];
  if (!p) return;
  $("persona-banner").innerHTML = `
    <div class="chunk-head">
      <div><strong>${esc(p.name)}</strong> — ${esc(p.title)}</div>
      <span class="badge badge-cyan">${esc(p.badge)}</span>
    </div>
    <div class="persona-facts">
      <span>IAM groups: <code>${esc(p.groups.join(", "))}</code></span>
      <span>BigQuery regions: <code>${esc(p.allowed_regions.length ? p.allowed_regions.join(", ") : "none")}</code></span>
    </div>
    <div class="text-muted">${fmt(p.summary)}</div>
  `;
}

function setScenarioActive(btn) {
  document.querySelectorAll(".preset-scenario").forEach((b) => b.classList.toggle("scenario-active", b === btn));
}

function markStale() {
  // Controls changed since the last run: the panels below no longer match what is selected.
  if ($("compare-grid").dataset.hasResults === "1") {
    $("compare-grid").classList.add("stale");
    $("run-status").textContent = "Settings changed. Press Compare to refresh the results below.";
  }
}

function setBusy(busy) {
  $("btn-run-rag").disabled = busy;
  document.querySelectorAll(".preset-scenario").forEach((b) => { b.disabled = busy; });
  $("btn-run-rag").textContent = busy ? "⏳ Running…" : "▶ Compare";
}

async function runComparison() {
  const query = $("rag-query-input").value.trim();
  const status = $("run-status");
  if (!query) {
    status.textContent = "Type a question first (or click a scenario).";
    $("rag-query-input").focus();
    return;
  }
  const prof = llmProfiles.find((x) => x.id === $("llm-select").value) || llmProfiles[0] || { provider: "ollama", model: "llama3.2:3b" };
  const apiKey = $("apikey-input").value.trim();
  const seq = ++runSeq;
  const started = Date.now();
  const isLocal = prof.provider === "ollama";

  setBusy(true);
  $("compare-grid").classList.remove("stale");
  const tick = () => {
    const s = Math.round((Date.now() - started) / 1000);
    status.textContent = `Running both pipelines with ${prof.model}… ${s}s` + (isLocal && s >= 8 ? " (local models can take a minute on CPU)" : "");
  };
  tick();
  const timer = setInterval(tick, 1000);

  try {
    const data = await fetchJson("/api/rag/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        persona_id: $("persona-select").value,
        search_strategy: $("strategy-select").value,
        compare_both: true,
        llm_config: { provider: prof.provider, model: prof.model, api_key: apiKey },
      }),
    });
    if (seq !== runSeq) return;

    const naive = data.naive_confused_deputy;
    const zl = data.zero_leak_acl_enforced;

    const armorEl = $("armor-alert");
    if (zl.model_armor && zl.model_armor.injection_detected) {
      armorEl.hidden = false;
      armorEl.innerHTML = `<span class="badge badge-amber">🛡️ Model Armor (simulated): ${esc(zl.model_armor.verdict)}</span>
        <div class="alert-body">${fmt(zl.model_armor.architect_note)}</div>`;
    } else {
      armorEl.hidden = true;
    }

    const nBadge = $("naive-leak-badge");
    if (naive.data_leak_occurred) {
      nBadge.className = "badge badge-rose";
      nBadge.textContent = `🚨 Leaked ${naive.leaked_chunk_ids.length}: ${naive.leaked_chunk_ids.join(", ")}`;
    } else {
      nBadge.className = "badge badge-amber";
      nBadge.textContent = "No leak this time (caller happened to be authorized)";
    }
    $("naive-answer").classList.remove("answer-empty", "answer-error");
    $("naive-answer").textContent = naive.answer;
    $("naive-meta").innerHTML = renderAnswerMeta(naive);
    $("naive-chunks").innerHTML = naive.retrieved_chunks.length
      ? naive.retrieved_chunks.map((c) => renderChunkCard(c, true)).join("")
      : `<div class="text-muted">No chunks retrieved.</div>`;

    const zBadge = $("zeroleak-badge");
    if (zl.data_leak_occurred) {
      zBadge.className = "badge badge-rose";
      zBadge.textContent = `🚨 Leaked ${zl.leaked_chunk_ids.length}: ${zl.leaked_chunk_ids.join(", ")}`;
    } else {
      zBadge.className = "badge badge-emerald";
      zBadge.textContent = `✓ 0 leaks · ${zl.blocked_by_acl_count} of ${zl.total_corpus_records} records blocked`;
    }
    $("zeroleak-answer").classList.remove("answer-empty", "answer-error");
    $("zeroleak-answer").textContent = zl.answer;
    $("zeroleak-meta").innerHTML = renderAnswerMeta(zl);
    $("zeroleak-chunks").innerHTML = zl.retrieved_chunks.length
      ? zl.retrieved_chunks.map((c) => renderChunkCard(c, false)).join("")
      : `<div class="text-muted">No authorized chunks matched.</div>`;

    $("zeroleak-blocked-count").textContent = `(${zl.blocked_summary.length})`;
    $("zeroleak-blocked").innerHTML = zl.blocked_summary.length
      ? zl.blocked_summary
          .map((b) => `<div class="chunk-card"><strong><code>${esc(b.id)}</code> — ${esc(b.title)}</strong><div class="text-muted">${esc(b.reason)}</div></div>`)
          .join("")
      : `<div class="text-muted">Nothing was blocked for this caller.</div>`;

    $("compare-grid").dataset.hasResults = "1";
    const fellBack = naive.llm_fallback_used || zl.llm_fallback_used;
    status.textContent = fellBack
      ? "Done, but the model did not answer on at least one side. See the warning under the answer."
      : `Done in ${((Date.now() - started) / 1000).toFixed(1)}s.`;
  } catch (err) {
    if (seq !== runSeq) return;
    status.textContent = "";
    ["naive-answer", "zeroleak-answer"].forEach((id) => {
      $(id).classList.remove("answer-empty");
      $(id).classList.add("answer-error");
      $(id).textContent = `Could not run the comparison: ${err.message}`;
    });
    ["naive-meta", "zeroleak-meta"].forEach((id) => { $(id).innerHTML = ""; });
  } finally {
    clearInterval(timer);
    if (seq === runSeq) setBusy(false);
  }
}

/* ---------- Tab 2: Architecture calculator ---------- */

async function runArchitectCalc() {
  const out = $("calc-output");
  const payload = {
    corpus_tokens: Number($("calc-tokens").value),
    update_freq: $("calc-freq").value,
    queries_per_day: Number($("calc-qpd").value),
    goal: $("calc-goal").value,
    needs_acls: $("calc-acls").checked,
    needs_citations: $("calc-citations").checked,
  };
  let data;
  try {
    data = await fetchJson("/api/architect/tradeoff", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (err) {
    out.innerHTML = `<div class="answer-box answer-error">Could not calculate: ${esc(err.message)}</div>`;
    return;
  }
  const verdictClass = (v) => (v === "BEST FIT" ? "badge-emerald" : v === "STRONG COMPLEMENT" ? "badge-cyan" : "badge-rose");
  out.innerHTML = `
    <div class="calc-rec">🏆 Recommended: ${esc(data.recommended_pattern)}</div>
    <p class="calc-rationale">${fmt(data.architect_rationale)}</p>

    <div class="table-wrap">
      <table class="tradeoff-table">
        <thead>
          <tr>
            <th>Pattern</th>
            <th>Est. monthly cost</th>
            <th>Est. p95 latency</th>
            <th>Per-user ACLs</th>
            <th>Fresh data</th>
            <th>Citations</th>
            <th>Verdict</th>
          </tr>
        </thead>
        <tbody>
          ${data.options.map((o) => `
            <tr>
              <td><strong>${esc(o.name)}</strong></td>
              <td>$${Number(o.est_monthly_cost_usd).toLocaleString(undefined, { maximumFractionDigits: 0 })} / mo</td>
              <td>~${esc(o.est_p95_latency_ms)} ms</td>
              <td>${o.supports_per_user_acls ? "✅ Yes" : "❌ No"}</td>
              <td>${o.supports_realtime_updates ? "✅ Yes" : "❌ No"}</td>
              <td>${o.supports_citations ? "✅ Yes" : "❌ No"}</td>
              <td><span class="badge ${verdictClass(o.verdict)}">${esc(o.verdict)}</span></td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
    <p class="text-muted footnote">${esc(data.pricing_note || "")}</p>

    <div class="soundbite-box">
      <div class="soundbite-title">🎤 30-second spoken answer</div>
      <div>${fmt(data.interview_30s_script)}</div>
    </div>
  `;
}

/* ---------- Tab 4: Data & ACL inspector ---------- */

function personaCanRead(p, rec) {
  // Mirrors the server-side check: an IAM group must match, and BigQuery rows also need the region.
  const groupOk = rec.allowed_groups.some((g) => p.groups.includes(g));
  if (!groupOk) return false;
  if (rec.rls_region) return p.allowed_regions.includes(rec.rls_region);
  return true;
}

function renderCorpus() {
  const sel = $("corpus-persona-filter").value;
  const p = personas.find((x) => x.id === sel);
  let readable = 0;
  $("corpus-list").innerHTML = corpus
    .map((c) => {
      const ok = p ? personaCanRead(p, c) : null;
      if (ok) readable += 1;
      const access = ok === null ? "" : ok
        ? `<span class="badge badge-emerald">✓ Can read</span>`
        : `<span class="badge badge-rose">✕ Blocked</span>`;
      return `
        <div class="chunk-card ${ok === false ? "chunk-dim" : ""}">
          <div class="chunk-head">
            <strong><code>${esc(c.id)}</code> — ${esc(c.title)}</strong>
            <span class="badge-group">${access}<span class="badge badge-cyan">${esc(c.connector)}</span></span>
          </div>
          <div class="text-muted">
            Allowed IAM groups: <code>${esc(c.allowed_groups.join(", "))}</code>
            ${c.rls_region ? ` • BigQuery RLS: <code>region = '${esc(c.rls_region)}'</code>` : ""}
            • Sensitivity: <code>${esc(c.sensitivity)}</code>
          </div>
          <div class="chunk-body">${fmt(c.content)}</div>
        </div>
      `;
    })
    .join("");
  $("corpus-summary").textContent = p
    ? `${p.name} can read ${readable} of ${corpus.length} records.`
    : `${corpus.length} records across all connectors.`;
}

/* ---------- Init ---------- */

function syncKeyBox() {
  const prof = llmProfiles.find((x) => x.id === $("llm-select").value);
  const needsKey = Boolean(prof && prof.group === "cloud_api" && !prof.has_api_key);
  $("apikey-wrap").hidden = !needsKey;
  if (needsKey) $("apikey-label").textContent = `${prof.provider} API key (required)`;
}

async function init() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => activateTab(btn.dataset.tab, true));
  });
  if (location.hash) activateTab(location.hash.slice(1), false);
  window.addEventListener("hashchange", () => activateTab(location.hash.slice(1), false));

  let boot;
  try {
    boot = await fetchJson("/api/bootstrap");
  } catch (err) {
    $("boot-error").hidden = false;
    $("boot-error").innerHTML = `<strong>The lab could not load its data.</strong> ${esc(err.message)} <button type="button" class="btn" onclick="location.reload()">Reload</button>`;
    $("llm-status-pill").textContent = "Server unreachable";
    $("llm-status-pill").className = "badge badge-rose";
    return;
  }
  personas = boot.personas || [];
  llmProfiles = (boot.llm && boot.llm.profiles) || [];
  corpus = boot.corpus || [];

  const pill = $("llm-status-pill");
  if (boot.llm && boot.llm.ollama_connected) {
    const n = boot.llm.ollama_models.length;
    pill.textContent = `🏠 Local Ollama: ${n} model${n === 1 ? "" : "s"}`;
    pill.title = boot.llm.ollama_models.join(", ");
    pill.className = "badge badge-emerald";
  } else {
    pill.textContent = "🏠 Local Ollama offline";
    pill.title = "Start Ollama on port 11434, or choose a cloud model with an API key.";
    pill.className = "badge badge-amber";
  }

  const pSel = $("persona-select");
  pSel.innerHTML = personas.map((p) => `<option value="${esc(p.id)}">${esc(p.name)} — ${esc(p.title)}</option>`).join("");
  pSel.addEventListener("change", () => { updatePersonaBanner(); setScenarioActive(null); markStale(); });
  updatePersonaBanner();

  const lSel = $("llm-select");
  const localProfs = llmProfiles.filter((p) => p.group === "local_onboard");
  const cloudProfs = llmProfiles.filter((p) => p.group !== "local_onboard");
  const ollamaUp = Boolean(boot.llm && boot.llm.ollama_connected);
  lSel.innerHTML = `
    <optgroup label="Local (Ollama)${ollamaUp ? "" : " — not running"}">
      ${localProfs.map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join("")}
    </optgroup>
    <optgroup label="Cloud APIs (optional)">
      ${cloudProfs.map((p) => `<option value="${esc(p.id)}">${esc(p.name)}${p.has_api_key ? " ✓ key ready" : " (needs key)"}</option>`).join("")}
    </optgroup>
  `;
  // Start on a route that can answer right away: a key-ready Gemini profile if Ollama is down or
  // a key is configured, otherwise the first local model.
  const gemProf = llmProfiles.find((p) => p.id === "cloud-gemini" && p.has_api_key);
  if (gemProf) lSel.value = gemProf.id;
  lSel.addEventListener("change", () => { syncKeyBox(); markStale(); });
  syncKeyBox();

  $("strategy-select").addEventListener("change", () => { setScenarioActive(null); markStale(); });
  $("rag-query-input").addEventListener("input", () => setScenarioActive(null));

  document.querySelectorAll(".preset-scenario").forEach((btn) => {
    btn.addEventListener("click", () => {
      $("persona-select").value = btn.dataset.persona;
      $("strategy-select").value = btn.dataset.strategy;
      $("rag-query-input").value = btn.dataset.query;
      updatePersonaBanner();
      setScenarioActive(btn);
      runComparison();
    });
  });

  $("rag-form").addEventListener("submit", (ev) => {
    ev.preventDefault();
    runComparison();
  });

  ["calc-tokens", "calc-freq", "calc-qpd", "calc-goal", "calc-acls", "calc-citations"].forEach((id) => {
    $(id).addEventListener("change", runArchitectCalc);
  });
  runArchitectCalc();

  // Tab 3: Code-level bug hunt
  const bugs = boot.bug_challenges || [];
  $("bug-challenges-list").innerHTML = bugs
    .map((b, i) => `
      <div class="card">
        <div class="card-title">Challenge ${i + 1} of ${bugs.length}: ${fmt(b.title.replace(/^Bug #\d+:\s*/, ""))}</div>
        <div class="bug-symptom"><strong>Customer symptom:</strong> ${fmt(b.symptom)}</div>
        <pre class="code-block">${esc(b.broken_code)}</pre>
        <div class="bug-question">❓ ${fmt(b.question)}</div>
        <details class="reveal">
          <summary>Show root cause and fix</summary>
          <div class="reveal-body">
            <div class="bug-cause"><strong>Root cause:</strong> ${fmt(b.root_cause)}</div>
            <pre class="code-block">${esc(b.fix_code)}</pre>
            <div class="soundbite-box"><div class="soundbite-title">🎤 30-second spoken answer</div>${fmt(b.interview_soundbite)}</div>
          </div>
        </details>
      </div>
    `)
    .join("");

  // Tab 4: Data & ACL inspector
  const cSel = $("corpus-persona-filter");
  cSel.innerHTML = `<option value="">Everyone (no filter)</option>` +
    personas.map((p) => `<option value="${esc(p.id)}">${esc(p.name)} — ${esc(p.title)}</option>`).join("");
  cSel.addEventListener("change", renderCorpus);
  renderCorpus();
}

document.addEventListener("DOMContentLoaded", init);
