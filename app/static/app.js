const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

let state = { today: null, goals: null, projects: null, weekly: null, outcomes: null, stats: null };
let analyticsData = null;
let driveDocsData = null;
let charts = {};
let availableDates = [];
let viewingArchive = false;
let editingIndex = -1;
let showAddForm = false;
let runMenuOpen = false;

const RUN_PROVIDERS = {
  codex: { label: "Codex", meta: "Default" },
  claude: { label: "Claude Code", meta: "Anthropic CLI" },
  gemini: { label: "Gemini CLI", meta: "Google CLI" },
};

// ── Theme ──

function getTheme() {
  return localStorage.getItem("pm-theme") || "dark";
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const btn = $("#theme-btn");
  if (btn) btn.textContent = theme === "dark" ? "☀" : "☾";
}

function toggleTheme() {
  const next = getTheme() === "dark" ? "light" : "dark";
  localStorage.setItem("pm-theme", next);
  applyTheme(next);
  if (analyticsData) {
    renderAnalytics();
  }
}

applyTheme(getTheme());

// ── Tabs ──

function switchTab(tab) {
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === tab));
  $$(".tab-content").forEach((c) => c.classList.toggle("hidden", c.id !== `tab-${tab}`));
  if (tab === "analytics" && !analyticsData) fetchAnalytics();
  if (tab === "docs" && !driveDocsData) fetchDriveDocs();
}

// ── Today tab ──

async function fetchAll() {
  const [today, goals, projects, weekly, outcomes, stats, dates] = await Promise.all([
    fetch("/api/today").then((r) => r.json()),
    fetch("/api/goals").then((r) => r.json()),
    fetch("/api/projects").then((r) => r.json()),
    fetch("/api/weekly-focus").then((r) => r.json()),
    fetch("/api/outcomes").then((r) => r.json()),
    fetch("/api/stats").then((r) => r.json()),
    fetch("/api/available-dates").then((r) => r.json()),
  ]);
  state = { today, goals, projects, weekly, outcomes, stats };
  availableDates = dates || [];
  viewingArchive = false;
  render();
}

function formatDate(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" });
}

function checkSvg() {
  return `<svg viewBox="0 0 12 12"><polyline points="2,6 5,9 10,3"/></svg>`;
}

function renderTaskForm(task, index) {
  const isNew = index === -1;
  const p = task ? task.priority : 3;
  const dur = task ? parseInt(task.duration) || 30 : 30;
  const title = task ? task.title : "";
  const disc = task ? task.discipline : "";
  const meta = task ? (task.meta || {}) : {};

  return `
    <div class="task-form" onclick="event.stopPropagation()">
      <div class="task-form-row">
        <label class="task-form-label">Priority
          <select class="task-form-select" id="tf-priority">
            <option value="1" ${p === 1 ? "selected" : ""}>P1</option>
            <option value="2" ${p === 2 ? "selected" : ""}>P2</option>
            <option value="3" ${p === 3 ? "selected" : ""}>P3</option>
          </select>
        </label>
        <label class="task-form-label">Duration (min)
          <input type="number" class="task-form-input task-form-dur" id="tf-duration" value="${dur}" min="5" step="5">
        </label>
      </div>
      <label class="task-form-label">Task
        <textarea class="task-form-input task-form-title" id="tf-title" rows="2" placeholder="What needs to be done...">${esc(title)}</textarea>
      </label>
      <label class="task-form-label">Discipline / Category
        <input type="text" class="task-form-input" id="tf-discipline" value="${esc(disc)}" placeholder="e.g. Decision science / Interview prep">
      </label>
      <div class="task-form-row">
        <label class="task-form-label">type
          <input type="text" class="task-form-input" id="tf-type" value="${esc(meta.type || "")}" placeholder="interview_prep">
        </label>
        <label class="task-form-label">goal
          <input type="text" class="task-form-input" id="tf-goal" value="${esc(meta.goal || "")}" placeholder="data_owner">
        </label>
        <label class="task-form-label">sub
          <input type="text" class="task-form-input" id="tf-sub" value="${esc(meta.sub || "")}" placeholder="decision_science">
        </label>
        <label class="task-form-label">backlog
          <input type="text" class="task-form-input" id="tf-backlog" value="${esc(meta.backlog || "")}" placeholder="4d">
        </label>
      </div>
      <div class="task-form-actions">
        <button class="form-btn form-btn-primary" onclick="saveTask(${index})">${isNew ? "Add Task" : "Save"}</button>
        <button class="form-btn form-btn-secondary" onclick="cancelEdit()">Cancel</button>
      </div>
    </div>`;
}

