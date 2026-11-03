/* Live UI: fetch an SSE stream, turn spans into a timeline, then let the
 * report's citation buttons open the exact source span. No framework. */

const $ = (selector) => document.querySelector(selector);

const STAGE_LABELS = {
  plan: "Planning",
  research: "Researching",
  evidence: "Collecting evidence",
  verify: "Verifying claims",
  write: "Writing the report",
};

const state = {
  running: false,
  startedAt: 0,
  timer: null,
  currentStage: null,
  spans: new Map(),
  subagents: 0,
  llmCalls: 0,
  tokens: 0,
  sources: [],
  source: null,
  passage: 0,
  refs: [],
  controller: null,
  finished: false,
  errored: false,
  events: 0,
  lastEvent: "",
};

const els = {
  hero: $("#hero"),
  workspace: $("#workspace"),
  ask: $("#ask"),
  question: $("#question"),
  go: $("#go"),
  newRun: $("#new-run"),
  examples: $("#examples"),
  fineprint: $("#fineprint"),
  runQuestion: $("#run-question"),
  statTime: $("#stat-time"),
  statCalls: $("#stat-calls"),
  statTokens: $("#stat-tokens"),
  statCost: $("#stat-cost"),
  rail: $("#rail"),
  timeline: $("#timeline"),
  error: $("#run-error"),
  report: $("#report"),
  sourceNote: $("#source-note"),
  modelPill: $("#model-pill"),
  drawer: $("#drawer"),
  scrim: $("#scrim"),
  drawerClose: $("#drawer-close"),
  kicker: $("#source-kicker"),
  sourceTitle: $("#source-title"),
  sourceUrl: $("#source-url"),
  also: $("#also-refs"),
  passageNav: $("#passage-nav"),
  passageCount: $("#passage-count"),
  prev: $("#prev-passage"),
  next: $("#next-passage"),
  verdict: $("#verdict"),
  trust: $("#trust"),
  verdictReason: $("#verdict-reason"),
  claim: $("#claim"),
  spanLabel: $("#span-label"),
  sourceText: $("#source-text"),
};

/* ------------------------------------------------------------------ */
/* boot                                                                */
/* ------------------------------------------------------------------ */
async function boot() {
  try {
    const response = await fetch("/api/config");
    const config = await response.json();
    const model = shortModel(config.model);
    els.modelPill.textContent = `${config.provider || "model"} · ${model}`;
    els.modelPill.title = `research: ${config.model}\njudge: ${config.judge_model}`;
    if (config.max_seconds) {
      const minutes = Math.round(config.max_seconds / 60);
      els.fineprint.textContent =
        "One run takes 1–3 minutes on a free-tier model. The trace is live; " +
        `a run is hard-stopped at ${minutes} minute${minutes === 1 ? "" : "s"}.`;
    }
  } catch {
    els.modelPill.textContent = "offline";
  }

  els.ask.addEventListener("submit", (event) => {
    event.preventDefault();
    const question = els.question.value.trim();
    if (question.length >= 8) startRun(question);
  });

  els.examples.addEventListener("click", (event) => {
    const chip = event.target.closest(".chip");
    if (!chip) return;
    els.question.value = chip.textContent.trim();
    els.question.focus();
  });

  els.newRun.addEventListener("click", resetToHero);
  els.drawerClose.addEventListener("click", closeDrawer);
  els.scrim.addEventListener("click", closeDrawer);
  els.prev.addEventListener("click", () => stepPassage(-1));
  els.next.addEventListener("click", () => stepPassage(1));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeDrawer();
    if (els.drawer.classList.contains("open")) {
      if (event.key === "ArrowLeft") stepPassage(-1);
      if (event.key === "ArrowRight") stepPassage(1);
    }
  });

  els.report.addEventListener("click", (event) => {
    const button = event.target.closest("button.cite");
    if (!button) return;
    event.preventDefault();
    const refs = (button.dataset.refs || "")
      .split(",")
      .map((part) => parseInt(part.trim(), 10))
      .filter((number) => Number.isFinite(number));
    if (refs.length) openSource(refs[0], refs);
  });
}

