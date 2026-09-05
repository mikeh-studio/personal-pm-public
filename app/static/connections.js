// Connection forms send credentials once to the local backend; never retain them in state/storage.
let connectionRows = [];
let apiPlanState = null;

async function connectionRequest(url, body) {
  const response = await apiFetch(url, body === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok || data.ok === false) throw new Error(data.error || 'Request failed.');
  return data;
}

async function loadConnections() {
  try {
    const data = await connectionRequest('/api/connections');
    connectionRows = data.connections;
    $('#connections').innerHTML = `
      <h1>Setting</h1><h2 class="setting-title">API connections</h2>
      <p class="connection-note">Choose how the skill calls a model. Your goals, selected project context, and planning answers go to that provider when you generate a plan. The skill’s rules and local validators still govern the result.</p>
      <p class="connection-note">API usage is billed by the provider. Requests cap final output at 4,096 tokens, with no automatic retry. This is not a spending cap; provider orchestration may cost extra. Test connection checks credentials and the model catalog without sending planner context.</p>
      ${connectionRows.map(c => `<form class="connection-card" onsubmit="saveConnection(event, '${c.id}')">
        <h2 class="provider-heading">${providerLogo("api:" + c.id)}${esc(c.label)}</h2>
        <p class="connection-note">${c.configured ? (c.available ? 'Configured · test to verify access' : 'Credential unavailable · reconnect') : 'Not connected'}</p>
        <label>Model ID<input id="conn-model-${c.id}" value="${esc(c.model)}" required maxlength="160" autocomplete="off" placeholder="Exact model ID from your provider"></label>
        <label>Key storage<select id="conn-storage-${c.id}" onchange="changeKeyStorage('${c.id}')">
          <option value="keychain" ${c.storage === 'keychain' ? 'selected' : ''}>System keychain (recommended)</option>
          <option value="memory" ${c.storage === 'memory' ? 'selected' : ''}>Temporary — until server stops</option>
          <option value="environment" ${c.storage === 'environment' ? 'selected' : ''}>Environment variable: ${esc(c.env)}</option>
        </select></label>
        <label>API key<input type="password" id="conn-key-${c.id}" autocomplete="off" spellcheck="false" maxlength="4096" ${c.storage === 'environment' ? 'disabled' : ''} placeholder="${c.configured ? 'Leave blank to retain the current key' : 'Paste your provider API key'}"></label>
        ${c.id === 'openrouter' ? `<label>Upstream provider slug<input id="conn-upstream-${c.id}" value="${esc(c.upstream)}" required maxlength="160" placeholder="For example: openai"></label><p class="connection-note">OpenRouter forwards context to this provider only. Fallbacks are disabled and routes permitting data collection are excluded; incompatible routes return an error.</p>` : ''}
        ${c.id === 'sakana' ? '<p class="connection-note">Fugu can route context to other model providers. Restrict its model pool when creating your API key in the Sakana console.</p>' : ''}
        <div class="connection-actions">
          <button type="submit" class="form-btn form-btn-primary">Save connection</button>
          <button type="button" class="form-btn" onclick="testConnection('${c.id}')" ${!c.available ? 'disabled' : ''}>Test connection</button>
          <button type="button" class="form-btn" onclick="disconnectConnection('${c.id}')" ${!c.configured ? 'disabled' : ''}>Disconnect</button>
        </div>
        <p class="connection-status" role="status" id="conn-status-${c.id}"></p>
      </form>`).join('')}
      <p class="connection-note">Keys are never saved in planner files, browser storage, or logs. Disconnect removes the app’s saved key; revoke it at the provider to invalidate it elsewhere. Environment variables remain under your control.</p>`;
  } catch (error) {
    $('#connections').textContent = error.message;
  }
}

function changeKeyStorage(id) {
  const input = $(`#conn-key-${id}`);
  input.value = '';
  input.disabled = $(`#conn-storage-${id}`).value === 'environment';
}

async function saveConnection(event, id) {
  event.preventDefault();
  const field = $(`#conn-key-${id}`);
  const body = {model: $(`#conn-model-${id}`).value.trim(), storage: $(`#conn-storage-${id}`).value,
    api_key: field.value, upstream: $(`#conn-upstream-${id}`)?.value.trim() || ''};
  field.value = '';
  const button = event.target.querySelector('[type=submit]');
  button.disabled = true;
  try {
    await connectionRequest(`/api/connections/${id}/save`, body);
    await loadConnections();
    $(`#conn-status-${id}`).textContent = 'Saved locally. Test connection to check access.';
  } catch (error) {
    $(`#conn-status-${id}`).textContent = error.message;
  } finally {
    body.api_key = '';
    button.disabled = false;
  }
}