function renderTasks(tasks) {
  if (!tasks || tasks.length === 0)
    return `<div class="empty-state"><div class="empty-state-title">No tasks yet</div><p>Run the personal PM flow to generate today's plan.</p></div>`;

  const checked = tasks.filter((t) => t.checked).length;
  const total = tasks.length;
  const pct = total > 0 ? Math.round((checked / total) * 100) : 0;
  const editable = !viewingArchive;

  let html = `
    <div class="progress-bar-wrapper">
      <div class="progress-label"><span>${checked} of ${total} tasks</span><span>${pct}%</span></div>
      <div class="progress-bar"><div class="progress-fill" style="width:${pct}%"></div></div>
    </div>
    <div class="task-list">`;

  tasks.forEach((task, i) => {
    if (editingIndex === i && editable) {
      html += renderTaskForm(task, i);
      return;
    }

    const cls = `task-card p${task.priority}${task.checked ? " checked" : ""}`;
    const backlogAge = task.meta && task.meta.backlog ? task.meta.backlog : "";
    const metaTags = Object.entries(task.meta || {})
      .filter(([k]) => k !== "backlog")
      .map(([k, v]) => `<span class="task-meta-tag">${esc(k)}: ${esc(v)}</span>`)
      .join("");

    html += `
      <div class="${cls}" data-index="${i}" onclick="toggleTask(${i})">
        <div class="task-checkbox">${checkSvg()}</div>
        <div class="task-body">
          <div class="task-top-row">
            <span class="task-priority">P${task.priority}</span>
            <span class="task-duration">${task.duration}</span>
            ${backlogAge ? `<span class="task-backlog-tag" title="Carried forward from prior runs">Backlog ${esc(backlogAge)}</span>` : ""}
          </div>
          <div class="task-title">${esc(task.title)}</div>
          ${task.discipline ? `<div class="task-discipline">${esc(task.discipline)}</div>` : ""}
          ${metaTags ? `<div class="task-meta">${metaTags}</div>` : ""}
        </div>
        ${editable ? `<div class="task-actions" onclick="event.stopPropagation()">
          <button class="task-action-btn" onclick="startEdit(${i})" title="Edit">&#9998;</button>
          <button class="task-action-btn task-action-delete" onclick="deleteTask(${i})" title="Delete">&times;</button>
        </div>` : ""}
      </div>`;
  });

  html += `</div>`;

  if (editable) {
    if (showAddForm) {
      html += renderTaskForm(null, -1);
    } else {
      html += `<button class="add-task-btn" onclick="openAddForm()">+ Add Task</button>`;
    }
  }

  return html;
}

function renderInfoSection(id, title, items) {
  if (!items || items.length === 0) return "";
  return `
    <div class="section">
      <div class="section-header" onclick="toggleSection('${id}')">
        <span class="section-title">${title}</span>
        <span class="section-count">${items.length}</span>
        <span class="section-toggle" id="toggle-${id}">&#9662;</span>
      </div>
      <div class="info-section" id="section-${id}">
        <div class="info-content">
          <ul class="info-list">
            ${items.map((item) => `<li class="info-item">${esc(item)}</li>`).join("")}
          </ul>
        </div>
      </div>
    </div>`;
}

function renderFeedback(feedback) {
  if (!feedback) return "";
  return `
    <div class="section">
      <div class="section-header"><span class="section-title">Feedback for Tomorrow</span></div>
      <div class="feedback-card">
        <div class="feedback-field">
          <div class="feedback-label">What worked</div>
          <textarea class="feedback-input" rows="2" placeholder="What went well today..."
            data-field="worked" onblur="saveFeedback(this)">${esc(feedback.worked || "")}</textarea>
        </div>
        <div class="feedback-field">
          <div class="feedback-label">What didn't work</div>
          <textarea class="feedback-input" rows="2" placeholder="What to avoid or change..."
            data-field="did_not_work" onblur="saveFeedback(this)">${esc(feedback.did_not_work || "")}</textarea>
        </div>
        <div class="feedback-field">
          <div class="feedback-label">New goal or constraint</div>
          <textarea class="feedback-input" rows="2" placeholder="Anything new to factor in..."
            data-field="new_goal" onblur="saveFeedback(this)">${esc(feedback.new_goal || "")}</textarea>
        </div>
      </div>
    </div>`;
}