/* ------------------------------------------------------------------ */
/* run                                                                 */
/* ------------------------------------------------------------------ */
async function startRun(question) {
  reset();
  state.running = true;
  state.startedAt = performance.now();
  state.controller = new AbortController();

  els.hero.hidden = true;
  els.workspace.hidden = false;
  els.newRun.hidden = true;
  els.question.disabled = true;
  els.go.disabled = true;
  els.ask.classList.add("busy");
  els.runQuestion.textContent = question;

  state.timer = window.setInterval(() => {
    els.statTime.textContent = elapsed(state.startedAt);
  }, 100);

  try {
    const response = await fetch("/api/research", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
      signal: state.controller.signal,
    });

    if (!response.ok) {
      const detail = await response.json().catch(() => null);
      throw new Error((detail && detail.detail) || `request failed (${response.status})`);
    }
    if (!response.body) throw new Error("streaming is not supported by this browser");

    await consume(response.body);
    if (!state.finished) {
      // The server closed without a `done` frame at all. That is different
      // from a run that failed (which sends error + done); usually the server
      // was restarted or crashed mid-run.
      showError(
        `The connection closed after ${elapsed(state.startedAt)} without a final ` +
          `event (${state.events} events, last: ${state.lastEvent || "none"}). ` +
          "Check the server terminal for a traceback.",
      );
    }
  } catch (error) {
    if (error.name !== "AbortError") showError(error.message || String(error));
  } finally {
    finishRun();
  }
}

function finishRun() {
  state.running = false;
  if (state.timer) window.clearInterval(state.timer);
  state.timer = null;
  els.question.disabled = false;
  els.go.disabled = false;
  els.ask.classList.remove("busy");
  els.newRun.hidden = false;
}

async function consume(stream) {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    buffer = buffer.replace(/\r\n/g, "\n");

    let cut;
    while ((cut = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      dispatch(frame);
    }
  }
  if (buffer.trim()) dispatch(buffer);
}

function dispatch(frame) {
  let event = "message";
  let data = "";
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return;

  let payload;
  try {
    payload = JSON.parse(data);
  } catch {
    return;
  }

  state.events += 1;
  if (event === "span") {
    state.lastEvent = `${payload.kind} ${payload.name || ""}`.trim();
    handleSpan(payload);
  } else if (event === "report") {
    state.lastEvent = "report";
    renderReport(payload.data);
  } else if (event === "error") {
    state.lastEvent = "error";
    showError(payload.message || "The run failed.", payload);
  } else if (event === "done") {
    // A `done` frame is terminal even when ok is false. Overwriting this with
    // `false` used to make the generic "stream ended" message replace the
    // real server error.
    state.finished = true;
    state.lastEvent = "done";
    if (!payload.ok && !state.errored) showError("The run failed without details.");
  }
}

/* ------------------------------------------------------------------ */
/* spans                                                               */
/* ------------------------------------------------------------------ */
function handleSpan(payload) {
  const span = payload.span || payload;
  if (span.kind === "pipeline") return;

  if (span.kind === "llm") {
    if (span.phase === "start") {
      state.llmCalls += 1;
      els.statCalls.textContent = String(state.llmCalls);
    } else {
      state.tokens += span.tokens || 0;
      els.statTokens.textContent = formatNumber(state.tokens);
    }
    return;
  }

  if (span.kind === "stage") {
    if (span.phase === "start") stageStart(span);
    else stageEnd(span);
    return;
  }
  if (span.kind === "subagent") {
    if (span.phase === "start") subagentStart(span);
    else subagentEnd(span);
    return;
  }
  if (span.kind === "tool") {
    if (span.phase === "start") toolStart(span);
    else toolEnd(span);
  }
}

