const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

let state = { today: null, goals: null, projects: null, weekly: null, outcomes: null, stats: null, morning: null };
let analyticsData = null;
let driveDocsData = null;
let charts = {};
let availableDates = [];
let viewingArchive = false;
let editingIndex = -1;
let showAddForm = false;
let editingProjectIndex = -1;
let showProjectAddForm = false;
let projectError = "";
let editingWeeklyIndex = -1;
let showWeeklyAddForm = false;
let weeklyError = "";
let runMenuOpen = false;
let selectedRunMode = "normal";
let selectedRunFocus = "Default";
let customRunFocus = "";
let morningDetailsOpen = false;

const RUN_PROVIDERS = {
  codex: { label: "Codex", meta: "Default" },
  claude: { label: "Claude Code", meta: "Anthropic CLI" },
  gemini: { label: "Gemini CLI", meta: "Google CLI" },
};

const RUN_FOCUS_OPTIONS = [
  "Default",
  "Judgement",
  "Data foundation",
  "Decision science",
  "Evaluation discipline",
  "Service / platform engineering",
  "Physical AI",
  "Experience Design",
];

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

// ── UI helpers: keyboard, toasts, confirm ──

// Opaque IDs (Drive doc ids, hashes) carry no meaning for the user — keep them out of tags.
function isOpaqueId(value) {
  const v = String(value || "");
  return /^[A-Za-z0-9_-]{20,}$/.test(v) && !/\s/.test(v);
}

function activateKey(event, fn) {
  if (event.key === "Enter" || event.key === " " || event.key === "Spacebar") {
    event.preventDefault();
    fn();
  }
}

function toast(message, type = "info") {
  const container = $("#toast-container");
  if (!container || !message) return;
  const el = document.createElement("div");
  el.className = `toast toast-${type}`;
  el.textContent = message;
  container.appendChild(el);
  requestAnimationFrame(() => el.classList.add("show"));
  setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 220);
  }, 2600);
}

function confirmDialog({ title, message = "", confirmLabel = "Delete", cancelLabel = "Cancel", danger = true }) {
  return new Promise((resolve) => {
    const previous = document.activeElement;
    const overlay = document.createElement("div");
    overlay.className = "confirm-overlay";
    overlay.innerHTML = `
      <div class="confirm-panel" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title">
        <h2 class="confirm-title" id="confirm-title">${esc(title)}</h2>
        ${message ? `<p class="confirm-message">${esc(message)}</p>` : ""}
        <div class="confirm-actions">
          <button type="button" class="form-btn form-btn-secondary" data-act="cancel">${esc(cancelLabel)}</button>
          <button type="button" class="form-btn ${danger ? "form-btn-danger" : "form-btn-primary"}" data-act="confirm">${esc(confirmLabel)}</button>
        </div>
      </div>`;

    function close(result) {
      document.removeEventListener("keydown", onKey, true);
      overlay.remove();
      if (previous && typeof previous.focus === "function") previous.focus();
      resolve(result);
    }

    function onKey(e) {
      if (e.key === "Escape") {
        e.preventDefault();
        close(false);
      }
    }

    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) return close(false);
      const act = e.target.closest("[data-act]");
      if (act) close(act.dataset.act === "confirm");
    });

    document.addEventListener("keydown", onKey, true);
    document.body.appendChild(overlay);
    const cancelBtn = overlay.querySelector('[data-act="cancel"]');
    if (cancelBtn) cancelBtn.focus();
  });
}

// ── First-run onboarding (goals + weekly focus) ──

let _onboardingDismissed = false;
let _onboardingState = null;

// Fetch JSON but surface accurate errors (a stale server returns a 404 HTML page,
// which would otherwise look like a network failure).
async function _onboardingFetch(url, payload) {
  let res;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new Error("Could not reach the app server. Is it still running?");
  }
  if (res.status === 404) {
    throw new Error("Onboarding isn't available on the running server — restart the app to load the latest version.");
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    throw new Error(`The server returned an unexpected response (HTTP ${res.status}).`);
  }
  if (!res.ok || (data && data.ok === false)) {
    throw new Error((data && data.error) || `Request failed (HTTP ${res.status}).`);
  }
  return data;
}

function needsOnboarding() {
  const hasGoals = !!(state.goals && (state.goals.overall_goals || []).length);
  const weekOf = defaultWeekOf();
  const weeks = (state.weekly && state.weekly.weeks) || [];
  const hasWeekly = weeks.some((w) => w.week_of === weekOf);
  return { need: !hasWeekly || !hasGoals, weekOf, needGoals: !hasGoals };
}

function maybeStartOnboarding() {
  if (_onboardingDismissed || viewingArchive) return;
  if (document.querySelector(".onboarding-overlay")) return;
  const { need, weekOf, needGoals } = needsOnboarding();
  if (!need) return;
  openOnboarding(weekOf, needGoals);
}

function openOnboarding(weekOf, needGoals) {
  _onboardingState = {
    step: "intro",
    weekOf,
    needGoals,
    provider: "codex",
    questions: [],
    answers: {},
    error: "",
  };
  renderOnboarding();
}

function setOnboardingProvider(value) {
  if (_onboardingState && RUN_PROVIDERS[value]) _onboardingState.provider = value;
}

function closeOnboarding(landOnToday = true) {
  _onboardingState = null;
  const el = document.querySelector(".onboarding-overlay");
  if (el) el.remove();
  if (landOnToday) switchTab("today");
}

function dismissOnboarding() {
  _onboardingDismissed = true;
  closeOnboarding(true);
}

function onboardingManualSetup() {
  _onboardingDismissed = true;
  closeOnboarding(false);
  switchTab("weekly");
  openWeeklyAddForm();
}

function startOnboardingQuestions() {
  if (!_onboardingState) return;
  _onboardingState.step = "loading";
  _onboardingState.error = "";
  renderOnboarding();
  _onboardingFetch("/api/onboarding/questions", {
    need_goals: _onboardingState.needGoals,
    provider: _onboardingState.provider,
  })
    .then((data) => {
      if (!_onboardingState) return;
      if (Array.isArray(data.questions) && data.questions.length) {
        _onboardingState.questions = data.questions;
        _onboardingState.step = "questions";
      } else {
        _onboardingState.step = "error";
        _onboardingState.error = "The assistant didn't return any questions. Try again.";
      }
      renderOnboarding();
    })
    .catch((err) => {
      if (!_onboardingState) return;
      _onboardingState.step = "error";
      _onboardingState.error = err.message || "Could not load questions.";
      renderOnboarding();
    });
}

function _captureOnboardingAnswers() {
  (_onboardingState.questions || []).forEach((q, i) => {
    const el = $(`#onb-q-${i}`);
    if (el) _onboardingState.answers[q.id] = el.value;
  });
}

function submitOnboarding() {
  if (!_onboardingState) return;
  _captureOnboardingAnswers();
  const qs = _onboardingState.questions || [];
  const answers = qs
    .map((q) => ({ id: q.id, label: q.label, answer: (_onboardingState.answers[q.id] || "").trim() }))
    .filter((a) => a.answer);

  if (answers.length < Math.min(2, qs.length)) {
    _onboardingState.error = "Answer at least a couple of questions so the draft is useful.";
    renderOnboarding();
    return;
  }

  _onboardingState.step = "generating";
  _onboardingState.error = "";
  renderOnboarding();

  _onboardingFetch("/api/onboarding/generate", {
    need_goals: _onboardingState.needGoals,
    provider: _onboardingState.provider,
    answers,
  })
    .then(async () => {
      if (!_onboardingState) return;
      _onboardingDismissed = true;
      closeOnboarding(true);
      toast("Weekly focus created", "success");
      await fetchAll();
    })
    .catch((err) => {
      if (!_onboardingState) return;
      _onboardingState.step = "questions";
      _onboardingState.error = err.message || "Could not generate the weekly focus.";
      renderOnboarding();
    });
}