function renderContext() {
  let html = `<div class="context-panel"><div class="section-header"><span class="section-title">Planning Context</span></div><div class="context-grid">`;

  if (state.goals) {
    html += `<div class="context-card"><div class="context-card-title">Goals</div>
      ${(state.goals.overall_goals || []).map((g) => `<div class="context-item">${esc(g)}</div>`).join("")}</div>`;
  }
  if (state.weekly) {
    html += `<div class="context-card"><div class="context-card-title">Weekly Focus — ${state.weekly.week_of || ""}</div>
      ${(state.weekly.priorities || []).map((p, i) => `<div class="context-item"><span class="label">${i + 1}.</span> ${esc(p)}</div>`).join("")}</div>`;
  }
  if (state.projects && state.projects.length > 0) {
    const active = state.projects.filter((p) => p.priority === "Now");
    html += `<div class="context-card"><div class="context-card-title">Active Projects</div>
      ${active.map((p) => `<div class="context-item"><span class="project-priority now">Now</span> ${esc(p.name)}</div>`).join("")}</div>`;
  }
  if (state.stats) {
    html += `<div class="context-card"><div class="context-card-title">Track Record</div>
      <div class="context-item"><span class="label">${state.stats.completion_days || 0}</span> days with completions</div>
      <div class="context-item"><span class="label">${state.stats.total_days || 0}</span> days tracked</div></div>`;
  }

  html += `</div></div>`;
  return html;
}

function renderToolbar(today) {
  const todayDate = new Date().toISOString().slice(0, 10);
  const currentDate = today ? today.date : null;
  const isViewingToday = !viewingArchive;

  const dateOptions = availableDates
    .map((d) => {
      const label = d === todayDate ? `${d} (today)` : d;
      const selected = viewingArchive && d === currentDate ? "selected" : "";
      return `<option value="${d}" ${selected}>${label}</option>`;
    })
    .join("");

  return `
    <div class="toolbar">
      <div class="run-picker" id="run-picker">
        <button class="toolbar-btn run-btn" onclick="toggleRunMenu(event)" id="run-btn" title="Choose a CLI runner for today's PM flow">
          <span class="run-icon">&#9654;</span> Run Today's Flow
        </button>
        <div class="run-menu ${runMenuOpen ? "" : "hidden"}" id="run-menu">
          ${Object.entries(RUN_PROVIDERS).map(([key, provider]) => `
            <button class="run-menu-item" onclick="runTodayFlow('${key}')">
              <span class="run-menu-label">${provider.label}</span>
              <span class="run-menu-meta">${provider.meta}</span>
            </button>
          `).join("")}
        </div>
      </div>
      <div class="toolbar-right">
        <select class="date-select" onchange="loadDate(this.value)" id="date-select">
          <option value="" ${isViewingToday ? "selected" : ""}>Current plan</option>
          ${dateOptions}
        </select>
      </div>
    </div>`;
}

function render() {
  const app = $("#app");
  const today = state.today;

  if (!today) {
    app.innerHTML = `${renderToolbar(null)}<div class="empty-state"><div class="empty-state-title">No plan found</div><p>Run the personal PM flow to generate today's plan.</p></div>`;
    return;
  }

  const todayDate = new Date().toISOString().slice(0, 10);
  const isCurrentDay = today.date === todayDate;
  const showStaleWarning = !viewingArchive && !isCurrentDay;

  app.innerHTML = `
    ${renderToolbar(today)}
    <div class="header">
      <div class="header-date">${formatDate(today.date)}</div>
      <div class="header-title">${viewingArchive ? "Archived Plan" : "Today's Plan"}</div>
      ${showStaleWarning ? `<div class="header-subtitle">This plan is from a previous day</div>` : ""}
      ${viewingArchive ? `<div class="header-subtitle archive-label">Viewing archived plan</div>` : ""}
    </div>
    <div class="section">
      <div class="section-header"><span class="section-title">Tasks</span><span class="section-count">${today.tasks.length}</span></div>
      ${renderTasks(today.tasks)}
    </div>
    ${renderInfoSection("carry", "Carry-forward", today.carry_forward)}
    ${renderInfoSection("heads", "Heads-up", today.heads_up)}
    ${!viewingArchive ? renderFeedback(today.feedback) : ""}
    ${!viewingArchive ? renderContext() : ""}`;

  if (_runActive) _showRunPanel();
}

async function toggleTask(index) {
  const res = await fetch("/api/toggle-task", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ index }),
  });
  const data = await res.json();
  if (data.ok) {
    state.today = data.today;
    render();
  }
}