function makeEvent(className, title) {
  const root = document.createElement("div");
  root.className = `event ${className}`;

  const icon = document.createElement("span");
  icon.className = "icon spin";

  const body = document.createElement("div");
  body.className = "body";

  const titleEl = document.createElement("div");
  titleEl.className = "title";
  titleEl.textContent = title;

  const sub = document.createElement("div");
  sub.className = "sub";
  sub.hidden = true;

  body.append(titleEl, sub);

  const side = document.createElement("span");
  side.className = "side";

  root.append(icon, body, side);
  return { root, icon, body, title: titleEl, sub, side };
}

function appendEvent(card, host = els.timeline) {
  const stick = nearBottom();
  host.append(card.root);
  if (stick) window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
}

function stageStart(span) {
  state.currentStage = span.name;
  setRail(span.name, "running");
  const card = makeEvent("stage", STAGE_LABELS[span.name] || span.name);
  card.sub.hidden = false;
  card.sub.textContent = "working…";
  card.root.dataset.spanId = span.id;
  state.spans.set(span.id, card);
  appendEvent(card);
}

function stageEnd(span) {
  const card = state.spans.get(span.id);
  if (!card) return;
  const failed = span.status === "error";
  setRail(span.name, failed ? "error" : "done");
  card.icon.className = `icon ${failed ? "warn" : "check"}`;
  card.side.textContent = formatDuration(span.duration_ms);

  if (failed) {
    card.sub.hidden = false;
    card.sub.textContent = span.error || "stage failed";
    return;
  }

  const attributes = span.attributes || {};
  if (span.name === "plan") {
    card.sub.hidden = true;
    const questions = Array.isArray(attributes.questions) ? attributes.questions : [];
    if (questions.length) {
      const list = document.createElement("ul");
      list.className = "questions";
      for (const entry of questions) {
        const item = document.createElement("li");
        item.textContent = entry.question || String(entry);
        list.append(item);
      }
      card.body.append(list);
    }
    card.side.textContent = plural(questions.length, "question");
  } else if (span.name === "research") {
    card.sub.hidden = false;
    card.sub.textContent = `${plural(attributes.findings || 0, "finding")} · ${plural(attributes.sources || 0, "source")}`;
  } else if (span.name === "evidence") {
    card.sub.hidden = false;
    const kept = attributes.evidence_kept || 0;
    const unverified = attributes.unverified_quotes || 0;
    card.sub.textContent = `${plural(kept, "quote")} kept · ${unverified} unverified`;
  } else if (span.name === "verify") {
    const counts = attributes.verdicts || {};
    const tags = document.createElement("div");
    tags.className = "summary-line";
    for (const [name, count] of Object.entries(counts)) {
      if (!count) continue;
      const tag = document.createElement("span");
      tag.className = `tag ${verdictClass(name)}`;
      tag.textContent = `${count} ${name}`;
      tags.append(tag);
    }
    if (attributes.judge_errors) {
      const tag = document.createElement("span");
      tag.className = "tag bad";
      tag.textContent = `${attributes.judge_errors} judge errors`;
      tags.append(tag);
    }
    card.body.append(tags);
    card.sub.hidden = false;
    card.sub.textContent = attributes.contradictions
      ? `${attributes.contradictions} contradiction(s) flagged`
      : "every quote checked against its claim";
  } else if (span.name === "write") {
    card.sub.hidden = false;
    card.sub.textContent = `${attributes.words || 0} words · ${attributes.citations || 0} citations`;
  }
}

function subagentStart(span) {
  state.subagents += 1;
  const card = makeEvent("subagent", `Sub-agent ${state.subagents}`);
  card.sub.hidden = false;
  const query = span.attributes && span.attributes.query;
  card.sub.textContent = query ? `${span.name} — “${query}”` : span.name;
  card.root.dataset.spanId = span.id;
  state.spans.set(span.id, card);
  appendEvent(card);
}