function _onboardingProviderField() {
  const options = Object.entries(RUN_PROVIDERS)
    .map(
      ([key, p]) =>
        `<option value="${key}" ${_onboardingState.provider === key ? "selected" : ""}>${esc(p.label)}</option>`
    )
    .join("");
  return `
    <label class="onb-provider">
      <span>Runner</span>
      <select class="run-menu-select" onchange="setOnboardingProvider(this.value)">${options}</select>
    </label>`;
}

function _onboardingBody() {
  const s = _onboardingState;
  const week = shortDate(s.weekOf);
  const errorHtml = s.error ? `<div class="form-error">${esc(s.error)}</div>` : "";

  if (s.step === "loading" || s.step === "generating") {
    const msg = s.step === "loading" ? "Thinking of a few good questions…" : "Drafting your weekly focus…";
    return `
      <div class="onb-kicker">Weekly setup</div>
      <h2 class="onb-title">Week of ${esc(week)}</h2>
      <div class="onb-loading"><span class="spinner"></span><span>${esc(msg)}</span></div>`;
  }

  if (s.step === "questions") {
    return `
      <div class="onb-kicker">Weekly setup</div>
      <h2 class="onb-title">A few questions for the week of ${esc(week)}</h2>
      <p class="onb-lead">Your answers are turned into a concrete weekly focus you can edit anytime.</p>
      ${errorHtml}
      <div class="onb-fields">
        ${(s.questions || [])
          .map(
            (q, i) => `
          <label class="onb-field">
            <span class="onb-q-label">${esc(q.label)}</span>
            ${q.help ? `<span class="onb-q-help">${esc(q.help)}</span>` : ""}
            <textarea class="task-form-input" id="onb-q-${i}" rows="2" placeholder="${esc(q.placeholder || "")}">${esc(s.answers[q.id] || "")}</textarea>
          </label>`
          )
          .join("")}
      </div>
      ${_onboardingProviderField()}
      <div class="onb-actions">
        <button type="button" class="form-btn form-btn-secondary" onclick="dismissOnboarding()">Skip for now</button>
        <button type="button" class="form-btn form-btn-primary" onclick="submitOnboarding()">Generate weekly focus</button>
      </div>
      <button type="button" class="onb-link" onclick="onboardingManualSetup()">I'll set it up manually</button>`;
  }

  if (s.step === "error") {
    return `
      <div class="onb-kicker">Weekly setup</div>
      <h2 class="onb-title">Couldn't reach the assistant</h2>
      ${errorHtml}
      <div class="onb-actions">
        <button type="button" class="form-btn form-btn-secondary" onclick="dismissOnboarding()">Skip for now</button>
        <button type="button" class="form-btn form-btn-primary" onclick="startOnboardingQuestions()">Try again</button>
      </div>
      <button type="button" class="onb-link" onclick="onboardingManualSetup()">I'll set it up manually</button>`;
  }

  // intro
  const lead = s.needGoals
    ? `You don't have goals or a focus for this week yet. Answer a few quick questions and I'll draft both.`
    : `There's no focus set for the week of ${esc(week)} yet. Answer a few quick questions and I'll draft one.`;
  return `
    <div class="onb-kicker">Weekly setup</div>
    <h2 class="onb-title">Let's set your focus for the week of ${esc(week)}</h2>
    <p class="onb-lead">${lead}</p>
    ${_onboardingProviderField()}
    <div class="onb-actions">
      <button type="button" class="form-btn form-btn-secondary" onclick="dismissOnboarding()">Skip for now</button>
      <button type="button" class="form-btn form-btn-primary" onclick="startOnboardingQuestions()">Start</button>
    </div>`;
}

function renderOnboarding() {
  if (!_onboardingState) return;
  let overlay = document.querySelector(".onboarding-overlay");
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.className = "onboarding-overlay";
    document.body.appendChild(overlay);
  }
  overlay.innerHTML = `<div class="onboarding-panel" role="dialog" aria-modal="true" aria-label="Weekly setup">${_onboardingBody()}</div>`;
  const firstField = overlay.querySelector("textarea");
  if (firstField) firstField.focus();
}

// ── Tabs ──

function switchTab(tab) {
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === tab));
  $$(".tab-content").forEach((c) => c.classList.toggle("hidden", c.id !== `tab-${tab}`));
  if (tab !== "today") {
    editingIndex = -1;
    showAddForm = false;
  }
  if (tab === "projects") {
    renderProjects();
    if (!driveDocsData) fetchProjectDocs();
  } else {
    editingProjectIndex = -1;
    showProjectAddForm = false;
    projectError = "";
  }
  if (tab === "weekly") {
    renderWeeklyFocus();
  } else {
    editingWeeklyIndex = -1;
    showWeeklyAddForm = false;
    weeklyError = "";
  }
  if (tab === "analytics" && !analyticsData) fetchAnalytics();
  if (tab === "docs") {
    if (driveDocsData) renderDriveDocs();
    else fetchDriveDocs();
  }
}

// ── Today tab ──

async function fetchMorningStatus() {
  try {
    return await fetch("/api/morning-status").then((r) => r.json());
  } catch (e) {
    return {
      status: "unknown",
      label: "Status unavailable",
      recommended_action: "Refresh status",
      error: e.message || "Unable to load morning status",
    };
  }
}

async function fetchAll() {
  const [today, goals, projects, weekly, outcomes, stats, dates, morning] = await Promise.all([
    fetch("/api/today").then((r) => r.json()),
    fetch("/api/goals").then((r) => r.json()),
    fetch("/api/projects").then((r) => r.json()),
    fetch("/api/weekly-focus").then((r) => r.json()),
    fetch("/api/outcomes").then((r) => r.json()),
    fetch("/api/stats").then((r) => r.json()),
    fetch("/api/available-dates").then((r) => r.json()),
    fetchMorningStatus(),
  ]);
  state = { today, goals, projects, weekly, outcomes, stats, morning };
  availableDates = dates || [];
  viewingArchive = false;
  render();
  if ($("#tab-projects") && !$("#tab-projects").classList.contains("hidden")) renderProjects();
  if ($("#tab-weekly") && !$("#tab-weekly").classList.contains("hidden")) renderWeeklyFocus();
  maybeStartOnboarding();
}

function formatDate(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" });
}

function checkSvg() {
  return `<svg viewBox="0 0 12 12"><polyline points="2,6 5,9 10,3"/></svg>`;
}

function normalizeTaskStatus(task) {
  const status = task && task.meta ? String(task.meta.status || "").toLowerCase() : "";
  if (["canceled", "cancelled", "cancel"].includes(status)) return "canceled";
  if (["deleted", "delete", "removed"].includes(status)) return "deleted";
  return "";
}