async function saveFeedback(el) {
  const field = el.dataset.field;
  const value = el.value.trim();
  await fetch("/api/update-feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ field, value }),
  });
}

function startEdit(index) {
  editingIndex = index;
  showAddForm = false;
  render();
}

function openAddForm() {
  showAddForm = true;
  editingIndex = -1;
  render();
}

function cancelEdit() {
  editingIndex = -1;
  showAddForm = false;
  render();
}

function _readForm(existingMeta = {}) {
  const meta = { ...existingMeta };
  meta.type = $("#tf-type").value.trim();
  meta.goal = $("#tf-goal").value.trim();
  meta.sub = $("#tf-sub").value.trim();
  const backlog = $("#tf-backlog").value.trim();
  if (backlog) {
    meta.backlog = backlog;
  } else {
    delete meta.backlog;
  }

  return {
    priority: parseInt($("#tf-priority").value),
    duration: parseInt($("#tf-duration").value) || 30,
    title: $("#tf-title").value.trim(),
    discipline: $("#tf-discipline").value.trim(),
    meta,
  };
}

async function saveTask(index) {
  const existingMeta = index === -1 ? {} : ((state.today.tasks[index] || {}).meta || {});
  const data = _readForm(existingMeta);
  if (!data.title) return;

  const url = index === -1 ? "/api/add-task" : "/api/edit-task";
  const body = index === -1 ? data : { index, ...data };

  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const result = await res.json();
  if (result.ok) {
    state.today = result.today;
    editingIndex = -1;
    showAddForm = false;
    render();
  }
}

async function deleteTask(index) {
  const res = await fetch("/api/delete-task", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ index }),
  });
  const result = await res.json();
  if (result.ok) {
    state.today = result.today;
    render();
  }
}

async function loadDate(dateStr) {
  if (!dateStr) {
    viewingArchive = false;
    await fetchAll();
    return;
  }

  const todayData = state.today;
  if (todayData && todayData.date === dateStr && !viewingArchive) {
    return;
  }

  const res = await fetch(`/api/archive/${dateStr}`);
  if (res.ok) {
    state.today = await res.json();
    viewingArchive = true;
    render();
  } else {
    if (todayData && todayData.date === dateStr) {
      viewingArchive = false;
      state.today = todayData;
      render();
    }
  }
}

let _pollTimer = null;
let _runActive = false;
let _activeRunProvider = "codex";

function runProviderLabel(provider) {
  return (RUN_PROVIDERS[provider] || RUN_PROVIDERS.codex).label;
}

function toggleRunMenu(event) {
  if (event) event.stopPropagation();
  if (_runActive) return;
  runMenuOpen = !runMenuOpen;
  render();
}

function _showRunPanel(providerLabel) {
  let panel = $("#run-progress");
  if (!panel) {
    const container = $("#app");
    if (!container) return;
    const div = document.createElement("div");
    div.id = "run-progress";
    div.className = "run-progress";
    div.innerHTML = `
      <div class="run-progress-header">
        <span class="spinner"></span>
        <span class="run-progress-title">Running PM flow with ${esc(providerLabel || runProviderLabel(_activeRunProvider))}…</span>
      </div>
      <pre class="run-progress-log" id="run-log"></pre>`;
    container.prepend(div);
  }
}

function _updateRunLog(log) {
  const el = $("#run-log");
  if (el) {
    el.textContent = log || "Starting…";
    el.scrollTop = el.scrollHeight;
  }
}

function _hideRunPanel() {
  const panel = $("#run-progress");
  if (panel) panel.remove();
}

async function runTodayFlow(provider = "codex") {
  const btn = $("#run-btn");
  if (!btn) return;

  _activeRunProvider = provider;
  runMenuOpen = false;
  const providerLabel = runProviderLabel(provider);

  btn.disabled = true;
  btn.classList.add("running");
  btn.innerHTML = `<span class="spinner"></span> Running ${providerLabel}…`;
  _runActive = true;

  _showRunPanel(providerLabel);

  try {
    const res = await fetch("/api/run-today", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider }),
    });
    const data = await res.json();
    if (!data.ok) {
      btn.innerHTML = `<span class="run-icon">&#9654;</span> ${data.error || "Error"}`;
      btn.classList.remove("running");
      btn.disabled = false;
      _runActive = false;
      _hideRunPanel();
      return;
    }
    _pollTimer = setInterval(pollRunStatus, 2000);
  } catch {
    btn.innerHTML = `<span class="run-icon">&#9654;</span> Failed`;
    btn.classList.remove("running");
    btn.disabled = false;
    _runActive = false;
    _hideRunPanel();
  }
}

