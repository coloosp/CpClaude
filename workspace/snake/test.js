// 无浏览器环境的验证：1) 纯逻辑单测  2) 用假 DOM 跑一遍 index.html 的内联脚本
const fs = require("fs"), path = require("path"), assert = require("assert");
const L = require("/home/coloop/ProjectSpace/Claude/workspace/snake/logic.js");
const ok = (m) => console.log("✓ " + m);

// ---- 1. 逻辑测试 ----
let s = L.createState(20, 20, () => 0);
assert.deepStrictEqual(s.snake[0], { x: 3, y: 2 });
L.step(s); assert.deepStrictEqual(s.snake[0], { x: 4, y: 2 }); assert.strictEqual(s.snake.length, 3);
ok("前进：头右移一格，长度不变");

s = L.createState(20, 20, () => 0); s.food = { x: 4, y: 2 }; L.step(s);
assert.strictEqual(s.score, 1); assert.strictEqual(s.snake.length, 4); assert.ok(s.eaten);
ok("吃食物：得分 +1，长度 +1，重新生成食物");

s = L.createState(20, 20, () => 0); L.turn(s, "left"); L.step(s);
assert.strictEqual(s.dir, "right"); ok("禁止 180° 反向");

L.turn(s, "up"); L.turn(s, "left"); L.step(s);
assert.strictEqual(s.dir, "up", "第二步才生效（排队，防一帧内连续转向）"); ok("转向排队");

s = L.createState(20, 20, () => 0); s.snake = [{ x: 0, y: 0 }, { x: 1, y: 0 }]; L.turn(s, "up"); L.step(s);
assert.ok(s.over); ok("撞墙 → 游戏结束");

s = L.createState(20, 20, () => 0);
s.snake = [{ x: 1, y: 1 }, { x: 1, y: 2 }, { x: 2, y: 2 }, { x: 2, y: 1 }, { x: 3, y: 1 }]; // 右侧有自己身体
s.food = { x: 9, y: 9 }; L.step(s); assert.ok(s.over); ok("撞自己 → 游戏结束");

// ---- 2. 假 DOM 冒烟测试：真跑 index.html 里的脚本 ----
const html = fs.readFileSync("/home/coloop/ProjectSpace/Claude/workspace/snake/index.html", "utf8");
const inline = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const drawCalls = [];
const ctx = new Proxy({}, { get: (t, k) => (k === "font" || k === "fillStyle" || k === "textAlign") ? "" : (...a) => { drawCalls.push([k, ...a]); } , set: () => true });
const els = { cv: { width: 300, height: 300, getContext: () => ctx }, score: { textContent: "0" }, tip: {} };
const listeners = {};
global.document = { getElementById: (id) => els[id] };
global.addEventListener = (k, f) => (listeners[k] = f);
let rafQueue = [];
global.requestAnimationFrame = (f) => rafQueue.push(f);
global.performance = { now: () => 0 };
global.SnakeLogic = L;
// 用 vm 编译执行，等价于浏览器解析（语法错误会在这里抛出）
const vm = require("vm");
vm.runInThisContext(inline, { filename: "index.html:inline" });
ok("内联脚本可解析执行（无语法/引用错误）");

// 推进 3 秒（每秒 8 步），每次 rAF 间隔 16ms
let t = 0;
for (let i = 0; i < 190; i++) { t += 16; const f = rafQueue.shift(); f(t); }
ok("跑 190 帧无异常，得分文本=" + els.score.textContent + "，绘制调用 " + drawCalls.length + " 次");

// 模拟按键：按 ↑ 然后一路走到撞墙
listeners.keydown({ key: "ArrowUp", preventDefault() {} });
for (let i = 0; i < 200; i++) { t += 16; const f = rafQueue.shift(); if (!f) break; f(t); }
const gameOverDrawn = drawCalls.some((c) => c[0] === "fillText" && String(c[1]).startsWith("游戏结束"));
assert.ok(gameOverDrawn, "应绘制游戏结束文字");
ok("键盘监听生效，撞墙后绘制“游戏结束”覆盖层");

// 空格重开
listeners.keydown({ key: " ", preventDefault() {} });
rafQueue.shift()(t = t + 16);
assert.strictEqual(String(els.score.textContent), "0");
ok("空格重开：得分归零");
console.log("\n全部通过 ✅");
