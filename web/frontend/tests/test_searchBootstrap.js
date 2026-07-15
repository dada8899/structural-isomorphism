'use strict';

const assert = require('assert');
const path = require('path');

const bootstrapPath = path.join(__dirname, '..', 'assets', 'js', 'search-bootstrap.js');

function fakeNode(tagName) {
  const classes = new Set();
  return {
    tagName: String(tagName || '').toUpperCase(),
    id: '',
    className: '',
    textContent: '',
    children: [],
    dataset: {},
    attributes: {},
    classList: { add(name) { classes.add(name); }, contains(name) { return classes.has(name); } },
    appendChild(child) { this.children.push(child); return child; },
    append(...children) { children.forEach((child) => this.appendChild(child)); },
    replaceChildren(...children) { this.children = children; },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    get lastChild() { return this.children[this.children.length - 1] || null; },
  };
}

function treeText(node) {
  return [node.textContent, ...node.children.map(treeText)].join(' ');
}

function treeIds(node) {
  return [node.id, ...node.children.flatMap(treeIds)].filter(Boolean);
}

function run(context, href) {
  const host = fakeNode('div');
  host.id = 'search-summary';
  let calls = 0;
  const document = {
    getElementById(id) { return id === 'search-summary' ? host : null; },
    createElement: fakeNode,
  };
  const window = {
    document,
    location: { href },
    resolvePrivateNavigationContext(options) {
      calls += 1;
      assert.strictEqual(options.kind, 'search');
      return context;
    },
  };
  global.window = window;
  delete require.cache[require.resolve(bootstrapPath)];
  require(bootstrapPath);
  return { host, window, calls };
}

const chinese = run({
  query: '团队 A 与 B 的反馈为何变慢？',
  rewritten_query: null,
  lang: 'zh',
}, 'https://beta.structural.test/search?context=' + 'a'.repeat(32));
assert.strictEqual(chinese.calls, 1);
assert.strictEqual(chinese.window.__structuralSearchBoot.attempted, true);
assert.strictEqual(chinese.window.__structuralSearchBoot.context.query, '团队 A 与 B 的反馈为何变慢？');
assert.strictEqual(chinese.host.dataset.searchBootstrap, 'ready');
assert.ok(chinese.host.classList.contains('search-summary--active'));
assert.ok(treeText(chinese.host).includes('团队 A 与 B 的反馈为何变慢？'));
assert.ok(treeText(chinese.host).includes('先按原问题检索'));
assert.strictEqual(new Set(treeIds(chinese.host)).size, treeIds(chinese.host).length);

// Re-execution is idempotent and cannot consume the one-time handoff twice.
delete require.cache[require.resolve(bootstrapPath)];
require(bootstrapPath);
assert.strictEqual(chinese.calls, 1);

const english = run({
  query: 'Why does delayed feedback create overshoot?',
  rewritten_query: 'How does feedback delay alter overshoot?',
  lang: 'en',
}, 'https://beta.structural.test/search?context=' + 'b'.repeat(32) + '&lang=en');
assert.ok(treeText(english.host).includes('Your question'));
assert.ok(treeText(english.host).includes('Rewritten as a research question:'));
assert.ok(treeText(english.host).includes('How does feedback delay alter overshoot?'));

const rejected = run(null, 'https://beta.structural.test/search?context=' + 'c'.repeat(32));
assert.strictEqual(rejected.window.__structuralSearchBoot.context, null);
assert.strictEqual(rejected.host.children.length, 0);

delete global.window;
console.log('search bootstrap tests passed');