function isInactiveTask(task) {
  return ["canceled", "deleted"].includes(normalizeTaskStatus(task));
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
      <details class="task-form-advanced" ${meta.type || meta.goal || meta.sub || meta.backlog ? "open" : ""}>
        <summary>Advanced metadata</summary>
        <div class="task-form-row">
          <label class="task-form-label">Type
            <input type="text" class="task-form-input" id="tf-type" value="${esc(meta.type || "")}" placeholder="interview_prep">
          </label>
          <label class="task-form-label">Goal
            <input type="text" class="task-form-input" id="tf-goal" value="${esc(meta.goal || "")}" placeholder="data_owner">
          </label>
          <label class="task-form-label">Sub
            <input type="text" class="task-form-input" id="tf-sub" value="${esc(meta.sub || "")}" placeholder="decision_science">
          </label>
          <label class="task-form-label">Backlog
            <input type="text" class="task-form-input" id="tf-backlog" value="${esc(meta.backlog || "")}" placeholder="4d">
          </label>
        </div>
      </details>
      <div class="task-form-actions">
        <button class="form-btn form-btn-primary" onclick="saveTask(${index})">${isNew ? "Add Task" : "Save"}</button>
        <button class="form-btn form-btn-secondary" onclick="cancelEdit()">Cancel</button>
      </div>
    </div>`;
}

function renderTasks(tasks) {
  if (!tasks || tasks.length === 0)
    return `<div class="empty-state"><div class="empty-state-title">No tasks yet</div><p>Run the personal PM flow to generate today's plan.</p></div>`;

  const activeTasks = tasks.filter((t) => !isInactiveTask(t));
  const checked = activeTasks.filter((t) => t.checked).length;
  const total = activeTasks.length;
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

    const inactive = isInactiveTask(task);
    const status = normalizeTaskStatus(task);
    const cls = `task-card p${task.priority}${task.checked ? " checked" : ""}${inactive ? " canceled" : ""}`;
    const backlogAge = task.meta && task.meta.backlog ? task.meta.backlog : "";
    const metaTags = Object.entries(task.meta || {})
      .filter(([k, v]) => !["backlog", "status", "doc"].includes(k) && !isOpaqueId(v))
      .map(([k, v]) => `<span class="task-meta-tag">${esc(prettyLabel(k))}: ${esc(prettyLabel(v))}</span>`)
      .join("");

    const checkbox = inactive
      ? `<span class="task-checkbox" aria-hidden="true">${checkSvg()}</span>`
      : `<button type="button" class="task-checkbox" role="checkbox" aria-checked="${task.checked ? "true" : "false"}" aria-label="Toggle task complete" onclick="event.stopPropagation(); toggleTask(${i})">${checkSvg()}</button>`;

    html += `
      <div class="${cls}" data-index="${i}" ${inactive ? "" : `onclick="toggleTask(${i})"`}>
        ${checkbox}
        <div class="task-body">
          <div class="task-top-row">
            <span class="task-priority">P${task.priority}</span>
            <span class="task-duration">${task.duration}</span>
            ${status ? `<span class="task-status-tag">${esc(status)}</span>` : ""}
            ${backlogAge ? `<span class="task-backlog-tag" title="Carried forward from prior runs">Backlog ${esc(backlogAge)}</span>` : ""}
          </div>
          <div class="task-title">${esc(task.title)}</div>
          ${task.discipline ? `<div class="task-discipline">${esc(task.discipline)}</div>` : ""}
          ${metaTags ? `<div class="task-meta">${metaTags}</div>` : ""}
        </div>
        ${editable ? `<div class="task-actions" onclick="event.stopPropagation()">
          <button class="task-action-btn" onclick="startEdit(${i})" title="Edit" aria-label="Edit task">&#9998;</button>
          ${inactive ? "" : `<button class="task-action-btn task-action-delete" onclick="deleteTask(${i})" title="Cancel carry-forward" aria-label="Cancel carry-forward">&times;</button>`}
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
      <div class="section-header" role="button" tabindex="0" aria-expanded="true" aria-label="Toggle ${esc(title)} section" onclick="toggleSection('${id}')" onkeydown="activateKey(event, () => toggleSection('${id}'))">
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

function taskCountByPriority(tasks) {
  return tasks.reduce((counts, task) => {
    const key = `P${task.priority}`;
    counts[key] = (counts[key] || 0) + 1;
    return counts;
  }, {});
}

function methodologyTaskShape(tasks) {
  const counts = taskCountByPriority(tasks);
  const parts = [];
  if (counts.P1) parts.push(`${counts.P1} P1 anchor`);
  if (counts.P2) parts.push(`${counts.P2} P2 support`);
  if (counts.P3) parts.push(`${counts.P3} P3 optional`);
  return parts.join(" · ") || "No active task shape";
}

function renderMethodology(today) {
  if (!today || !Array.isArray(today.tasks)) return "";

  const tasks = today.tasks;
  const backlogCount = tasks.filter((task) => task.meta && task.meta.backlog).length;
  const artifactCount = tasks.filter((task) => {
    const text = `${task.title || ""} ${task.discipline || ""} ${Object.values(task.meta || {}).join(" ")}`.toLowerCase();
    return /artifact|scorecard|template|checklist|map|contract|rubric|draft|rep/.test(text);
  }).length;
  const eligibleProjects = (state.projects || []).filter((project) => !["Paused", "Closed"].includes(project.status));
  const excludedProjects = (state.projects || []).filter((project) => ["Paused", "Closed"].includes(project.status));
  const weeklyLabel = state.weekly && state.weekly.week_of ? shortDate(state.weekly.week_of) : "not set";

  const steps = [
    {
      label: "Priority shape",
      detail: `${methodologyTaskShape(tasks)}. P1 defines the success condition; lower priorities support it or stay skippable.`,
    },
    {
      label: "Source order",
      detail: `Goals, active projects, weekly focus (${weeklyLabel}), carry-forward, and adaptive memory are read before optional external handoffs.`,
    },
    {
      label: "Project filter",
      detail: `${eligibleProjects.length} eligible projects can generate work; ${excludedProjects.length} paused or closed projects are historical unless explicitly selected.`,
    },
    {
      label: "Carry-forward",
      detail: backlogCount
        ? `${backlogCount} task${backlogCount === 1 ? "" : "s"} carry backlog age metadata and should be narrowed if repeated.`
        : "No task carries backlog age metadata in this plan.",
    },
    {
      label: "Output bias",
      detail: artifactCount
        ? `${artifactCount} task${artifactCount === 1 ? "" : "s"} point toward a concrete artifact, scored rep, checklist, template, or map.`
        : "The planner should prefer concrete artifacts or scored reps when shaping the next plan.",
    },
  ];

  return `
    <div class="section">
      <div class="section-header" role="button" tabindex="0" aria-expanded="false" aria-label="Toggle Methodology section" onclick="toggleSection('methodology')" onkeydown="activateKey(event, () => toggleSection('methodology'))">
        <span class="section-title">Methodology</span>
        <span class="section-count">${steps.length}</span>
        <span class="section-toggle collapsed" id="toggle-methodology">&#9662;</span>
      </div>
      <div class="methodology-section collapsed" id="section-methodology">
        ${steps.map((step, index) => `
          <div class="methodology-item">
            <span>${index + 1}</span>
            <div>
              <div class="methodology-label">${esc(step.label)}</div>
              <p>${esc(step.detail)}</p>
            </div>
          </div>
        `).join("")}
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
    const active = state.projects.filter((p) => p.priority === "Now" && !["Paused", "Closed"].includes(p.status));
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

function runFocusValue() {
  return selectedRunFocus === "__custom__" ? customRunFocus.trim() : selectedRunFocus;
}

function runTypeLabel() {
  if (selectedRunMode === "normal") return "Normal planning";
  return `Specific focus: ${runFocusValue() || "Custom focus"}`;
}

function setRunMode(value) {
  selectedRunMode = value === "focus" ? "focus" : "normal";
  render();
}

function setRunFocus(value) {
  selectedRunFocus = value || "Default";
  render();
}

function setCustomRunFocus(value) {
  customRunFocus = value || "";
}

function renderRunTypeControls() {
  const focusOptions = RUN_FOCUS_OPTIONS
    .map((focus) => `<option value="${esc(focus)}" ${selectedRunFocus === focus ? "selected" : ""}>${esc(focus)}</option>`)
    .join("");
  const customSelected = selectedRunFocus === "__custom__" ? "selected" : "";
  const customInput = selectedRunFocus === "__custom__"
    ? `<input class="run-menu-input" value="${esc(customRunFocus)}" placeholder="Custom focus" maxlength="80" oninput="setCustomRunFocus(this.value)" onclick="event.stopPropagation()">`
    : "";

  return `
    <div class="run-menu-section">
      <label class="run-menu-field">Run type
        <select class="run-menu-select" onchange="setRunMode(this.value)" onclick="event.stopPropagation()">
          <option value="normal" ${selectedRunMode === "normal" ? "selected" : ""}>Normal planning</option>
          <option value="focus" ${selectedRunMode === "focus" ? "selected" : ""}>Specific focus</option>
        </select>
      </label>
      ${selectedRunMode === "focus" ? `
        <label class="run-menu-field">Focus
          <select class="run-menu-select" onchange="setRunFocus(this.value)" onclick="event.stopPropagation()">
            ${focusOptions}
            <option value="__custom__" ${customSelected}>Custom focus</option>
          </select>
        </label>
        ${customInput}
      ` : ""}
    </div>`;
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
          ${renderRunTypeControls()}
          <div class="run-menu-divider"></div>
          <div class="run-menu-heading">Runner</div>
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

function formatRunTime(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function morningStatusCopy(status) {
  const map = {
    ready: { title: "Ready", detail: "Today's plan is current." },
    stale: { title: "Stale", detail: "The current plan is from a prior day." },
    missing: { title: "No plan yet", detail: "Run the morning flow to create today's plan." },
    failed: { title: "Run failed", detail: "The latest autonomous run needs review." },
    no_run: { title: "No run yet", detail: "A current plan exists without a recorded autonomous run today." },
    running: { title: "Running", detail: "A planner run is active in this app." },
    unknown: { title: "Status unavailable", detail: "Refresh status to try again." },
  };
  return map[status] || map.unknown;
}

function latestRunLines(run) {
  if (!run) return [];
  const lines = [];
  if (run.started_at) lines.push(`Started: ${formatRunTime(run.started_at)}`);
  if (run.ended_at) lines.push(`Ended: ${formatRunTime(run.ended_at)}`);
  if (run.focus) lines.push(`Focus: ${run.focus}`);
  if (Array.isArray(run.actions) && run.actions.length) lines.push(`Actions: ${run.actions.join(", ")}`);
  if (Array.isArray(run.errors) && run.errors.length) lines.push(`Errors: ${run.errors.join(" | ")}`);
  if (run.exit_code !== undefined) lines.push(`Exit code: ${run.exit_code}`);
  return lines;
}

function renderMorningBanner() {
  const morning = state.morning;
  if (!morning) return "";

  const status = morning.status || "unknown";
  const copy = morningStatusCopy(status);
  const latest = morning.latest_run || null;
  const lastRun = latest && latest.started_at ? `Last run ${formatRunTime(latest.started_at)}` : "No autonomous run recorded";
  const planText = morning.plan_date ? `Plan ${morning.plan_date}` : "No plan date";
  const action = morning.recommended_action || "Review plan";
  const details = latestRunLines(latest);
  const hasDetails = details.length > 0 || morning.run_log_path || morning.error;
  const runDisabled = _runActive || status === "running" ? "disabled" : "";

  return `
    <div class="morning-banner ${esc(status)}">
      <div class="morning-main">
        <div class="morning-status-pill">${esc(copy.title)}</div>
        <div class="morning-copy">
          <div class="morning-title">${esc(copy.detail)}</div>
          <div class="morning-meta">${esc(planText)} · ${esc(lastRun)} · ${esc(action)}</div>
        </div>
      </div>
      <div class="morning-actions">
        <button class="morning-btn" onclick="refreshMorningStatus()">Refresh</button>
        <button class="morning-btn morning-btn-primary" onclick="runTodayFlow('codex')" ${runDisabled}>Run</button>
        ${hasDetails ? `<button class="morning-btn" onclick="toggleMorningDetails()">${morningDetailsOpen ? "Hide" : "Details"}</button>` : ""}
      </div>
      ${morningDetailsOpen && hasDetails ? `
        <div class="morning-details">
          ${details.map((line) => `<div>${esc(line)}</div>`).join("")}
          ${morning.error ? `<div>${esc(morning.error)}</div>` : ""}
          ${morning.run_log_path ? `<div>Run log: ${esc(morning.run_log_path)}</div>` : ""}
          ${morning.token_usage_log_path ? `<div>Token log: ${esc(morning.token_usage_log_path)}</div>` : ""}
          ${morning.data_root ? `<div>Data root: ${esc(morning.data_root)}</div>` : ""}
        </div>
      ` : ""}
    </div>`;
}

async function refreshMorningStatus() {
  state.morning = await fetchMorningStatus();
  render();
}

function toggleMorningDetails() {
  morningDetailsOpen = !morningDetailsOpen;
  render();
}

function render() {
  const app = $("#app");
  const today = state.today;
  const scrollY = window.scrollY;

  if (!today) {
    app.innerHTML = `${renderToolbar(null)}${!viewingArchive ? renderMorningBanner() : ""}<div class="empty-state"><div class="empty-state-title">No plan found</div><p>Run the personal PM flow to generate today's plan.</p></div>`;
    return;
  }

  const todayDate = new Date().toISOString().slice(0, 10);
  const isCurrentDay = today.date === todayDate;
  const showStaleWarning = !viewingArchive && !isCurrentDay;

  app.innerHTML = `
    ${renderToolbar(today)}
    ${!viewingArchive ? renderMorningBanner() : ""}
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
    ${!viewingArchive ? renderMethodology(today) : ""}
    ${renderInfoSection("carry", "Carry-forward", today.carry_forward)}
    ${renderInfoSection("heads", "Heads-up", today.heads_up)}
    ${!viewingArchive ? renderFeedback(today.feedback) : ""}
    ${!viewingArchive ? renderContext() : ""}`;

  window.scrollTo(0, scrollY);
  if (_runActive) _showRunPanel();
}