async function pollRunStatus() {
  const res = await fetch("/api/run-status");
  const data = await res.json();
  const providerLabel = data.provider_label || runProviderLabel(_activeRunProvider);

  _updateRunLog(data.log);

  if (!data.running) {
    clearInterval(_pollTimer);
    _pollTimer = null;
    _runActive = false;

    const header = $(".run-progress-header");
    if (header) {
      header.innerHTML = `<span class="run-progress-done">&#10003;</span><span class="run-progress-title">${esc(providerLabel)} flow complete</span>`;
    }

    setTimeout(async () => {
      _hideRunPanel();
      viewingArchive = false;
      await fetchAll();
      const btn = $("#run-btn");
      if (btn) {
        btn.disabled = false;
        btn.classList.remove("running");
        btn.innerHTML = `<span class="run-icon">&#9654;</span> Run Today's Flow`;
      }
    }, 2000);
  }
}

document.addEventListener("click", (event) => {
  if (!runMenuOpen) return;
  if (event.target.closest("#run-picker")) return;
  runMenuOpen = false;
  render();
});

function toggleSection(id) {
  const section = $(`#section-${id}`);
  const toggle = $(`#toggle-${id}`);
  section.classList.toggle("collapsed");
  toggle.classList.toggle("collapsed");
}

function esc(str) {
  const div = document.createElement("div");
  div.textContent = str || "";
  return div.innerHTML;
}

function safeHref(url) {
  try {
    const parsed = new URL(url);
    if (parsed.protocol === "https:" || parsed.protocol === "http:") return parsed.href;
  } catch {
    return "";
  }
  return "";
}

// ── Analytics tab ──

const SUB_COLORS = {
  decision_science: "#10b981",
  career_assets: "#f59e0b",
  data_foundation: "#06b6d4",
  website: "#a78bfa",
  evaluation_discipline: "#ef4444",
  service_platform_eng: "#84cc16",
  writing: "#ec4899",
  physical_ai: "#6366f1",
  other: "#6b6b6b",
};

const TYPE_COLORS = {
  interview_prep: "#f59e0b",
  project_work: "#6366f1",
  skill_practice: "#06b6d4",
  career: "#ec4899",
  writing: "#10b981",
  design_exploration: "#a78bfa",
  other: "#6b6b6b",
};

