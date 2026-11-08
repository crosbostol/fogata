const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

// A small DOM double exercises the browser application's API/auth/navigation flows.
// Visual layout and native browser accessibility still need browser QA.
class Element {
  constructor() {
    this.hidden = false;
    this.disabled = false;
    this.value = '';
    this.type = 'password';
    this.textContent = '';
    this.dataset = {};
    this.attrs = {};
    this.listeners = {};
    this.children = [];
    this.firstChild = { textContent: '' };
    this.classList = { toggle() {}, remove() {} };
  }
  addEventListener(name, fn) { this.listeners[name] = fn; }
  setAttribute(name, value) { this.attrs[name] = value; }
  removeAttribute(name) { delete this.attrs[name]; }
  append(child) { this.children.push(child); }
  focus() { this.focused = true; }
  async trigger(name) { return this.listeners[name]?.({ preventDefault() {} }); }
}

function app({ demo = false, response = () => ({ phase: 'off' }) } = {}) {
  const elements = new Map();
  const timeouts = new Map();
  const intervals = new Map();
  const calls = [];
  const navigations = [];
  const windowEvents = {};
  let nextId = 1;
  const element = (id) => {
    if (!elements.has(id)) elements.set(id, new Element());
    return elements.get(id);
  };
  const context = {
    window: {
      PORTAL_CONFIG: { apiBaseUrl: 'https://example.azurewebsites.net', demo },
      location: { href: 'https://portal.example.test/', assign: (url) => navigations.push(url) },
      addEventListener: (event, callback) => { windowEvents[event] = callback; },
    },
    document: {
      getElementById: element,
      querySelectorAll: () => [new Element(), new Element(), new Element(), new Element()],
      createElement: () => new Element(),
    },
    navigator: { clipboard: { async writeText() {} } },
    fetch: async (url, options) => {
      calls.push({ url, options });
      const body = await response(url, options);
      return { ok: !body.httpStatus || body.httpStatus < 400, status: body.httpStatus || 200, json: async () => body };
    },
    URL, AbortController, console,
    setTimeout: (fn, delay) => { const id = nextId++; timeouts.set(id, { fn, delay }); return id; },
    clearTimeout: (id) => timeouts.delete(id),
    setInterval: (fn, delay) => { const id = nextId++; intervals.set(id, { fn, delay }); return id; },
    clearInterval: (id) => intervals.delete(id),
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '..', 'app.js'), 'utf8'), context);
  return { element, calls, timeouts, intervals, navigations, windowEvents };
}

async function login(ui) {
  ui.element('password').value = 'a-long-shared-password';
  await ui.element('login-form').trigger('submit');
}

test('opening the page does not query the API or start a VM', () => {
  const ui = app();
  assert.equal(ui.calls.length, 0);
  assert.equal(ui.timeouts.size, 0);
});

test('login only reads status; clicking start makes exactly one POST', async () => {
  const ui = app({ response: (url) => ({ phase: url.endsWith('/start') ? 'starting' : 'off', usedHours: 12, maxHours: 180 }) });
  await login(ui);
  assert.equal(ui.calls.length, 1);
  assert.equal(ui.calls[0].url, 'https://example.azurewebsites.net/api/status');
  assert.equal(ui.calls[0].options.method, 'GET');
  assert.equal(ui.calls[0].options.headers['X-Portal-Password'], 'a-long-shared-password');
  assert.equal(ui.calls[0].options.credentials, 'omit');
  assert.equal(ui.element('password').value, '');
  assert.equal(ui.element('dashboard').hidden, false);
  await ui.element('start-button').trigger('click');
  assert.equal(ui.calls.length, 2);
  assert.equal(ui.calls[1].options.method, 'POST');
  assert.equal(ui.element('start-button').disabled, true);
  assert.equal(ui.element('game-section').hidden, false);
});

test('a rejected password leaves no polling or dashboard session', async () => {
  const ui = app({ response: () => ({ httpStatus: 401 }) });
  await login(ui);
  assert.equal(ui.element('login-form').hidden, false);
  assert.equal(ui.element('dashboard').hidden, true);
  assert.equal(ui.timeouts.size, 0);
  assert.match(ui.element('notice').textContent, /contraseña/);
  assert.equal(ui.element('notice').textContent.includes('a-long-shared-password'), false);
});

test('budget limit disables further starts and exposes API message as text', async () => {
  const ui = app({ response: (url) => url.endsWith('/start') ? { httpStatus: 429, phase: 'blocked', message: 'Límite mensual alcanzado' } : { phase: 'off' } });
  await login(ui);
  await ui.element('start-button').trigger('click');
  assert.equal(ui.element('start-button').disabled, true);
  assert.equal(ui.element('notice').textContent, 'Límite mensual alcanzado');
});

test('ready status redirects only to a valid panel URL after a cancelable countdown', async () => {
  const ui = app({ response: () => ({ phase: 'ready', panelUrl: 'https://panel.example.test/', players: 2 }) });
  await login(ui);
  assert.equal(ui.navigations.length, 0);
  assert.equal(ui.intervals.size, 1);
  const tick = [...ui.intervals.values()][0].fn;
  for (let i = 0; i < 10; i++) tick();
  assert.deepEqual(ui.navigations, ['https://panel.example.test/']);
  const canceled = app({ response: () => ({ phase: 'ready', panelUrl: 'https://panel.example.test/' }) });
  await login(canceled);
  await canceled.element('cancel-redirect').trigger('click');
  assert.equal(canceled.intervals.size, 0);
  assert.equal(canceled.element('redirect-notice').hidden, true);
});

test('an unexpected panel URL cannot become a script navigation', async () => {
  const ui = app({ response: () => ({ phase: 'ready', panelUrl: 'javascript:alert(1)' }) });
  await login(ui);
  assert.equal(ui.intervals.size, 0);
  assert.equal(ui.element('panel-link').hidden, true);
  assert.equal(ui.navigations.length, 0);
});

test('demo never calls Azure or stores credentials and is visibly identified', async () => {
  const ui = app({ demo: true });
  assert.equal(ui.element('demo-banner').hidden, false);
  await login(ui);
  await ui.element('start-button').trigger('click');
  assert.equal(ui.calls.length, 0);
  assert.match(ui.element('status-badge').textContent, /Demo/);
  assert.equal(ui.element('game-section').hidden, false);
  await ui.element('logout-button').trigger('click');
  assert.equal(ui.element('dashboard').hidden, true);
  assert.equal(ui.timeouts.size, 0);
});

test('logging out while a start request is in flight prevents later redirect', async () => {
  let finishStart;
  const ui = app({ response: (url) => url.endsWith('/start') ? new Promise((resolve) => { finishStart = resolve; }) : { phase: 'off' } });
  await login(ui);
  const starting = ui.element('start-button').trigger('click');
  await ui.element('logout-button').trigger('click');
  finishStart({ phase: 'ready', panelUrl: 'https://panel.example.test/' });
  await starting;
  assert.equal(ui.element('dashboard').hidden, true);
  assert.equal(ui.intervals.size, 0);
  assert.equal(ui.navigations.length, 0);
});
