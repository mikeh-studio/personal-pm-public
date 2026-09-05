const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const staticDir = join(__dirname, '..', 'app', 'static');
// Exercise the real renderers without bootstrapping network requests or a browser.
const source = readFileSync(join(staticDir, 'app.js'), 'utf8').split('// ── Init ──')[0];
function harness(fixture = {}) {
  const nodes = new Map();
  function node(selector) {
    if (!nodes.has(selector)) {
      const classes = new Set();
      nodes.set(selector, {
        innerHTML: '', dataset: {}, attributes: {},
        classList: { toggle(name, on) { on ? classes.add(name) : classes.delete(name); }, contains(name) { return classes.has(name); } },
        setAttribute(name, value) { this.attributes[name] = value; },
        removeAttribute(name) { delete this.attributes[name]; },
        focus() { this.focused = true; },
        querySelector() { return null; },
      });
    }
    return nodes.get(selector);
  }
  const tabs = ['today', 'projects', 'weekly', 'analytics', 'connections'].map(name => {
    const el = node(`tab:${name}`); el.dataset.tab = name; return el;
  });
  const sections = ['connections', 'docs'].map(name => {
    const el = node(`section:${name}`); el.dataset.section = name; return el;
  });
  const panels = ['today', 'projects', 'weekly', 'analytics', 'connections', 'docs'].map(name => {
    const el = node(`#tab-${name}`); el.id = `tab-${name}`; return el;
  });
  const context = vm.createContext({
    URL, fixture,
    window: { scrollY: 0, scrollTo() {} },
    document: { querySelector: node, querySelectorAll: selector => ({ '.tab': tabs, '[data-section]': sections, '.tab-content': panels }[selector] || []), documentElement: node('root'), addEventListener() {} },
    localStorage: { getItem: () => 'dark' },
    fetch() { throw new Error('Renderer must not send requests'); },
  });
  vm.runInContext(source, context);
  vm.runInContext('Object.assign(state, fixture); driveDocsData = {docs: []};', context);
  return { run: script => vm.runInContext(script, context), node };
}

test('onboarding renders and retains missing context while editing goals', () => {
  const h = harness({goals: {overall_goals: ['Learn a language'], setup_fields: [
    {key: 'deadlines', label: 'Near-term deadlines', help: 'State any deadline'},
    {key: 'daily_practice', label: 'Daily practice preferences', help: 'Keep it small'},
  ]}});
  h.run(`openOnboarding('2026-09-07')`);
  let html = h.node('.onboarding-overlay').innerHTML;
  assert.match(html, /id="onb-context-deadlines"/);
  assert.match(html, /id="onb-context-daily_practice"/);
  assert.doesNotMatch(html, /id="onb-context-disciplines"/);
  h.node('#onb-goal-0').value = 'Learn a language';
  h.node('#onb-context-deadlines').value = 'No fixed deadlines';
  h.node('#onb-context-daily_practice').value = '<img src=x onerror=alert(1)>';
  h.run('addOnboardingGoal()');
  html = h.node('.onboarding-overlay').innerHTML;
  assert.match(html, /No fixed deadlines/);
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.equal(h.run('_onboardingState.contextDraft.deadlines'), 'No fixed deadlines');
});

test('existing weekly focus still prompts for missing goal context', () => {
  const h = harness({goals: {overall_goals: ['Learn'], setup_fields: [{key: 'daily_practice'}]}});
  h.run('state.weekly = {weeks: [{week_of: defaultWeekOf()}]}');
  assert.equal(h.run('needsOnboarding().need'), true);
  assert.equal(h.run('needsOnboarding().needWeekly'), false);
  h.run('state.goals.setup_fields = []');
  assert.equal(h.run('needsOnboarding().need'), false);
});

const projects = [
  { name: 'Archived work', priority: 'Later', status: 'Closed', notes: 'Keep history' },
  { name: 'Active project', priority: 'Now', status: 'Active', next_action: 'Ship slice', notes: '<script>alert(1)</script>', index: 7 },
  { name: 'Paused work', priority: 'Next', status: 'Paused', next_action: 'Wait' },
];
test('project rows preserve details, linked documents, closed history and edit identity', () => {
  const h = harness({ projects, today: { tasks: [{title: 'Active project task', meta: {}}] } });
  h.run(`driveDocsData.docs = [{title: 'Design evidence', matched_projects: ['Active project'], url: 'https://example.com/design'}]; renderProjects()`);
  const html = h.node('#projects').innerHTML;
  for (const text of ['Closed projects · 1', 'Archived work', 'Keep history', 'Paused work', 'Ship slice', 'Design evidence', 'Active project task', 'startProjectEdit(7)', 'deleteProject(0)']) assert.ok(html.includes(text), text);
  assert.ok(html.includes('&lt;script&gt;'));
  assert.ok(!html.includes('<script>'));
  assert.equal(h.run('selectProjectPullCandidate(state.projects).name'), 'Active project');
  h.run('startProjectEdit(7)');
  assert.match(h.node('#projects').innerHTML, /saveProject\(7\)/);
  assert.ok(h.node('#pf-name').focused);
});