async function toggleTask(index) {
  try {
    const res = await fetch("/api/toggle-task", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ index }),
    });
    const data = await res.json();
    if (data.ok) {
      state.today = data.today;
      render();
    } else {
      toast(data.error || "Couldn't update task", "error");
    }
  } catch {
    toast("Couldn't update task — check your connection", "error");
  }
}

async function saveFeedback(el) {
  const field = el.dataset.field;
  const value = el.value.trim();
  if (value === (el.defaultValue || "").trim()) return; // nothing changed
  try {
    const res = await fetch("/api/update-feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ field, value }),
    });
    if (!res.ok) {
      toast("Couldn't save feedback", "error");
      return;
    }
    el.defaultValue = value;
    toast("Feedback saved", "success");
  } catch {
    toast("Couldn't save feedback — check your connection", "error");
  }
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

  try {
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
    } else {
      toast(result.error || "Couldn't save task", "error");
    }
  } catch {
    toast("Couldn't save task — check your connection", "error");
  }
}

async function deleteTask(index) {
  const ok = await confirmDialog({
    title: "Cancel this task?",
    message: "It will be marked canceled and stop carrying forward to future plans.",
    confirmLabel: "Cancel task",
    cancelLabel: "Keep task",
  });
  if (!ok) return;

  try {
    const res = await fetch("/api/delete-task", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ index }),
    });
    const result = await res.json();
    if (result.ok) {
      state.today = result.today;
      render();
    } else {
      toast(result.error || "Couldn't cancel task", "error");
    }
  } catch {
    toast("Couldn't cancel task — check your connection", "error");
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
let _activeRunType = "Normal planning";

function runProviderLabel(provider) {
  return (RUN_PROVIDERS[provider] || RUN_PROVIDERS.codex).label;
}

function toggleRunMenu(event) {
  if (event) event.stopPropagation();
  if (_runActive) return;
  runMenuOpen = !runMenuOpen;
  render();
}

function selectedRunPayload() {
  const focus = runFocusValue();
  if (selectedRunMode === "focus" && !focus) {
    return { error: "Enter a custom focus before running." };
  }

  return {
    mode: selectedRunMode,
    focus: selectedRunMode === "focus" ? focus : "",
    label: runTypeLabel(),
  };
}

function _showRunPanel(providerLabel, runType) {
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
        <span class="run-progress-title">Running ${esc(runType || _activeRunType)} with ${esc(providerLabel || runProviderLabel(_activeRunProvider))}...</span>
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

  const runPayload = selectedRunPayload();
  if (runPayload.error) {
    btn.innerHTML = `<span class="run-icon">&#9654;</span> ${runPayload.error}`;
    setTimeout(() => {
      btn.innerHTML = `<span class="run-icon">&#9654;</span> Run Today's Flow`;
    }, 1800);
    return;
  }

  _activeRunProvider = provider;
  _activeRunType = runPayload.label;
  runMenuOpen = false;
  const providerLabel = runProviderLabel(provider);

  btn.disabled = true;
  btn.classList.add("running");
  btn.innerHTML = `<span class="spinner"></span> Running ${providerLabel}…`;
  _runActive = true;

  _showRunPanel(providerLabel, runPayload.label);

  try {
    const res = await fetch("/api/run-today", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider, mode: runPayload.mode, focus: runPayload.focus }),
    });
    const data = await res.json();
    if (!data.ok) {
      btn.innerHTML = `<span class="run-icon">&#9654;</span> ${data.error || "Error"}`;
      btn.classList.remove("running");
      btn.disabled = false;
      _runActive = false;
      _hideRunPanel();
      await refreshMorningStatus();
      return;
    }
    _pollTimer = setInterval(pollRunStatus, 2000);
  } catch {
    btn.innerHTML = `<span class="run-icon">&#9654;</span> Failed`;
    btn.classList.remove("running");
    btn.disabled = false;
    _runActive = false;
    _hideRunPanel();
    await refreshMorningStatus();
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
      header.innerHTML = `<span class="run-progress-done">&#10003;</span><span class="run-progress-title">${esc(providerLabel)} ${esc(_activeRunType)} complete</span>`;
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
  const header = toggle.closest(".section-header");
  if (header) {
    header.setAttribute("aria-expanded", section.classList.contains("collapsed") ? "false" : "true");
  }
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

// ── Projects tab ──

async function fetchProjectDocs() {
  try {
    driveDocsData = await fetch("/api/recent-docs").then((r) => r.json());
  } catch (e) {
    driveDocsData = { error: e.message || "Unable to load recent docs" };
  }
  renderProjects();
}

function normalizeMatch(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/&/g, "and")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function recentDocsList() {
  if (!driveDocsData || driveDocsData.error || !Array.isArray(driveDocsData.docs)) return [];
  return driveDocsData.docs;
}

function projectDocs(project) {
  const projectName = normalizeMatch(project.name);
  if (!projectName) return [];

  return recentDocsList()
    .filter((doc) => {
      const matched = doc.matched_projects || [];
      return matched.some((name) => {
        const normalized = normalizeMatch(name);
        return normalized === projectName || normalized.includes(projectName) || projectName.includes(normalized);
      });
    })
    .sort((a, b) => String(b.activity_at || b.modified_at || "").localeCompare(String(a.activity_at || a.modified_at || "")));
}

function projectTasks(project) {
  const tasks = (state.today && state.today.tasks) || [];
  const projectName = normalizeMatch(project.name);
  const terms = [...new Set(projectName.split(" ").filter((term) => term.length >= 6))];

  return tasks.filter((task) => {
    const meta = Object.values(task.meta || {}).join(" ");
    const text = normalizeMatch(`${task.title} ${task.discipline} ${meta}`);
    const matchedTerms = terms.filter((term) => text.includes(term));
    return text.includes(projectName) || (task.meta && task.meta.type === "project_work" && matchedTerms.length >= 2);
  });
}

function projectScore(project) {
  const priorityScore = { Now: 6, Next: 3, Later: 1 }[project.priority] || 0;
  const statusScore = { Active: 5, Idea: 2, Paused: -2, Closed: -6 }[project.status] || 0;
  const actionScore = project.next_action ? 3 : 0;
  const docScore = Math.min(projectDocs(project).length, 3);
  const taskScore = projectTasks(project).length > 0 ? 2 : 0;
  return priorityScore + statusScore + actionScore + docScore + taskScore;
}

function selectProjectPullCandidate(projects) {
  return [...projects]
    .filter((project) => project.next_action && project.status !== "Paused" && project.status !== "Closed")
    .sort((a, b) => projectScore(b) - projectScore(a))[0];
}

function projectIndex(project, fallback) {
  return Number.isInteger(project.index) ? project.index : fallback;
}

function renderProjectForm(project, index) {
  const isNew = index === -1;
  const priority = project ? project.priority : "Now";
  const status = project ? project.status : "Idea";
  const name = project ? project.name : "";
  const discipline = project ? project.discipline : "";
  const nextAction = project ? project.next_action : "";
  const notes = project ? project.notes : "";

  return `
    <div class="project-edit-overlay" onclick="cancelProjectEdit()">
      <div class="project-edit-panel" onclick="event.stopPropagation()">
        <div class="project-edit-header">
          <div>
            <div class="project-edit-kicker">${isNew ? "New Project" : "Edit Project"}</div>
            <h2>${esc(isNew ? "Add Project" : name || "Edit Project")}</h2>
          </div>
          <button class="task-action-btn" onclick="cancelProjectEdit()" title="Close">&times;</button>
        </div>
        <div class="task-form project-form">
          ${projectError ? `<div class="form-error">${esc(projectError)}</div>` : ""}
          <label class="task-form-label">Project
            <textarea class="task-form-input task-form-title" id="pf-name" rows="2" placeholder="Project name">${esc(name)}</textarea>
          </label>
          <div class="task-form-row">
            <label class="task-form-label">Priority
              <select class="task-form-select" id="pf-priority">
                <option value="Now" ${priority === "Now" ? "selected" : ""}>Now</option>
                <option value="Next" ${priority === "Next" ? "selected" : ""}>Next</option>
                <option value="Later" ${priority === "Later" ? "selected" : ""}>Later</option>
              </select>
            </label>
            <label class="task-form-label">Status
              <select class="task-form-select" id="pf-status">
                <option value="Active" ${status === "Active" ? "selected" : ""}>Active</option>
                <option value="Idea" ${status === "Idea" ? "selected" : ""}>Idea</option>
                <option value="Paused" ${status === "Paused" ? "selected" : ""}>Paused</option>
                <option value="Closed" ${status === "Closed" ? "selected" : ""}>Closed</option>
              </select>
            </label>
          </div>
          <label class="task-form-label">Discipline
            <input type="text" class="task-form-input" id="pf-discipline" value="${esc(discipline)}" placeholder="e.g. Data foundation, Evaluation">
          </label>
          <label class="task-form-label">Next Action
            <textarea class="task-form-input task-form-title" id="pf-next-action" rows="3" placeholder="Smallest useful next step">${esc(nextAction)}</textarea>
          </label>
          <label class="task-form-label">Notes
            <textarea class="task-form-input task-form-title" id="pf-notes" rows="4" placeholder="Why this project matters or current constraint">${esc(notes)}</textarea>
          </label>
          <div class="task-form-actions">
            <button class="form-btn form-btn-primary" onclick="saveProject(${index})">${isNew ? "Add Project" : "Save"}</button>
            <button class="form-btn form-btn-secondary" onclick="cancelProjectEdit()">Cancel</button>
          </div>
        </div>
      </div>
    </div>`;
}

function renderProjectEditor(projects) {
  if (showProjectAddForm) return renderProjectForm(null, -1);
  if (editingProjectIndex === -1) return "";

  const project = projects.find((item) => item.index === editingProjectIndex);
  if (!project) return "";
  return renderProjectForm(project, editingProjectIndex);
}

function renderProjectClosedSection(projects) {
  if (!projects.length) return "";

  return `
    <section class="project-closed-section">
      <div class="project-lane-header">
        <span>Closed</span>
        <span>${projects.length}</span>
      </div>
      <div class="project-card-list project-closed-list">
        ${projects.map((project) => renderProjectCard(project, project.index)).join("")}
      </div>
    </section>`;
}

function _readProjectForm() {
  return {
    name: $("#pf-name").value.trim(),
    priority: $("#pf-priority").value,
    status: $("#pf-status").value,
    discipline: $("#pf-discipline").value.trim(),
    next_action: $("#pf-next-action").value.trim(),
    notes: $("#pf-notes").value.trim(),
  };
}

function openProjectAddForm() {
  showProjectAddForm = true;
  editingProjectIndex = -1;
  projectError = "";
  renderProjects();
}

function startProjectEdit(index) {
  editingProjectIndex = index;
  showProjectAddForm = false;
  projectError = "";
  renderProjects();
}

function cancelProjectEdit() {
  editingProjectIndex = -1;
  showProjectAddForm = false;
  projectError = "";
  renderProjects();
}

async function saveProject(index) {
  const data = _readProjectForm();
  if (!data.name) {
    projectError = "Project name is required.";
    renderProjects();
    return;
  }

  const url = index === -1 ? "/api/add-project" : "/api/edit-project";
  const body = index === -1 ? data : { index, ...data };
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const result = await res.json();

  if (result.ok) {
    state.projects = result.projects || [];
    editingProjectIndex = -1;
    showProjectAddForm = false;
    projectError = "";
    renderProjects();
  } else {
    projectError = result.error || "Project update failed.";
    renderProjects();
  }
}

async function deleteProject(index) {
  const project = (state.projects || []).find((item, i) => projectIndex(item, i) === index);
  const ok = await confirmDialog({
    title: "Delete this project?",
    message: project && project.name
      ? `"${project.name}" will be permanently removed. This can't be undone.`
      : "This project will be permanently removed. This can't be undone.",
    confirmLabel: "Delete project",
  });
  if (!ok) return;

  try {
    const res = await fetch("/api/delete-project", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ index }),
    });
    const result = await res.json();

    if (result.ok) {
      state.projects = result.projects || [];
      editingProjectIndex = -1;
      showProjectAddForm = false;
      projectError = "";
      renderProjects();
    } else {
      projectError = result.error || "Project delete failed.";
      renderProjects();
    }
  } catch {
    toast("Couldn't delete project — check your connection", "error");
  }
}