function prettyLabel(s) {
  return (s || "other").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

async function fetchAnalytics() {
  analyticsData = await fetch("/api/analytics").then((r) => r.json());
  renderAnalytics();
}

// Fill in all dates between first and last day so charts show gaps
function fillDateGaps(days) {
  if (!days || days.length === 0) return [];

  const dayMap = {};
  days.forEach((d) => { dayMap[d.date] = d; });

  const first = new Date(days[0].date + "T00:00:00");
  const last = new Date(days[days.length - 1].date + "T00:00:00");
  const filled = [];
  const cur = new Date(first);

  while (cur <= last) {
    const key = cur.toISOString().slice(0, 10);
    if (dayMap[key]) {
      filled.push(dayMap[key]);
    } else {
      filled.push({
        date: key,
        planned: 0,
        completed: 0,
        completion_rate: null,
        by_priority: {},
        by_sub: {},
        by_type: {},
        planned_minutes: 0,
        completed_minutes: 0,
        _noRun: true,
      });
    }
    cur.setDate(cur.getDate() + 1);
  }

  return filled;
}

function renderAnalytics() {
  const el = $("#analytics");
  const d = analyticsData;
  if (!d || !d.days || d.days.length === 0) {
    el.innerHTML = `<div class="empty-state"><div class="empty-state-title">No archive data yet</div><p>Run the PM flow for a few days to see analytics.</p></div>`;
    return;
  }

  const s = d.summary;

  el.innerHTML = `
    <div class="analytics-header">
      <h1>90-Day Analytics</h1>
      <p>${s.total_days} days tracked &middot; ${s.total_completed} tasks completed &middot; ${s.total_completed_hours}h logged</p>
    </div>

    <div class="summary-grid">
      <div class="summary-card">
        <div class="big-number ${s.overall_completion_rate >= 40 ? "green" : s.overall_completion_rate >= 20 ? "amber" : "red"}">${s.overall_completion_rate}%</div>
        <div class="card-label">Completion Rate</div>
      </div>
      <div class="summary-card">
        <div class="big-number blue">${s.total_days}</div>
        <div class="card-label">Days Run</div>
      </div>
      <div class="summary-card">
        <div class="big-number green">${s.days_with_completions}</div>
        <div class="card-label">Productive Days</div>
      </div>
      <div class="summary-card">
        <div class="big-number">${s.avg_completed_per_day}</div>
        <div class="card-label">Avg / Day</div>
      </div>
    </div>

    <div class="chart-section">
      <div class="chart-card">
        <div class="chart-card-title">Completion Rate Over Time</div>
        <div class="chart-container"><canvas id="chart-rate"></canvas></div>
      </div>
    </div>

    <div class="chart-section">
      <div class="chart-card">
        <div class="chart-card-title">Planned vs Completed per Day</div>
        <div class="chart-container"><canvas id="chart-daily"></canvas></div>
      </div>
    </div>

    <div class="chart-section">
      <div class="chart-card">
        <div class="chart-card-title">Completed Tasks by Category</div>
        <div class="chart-container tall"><canvas id="chart-stacked"></canvas></div>
      </div>
    </div>

    <div class="chart-section chart-row">
      <div class="chart-card">
        <div class="chart-card-title">By Discipline</div>
        <div class="chart-container"><canvas id="chart-sub-donut"></canvas></div>
      </div>
      <div class="chart-card">
        <div class="chart-card-title">By Task Type</div>
        <div class="chart-container"><canvas id="chart-type-donut"></canvas></div>
      </div>
    </div>

    <div class="chart-section">
      <div class="chart-card">
        <div class="chart-card-title">Activity Heatmap</div>
        <div id="heatmap-container"></div>
      </div>
    </div>`;

  drawCharts(d);
}

function shortDate(dateStr) {
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function destroyCharts() {
  Object.values(charts).forEach((c) => { if (c) c.destroy(); });
  charts = {};
}

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function drawCharts(d) {
  destroyCharts();

  const filledDays = fillDateGaps(d.days);
  const labels = filledDays.map((x) => shortDate(x.date));

  const gridColor = cssVar("--chart-grid") || "rgba(255,255,255,0.06)";
  const tickColor = cssVar("--chart-tick") || "#6b6b6b";
  const tooltipBg = cssVar("--chart-tooltip-bg") || "#2f2f2f";
  const plannedBarColor = cssVar("--chart-planned-bar") || "rgba(255,255,255,0.1)";

  const baseOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
  };

  const scaleDefaults = {
    grid: { color: gridColor, drawBorder: false },
    ticks: { font: { size: 11, family: "ui-sans-serif, -apple-system, sans-serif" }, color: tickColor },
  };

  const tooltipStyle = {
    backgroundColor: tooltipBg,
    titleColor: "#e8e6e3",
    bodyColor: "#e8e6e3",
    titleFont: { size: 12 },
    bodyFont: { size: 12 },
    cornerRadius: 6,
    padding: 8,
  };

  // 1. Completion rate line — null values create gaps for no-run days
  charts.rate = new Chart($("#chart-rate"), {
    type: "line",
    data: {
      labels,
      datasets: [{
        data: filledDays.map((x) => x.completion_rate),
        borderColor: "#84cc16",
        backgroundColor: "rgba(132, 204, 22, 0.08)",
        fill: true,
        tension: 0.35,
        pointRadius: filledDays.map((x) => x._noRun ? 0 : 5),
        pointBackgroundColor: "#84cc16",
        pointBorderColor: cssVar("--surface") || "#202020",
        pointBorderWidth: 2,
        borderWidth: 2.5,
        spanGaps: false,
      }],
    },
    options: {
      ...baseOptions,
      scales: {
        x: scaleDefaults,
        y: { ...scaleDefaults, min: 0, max: 100, ticks: { ...scaleDefaults.ticks, callback: (v) => v + "%" } },
      },
      plugins: {
        ...baseOptions.plugins,
        tooltip: { ...tooltipStyle, callbacks: { label: (ctx) => ctx.parsed.y !== null ? ctx.parsed.y + "% completed" : "No run" } },
      },
    },
  });

  // 2. Planned vs completed grouped bar — no-run days show empty
  charts.daily = new Chart($("#chart-daily"), {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "Planned", data: filledDays.map((x) => x.planned || 0), backgroundColor: plannedBarColor, borderRadius: 3 },
        { label: "Completed", data: filledDays.map((x) => x.completed || 0), backgroundColor: "#84cc16", borderRadius: 3 },
      ],
    },
    options: {
      ...baseOptions,
      plugins: {
        ...baseOptions.plugins,
        legend: { display: true, position: "top", labels: { boxWidth: 10, font: { size: 11 }, padding: 16, color: tickColor } },
        tooltip: tooltipStyle,
      },
      scales: {
        x: scaleDefaults,
        y: { ...scaleDefaults, beginAtZero: true, ticks: { ...scaleDefaults.ticks, stepSize: 1 } },
      },
    },
  });

  // 3. Stacked bar by sub category — uses filled days
  const allSubs = new Set();
  filledDays.forEach((day) => Object.keys(day.by_sub).forEach((s) => allSubs.add(s)));
  const subList = [...allSubs].sort();

  const stackedDatasets = subList.map((sub) => ({
    label: prettyLabel(sub),
    data: filledDays.map((day) => day.by_sub[sub] || 0),
    backgroundColor: SUB_COLORS[sub] || "#6b6b6b",
    borderRadius: 2,
  }));

  charts.stacked = new Chart($("#chart-stacked"), {
    type: "bar",
    data: { labels, datasets: stackedDatasets },
    options: {
      ...baseOptions,
      plugins: {
        ...baseOptions.plugins,
        legend: { display: true, position: "top", labels: { boxWidth: 10, font: { size: 10 }, padding: 12, color: tickColor } },
        tooltip: tooltipStyle,
      },
      scales: {
        x: { ...scaleDefaults, stacked: true },
        y: { ...scaleDefaults, stacked: true, beginAtZero: true, ticks: { ...scaleDefaults.ticks, stepSize: 1 } },
      },
    },
  });

  // 4. Sub donut
  const subData = d.summary.by_sub;
  const subKeys = Object.keys(subData).sort((a, b) => subData[b] - subData[a]);
  charts.subDonut = new Chart($("#chart-sub-donut"), {
    type: "doughnut",
    data: {
      labels: subKeys.map(prettyLabel),
      datasets: [{
        data: subKeys.map((k) => subData[k]),
        backgroundColor: subKeys.map((k) => SUB_COLORS[k] || "#6b6b6b"),
        borderWidth: 2,
        borderColor: cssVar("--surface") || "#202020",
      }],
    },
    options: {
      ...baseOptions,
      cutout: "65%",
      plugins: {
        ...baseOptions.plugins,
        legend: { display: true, position: "right", labels: { boxWidth: 10, font: { size: 11 }, padding: 10, color: tickColor } },
        tooltip: tooltipStyle,
      },
    },
  });

  // 5. Type donut
  const typeData = d.summary.by_type;
  const typeKeys = Object.keys(typeData).sort((a, b) => typeData[b] - typeData[a]);
  charts.typeDonut = new Chart($("#chart-type-donut"), {
    type: "doughnut",
    data: {
      labels: typeKeys.map(prettyLabel),
      datasets: [{
        data: typeKeys.map((k) => typeData[k]),
        backgroundColor: typeKeys.map((k) => TYPE_COLORS[k] || "#6b6b6b"),
        borderWidth: 2,
        borderColor: cssVar("--surface") || "#202020",
      }],
    },
    options: {
      ...baseOptions,
      cutout: "65%",
      plugins: {
        ...baseOptions.plugins,
        legend: { display: true, position: "right", labels: { boxWidth: 10, font: { size: 11 }, padding: 10, color: tickColor } },
        tooltip: tooltipStyle,
      },
    },
  });

  // 6. Heatmap
  renderHeatmap(d.days);
}