test('empty and all-closed portfolios retain add and edit actions', () => {
  const h = harness({projects: []});
  h.run('openProjectAddForm()');
  assert.match(h.node('#projects').innerHTML, /saveProject\(-1\)/);
  h.run(`cancelProjectEdit(); state.projects = [${JSON.stringify(projects[0])}]; renderProjects()`);
  assert.match(h.node('#projects').innerHTML, /All projects are closed/);
  assert.match(h.node('#projects').innerHTML, /startProjectEdit\(0\)/);
});

const weekly = { weeks: [
  { week_of: '2026-08-31', index: 4, why: 'Ship the workflow', notes: 'Limit scope', priority_items: [{text: 'First outcome', checked: true}, {text: 'Second outcome', checked: false}] },
  { week_of: '2026-08-24', index: 9, why: 'Earlier theme', notes: 'Earlier notes', priorities: ['Prior outcome'] },
] };
test('weekly focus shows progress, retains previous weeks and edits their original identity', () => {
  const h = harness({weekly});
  h.run('renderWeeklyFocus()');
  const html = h.node('#weekly-focus').innerHTML;
  assert.ok(html.indexOf('Ship the workflow') < html.indexOf('Previous weeks'));
  for (const text of ['max="2" value="1"', '1 of 2 completed', 'Limit scope', 'Earlier notes', 'Prior outcome', 'startWeeklyEdit(9)']) assert.ok(html.includes(text), text);
  h.run('startWeeklyEdit(9)');
  assert.match(h.node('#weekly-focus').innerHTML, /id="wf-week-of" value="2026-08-24"/);
  assert.match(h.node('#weekly-focus').innerHTML, /saveWeeklyFocus\(9\)/);
  assert.ok(h.node('#wf-week-of').focused);
});

test('opening a weekly editor does not add blank outcomes to the saved focus', () => {
  const h = harness({weekly: JSON.parse(JSON.stringify(weekly))});
  h.run('startWeeklyEdit(4); cancelWeeklyEdit()');
  assert.equal(h.run('state.weekly.weeks[0].priority_items.length'), 2);
  assert.match(h.node('#weekly-focus').innerHTML, /1 of 2 completed/);
});

test('empty weekly focus can be created and untrusted outcome text is escaped', () => {
  const h = harness();
  h.run('openWeeklyAddForm()');
  assert.match(h.node('#weekly-focus').innerHTML, /saveWeeklyFocus\(-1\)/);
  const output = h.run(`weekOutcomes({priorities: ['<img src=x onerror=alert(1)>']})`);
  assert.ok(!output.includes('<img'));
  assert.ok(output.includes('&lt;img'));
  assert.ok(!h.run('weekProgress({priorities: []})').includes('<progress'));
});

test('Documents stays under Setting while Today restores the primary navigation', () => {
  const h = harness();
  h.run('switchTab("docs")');
  assert.equal(h.node('tab:connections').attributes['aria-current'], 'page');
  assert.equal(h.node('section:docs').attributes['aria-pressed'], 'true');
  assert.equal(h.node('#setting-sections').classList.contains('hidden'), false);
  assert.equal(h.node('#tab-docs').classList.contains('hidden'), false);
  h.run('switchTab("today")');
  assert.equal(h.node('#setting-sections').classList.contains('hidden'), true);
  assert.equal(h.node('tab:connections').attributes['aria-current'], undefined);
  assert.equal(h.node('tab:today').attributes['aria-current'], 'page');
});

const today = {date: '2026-09-04', tasks: [
  {title: 'Review release checklist', priority: 1, duration: '45m', checked: false, meta: {type: 'project_work'}},
], feedback: {worked: 'Shipped one slice'}, carry_forward: ['Keep scope small'], heads_up: ['Time is limited']};

test('Plan + Review retains task actions, feedback, and planning context', () => {
  const h = harness({today});
  h.run('render()');
  const html = h.node('#app').innerHTML;
  for (const text of ['today-primary', 'today-review', 'Review release checklist', 'toggleTask(0)', 'startEdit(0)', 'Task details', 'Keep scope small', 'Time is limited', 'feedback-worked', 'Shipped one slice', 'saveFeedback(this)']) assert.ok(html.includes(text), text);
  assert.ok(!html.includes('data-layout='));
});

test('archived Plan + Review shows feedback without mutation controls', () => {
  const h = harness({today});
  h.run('viewingArchive = true; render()');
  const html = h.node('#app').innerHTML;
  assert.ok(html.includes('Archived Plan'));
  assert.ok(html.includes('Shipped one slice'));
  for (const text of ['saveFeedback(this)', 'startEdit(0)', 'openAddForm()', 'toggleTask(0)']) assert.ok(!html.includes(text), text);
});

test('empty plan can add its first task and failed planner status stays visible', () => {
  const h = harness({today: {...today, tasks: []}, morning: {status: 'failed'}});
  h.run('openAddForm()');
  const html = h.node('#app').innerHTML;
  assert.ok(html.includes('saveTask(-1)'));
  assert.ok(html.indexOf('morning-banner failed') < html.indexOf('today-workspace'));
});

test('saved sidebar feedback survives the next render', async () => {
  const h = harness({today: JSON.parse(JSON.stringify(today))});
  h.run(`apiFetch = async () => ({ok: true, json: async () => ({ok: true})}); toast = () => {};`);
  await h.run(`saveFeedback({dataset: {field: 'worked'}, value: 'New saved feedback', defaultValue: ''})`);
  h.run('render()');
  assert.ok(h.node('#app').innerHTML.includes('New saved feedback'));
});