function renderProjects() {
  const el = $("#projects");
  if (!el) return;

  if (state.projects === null) {
    el.innerHTML = `<div class="loading">Loading projects...</div>`;
    return;
  }

  const projects = (state.projects || []).map((project, index) => ({
    ...project,
    index: projectIndex(project, index),
  }));
  if (projects.length === 0) {
    el.innerHTML = `
      <div class="empty-state"><div class="empty-state-title">No projects found</div><p>Add a project to build a portfolio view.</p></div>
      <button class="add-task-btn add-project-btn" onclick="openProjectAddForm()">+ Add Project</button>
      ${renderProjectEditor(projects)}`;
    return;
  }

  const openProjects = projects.filter((project) => project.status !== "Closed");
  const closedProjects = projects.filter((project) => project.status === "Closed");
  const active = projects.filter((project) => project.status === "Active");
  const now = openProjects.filter((project) => project.priority === "Now");
  const withActions = openProjects.filter((project) => project.next_action);
  const linkedDocs = projects.filter((project) => projectDocs(project).length > 0);
  const candidate = selectProjectPullCandidate(openProjects);
  const docsNote = driveDocsData && driveDocsData.error ? "docs cache unavailable" : `${linkedDocs.length} with recent docs`;
  const statusNote = `${active.length} active${closedProjects.length ? ` &middot; ${closedProjects.length} closed` : ""}`;

  el.innerHTML = `
    <div class="projects-header">
      <h1>Projects</h1>
      <p>${projects.length} projects &middot; ${statusNote} &middot; ${docsNote}</p>
    </div>

    <div class="summary-grid project-summary">
      <div class="summary-card">
        <div class="big-number green">${now.length}</div>
        <div class="card-label">Now</div>
      </div>
      <div class="summary-card">
        <div class="big-number">${active.length}</div>
        <div class="card-label">Active</div>
      </div>
      <div class="summary-card">
        <div class="big-number amber">${withActions.length}</div>
        <div class="card-label">Next Actions</div>
      </div>
      <div class="summary-card">
        <div class="big-number blue">${linkedDocs.length}</div>
        <div class="card-label">Doc Linked</div>
      </div>
    </div>

    ${projectError && !showProjectAddForm && editingProjectIndex === -1 ? `<div class="form-error project-global-error">${esc(projectError)}</div>` : ""}
    ${candidate ? renderProjectPull(candidate) : ""}

    <div class="project-board">
      ${renderProjectLane("Now", openProjects.filter((project) => project.priority === "Now"))}
      ${renderProjectLane("Next", openProjects.filter((project) => project.priority === "Next"))}
      ${renderProjectLane("Later", openProjects.filter((project) => project.priority === "Later"))}
    </div>
    ${renderProjectClosedSection(closedProjects)}

    <button class="add-task-btn add-project-btn" onclick="openProjectAddForm()">+ Add Project</button>
    ${renderProjectEditor(projects)}`;
}