function renderHeatmap(days) {
  const container = $("#heatmap-container");
  const dayMap = {};
  days.forEach((d) => { dayMap[d.date] = d.completed; });

  const today = new Date();
  const start = new Date(today);
  start.setDate(start.getDate() - 89);

  let html = `<div class="heatmap-grid">`;
  const cur = new Date(start);

  while (cur <= today) {
    const key = cur.toISOString().slice(0, 10);
    const count = dayMap[key];
    let level = "empty";
    let title = key;

    if (count !== undefined) {
      if (count === 0) level = "level-0";
      else if (count === 1) level = "level-1";
      else if (count === 2) level = "level-2";
      else if (count <= 3) level = "level-3";
      else level = "level-4";
      title = `${key}: ${count} completed`;
    }

    html += `<div class="heatmap-cell ${level}" title="${title}"></div>`;
    cur.setDate(cur.getDate() + 1);
  }

  html += `</div>`;
  html += `<div class="heatmap-legend">
    <span>Less</span>
    <div class="heatmap-cell level-0"></div>
    <div class="heatmap-cell level-1"></div>
    <div class="heatmap-cell level-2"></div>
    <div class="heatmap-cell level-3"></div>
    <div class="heatmap-cell level-4"></div>
    <span>More</span>
  </div>`;

  container.innerHTML = html;
}

