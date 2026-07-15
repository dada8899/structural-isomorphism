'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const utilsSource = fs.readFileSync(
  path.join(__dirname, '..', 'assets', 'js', 'utils.js'),
  'utf8'
);
const sidebarSource = fs.readFileSync(
  path.join(__dirname, '..', 'assets', 'js', 'history-sidebar.js'),
  'utf8'
);

function fakeStorage(map, options = {}) {
  return {
    getItem(key) {
      if (options.throwGet) throw new Error('storage read blocked');
      return map.has(String(key)) ? map.get(String(key)) : null;
    },
    setItem(key, value) {
      if (options.throwSet) throw new Error('storage write blocked');
      if (!options.noopSet) map.set(String(key), String(value));
    },
    removeItem(key) {
      if (options.throwRemove) throw new Error('storage remove blocked');
      if (!options.noopRemove) map.delete(String(key));
    },
  };
}

function loadUtils({sharedLocal, tabSession, localOptions, sessionOptions, crypto}) {
  const cookies = new Map();
  const fetchCalls = [];
  const eventListeners = new Map();
  class FakeEvent {
    constructor(type) { this.type = type; }
  }
  const document = {
    querySelector() { return null; },
    addEventListener() {},
  };
  Object.defineProperty(document, 'cookie', {
    configurable: true,
    get() {
      return Array.from(cookies.entries())
        .map(([key, value]) => `${key}=${value}`)
        .join('; ');
    },
    set(raw) {
      const first = String(raw).split(';', 1)[0];
      const index = first.indexOf('=');
      if (index < 1) return;
      cookies.set(first.slice(0, index), first.slice(index + 1));
    },
  });
  const window = {
    document,
    location: {
      origin: 'https://beta.structural.test',
      protocol: 'https:',
    },
    localStorage: fakeStorage(sharedLocal, localOptions),
    sessionStorage: fakeStorage(tabSession, sessionOptions),
    crypto,
    console: {warn() {}, error() {}, log() {}},
    addEventListener(type, handler) {
      const handlers = eventListeners.get(type) || [];
      handlers.push(handler);
      eventListeners.set(type, handlers);
    },
    dispatchEvent(event) {
      (eventListeners.get(event.type) || []).forEach(handler => handler(event));
      return true;
    },
    requestAnimationFrame(callback) { callback(); },
  };
  window.window = window;
  const context = vm.createContext({
    window,
    document,
    localStorage: window.localStorage,
    sessionStorage: window.sessionStorage,
    fetch(url, options) {
      fetchCalls.push({url, options});
      return Promise.resolve({ok: true, json: () => Promise.resolve({items: []})});
    },
    URL,
    Event: FakeEvent,
    Uint8Array,
    encodeURIComponent,
    decodeURIComponent,
    setTimeout,
    setInterval,
    clearInterval,
    console: window.console,
  });
  vm.runInContext(utilsSource, context, {filename: 'utils.js'});
  return {window, cookies, fetchCalls, sharedLocal, tabSession};
}

function secureCrypto() {
  return {randomUUID: () => '12345678-1234-4123-8123-123456789abc'};
}