function subagentEnd(span) {
  const card = state.spans.get(span.id);
  if (!card) return;
  const failed = span.status === "error";
  card.icon.className = `icon ${failed ? "warn" : "check"}`;
  card.side.textContent = formatDuration(span.duration_ms);
  if (failed) {
    card.sub.textContent = span.error || "sub-agent failed";
    return;
  }
  const attributes = span.attributes || {};
  card.sub.textContent = `${plural(attributes.findings || 0, "finding")} · ${plural(attributes.sources || 0, "source")}`;

  const urls = Array.isArray(attributes.urls) ? attributes.urls : [];
  if (urls.length) {
    const tags = document.createElement("div");
    tags.className = "summary-line";
    for (const url of urls) {
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = shortDomain(url);
      tags.append(tag);
    }
    // Tags belong with the findings line, above any tool rows.
    const tools = card.body.querySelector(".tool-list");
    card.body.insertBefore(tags, tools);
  }
}

function toolStart(span) {
  const query = toolQuery(span);
  const card = makeEvent("tool", span.name);
  card.sub.hidden = false;
  card.sub.textContent = query ? `“${query}”` : "running…";
  card.root.dataset.spanId = span.id;
  state.spans.set(span.id, card);

  // Keep a sub-agent's tools inside its card, so concurrent agents don't turn
  // the timeline into an interleaved pile of orphan rows.
  const parent = state.spans.get(span.parent_id);
  let host = els.timeline;
  if (parent) {
    let list = parent.body.querySelector(".tool-list");
    if (!list) {
      list = document.createElement("div");
      list.className = "tool-list";
      parent.body.append(list);
    }
    host = list;
  }
  appendEvent(card, host);
}

function toolEnd(span) {
  const card = state.spans.get(span.id);
  if (!card) return;
  const failed = span.status === "error";
  card.icon.className = `icon ${failed ? "warn" : "check"}`;
  const size = span.attributes && span.attributes.output_chars;
  card.side.textContent = [
    failed ? "" : size ? `${formatNumber(size)} chars` : "",
    formatDuration(span.duration_ms),
  ]
    .filter(Boolean)
    .join(" · ");
  if (failed) {
    card.sub.textContent = span.error || "tool failed";
  }
}

function toolQuery(span) {
  const raw = span.attributes && span.attributes.args;
  if (typeof raw !== "string") return "";
  try {
    const args = JSON.parse(raw);
    return args.query || args.url || "";
  } catch {
    return raw;
  }
}