async function testConnection(id) {
  $(`#conn-status-${id}`).textContent = 'Checking credentials and model catalog…';
  try {
    const data = await connectionRequest(`/api/connections/${id}/test`, {});
    $(`#conn-status-${id}`).textContent = data.note;
  } catch (error) { $(`#conn-status-${id}`).textContent = error.message; }
}

async function disconnectConnection(id) {
  try {
    await connectionRequest(`/api/connections/${id}/disconnect`, {});
    await loadConnections();
    toast('Connection removed');
  } catch (error) { $(`#conn-status-${id}`).textContent = error.message; }
}

function openApiPlan(provider) {
  apiPlanState = {provider, context: '', result: null, error: '', busy: false};
  renderApiPlan();
}

function closeApiPlan() {
  if (apiPlanState?.busy) return;
  apiPlanState = null;
  $('#api-plan-overlay')?.remove();
}

function renderApiPlan() {
  if (!apiPlanState) return;
  let overlay = $('#api-plan-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'api-plan-overlay';
    overlay.className = 'onboarding-overlay';
    document.body.appendChild(overlay);
  }
  const s = apiPlanState;
  const result = s.result;
  const tasks = (result?.plan_markdown || '').split('\n').filter(line => /^- \[[ xX]\]/.test(line));
  overlay.innerHTML = `<div class="onboarding-panel" role="dialog" aria-modal="true" aria-labelledby="api-plan-title">
    <h2 id="api-plan-title" class="provider-heading">${providerLogo("api:" + s.provider)}Plan with ${esc(RUN_PROVIDERS['api:' + s.provider]?.label || s.provider)}</h2>
    <p class="connection-note">The skill will share saved goals, project and weekly context, recent outcome summaries, today’s plan, and your notes below with this provider. Your API key stays with the local backend. A draft is shown before saving.</p>
    <label>What matters now, what have you finished, and how much time remains?
      <textarea id="api-plan-context" maxlength="8000" rows="4" ${s.busy ? 'disabled' : ''} placeholder="A short update is enough. Leave time blank if you’re unsure.">${esc(s.context)}</textarea>
    </label>
    ${result ? `<p>${esc(result.summary)}</p>${result.questions.map(q => `<p class="api-question">${esc(q)}</p>`).join('')}` : ''}
    ${tasks.length ? `<div class="api-plan-preview">${tasks.map(line => `<p>${esc(line.split(' | ')[0])}</p>`).join('')}</div><details><summary>Full plan and notes</summary><pre class="api-plan-source">${esc(result.plan_markdown)}</pre></details>` : ''}
    <p role="status" class="connection-status">${esc(s.busy ? 'Working…' : s.error)}</p>
    <div class="connection-actions">
      <button class="form-btn form-btn-primary" onclick="generateApiPlan()" ${s.busy ? 'disabled' : ''}>${result?.questions.length ? 'Answer and continue' : 'Generate draft'}</button>
      ${result?.draft_id ? `<button class="form-btn form-btn-primary" onclick="applyApiPlan()" ${s.busy ? 'disabled' : ''}>Apply this plan</button>` : ''}
      <button class="form-btn" onclick="closeApiPlan()" ${s.busy ? 'disabled' : ''}>Close</button>
    </div>
  </div>`;
}

async function generateApiPlan() {
  if (!apiPlanState || apiPlanState.busy) return;
  const s = apiPlanState;
  const selection = selectedRunPayload();
  if (selection.error) { s.error = selection.error; renderApiPlan(); return; }
  s.context = $('#api-plan-context').value;
  const questionContext = s.result?.questions?.length ? '\nQuestions being answered: ' + s.result.questions.join(' ') : '';
  const requestContext = s.context + questionContext;
  s.busy = true; s.error = ''; s.result = null;
  renderApiPlan();
  try {
    s.result = await connectionRequest('/api/plan/draft', {provider: s.provider, mode: selection.mode,
      focus: selection.focus, context: requestContext});
  } catch (error) { s.error = error.message; }
  finally { s.busy = false; renderApiPlan(); }
}

async function applyApiPlan() {
  if (!apiPlanState?.result?.draft_id || apiPlanState.busy) return;
  const s = apiPlanState;
  s.busy = true; renderApiPlan();
  try {
    await connectionRequest('/api/plan/apply', {draft_id: s.result.draft_id});
    s.busy = false; closeApiPlan();
    await fetchAll(); toast('Plan saved', 'success');
  } catch (error) { s.busy = false; s.error = error.message; renderApiPlan(); }
}