async function run() {
  console.log('history privacy tests');

  {
    const shared = new Map([
      ['structural_history', JSON.stringify([{query: 'legacy raw private query'}])],
    ]);
    const alpha = loadUtils({
      sharedLocal: shared,
      tabSession: new Map(),
      crypto: secureCrypto(),
    });
    assert.strictEqual(shared.has('structural_history'), false);
    assert.strictEqual(shared.get('structural_history_local_cleanup_v2'), '1');
    assert.deepStrictEqual(Array.from(alpha.window.getHistory()), []);
    const alphaEvents = [];
    alpha.window.addEventListener('structural:history-changed', event => alphaEvents.push(event));
    alpha.window.addToHistory({query: 'tab alpha private query', timestamp: 1});
    assert.strictEqual(alphaEvents.length, 1);
    assert.strictEqual(alphaEvents[0].detail, undefined);

    const beta = loadUtils({
      sharedLocal: shared,
      tabSession: new Map(),
      crypto: secureCrypto(),
    });
    const betaEvents = [];
    beta.window.addEventListener('structural:history-changed', event => betaEvents.push(event));
    beta.window.addToHistory({query: 'tab beta private query', timestamp: 2});
    assert.strictEqual(betaEvents.length, 1);
    assert.strictEqual(alphaEvents.length, 1);

    assert.deepStrictEqual(
      Array.from(alpha.window.getHistory(), entry => entry.query),
      ['tab alpha private query']
    );
    assert.deepStrictEqual(
      Array.from(beta.window.getHistory(), entry => entry.query),
      ['tab beta private query']
    );
    const sharedPayload = JSON.stringify(Array.from(shared.entries()));
    assert(!sharedPayload.includes('legacy raw private query'));
    assert(!sharedPayload.includes('tab alpha private query'));
    assert(!sharedPayload.includes('tab beta private query'));
    console.log('  ok   - legacy raw local history is deleted and two tabs stay isolated');
  }

  {
    const shared = new Map([
      ['structural_history', JSON.stringify([{query: 'legacy secret survives no-op remove'}])],
    ]);
    const guarded = loadUtils({
      sharedLocal: shared,
      tabSession: new Map(),
      localOptions: {noopRemove: true},
      crypto: secureCrypto(),
    });
    assert.strictEqual(shared.get('structural_history'), '[]');
    assert(!JSON.stringify(Array.from(shared.entries())).includes('legacy secret'));
    assert.deepStrictEqual(Array.from(guarded.window.getHistory()), []);
    console.log('  ok   - no-op legacy removal is overwritten and verified without migration');
  }

  {
    const shared = new Map();
    const blocked = loadUtils({
      sharedLocal: shared,
      tabSession: new Map(),
      sessionOptions: {throwGet: true, throwSet: true},
      crypto: secureCrypto(),
    });
    assert.deepStrictEqual(Array.from(blocked.window.getHistory()), []);
    assert.deepStrictEqual(
      Array.from(blocked.window.addToHistory({query: 'must not fall back'})),
      []
    );
    assert(!JSON.stringify(Array.from(shared.entries())).includes('must not fall back'));

    const noOp = loadUtils({
      sharedLocal: new Map(),
      tabSession: new Map(),
      sessionOptions: {noopSet: true},
      crypto: secureCrypto(),
    });
    assert.deepStrictEqual(
      Array.from(noOp.window.addToHistory({query: 'unverified write'})),
      []
    );
    console.log('  ok   - throwing and no-op session storage fail closed without local fallback');
  }

  {
    const unicode = loadUtils({
      sharedLocal: new Map(),
      tabSession: new Map(),
      crypto: secureCrypto(),
    });
    const atLimit = '🧪'.repeat(8000);
    unicode.window.addToHistory({query: atLimit, timestamp: 3});
    assert.strictEqual(
      Array.from(Array.from(unicode.window.getHistory())[0].query).length,
      8000
    );
    unicode.window.addToHistory({query: atLimit + '🧪', timestamp: 4});
    assert.strictEqual(Array.from(unicode.window.getHistory()).length, 1);
    assert.strictEqual(Array.from(unicode.window.getHistory())[0].timestamp, 3);
    console.log('  ok   - history uses the shared 8000 Unicode code-point boundary');
  }

  {
    const defaultLocal = new Map();
    const normal = loadUtils({
      sharedLocal: defaultLocal,
      tabSession: new Map(),
      crypto: secureCrypto(),
    });
    assert.strictEqual(normal.window.isRemoteHistoryEnabled(), false);
    assert.strictEqual(normal.window.getDeviceId(), null);
    assert.strictEqual(await normal.window.recordHistoryRemote('private query', 'search'), null);
    assert.strictEqual(normal.fetchCalls.length, 0);
    assert.strictEqual(normal.cookies.size, 0);

    const cryptoFailure = loadUtils({
      sharedLocal: new Map([['structural_use_remote_history', '1']]),
      tabSession: new Map(),
      crypto: {randomUUID() { throw new Error('entropy unavailable'); }},
    });
    assert.strictEqual(cryptoFailure.window.getDeviceId(), null);
    assert.strictEqual(
      await cryptoFailure.window.recordHistoryRemote('private query', 'search'),
      null
    );
    assert.strictEqual(cryptoFailure.fetchCalls.length, 0);
    assert.strictEqual(cryptoFailure.cookies.size, 0);
    console.log('  ok   - remote history is opt-in and crypto failure creates no id or request');
  }

  {
    const optedIn = loadUtils({
      sharedLocal: new Map([['structural_use_remote_history', '1']]),
      tabSession: new Map(),
      crypto: secureCrypto(),
    });
    const deviceId = optedIn.window.getDeviceId();
    assert.strictEqual(deviceId, '12345678-1234-4123-8123-123456789abc');
    await optedIn.window.recordHistoryRemote('explicit remote query', 'search');
    assert.strictEqual(optedIn.fetchCalls.length, 1);
    assert.strictEqual(
      optedIn.fetchCalls[0].options.headers['X-Device-ID'],
      deviceId
    );
    console.log('  ok   - explicit opt-in uses a verified WebCrypto device id');
  }

  assert(!sidebarSource.includes("addEventListener('storage'"));
  assert(sidebarSource.includes("addEventListener('structural:history-changed'"));
  assert(sidebarSource.includes('window.isRemoteHistoryEnabled() === true'));
  assert(!sidebarSource.includes("window.Storage.set('structural_history'"));
  console.log('  ok   - sidebar has no cross-tab storage listener or raw local write');
  console.log('\nall tests passed.');
}

run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
