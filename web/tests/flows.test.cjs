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
    this.open = false;
    this.style = {};
    this.value = '';
    this.type = 'password';
    this.textContent = '';
    this.dataset = {};
    this.attrs = {};
    this.listeners = {};
    this.children = [];
    this.firstChild = { textContent: '' };
    this.classList = { toggle() {}, remove() {}, add() {} };
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
  let clock = 100000;
  class FakeDate extends Date { static now() { return clock; } }
  const element = (id) => {
    if (!elements.has(id)) {
      const item = new Element();
      if (['stop-confirmation','stop-button','dashboard','demo-banner','redirect-notice'].includes(id)) item.hidden = true;
      elements.set(id, item);
    }
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
      addEventListener() {},
      querySelectorAll: () => [new Element(), new Element(), new Element(), new Element()],
      createElement: () => new Element(),
    },
    navigator: { clipboard: { async writeText() {} } },
    fetch: async (url, options) => {
      calls.push({ url, options });
      const body = await response(url, options);
      return { ok: !body.httpStatus || body.httpStatus < 400, status: body.httpStatus || 200, json: async () => body };
    },
    Date: FakeDate, performance: { now: () => clock },
    requestAnimationFrame: () => 123, cancelAnimationFrame() {},
    URL, AbortController, console,
    setTimeout: (fn, delay) => { const id = nextId++; timeouts.set(id, { fn, delay }); return id; },
    clearTimeout: (id) => timeouts.delete(id),
    setInterval: (fn, delay) => { const id = nextId++; intervals.set(id, { fn, delay }); return id; },
    clearInterval: (id) => intervals.delete(id),
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'games.js'), 'utf8'), context);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'app.js'), 'utf8'), context);
  return { element, calls, timeouts, intervals, navigations, windowEvents, advance: (ms) => { clock += ms; } };
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
  const ui = app({ response: (url) => url.endsWith('/start') ? { httpStatus: 429, phase: 'blocked', message: 'LÃ­mite mensual alcanzado' } : { phase: 'off' } });
  await login(ui);
  await ui.element('start-button').trigger('click');
  assert.equal(ui.element('start-button').disabled, true);
  assert.equal(ui.element('notice').textContent, 'LÃ­mite mensual alcanzado');
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


test('manual shutdown requires confirmation, warns about players, and sends one POST', async () => {
  const ui = app({ response: (url) => ({ phase: url.endsWith('/stop') ? 'stopping' : 'ready', players: 3 }) });
  await login(ui);
  await ui.element('stop-button').trigger('click');
  assert.equal(ui.calls.length, 1);
  assert.match(ui.element('stop-warning').textContent, /3 jugador/);
  await ui.element('cancel-stop').trigger('click');
  await ui.element('confirm-stop').trigger('click');
  assert.equal(ui.calls.length, 1);
  await ui.element('stop-button').trigger('click');
  await ui.element('confirm-stop').trigger('click');
  assert.equal(ui.calls.at(-1).url, 'https://example.azurewebsites.net/api/stop');
  assert.equal(ui.calls.at(-1).options.method, 'POST');
  assert.equal(ui.element('status-badge').textContent, 'Apagando');
  assert.equal(ui.element('stop-button').hidden, true);
});

test('games remain available while ready, opening them cancels redirection', async () => {
  const ui = app({ response: () => ({ phase: 'ready', panelUrl: 'https://panel.example.test/' }) });
  await login(ui);
  assert.equal(ui.element('games-accordion').open, false);
  assert.equal(ui.element('game-section').hidden, false);
  ui.element('games-accordion').open = true;
  await ui.element('games-accordion').trigger('toggle');
  assert.equal(ui.intervals.size, 0);
  assert.equal(ui.calls.length, 1);
});

test('CPS ends after 15 seconds and closing the accordion stops local timers', async () => {
  const ui = app();
  await ui.element('cps-start').trigger('click');
  for (let i = 0; i < 30; i++) await ui.element('cps-target').trigger('click');
  ui.advance(15000);
  [...ui.intervals.values()][0].fn();
  assert.match(ui.element('cps-score').textContent, /30 clics.*2,00 CPS/);
  assert.equal(ui.element('cps-target').disabled, true);
  await ui.element('cps-start').trigger('click');
  await ui.element('games-accordion').trigger('toggle');
  assert.equal(ui.intervals.size, 0);
  assert.equal(ui.calls.length, 0);
});

test('campfire and runner interactions never call Azure', async () => {
  const ui = app();
  await ui.element('campfire').trigger('click');
  await ui.element('runner-start').trigger('click');
  await ui.element('runner-track').trigger('click');
  assert.equal(ui.calls.length, 0);
  assert.match(ui.element('runner-score').textContent, /Salta/);
  ui.windowEvents.pagehide();
  assert.equal(ui.intervals.size, 0);
  assert.equal(ui.timeouts.size, 0);
});

const { ClickRound, Runner } = require('../games.js');
test('an older status poll cannot replace a confirmed shutdown with ready', async () => {
  let finishPoll;
  let statusCalls = 0;
  const ui = app({ response: (url) => {
    if (url.endsWith('/stop')) return { phase: 'stopping' };
    statusCalls++;
    return statusCalls === 1 ? { phase: 'ready' } : new Promise(resolve => { finishPoll = resolve; });
  } });
  await login(ui);
  const pending = [...ui.timeouts.values()].find(timer => timer.delay === 12000).fn();
  await ui.element('stop-button').trigger('click');
  await ui.element('confirm-stop').trigger('click');
  finishPoll({ phase: 'ready', panelUrl: 'https://panel.example.test/' });
  await pending;
  assert.equal(ui.element('status-badge').textContent, 'Apagando');
  assert.equal(ui.intervals.size, 0);
});

test('CPS rejects clicks at or after the exact deadline', () => {
  const round = new ClickRound(1000);
  round.click(1000); round.click(15999); round.click(16000); round.click(20000);
  assert.equal(round.result(16000).clicks, 2);
  assert.equal(round.result(17000).remaining, 0);
  assert.equal(round.result(17000).cps, 2 / 15);
});
test('runner collides with a log on the ground and clears it with a timed jump', () => {
  const collision = new Runner(() => 0);
  collision.obstacle = 14;
  collision.step(0.02);
  assert.equal(collision.over, true);
  const jumping = new Runner(() => 0);
  jumping.obstacle = 24;
  jumping.jump();
  for (let i = 0; i < 65; i++) jumping.step(0.01);
  assert.equal(jumping.over, false);
  assert.ok(jumping.obstacle < 8);
});