/* ------------------------------------------------------------------ */
/* report                                                              */
/* ------------------------------------------------------------------ */
function renderReport(data) {
  state.finished = true;
  state.sources = Array.isArray(data.sources) ? data.sources : [];

  const trace = data.trace || {};
  els.statTime.textContent = formatDuration(trace.duration_ms || 0);
  els.statCalls.textContent = String(trace.llm_calls ?? state.llmCalls);
  els.statTokens.textContent = formatNumber((trace.tokens && trace.tokens.total) || state.tokens);
  els.statCost.textContent = formatCost(trace.cost_usd);
  els.statCost.title =
    trace.cost_usd == null
      ? "One or more models has no price in this deployment; cost is unknown, not zero."
      : "Estimated from token usage and the local price table.";

  els.report.innerHTML = reportSummary(data) + data.html;
  els.report.hidden = false;
  els.sourceNote.hidden = false;

  const stick = nearBottom();
  if (stick) {
    window.setTimeout(() => {
      els.report.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 120);
  }
}

function reportSummary(data) {
  const stats = data.stats || {};
  const verdicts = stats.verdicts || {};
  const judged = Object.values(verdicts).reduce((sum, value) => sum + value, 0);
  const good = (verdicts.supported || 0) + (verdicts.partial || 0);
  const trace = data.trace || {};

  const tags = [
    `${stats.cited_passages || 0} cited quotes`,
    `${stats.cited_sources || 0} sources`,
    `${stats.words || 0} words`,
  ];
  if (judged) tags.push(`${good}/${judged} supported`);
  tags.push(formatDuration(trace.duration_ms || 0));
  tags.push(formatCost(trace.cost_usd));

  const chips = tags
    .map((text) => `<span class="tag">${escapeHtml(text)}</span>`)
    .join("");

  return `<div class="report-hero"><span class="ready">report ready</span>${chips}</div>`;
}

/* ------------------------------------------------------------------ */
/* source drawer                                                       */
/* ------------------------------------------------------------------ */
function openSource(number, refs = [number]) {
  const source = state.sources.find((item) => item.number === number);
  if (!source) return;
  state.source = source;
  state.passage = 0;
  state.refs = refs.length ? refs : [number];
  renderSource();

  els.drawer.classList.add("open");
  els.drawer.setAttribute("aria-hidden", "false");
  els.scrim.hidden = false;
  document.body.classList.add("locked");
}

function renderSource() {
  const source = state.source;
  if (!source) return;
  const passage = source.passages[state.passage] || source.passages[0];
  if (!passage) return;

  els.kicker.textContent = `source ${source.number} of ${state.sources.length}`;
  els.sourceTitle.textContent = source.title || source.domain;
  els.sourceUrl.href = source.url;
  els.sourceUrl.textContent = displayUrl(source.url);

  els.also.innerHTML = "";
  if (state.refs.length > 1) {
    for (const number of state.refs) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `[${number}]`;
      button.setAttribute("aria-current", number === source.number ? "true" : "false");
      button.addEventListener("click", () => openSource(number, state.refs));
      els.also.append(button);
    }
  }

  const total = source.passages.length;
  els.passageNav.hidden = total <= 1;
  els.passageCount.textContent = `passage ${state.passage + 1} of ${total}`;
  els.prev.disabled = state.passage <= 0;
  els.next.disabled = state.passage >= total - 1;

  els.verdict.className = `badge ${verdictClass(passage.support)}`;
  els.verdict.textContent = `${verdictGlyph(passage.support)} ${passage.support}`;
  els.trust.textContent = `${passage.trust} · ${passage.confidence} confidence`;
  els.verdictReason.textContent = passage.support_reason || "No judge reason recorded.";
  els.claim.textContent = `Claim: ${passage.claim}`;

  renderSourceText(source, passage);
}

function renderSourceText(source, passage) {
  els.sourceText.innerHTML = "";
  const text = source.text || "";

  if (!text) {
    const missing = document.createElement("div");
    missing.className = "source-missing";
    missing.textContent = passage.quote;
    els.sourceText.append(missing);
    els.spanLabel.textContent = "page text was not retained for this source";
    return;
  }

  let start = passage.span ? passage.span.start : null;
  let end = passage.span ? passage.span.end : null;
  let label = "quote located by text match";

  if (start == null || end == null) {
    const found = text.indexOf(passage.quote);
    if (found !== -1) {
      start = found;
      end = found + passage.quote.length;
    }
  }
  if (start != null && end != null) {
    label = `characters ${formatNumber(start)}–${formatNumber(end)} · ${formatNumber(end - start)} chars`;
  }

  els.spanLabel.textContent = label;

  if (start == null || end == null) {
    els.sourceText.textContent = text;
    return;
  }

  const before = document.createTextNode(text.slice(0, start));
  const mark = document.createElement("mark");
  mark.id = "quote-mark";
  mark.textContent = text.slice(start, end);
  mark.title = `characters ${formatNumber(start)}–${formatNumber(end)}`;
  const after = document.createTextNode(text.slice(end));
  els.sourceText.append(before, mark, after);

  window.requestAnimationFrame(() => {
    const box = els.sourceText;
    const offset = mark.offsetTop - box.clientHeight / 2 + mark.offsetHeight / 2;
    box.scrollTop = Math.max(0, offset - 20);
  });
}

function stepPassage(delta) {
  if (!state.source) return;
  const next = state.passage + delta;
  if (next < 0 || next >= state.source.passages.length) return;
  state.passage = next;
  renderSource();
}

function closeDrawer() {
  if (!els.drawer.classList.contains("open")) return;
  els.drawer.classList.remove("open");
  els.drawer.setAttribute("aria-hidden", "true");
  els.scrim.hidden = true;
  document.body.classList.remove("locked");
}

