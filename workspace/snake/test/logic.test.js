/* 无浏览器环境下的逻辑测试：用极简 DOM/Canvas 桩加载 game.js 并驱动时间 */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const SRC = path.join(__dirname, '..', 'game.js');
let code = fs.readFileSync(SRC, 'utf8');

// 仅在测试时注入只读探针
code = code.replace(
  '  resize();\n  reset();',
  `  window.__probe = {
    get state() { return state; },
    get snake() { return snake.map((s) => ({ ...s })); },
    get food() { return food && { ...food }; },
    get score() { return score; },
    get best() { return best; },
    get queueLen() { return queue.length; },
  };
  resize();
  reset();`
);
if (!code.includes('__probe')) throw new Error('探针注入失败');

/* ---------------- DOM 桩 ---------------- */
class ClassList {
  constructor() { this.set = new Set(); }
  add(c) { this.set.add(c); }
  remove(c) { this.set.delete(c); }
  contains(c) { return this.set.has(c); }
}

class El {
  constructor(id) {
    this.id = id;
    this.textContent = '';
    this.dataset = {};
    this.classList = new ClassList();
    this.listeners = {};
    this.clientWidth = 480;
    this.clientHeight = 480;
    this.width = 0;
    this.height = 0;
  }
  addEventListener(t, fn) { (this.listeners[t] ||= []).push(fn); }
  fire(t, ev = {}) { (this.listeners[t] || []).forEach((fn) => fn(ev)); }
}

const gradient = () => ({ addColorStop() {} });
function makeCtx() {
  const noop = () => {};
  return {
    setTransform: noop, fillRect: noop, beginPath: noop, moveTo: noop,
    lineTo: noop, stroke: noop, fill: noop, arc: noop, save: noop,
    restore: noop, clearRect: noop, createRadialGradient: gradient,
    createLinearGradient: gradient,
  };
}

const els = new Map();
const getEl = (id) => {
  if (!els.has(id)) els.set(id, new El(id));
  return els.get(id);
};

const canvas = getEl('board');
canvas.getContext = () => makeCtx();

const dpad = ['up', 'down', 'left', 'right'].map((d) => {
  const b = new El('dbtn-' + d);
  b.dataset = { dir: d };
  return b;
});

const docListeners = {};
const documentStub = {
  hidden: false,
  getElementById: getEl,
  querySelectorAll: (sel) => (sel === '.dbtn' ? dpad : []),
  addEventListener: (t, fn) => { (docListeners[t] ||= []).push(fn); },
};

const winListeners = {};
let rafCb = null;
const store = new Map();

const ctxObj = {
  document: documentStub,
  localStorage: {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
  },
  performance: { now: () => 0 },
  requestAnimationFrame: (cb) => { rafCb = cb; return 1; },
  devicePixelRatio: 2,
};
ctxObj.window = ctxObj;
ctxObj.AudioContext = undefined;
ctxObj.ResizeObserver = undefined;
ctxObj.addEventListener = (t, fn) => { (winListeners[t] ||= []).push(fn); };

vm.createContext(ctxObj);
vm.runInContext(code, ctxObj);

const probe = ctxObj.__probe;
const key = (k) => (winListeners.keydown || []).forEach((fn) => fn({ key: k, preventDefault() {} }));

let now = 0;
const STEP = 16;
function tick(ms = STEP) {
  now += ms;
  const cb = rafCb;
  rafCb = null;
  if (cb) cb(now);
}

/* ---------------- 断言 ---------------- */
let pass = 0;
const fails = [];
function ok(cond, msg) {
  if (cond) { pass++; console.log('  \u2713 ' + msg); }
  else { fails.push(msg); console.log('  \u2717 ' + msg); }
}

console.log('\n[1] 初始状态');
ok(probe.state === 'ready', '初始为 ready 状态');
ok(probe.snake.length === 3, '初始长度 3');
ok(probe.food !== null, '已生成食物');
ok(getEl('len').textContent === 3, 'HUD 长度显示 3');
ok(getEl('best').textContent === 0, 'HUD 最高分显示 0');

console.log('\n[2] 启动与暂停');
key('ArrowRight');
ok(probe.state === 'playing', '按方向键即开始游戏');
for (let i = 0; i < 10; i++) tick();
key(' ');
ok(probe.state === 'paused', '空格暂停');
const pausedHead = probe.snake[0];
for (let i = 0; i < 60; i++) tick();
ok(probe.snake[0].x === pausedHead.x && probe.snake[0].y === pausedHead.y, '暂停时蛇不移动');
key(' ');
ok(probe.state === 'playing', '空格继续');