// ── Docs tab ──

async function fetchDriveDocs() {
  driveDocsData = await fetch("/api/recent-docs").then((r) => r.json());
  renderDriveDocs();
}

function renderDocPills(values, cls = "") {
  if (!values || values.length === 0) return "";
  return values.map((value) => `<span class="doc-pill ${cls}">${esc(prettyLabel(value))}</span>`).join("");
}

function renderDriveDocs() {
  const el = $("#docs");
  const d = driveDocsData;
  if (!d) {
    el.innerHTML = `<div class="loading">Loading recent docs...</div>`;
    return;
  }

  if (d.error) {
    el.innerHTML = `<div class="empty-state"><div class="empty-state-title">Docs cache is invalid</div><p>${esc(d.error)}</p></div>`;
    return;
  }

  const docs = d.docs || [];
  const s = d.summary || {};
  const generated = d.generated_at ? formatDate(d.generated_at.slice(0, 10)) : "No scan yet";
  const source = d.source ? String(d.source).replace(/_/g, " ") : "cache";
  const lookback = d.lookback_days ? `${d.lookback_days} days` : "configured window";

  if (docs.length === 0) {
    el.innerHTML = `
      <div class="docs-header">
        <h1>Recent Docs</h1>
        <p>${d.missing ? "No docs cache found" : "No matching docs found"} &middot; ${esc(source)}</p>
      </div>
      <div class="empty-state"><div class="empty-state-title">No goal-linked docs yet</div><p>No recent Drive document metadata is cached for this workspace.</p></div>`;
    return;
  }

  el.innerHTML = `
    <div class="docs-header">
      <h1>Recent Docs</h1>
      <p>${docs.length} docs matched &middot; ${esc(lookback)} &middot; scanned ${esc(generated)}</p>
    </div>

    <div class="summary-grid docs-summary">
      <div class="summary-card">
        <div class="big-number blue">${s.total || docs.length}</div>
        <div class="card-label">Matched Docs</div>
      </div>
      <div class="summary-card">
        <div class="big-number green">${s.high_confidence || 0}</div>
        <div class="card-label">High Confidence</div>
      </div>
      <div class="summary-card">
        <div class="big-number amber">${s.actionable || 0}</div>
        <div class="card-label">Actionable</div>
      </div>
      <div class="summary-card">
        <div class="big-number">${Object.keys(s.projects || {}).length}</div>
        <div class="card-label">Projects</div>
      </div>
    </div>

    <div class="doc-list">
      ${docs.map(renderDriveDocCard).join("")}
    </div>`;
}

function renderDriveDocCard(doc) {
  const href = safeHref(doc.url || "");
  const created = doc.created_at ? shortDate(doc.created_at.slice(0, 10)) : "Unknown date";
  const modified = doc.modified_at ? shortDate(doc.modified_at.slice(0, 10)) : "";
  const confidence = Math.round((doc.confidence || 0) * 100);
  const priority = doc.priority_hint ? `<span class="doc-priority">${esc(doc.priority_hint)}</span>` : "";
  const title = esc(doc.title || "Untitled document");
  const titleMarkup = href
    ? `<a class="doc-title" href="${esc(href)}" target="_blank" rel="noreferrer">${title}</a>`
    : `<div class="doc-title">${title}</div>`;

  return `
    <article class="doc-card">
      <div class="doc-card-top">
        <div class="doc-date">${esc(created)}${modified ? ` &middot; modified ${esc(modified)}` : ""}</div>
        <div class="doc-badges">
          ${priority}
          <span class="doc-confidence">${confidence}%</span>
        </div>
      </div>
      ${titleMarkup}
      ${doc.summary ? `<p class="doc-summary">${esc(doc.summary)}</p>` : ""}
      ${doc.reason ? `<p class="doc-reason">${esc(doc.reason)}</p>` : ""}
      <div class="doc-pill-row">
        ${renderDocPills(doc.matched_goals || [], "goal")}
        ${renderDocPills(doc.matched_projects || [], "project")}
        ${renderDocPills(doc.matched_keywords || [])}
      </div>
    </article>`;
}

// ── Init ──

fetchAll();

if (location.hash === "#analytics") switchTab("analytics");
if (location.hash === "#docs") switchTab("docs");