function renderProjectPull(project) {
  const docs = projectDocs(project);
  const doc = docs[0];
  const docLink = doc && safeHref(doc.url || "");
  const docTitle = doc ? esc(doc.title || "Untitled document") : "";

  return `
    <section class="project-pull">
      <div>
        <div class="project-pull-label">Daily Pull Candidate</div>
        <div class="project-pull-title">${esc(project.name)}</div>
        <p>${esc(project.next_action || "Define the next concrete action.")}</p>
        ${doc ? `<div class="project-pull-doc">Recent evidence: ${docLink ? `<a href="${esc(docLink)}" target="_blank" rel="noreferrer">${docTitle}</a>` : docTitle}</div>` : ""}
      </div>
      <span class="project-score" title="Priority, status, next action, recent docs, and today's tasks">${projectScore(project)}</span>
    </section>`;
}

function renderProjectLane(title, projects) {
  return `
    <section class="project-lane">
      <div class="project-lane-header">
        <span>${esc(title)}</span>
        <span>${projects.length}</span>
      </div>
      <div class="project-card-list">
        ${projects.length ? projects.map((project, i) => renderProjectCard(project, projectIndex(project, i))).join("") : `<div class="project-empty">No ${esc(title.toLowerCase())} projects</div>`}
      </div>
    </section>`;
}

function renderProjectCard(project, index) {
  const docs = projectDocs(project).slice(0, 2);
  const tasks = projectTasks(project).slice(0, 1);
  const statusClass = normalizeMatch(project.status).replace(/\s+/g, "-");
  const priorityClass = normalizeMatch(project.priority).replace(/\s+/g, "-");

  return `
    <article class="project-card ${priorityClass}">
      <div class="project-card-top">
        <span class="project-priority ${priorityClass}">${esc(project.priority)}</span>
        <span class="project-status ${statusClass}">${esc(project.status)}</span>
      </div>
      <div class="project-title">${esc(project.name)}</div>
      ${project.discipline ? `<div class="project-discipline">${esc(project.discipline)}</div>` : ""}
      ${project.next_action ? `<div class="project-field"><span>Next action</span><p>${esc(project.next_action)}</p></div>` : ""}
      ${tasks.length ? `<div class="project-field"><span>Today</span><p>${esc(tasks[0].title)}</p></div>` : ""}
      ${project.notes ? `<div class="project-notes">${esc(project.notes)}</div>` : ""}
      ${docs.length ? `<div class="project-docs">${docs.map(renderProjectDocLink).join("")}</div>` : ""}
      <div class="task-actions project-actions" onclick="event.stopPropagation()">
        <button class="task-action-btn" onclick="startProjectEdit(${index})" title="Edit">&#9998;</button>
        <button class="task-action-btn task-action-delete" onclick="deleteProject(${index})" title="Delete">&times;</button>
      </div>
    </article>`;
}

function renderProjectDocLink(doc) {
  const href = safeHref(doc.url || "");
  const date = doc.activity_date ? shortDate(doc.activity_date.slice(0, 10)) : "";
  const title = esc(doc.title || "Untitled document");
  const label = date ? `${title} - ${esc(date)}` : title;

  if (!href) return `<div class="project-doc-link">${label}</div>`;
  return `<a class="project-doc-link" href="${esc(href)}" target="_blank" rel="noreferrer">${label}</a>`;
}

// ── Weekly Focus tab ──