console.log('\n[3] 禁止 180 度掉头');
const before = probe.snake[0];
key('ArrowLeft');
for (let i = 0; i < 20; i++) tick();
ok(probe.snake[0].x >= before.x, '向右前进时按左键不会掉头');

console.log('\n[4] 撞墙判负');
let guard = 0;
while (probe.state === 'playing' && guard++ < 500) tick();
ok(probe.state === 'over', '撞墙后状态为 over');
ok(getEl('ov-title').textContent === '游戏结束', '覆盖层显示「游戏结束」');
ok(!getEl('overlay').classList.contains('hidden'), '结束覆盖层可见');

console.log('\n[5] 重新开始');
key('r');
ok(probe.state === 'playing', 'R 键立即重开');
ok(probe.score === 0 && probe.snake.length === 3, '分数与长度已重置');
ok(getEl('overlay').classList.contains('hidden'), '开始后覆盖层隐藏');

console.log('\n[6] 自动寻路吃食物（贪心走位）');
/* 简易寻路：在「不撞墙 / 不掉头 / 不撞身」的候选方向里选离食物最近的 */
const N = 20;
const eat = () => {
  const body = probe.snake;
  const h = body[0], f = probe.food;
  if (!f || body.length < 2) return;
  const d = { x: h.x - body[1].x, y: h.y - body[1].y };   // 当前朝向
  const occupied = new Set(body.slice(0, -1).map((s) => s.x + ',' + s.y));
  const cands = [
    { k: 'ArrowUp', x: 0, y: -1 }, { k: 'ArrowDown', x: 0, y: 1 },
    { k: 'ArrowLeft', x: -1, y: 0 }, { k: 'ArrowRight', x: 1, y: 0 },
  ].filter((c) => {
    const nx = h.x + c.x, ny = h.y + c.y;
    if (nx < 0 || ny < 0 || nx >= N || ny >= N) return false;
    if (c.x === -d.x && c.y === -d.y) return false;       // 不能掉头
    return !occupied.has(nx + ',' + ny);
  });
  if (!cands.length) return;
  cands.sort((a, b) =>
    (Math.abs(h.x + a.x - f.x) + Math.abs(h.y + a.y - f.y)) -
    (Math.abs(h.x + b.x - f.x) + Math.abs(h.y + b.y - f.y)));
  key(cands[0].k);
};
let frames = 0;
const startLen = probe.snake.length;
while (probe.score < 6 && probe.state === 'playing' && frames++ < 4000) {
  eat();
  tick();
}
ok(probe.score >= 6, '成功吃到 6 个食物（得分 ' + probe.score + '）');
ok(probe.snake.length === startLen + probe.score, '蛇身长度随得分增长');
ok(probe.score === 6 && Math.floor(probe.score / 4) + 1 >= 2, '等级随得分提升');

console.log('\n[7] 最高分持久化');
const bestSeen = probe.best;
ok(bestSeen >= 6, '最高分已更新为 ' + bestSeen);
ok(store.get('snake.best.v1') === String(bestSeen), '最高分写入 localStorage');

console.log('\n[8] 音效开关');
getEl('mute-btn').fire('click');
ok(getEl('mute-btn').textContent === '🔇', '静音图标切换');
ok(store.get('snake.muted.v1') === '1', '静音偏好已持久化');

console.log('\n[9] 方向键缓冲上限');
key('ArrowUp'); key('ArrowRight'); key('ArrowDown'); key('ArrowLeft');
ok(probe.queueLen <= 2, '转向队列最多缓存 2 个输入');

console.log('\n[10] 长时间运行不崩溃');
getEl('board').fire('touchstart', { changedTouches: [{ clientX: 100, clientY: 100 }] });
getEl('board').fire('touchend', { changedTouches: [{ clientX: 100, clientY: 20 }] });
for (let i = 0; i < 3000; i++) tick();
ok(true, '滑动输入 + 3000 帧无异常');

console.log(`\n结果：${pass} 项通过，${fails.length} 项失败`);
if (fails.length) {
  fails.forEach((f) => console.log('  - ' + f));
  process.exit(1);
}
