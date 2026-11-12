'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'assets', 'js', 'history-sidebar.js'), 'utf8'
);

function node() {
  const attributes = new Map();
  const classes = new Set();
  return {
    classList: {
      add(value) { classes.add(value); },
      remove(value) { classes.delete(value); },
      contains(value) { return classes.has(value); },
      toggle(value) {
        if (classes.has(value)) { classes.delete(value); return false; }
        classes.add(value); return true;
      },
    },
    setAttribute(name, value) { attributes.set(name, String(value)); },
    removeAttribute(name) { attributes.delete(name); },
    getAttribute(name) { return attributes.has(name) ? attributes.get(name) : null; },
    focus() {},
  };
}

let width = 1023;
const sidebar = node();
const trigger = node();
const toggle = node();
const backdrop = node();
const body = node();
const ids = new Map([
  ['history-sidebar', sidebar], ['history-sidebar-trigger', trigger],
  ['history-sidebar-backdrop', backdrop],
]);
const document = {
  readyState: 'loading', body,
  getElementById(id) { return ids.get(id) || null; },
  querySelector(selector) {
    return selector === '.history-sidebar__toggle' ? toggle : null;
  },
  addEventListener() {},
};
const queries = [];
const window = {
  document,
  matchMedia(query) {
    queries.push(query);
    return {get matches() { return width <= 1023; }};
  },
  requestAnimationFrame() {},
};
Object.defineProperty(window, 'innerWidth', {
  get() { throw new Error('breakpoint check flushed dirty layout via innerWidth'); },
});
window.getComputedStyle = () => { throw new Error('geometry/style fallback is forbidden'); };
const context = vm.createContext({window, document, console, setTimeout});
vm.runInContext(source, context, {filename: 'history-sidebar.js'});

window.HistorySidebar.openDrawer();
assert.strictEqual(sidebar.getAttribute('role'), 'dialog');
assert.strictEqual(sidebar.getAttribute('aria-modal'), 'true');
assert.strictEqual(trigger.getAttribute('aria-expanded'), 'true');
window.HistorySidebar.closeDrawer(false);
assert.strictEqual(sidebar.getAttribute('aria-hidden'), 'true');
assert.notStrictEqual(sidebar.getAttribute('inert'), null);

// Exercise the public API with the same live query after a viewport change.
width = 1024;
window.HistorySidebar.closeDrawer(false);
assert.strictEqual(sidebar.getAttribute('role'), null);
assert.strictEqual(sidebar.getAttribute('aria-modal'), null);
assert.strictEqual(sidebar.getAttribute('aria-hidden'), 'false');
assert.strictEqual(sidebar.getAttribute('inert'), null);

width = 390;
window.HistorySidebar.openDrawer();
assert.strictEqual(sidebar.getAttribute('role'), 'dialog');
assert.strictEqual(sidebar.getAttribute('aria-modal'), 'true');
window.HistorySidebar.closeDrawer(false);
assert.strictEqual(sidebar.getAttribute('aria-hidden'), 'true');
width = 1280;
window.HistorySidebar.closeDrawer(false);
assert.strictEqual(sidebar.getAttribute('inert'), null);
assert(queries.length > 0);
assert(queries.every(query => query === '(max-width: 1023px)'));
assert(source.includes('@media (max-width: 1023px)'));
assert(source.includes('@media (min-width: 1024px)'));
console.log('history sidebar breakpoint avoids geometry reads and remains live across resize');