function weeklyFocusWeeks() {
  if (!state.weekly) return [];
  const weeks = Array.isArray(state.weekly.weeks) ? state.weekly.weeks : [state.weekly];
  return weeks
    .filter((week) => week && week.week_of)
    .map((week, index) => ({ ...week, index: Number.isInteger(week.index) ? week.index : index }));
}

function defaultWeekOf() {
  const d = new Date();
  const day = d.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  d.setDate(d.getDate() + diff);
  return d.toISOString().slice(0, 10);
}

function weeklyPriorityItems(week) {
  const items = Array.isArray(week && week.priority_items) ? week.priority_items : [];
  if (items.length) return items;
  return (week && week.priorities ? week.priorities : []).map((text, index) => ({
    number: index + 1,
    checked: false,
    text,
  }));
}

function renderWeeklyForm(week, index) {
  const isNew = index === -1;
  const weekOf = week ? week.week_of : defaultWeekOf();
  const why = week ? week.why || "" : "";
  const notes = week ? week.notes || "" : "";
  const priorities = weeklyPriorityItems(week || {});
  while (priorities.length < 3) {
    priorities.push({ number: priorities.length + 1, checked: false, text: "" });
  }

  return `
    <div class="project-edit-overlay" onclick="cancelWeeklyEdit()">
      <div class="project-edit-panel weekly-edit-panel" onclick="event.stopPropagation()">
        <div class="project-edit-header">
          <div>
            <div class="project-edit-kicker">${isNew ? "New Week" : "Edit Week"}</div>
            <h2>${esc(isNew ? "Add Weekly Focus" : `Week of ${weekOf}`)}</h2>
          </div>
          <button class="task-action-btn" onclick="cancelWeeklyEdit()" title="Close">&times;</button>
        </div>
        <div class="task-form project-form">
          ${weeklyError ? `<div class="form-error">${esc(weeklyError)}</div>` : ""}
          <label class="task-form-label">Week Of
            <input type="date" class="task-form-input" id="wf-week-of" value="${esc(weekOf)}">
          </label>
          <label class="task-form-label">Why This Week
            <textarea class="task-form-input task-form-title" id="wf-why" rows="2" placeholder="Theme or constraint for the week">${esc(why)}</textarea>
          </label>
          <div class="weekly-priority-editor">
            ${priorities.slice(0, 5).map((priority, i) => `
              <div class="weekly-priority-row">
                <label class="weekly-check-label" title="Mark priority complete">
                  <input type="checkbox" id="wf-priority-${i}-checked" ${priority.checked ? "checked" : ""}>
                </label>
                <label class="task-form-label">Priority ${i + 1}
                  <textarea class="task-form-input task-form-title" id="wf-priority-${i}" rows="2" placeholder="Weekly priority">${esc(priority.text || "")}</textarea>
                </label>
              </div>
            `).join("")}
          </div>
          <label class="task-form-label">Notes
            <textarea class="task-form-input task-form-title" id="wf-notes" rows="5" placeholder="Carry-over, constraints, or reminders">${esc(notes)}</textarea>
          </label>
          <div class="task-form-actions">
            <button class="form-btn form-btn-primary" onclick="saveWeeklyFocus(${index})">${isNew ? "Add Week" : "Save"}</button>
            <button class="form-btn form-btn-secondary" onclick="cancelWeeklyEdit()">Cancel</button>
          </div>
        </div>
      </div>
    </div>`;
}

function renderWeeklyEditor(weeks) {
  if (showWeeklyAddForm) return renderWeeklyForm(null, -1);
  if (editingWeeklyIndex === -1) return "";

  const week = weeks.find((item) => item.index === editingWeeklyIndex);
  if (!week) return "";
  return renderWeeklyForm(week, editingWeeklyIndex);
}

function _readWeeklyForm() {
  const priorities = [];
  for (let i = 0; i < 5; i += 1) {
    const input = $(`#wf-priority-${i}`);
    if (!input) continue;
    const text = input.value.trim();
    if (!text) continue;
    priorities.push({
      text,
      checked: !!$(`#wf-priority-${i}-checked`)?.checked,
    });
  }
  return {
    week_of: $("#wf-week-of").value,
    why: $("#wf-why").value.trim(),
    priorities,
    notes: $("#wf-notes").value.trim(),
  };
}

function openWeeklyAddForm() {
  showWeeklyAddForm = true;
  editingWeeklyIndex = -1;
  weeklyError = "";
  renderWeeklyFocus();
}

function startWeeklyEdit(index) {
  editingWeeklyIndex = index;
  showWeeklyAddForm = false;
  weeklyError = "";
  renderWeeklyFocus();
}

function cancelWeeklyEdit() {
  editingWeeklyIndex = -1;
  showWeeklyAddForm = false;
  weeklyError = "";
  renderWeeklyFocus();
}

async function saveWeeklyFocus(index) {
  const data = _readWeeklyForm();
  if (!data.week_of) {
    weeklyError = "Week date is required.";
    renderWeeklyFocus();
    return;
  }
  if (!data.priorities.length) {
    weeklyError = "Add at least one priority.";
    renderWeeklyFocus();
    return;
  }

  const url = index === -1 ? "/api/add-weekly-focus" : "/api/edit-weekly-focus";
  const body = index === -1 ? data : { index, ...data };
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const result = await res.json();

  if (result.ok) {
    state.weekly = result.weekly;
    editingWeeklyIndex = -1;
    showWeeklyAddForm = false;
    weeklyError = "";
    renderWeeklyFocus();
    render();
  } else {
    weeklyError = result.error || "Weekly focus update failed.";
    renderWeeklyFocus();
  }
}

async function deleteWeeklyFocus(index) {
  const ok = await confirmDialog({
    title: "Delete this week?",
    message: "This weekly focus and its priorities will be permanently removed.",
    confirmLabel: "Delete week",
  });
  if (!ok) return;

  const res = await fetch("/api/delete-weekly-focus", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ index }),
  });
  const result = await res.json();

  if (result.ok) {
    state.weekly = result.weekly;
    editingWeeklyIndex = -1;
    showWeeklyAddForm = false;
    weeklyError = "";
    renderWeeklyFocus();
    render();
  } else {
    weeklyError = result.error || "Weekly focus delete failed.";
    renderWeeklyFocus();
  }
}

function renderWeeklyFocus() {
  const el = $("#weekly-focus");
  if (!el) return;

  const weeks = weeklyFocusWeeks();
  if (!state.weekly || weeks.length === 0) {
    el.innerHTML = `
      <div class="empty-state"><div class="empty-state-title">No weekly focus found</div><p>Add a weekly focus to set the active planning theme.</p></div>
      <button class="add-task-btn add-project-btn" onclick="openWeeklyAddForm()">+ Add Weekly Focus</button>
      ${renderWeeklyEditor(weeks)}`;
    return;
  }

  const latest = weeks[0];
  const activePriorities = weeklyPriorityItems(latest).filter((item) => !item.checked).length;
  const completedPriorities = weeks.reduce(
    (sum, week) => sum + weeklyPriorityItems(week).filter((item) => item.checked).length,
    0
  );
  const withNotes = weeks.filter((week) => week.notes).length;

  el.innerHTML = `
    <div class="projects-header weekly-header">
      <h1>Weekly Focus</h1>
      <p>${weeks.length} weeks &middot; latest ${esc(shortDate(latest.week_of))} &middot; ${activePriorities} active priorities</p>
    </div>

    <div class="summary-grid project-summary">
      <div class="summary-card">
        <div class="big-number green">${weeklyPriorityItems(latest).length}</div>
        <div class="card-label">Latest Priorities</div>
      </div>
      <div class="summary-card">
        <div class="big-number amber">${activePriorities}</div>
        <div class="card-label">Open This Week</div>
      </div>
      <div class="summary-card">
        <div class="big-number">${completedPriorities}</div>
        <div class="card-label">Checked Off</div>
      </div>
      <div class="summary-card">
        <div class="big-number blue">${withNotes}</div>
        <div class="card-label">With Notes</div>
      </div>
    </div>

    ${weeklyError && !showWeeklyAddForm && editingWeeklyIndex === -1 ? `<div class="form-error project-global-error">${esc(weeklyError)}</div>` : ""}
    ${renderWeeklyCurrent(latest)}
    <div class="weekly-list">
      ${weeks.map((week, position) => renderWeeklyCard(week, position)).join("")}
    </div>
    <button class="add-task-btn add-project-btn" onclick="openWeeklyAddForm()">+ Add Weekly Focus</button>
    ${renderWeeklyEditor(weeks)}`;
}

