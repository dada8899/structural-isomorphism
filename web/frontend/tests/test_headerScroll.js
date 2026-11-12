'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const source = fs.readFileSync(process.env.HEADER_SCROLL_SOURCE || path.join(
  __dirname, '..', 'assets', 'js', 'utils.js'
), 'utf8');

function fixture(present = true) {
  const frames = [], tasks = [], listeners = new Map();
  let reads = 0, y = 0, dirty = true;
  function newHeader() {
    const classes = new Set();
    return {isConnected: true, classes, classList: {
      add: name => classes.add(name), remove: name => classes.delete(name),
    }};
  }
  let header = present ? newHeader() : null;
  const document = {querySelector: () => header, addEventListener() {}};
  const window = {
    requestAnimationFrame: fn => frames.push(fn),
    setTimeout: (fn, delay) => { assert.strictEqual(delay, 0); tasks.push(fn); },
    addEventListener(type, fn, options) {
      if (type === 'scroll') assert.strictEqual(options.passive, true);
      listeners.set(type, [...(listeners.get(type) || []), fn]);
    },
    get scrollY() {
      reads += 1;
      if (dirty) throw new Error('geometry read during DOM writes');
      return y;
    },
  };
  vm.runInNewContext(source, {window, document, console}, {filename: 'utils.js'});
  return {
    window, frames, tasks, listeners,
    get header() { return header; },
    get reads() { return reads; },
    setY(value) { y = value; },
    replaceHeader() { if (header) header.isConnected = false; header = newHeader(); },
    removeHeader() { if (header) header.isConnected = false; header = null; },
    emit(type) { (listeners.get(type) || []).forEach(fn => fn()); },
    frame() { frames.splice(0).forEach(fn => fn()); },
    render() { dirty = false; tasks.splice(0).forEach(fn => fn()); },
    dirty() { dirty = true; },
  };
}

let passed = 0;
function test(name, run) {
  run(); passed += 1; console.log('PASS ' + name);
}

test('boot callers do not read geometry synchronously or inside the frame', () => {
  const f = fixture();
  f.window.initHeaderScroll(); f.window.initHeaderScroll();
  assert.strictEqual(f.reads, 0);
  assert.strictEqual(f.frames.length, 1);
  f.frame(); assert.strictEqual(f.reads, 0);
  f.render(); assert.strictEqual(f.reads, 1);
  assert.strictEqual(f.header.classes.has('scrolled'), false);
});

test('repeated initialization and scroll bursts keep one passive listener/read', () => {
  const f = fixture();
  for (let i = 0; i < 10; i += 1) f.window.initHeaderScroll();
  assert.strictEqual(f.listeners.get('scroll').length, 1);
  assert.strictEqual(f.listeners.get('pageshow').length, 1);
  f.setY(300);
  for (let i = 0; i < 10; i += 1) f.emit('scroll');
  assert.strictEqual(f.frames.length, 1);
  f.frame(); f.render();
  assert.strictEqual(f.reads, 1);
  assert.strictEqual(f.header.classes.has('scrolled'), true);
});

test('the original four-pixel boundary works in both directions', () => {
  const f = fixture(); f.window.initHeaderScroll();
  for (const [y, expected] of [[4, false], [4.5, true], [200, true], [0, false]]) {
    f.setY(y); f.emit('scroll'); f.frame(); f.render();
    assert.strictEqual(f.header.classes.has('scrolled'), expected);
  }
});

test('pageshow reads the latest restored position without a scroll event', () => {
  const f = fixture(); f.window.initHeaderScroll(); f.frame(); f.render();
  f.dirty(); f.setY(500); f.emit('pageshow');
  assert.strictEqual(f.reads, 1);
  f.frame(); f.render();
  assert.strictEqual(f.header.classes.has('scrolled'), true);
  f.setY(0); f.emit('pageshow'); f.frame(); f.render();
  assert.strictEqual(f.header.classes.has('scrolled'), false);
});

test('a replaced header receives the pending update without duplicate listeners', () => {
  const f = fixture(); f.window.initHeaderScroll();
  const old = f.header; f.replaceHeader(); f.setY(100);
  f.window.initHeaderScroll(); f.frame(); f.render();
  assert.strictEqual(old.classes.size, 0);
  assert.strictEqual(f.header.classes.has('scrolled'), true);
  assert.strictEqual(f.listeners.get('scroll').length, 1);
});

test('missing or detached headers do not read layout and can initialize later', () => {
  const f = fixture(false); f.window.initHeaderScroll();
  assert.strictEqual(f.listeners.size, 0); assert.strictEqual(f.frames.length, 0);
  f.replaceHeader(); f.window.initHeaderScroll();
  f.removeHeader(); f.frame(); f.render();
  assert.strictEqual(f.reads, 0);
  f.window.initHeaderScroll();
  f.replaceHeader(); f.window.initHeaderScroll(); f.setY(10); f.frame(); f.render();
  assert.strictEqual(f.header.classes.has('scrolled'), true);
  assert.strictEqual(f.listeners.get('scroll').length, 1);
});

console.log(`${passed} header-scroll contracts passed`);