/* ------------------------------------------------------------------ */
/* helpers                                                             */
/* ------------------------------------------------------------------ */
function setRail(stage, status) {
  const item = els.rail.querySelector(`[data-stage="${stage}"]`);
  if (!item) return;
  item.classList.remove("running", "done", "error");
  item.classList.add(status);
}

function showError(message, payload = {}) {
  state.errored = true;
  els.error.hidden = false;
  let text = message;
  if (payload.stage_errors && Object.keys(payload.stage_errors).length) {
    const stages = Object.entries(payload.stage_errors)
      .map(([stage, error]) => `${stage}: ${error}`)
      .join("\n");
    text += `\n\n${stages}`;
  }
  if (payload.trace) {
    text += `\n\nThe run produced ${payload.trace.span_count || 0} spans in ${formatDuration(
      payload.trace.duration_ms || 0,
    )}.`;
  }
  els.error.textContent = text;
  if (state.currentStage) setRail(state.currentStage, "error");
}

function reset() {
  if (state.controller) state.controller.abort();
  state.controller = null;
  state.finished = false;
  state.errored = false;
  state.events = 0;
  state.lastEvent = "";
  state.currentStage = null;
  state.spans.clear();
  state.subagents = 0;
  state.llmCalls = 0;
  state.tokens = 0;
  state.sources = [];
  state.source = null;
  state.refs = [];

  els.timeline.innerHTML = "";
  els.report.innerHTML = "";
  els.report.hidden = true;
  els.sourceNote.hidden = true;
  els.error.hidden = true;
  els.error.textContent = "";
  els.statTime.textContent = "0.0s";
  els.statCalls.textContent = "0";
  els.statTokens.textContent = "0";
  els.statCost.textContent = "—";
  els.rail.querySelectorAll("li").forEach((item) => {
    item.classList.remove("running", "done", "error");
  });
  closeDrawer();
}

function resetToHero() {
  reset();
  els.workspace.hidden = true;
  els.hero.hidden = false;
  els.newRun.hidden = true;
  els.question.disabled = false;
  els.go.disabled = false;
  els.ask.classList.remove("busy");
  els.question.focus();
}

function nearBottom() {
  return window.innerHeight + window.scrollY >= document.body.offsetHeight - 220;
}

function elapsed(startedAt) {
  return `${((performance.now() - startedAt) / 1000).toFixed(1)}s`;
}

function formatDuration(ms) {
  if (!ms) return "0s";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const minutes = Math.floor(ms / 60_000);
  const seconds = Math.round((ms % 60_000) / 1000);
  return `${minutes}m ${seconds}s`;
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString("en-US");
}

function plural(count, word) {
  return `${formatNumber(count)} ${word}${Number(count) === 1 ? "" : "s"}`;
}

function formatCost(value) {
  if (value == null) return "n/a";
  const number = Number(value);
  if (!Number.isFinite(number)) return "n/a";
  if (number === 0) return "$0.0000";
  if (number < 0.01) return `$${number.toFixed(6)}`;
  return `$${number.toFixed(4)}`;
}

function shortModel(model) {
  if (!model) return "unknown";
  return model.replace(/^openai\//, "");
}

function shortDomain(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function displayUrl(url) {
  try {
    const parsed = new URL(url);
    const path = parsed.pathname === "/" ? "" : parsed.pathname;
    const text = `${parsed.hostname.replace(/^www\./, "")}${path}`;
    return text.length > 72 ? `${text.slice(0, 69)}…` : text;
  } catch {
    return url;
  }
}

function verdictClass(name) {
  if (name === "supported") return "good";
  if (name === "partial") return "warn";
  if (name === "unsupported" || name === "contradicted") return "bad";
  return "";
}

function verdictGlyph(name) {
  if (name === "supported") return "✓";
  if (name === "partial") return "~";
  if (name === "contradicted") return "≠";
  return "!";
}

function escapeHtml(text) {
  return String(text)
    .replaceAll(/&/g, "&amp;")
    .replaceAll(/</g, "&lt;")
    .replaceAll(/>/g, "&gt;")
    .replaceAll(/"/g, "&quot;");
}

boot();