function renderWeeklyCurrent(week) {
  return `
    <section class="project-pull weekly-current">
      <div>
        <div class="project-pull-label">Current Planning Theme</div>
        <div class="project-pull-title">Week of ${esc(shortDate(week.week_of))}</div>
        <p>${esc(week.why || "No weekly theme set yet.")}</p>
      </div>
      <span class="project-score" title="Open priorities">${weeklyPriorityItems(week).filter((item) => !item.checked).length}</span>
    </section>`;
}

function renderWeeklyCard(week, position) {
  const priorities = weeklyPriorityItems(week);
  return `
    <article class="project-card weekly-card">
      <div class="project-card-top">
        <span class="project-priority now">${esc(shortDate(week.week_of))}</span>
        <span class="project-status ${position === 0 ? "active" : "paused"}">${position === 0 ? "Latest" : "History"}</span>
      </div>
      ${week.why ? `<div class="project-field"><span>Why this week</span><p>${esc(week.why)}</p></div>` : ""}
      <div class="weekly-priority-list">
        ${priorities.map((priority, i) => `
          <div class="weekly-priority ${priority.checked ? "done" : ""}">
            <span>${priority.checked ? checkSvg() : i + 1}</span>
            <p>${esc(priority.text)}</p>
          </div>
        `).join("")}
      </div>
      ${week.notes ? `<div class="project-notes weekly-notes">${esc(week.notes)}</div>` : ""}
      <div class="task-actions project-actions" onclick="event.stopPropagation()">
        <button class="task-action-btn" onclick="startWeeklyEdit(${week.index})" title="Edit">&#9998;</button>
        <button class="task-action-btn task-action-delete" onclick="deleteWeeklyFocus(${week.index})" title="Delete">&times;</button>
      </div>
    </article>`;
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
  const currentPlan = d.current_plan || null;

  el.innerHTML = `
    <div class="analytics-header">
      <h1>90-Day Analytics</h1>
      <p>${s.total_days} days tracked &middot; ${s.total_completed} tasks completed &middot; ${s.total_deleted_canceled || 0} deleted/canceled &middot; ${s.total_completed_hours}h logged</p>
    </div>
    ${renderCurrentPlanPreview(currentPlan)}

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
      <div class="summary-card">
        <div class="big-number amber">${s.total_deleted_canceled || 0}</div>
        <div class="card-label">Deleted / Canceled</div>
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
    </div>

    ${renderPlannerRunHistory(d.run_history)}`;

  drawCharts(d);
}

function renderCurrentPlanPreview(plan) {
  if (!plan || plan.included_in_history) return "";

  const completionClass = plan.completed === 0 ? "red" : plan.completion_rate >= 50 ? "green" : "amber";
  return `
    <section class="analytics-current-plan">
      <div>
        <div class="analytics-current-label">Current Plan Preview</div>
        <div class="analytics-current-title">${esc(shortDate(plan.date))} is not in historical analytics yet</div>
        <p>Today has ${plan.planned} planned tasks, ${plan.completed} checked off, and ${plan.planned_minutes} planned minutes. It will enter the trend charts after rollover archives the day and updates the task ledger.</p>
      </div>
      <div class="analytics-current-stats">
        <div>
          <span class="${completionClass}">${plan.completion_rate}%</span>
          <label>current</label>
        </div>
        <div>
          <span>${plan.completed}/${plan.planned}</span>
          <label>tasks</label>
        </div>
      </div>
    </section>`;
}

function renderPlannerRunHistory(runHistory) {
  const summary = runHistory && runHistory.summary ? runHistory.summary : null;
  const runs = Array.isArray(runHistory && runHistory.runs) ? runHistory.runs.slice(-5).reverse() : [];
  if (!summary || summary.total === 0) {
    return `
      <details class="analytics-run-history">
        <summary>
          <span>Planner Runs</span>
          <span>No durable run records</span>
        </summary>
        <p>Runs appear here after the app writes a record to the local run ledger.</p>
      </details>`;
  }

  return `
    <details class="analytics-run-history">
      <summary>
        <span>Planner Runs</span>
        <span>${summary.total} recorded &middot; ${summary.successful} successful &middot; ${summary.failed} failed</span>
      </summary>
      <div class="analytics-run-history-head">
        <div>
          <div class="analytics-current-label">Planner Runs</div>
          <div class="analytics-current-title">${summary.total} runs recorded in the last 90 days</div>
          <p>${summary.successful} successful &middot; ${summary.failed} failed &middot; ${summary.skipped} skipped</p>
        </div>
      </div>
      <div class="analytics-run-list">
        ${runs.map((run) => {
          const status = esc(run.status || "unknown");
          const title = run.provider_label || run.mode || "Planner";
          const runType = run.run_type || run.focus || run.mode || "";
          const tokens = run.total_tokens ? ` &middot; ${Number(run.total_tokens).toLocaleString()} tokens` : "";
          const errors = Array.isArray(run.errors) && run.errors.length ? `<div class="analytics-run-error">${esc(run.errors.join(" | "))}</div>` : "";
          return `
            <div class="analytics-run-row">
              <span class="analytics-run-status ${status}">${status}</span>
              <div>
                <div class="analytics-run-title">${esc(title)}${runType ? ` <span>${esc(runType)}</span>` : ""}</div>
                <div class="analytics-run-meta">${esc(formatRunTime(run.started_at || ""))}${tokens}</div>
                ${errors}
              </div>
            </div>`;
        }).join("")}
      </div>
    </details>`;
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
  const runDate = d.run_date ? formatDate(String(d.run_date).slice(0, 10)) : generated;
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
      <p>${docs.length} docs matched &middot; run ${esc(runDate)} &middot; ${esc(lookback)} &middot; scanned ${esc(generated)}</p>
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
  const activity = doc.activity_date ? shortDate(doc.activity_date.slice(0, 10)) : "";
  const created = doc.created_at ? shortDate(doc.created_at.slice(0, 10)) : "Unknown date";
  const modified = doc.modified_at ? shortDate(doc.modified_at.slice(0, 10)) : "";
  const confidence = Math.round((doc.confidence || 0) * 100);
  const priority = doc.priority_hint ? `<span class="doc-priority">${esc(doc.priority_hint)}</span>` : "";
  const title = esc(doc.title || "Untitled document");
  const keyPoints = (doc.key_points || []).slice(0, 3);
  const titleMarkup = href
    ? `<a class="doc-title" href="${esc(href)}" target="_blank" rel="noreferrer">${title}</a>`
    : `<div class="doc-title">${title}</div>`;

  return `
    <article class="doc-card">
      <div class="doc-card-top">
        <div class="doc-date">${activity ? `activity ${esc(activity)}` : esc(created)}${modified ? ` &middot; modified ${esc(modified)}` : ""}</div>
        <div class="doc-badges">
          ${priority}
          <span class="doc-confidence">${confidence}%</span>
        </div>
      </div>
      ${titleMarkup}
      ${doc.summary ? `<p class="doc-summary">${esc(doc.summary)}</p>` : ""}
      ${keyPoints.length ? `<ul class="doc-key-points">${keyPoints.map((point) => `<li>${esc(point)}</li>`).join("")}</ul>` : ""}
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

if (location.hash === "#projects") switchTab("projects");
if (location.hash === "#weekly") switchTab("weekly");
if (location.hash === "#analytics") switchTab("analytics");
if (location.hash === "#docs") switchTab("docs");
