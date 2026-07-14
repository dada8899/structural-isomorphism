'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'assets', 'js', 'analytics-consent.js'),
  'utf8'
);

function boot(pathname) {
  const scripts = [];
  const nodes = new Map();
  let assigned = null;
  const location = {
    href: 'https://beta.structural.bytedance.city' + pathname,
    pathname,
    assign(value) { assigned = value; },
  };
  const document = {
    readyState: 'complete',
    documentElement: {lang: 'zh'},
    head: {
      appendChild(node) {
        scripts.push(node);
        if (node.id) nodes.set(node.id, node);
      },
    },
    body: {appendChild(node) { if (node.id) nodes.set(node.id, node); }},
    addEventListener() {},
    createElement() { return {dataset: {}, remove() { nodes.delete(this.id); }}; },
    getElementById(id) { return nodes.get(id) || null; },
    querySelectorAll() { return []; },
  };
  const storage = JSON.stringify({version: 1, analytics: true});
  const window = {
    location,
    localStorage: {
      getItem() { return storage; },
      setItem() {},
    },
    doNotTrack: '0',
  };
  const context = vm.createContext({
    URL,
    Date,
    JSON,
    console,
    document,
    navigator: {doNotTrack: '0', msDoNotTrack: '0'},
    window,
  });
  vm.runInContext(source, context, {filename: 'analytics-consent.js'});
  return {
    scripts,
    open: window.StructuralAnalytics.open,
    assigned: () => assigned,
  };
}

test('stored consent cannot inject Plausible on any private research route', () => {
  for (const pathname of [
    '/analyze', '/analyze/', '/analyze.html', '/reports', '/reports/',
    '/reports.html', '/report', '/report/', '/report.html',
    '/report/r_0123456789abcdef',
    '/report/share/0123456789abcdef0123456789abcdef',
  ]) {
    const runtime = boot(pathname);
    assert.equal(runtime.scripts.length, 0, pathname);
    runtime.open();
    assert.equal(runtime.scripts.length, 0, pathname);
    assert.equal(runtime.assigned(), '/privacy#analytics', pathname);
  }
});

test('sensitive route matching does not disable unrelated public pages', () => {
  for (const pathname of ['/analyzer', '/reporting', '/discoveries']) {
    const runtime = boot(pathname);
    assert.equal(runtime.scripts.length, 1, pathname);
    assert.equal(runtime.scripts[0].src, 'https://plausible.bytedance.city/js/script.js');
  }
});
