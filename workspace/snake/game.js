/* 贪吃蛇 · canvas 实现（零依赖） */
(() => {
  'use strict';

  /* ---------- 配置 ---------- */
  const COLS = 20;
  const ROWS = 20;
  const BASE_STEP = 145;   // 1 级时每步毫秒
  const MIN_STEP = 68;     // 最快
  const STEP_DROP = 7;     // 每升一级缩短
  const LEVEL_EVERY = 4;   // 每得多少分升一级
  const START_LEN = 3;
  const KEY = { best: 'snake.best.v1', mute: 'snake.muted.v1' };

  /* ---------- DOM ---------- */
  const $ = (id) => document.getElementById(id);
  const canvas = $('board');
  const ctx = canvas.getContext('2d');
  const elScore = $('score');
  const elBest = $('best');
  const elLevel = $('level');
  const elLen = $('len');
  const overlay = $('overlay');
  const ovTitle = $('ov-title');
  const ovSub = $('ov-sub');
  const ovBtn = $('ov-btn');
  const muteBtn = $('mute-btn');

  /* ---------- 状态 ---------- */
  let snake = [];          // [{x,y}]，头在 [0]
  let prevSnake = [];      // 上一步位置，用于插值动画
  let dir = { x: 1, y: 0 };
  let queue = [];          // 待生效的转向
  let food = null;
  let score = 0;
  let best = 0;
  let state = 'ready';     // ready | playing | paused | over | win
  let acc = 0;             // 步进累加器
  let lastTs = 0;
  let eatFlash = 0;
  let cell = 20;
  let overlayAction = 'start';
  let muted = false;

  try {
    best = Number(localStorage.getItem(KEY.best)) || 0;
    muted = localStorage.getItem(KEY.mute) === '1';
  } catch (_) { /* 隐私模式下忽略 */ }
  muteBtn.textContent = muted ? '🔇' : '🔊';

  /* ---------- 音效 ---------- */
  let audio = null;
  function beep(freq, dur, type = 'sine', vol = 0.06) {
    if (muted) return;
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      if (audio.state === 'suspended') audio.resume();
      const t = audio.currentTime;
      const osc = audio.createOscillator();
      const gain = audio.createGain();
      osc.type = type;
      osc.frequency.setValueAtTime(freq, t);
      gain.gain.setValueAtTime(vol, t);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + dur);
      osc.connect(gain).connect(audio.destination);
      osc.start(t);
      osc.stop(t + dur);
    } catch (_) { /* 无音频能力则静默 */ }
  }

  /* ---------- HUD ---------- */
  const level = () => Math.floor(score / LEVEL_EVERY) + 1;
  const stepMs = () => Math.max(MIN_STEP, BASE_STEP - (level() - 1) * STEP_DROP);

  function updateHud() {
    elScore.textContent = score;
    elBest.textContent = best;
    elLevel.textContent = level();
    elLen.textContent = snake.length;
  }

  function saveBest() {
    if (score <= best) return;
    best = score;
    try { localStorage.setItem(KEY.best, String(best)); } catch (_) {}
  }

  function showOverlay(title, sub, btn, action) {
    ovTitle.textContent = title;
    ovSub.textContent = sub;
    ovBtn.textContent = btn;
    overlayAction = action;
    overlay.classList.remove('hidden');
  }

  const hideOverlay = () => overlay.classList.add('hidden');

  /* ---------- 游戏流程 ---------- */
  function spawnFood() {
    const taken = new Set(snake.map((s) => s.x + ',' + s.y));
    const free = [];
    for (let y = 0; y < ROWS; y++) {
      for (let x = 0; x < COLS; x++) {
        if (!taken.has(x + ',' + y)) free.push({ x, y });
      }
    }
    if (!free.length) return null;
    return free[(Math.random() * free.length) | 0];
  }

  function reset() {
    const midY = (ROWS / 2) | 0;
    snake = [];
    for (let i = 0; i < START_LEN; i++) snake.push({ x: 4 - i, y: midY });
    prevSnake = snake.map((s) => ({ ...s }));
    dir = { x: 1, y: 0 };
    queue = [];
    score = 0;
    acc = 0;
    eatFlash = 0;
    food = spawnFood();
    state = 'ready';
    updateHud();
  }

  function startGame() {
    if (state === 'over' || state === 'win' || state === 'ready') reset();
    state = 'playing';
    queue = [];
    acc = 0;
    hideOverlay();
  }

  function togglePause() {
    if (state === 'playing') {
      state = 'paused';
      prevSnake = snake.map((s) => ({ ...s }));
      acc = 0;
      showOverlay('已暂停', '按空格或点击按钮继续', '继续游戏', 'resume');
    } else if (state === 'paused') {
      startGame();
    }
  }

  function die() {
    state = 'over';
    prevSnake = snake.map((s) => ({ ...s }));
    acc = 0;
    beep(190, 0.32, 'sawtooth', 0.08);
    saveBest();
    updateHud();
    showOverlay('游戏结束', `得分 ${score} · 长度 ${snake.length} · 等级 ${level()}`, '再来一局', 'start');
  }

  function win() {
    state = 'win';
    saveBest();
    updateHud();
    showOverlay('满屏通关！', `你把整个棋盘都吃满了，得分 ${score}`, '再来一局', 'start');
  }

  function pushDir(x, y) {
    const last = queue.length ? queue[queue.length - 1] : dir;
    if (last.x === x && last.y === y) return;      // 同向忽略
    if (last.x === -x && last.y === -y) return;    // 禁止 180° 掉头
    if (queue.length < 2) queue.push({ x, y });
  }

  function step() {
    while (queue.length) {
      const nd = queue.shift();
      if (nd.x === -dir.x && nd.y === -dir.y) continue;
      if (nd.x === dir.x && nd.y === dir.y) continue;
      dir = nd;
      break;
    }

    const head = { x: snake[0].x + dir.x, y: snake[0].y + dir.y };

    if (head.x < 0 || head.y < 0 || head.x >= COLS || head.y >= ROWS) return die();

    const ate = !!food && head.x === food.x && head.y === food.y;
    const body = ate ? snake : snake.slice(0, -1);
    if (body.some((s) => s.x === head.x && s.y === head.y)) return die();

    prevSnake = snake.map((s) => ({ ...s }));
    snake.unshift(head);

    if (ate) {
      score += 1;
      saveBest();
      eatFlash = 1;
      beep(680 + Math.min(score, 12) * 18, 0.07, 'square', 0.05);
      food = spawnFood();
      updateHud();
      if (!food) return win();
    } else {
      snake.pop();
    }
  }

  /* ---------- 渲染 ---------- */
  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const size = Math.max(160, Math.round(canvas.clientWidth || 320));
    canvas.width = Math.round(size * dpr);
    canvas.height = Math.round(size * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    cell = size / COLS;
  }

  function drawGrid(size) {
    ctx.fillStyle = '#0c1224';
    ctx.fillRect(0, 0, size, size);

    ctx.strokeStyle = 'rgba(255,255,255,0.035)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let i = 1; i < COLS; i++) {
      const p = Math.round(i * cell) + 0.5;
      ctx.moveTo(p, 0); ctx.lineTo(p, size);
      ctx.moveTo(0, p); ctx.lineTo(size, p);
    }
    ctx.stroke();

    // 棋盘内阴影，增加纵深
    const g = ctx.createRadialGradient(size / 2, size / 2, size * 0.25, size / 2, size / 2, size * 0.75);
    g.addColorStop(0, 'rgba(0,0,0,0)');
    g.addColorStop(1, 'rgba(0,0,0,0.35)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, size, size);
  }

  function drawFood(time) {
    const cx = (food.x + 0.5) * cell;
    const cy = (food.y + 0.5) * cell;
    const pulse = 1 + Math.sin(time / 260) * 0.07;
    const r = cell * 0.31 * pulse;

    ctx.save();
    ctx.shadowColor = 'rgba(255,96,120,0.85)';
    ctx.shadowBlur = cell * 0.9;
    ctx.fillStyle = '#ff5c7a';
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    ctx.fillStyle = 'rgba(255,255,255,0.72)';
    ctx.beginPath();
    ctx.arc(cx - r * 0.32, cy - r * 0.34, r * 0.28, 0, Math.PI * 2);
    ctx.fill();
  }

  function drawSnake(alpha) {
    const pts = snake.map((s, i) => {
      const p = prevSnake[Math.min(i, prevSnake.length - 1)] || s;
      return {
        x: (p.x + (s.x - p.x) * alpha + 0.5) * cell,
        y: (p.y + (s.y - p.y) * alpha + 0.5) * cell,
      };
    });
    if (!pts.length) return;

    const head = pts[0];

    // 身体
    ctx.save();
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.shadowColor = 'rgba(61,220,151,0.45)';
    ctx.shadowBlur = cell * 0.7;

    const grad = ctx.createLinearGradient(head.x, head.y, pts[pts.length - 1].x, pts[pts.length - 1].y);
    grad.addColorStop(0, '#7bf5c0');
    grad.addColorStop(1, '#189a72');
    ctx.strokeStyle = grad;
    ctx.lineWidth = cell * 0.78;

    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
    if (pts.length === 1) ctx.lineTo(pts[0].x + 0.01, pts[0].y);
    ctx.stroke();
    ctx.restore();

    // 头部
    const hr = cell * 0.44;
    ctx.save();
    ctx.shadowColor = 'rgba(120,255,200,0.7)';
    ctx.shadowBlur = cell * 0.8;
    ctx.fillStyle = '#a5ffd8';
    ctx.beginPath();
    ctx.arc(head.x, head.y, hr, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    // 眼睛
    const px = -dir.y, py = dir.x;
    const eo = hr * 0.42, ef = hr * 0.3, er = Math.max(1.4, cell * 0.085);
    for (const s of [1, -1]) {
      const ex = head.x + dir.x * ef + px * eo * s;
      const ey = head.y + dir.y * ef + py * eo * s;
      ctx.fillStyle = '#062b1f';
      ctx.beginPath();
      ctx.arc(ex, ey, er, 0, Math.PI * 2);
      ctx.fill();
    }

    // 吃到食物瞬间的光圈
    if (eatFlash > 0) {
      ctx.save();
      ctx.globalAlpha = eatFlash * 0.65;
      ctx.strokeStyle = '#b9ffe0';
      ctx.lineWidth = Math.max(1.5, cell * 0.1);
      ctx.beginPath();
      ctx.arc(head.x, head.y, hr + (1 - eatFlash) * cell * 1.6, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }
  }

  /* ---------- 主循环 ---------- */
  function frame(ts) {
    if (!lastTs) lastTs = ts;
    const dt = Math.min(ts - lastTs, 250);
    lastTs = ts;

    if (state === 'playing') {
      acc += dt;
      let guard = 0;
      while (acc >= stepMs() && state === 'playing' && guard++ < 8) {
        acc -= stepMs();
        step();
      }
    }
    if (eatFlash > 0) eatFlash = Math.max(0, eatFlash - dt / 220);

    const size = COLS * cell;
    drawGrid(size);
    if (food) drawFood(ts);
    drawSnake(state === 'playing' ? Math.min(acc / stepMs(), 1) : 0);

    requestAnimationFrame(frame);
  }

  /* ---------- 输入 ---------- */
  const DIRS = {
    up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0],
    ArrowUp: [0, -1], ArrowDown: [0, 1], ArrowLeft: [-1, 0], ArrowRight: [1, 0],
    w: [0, -1], s: [0, 1], a: [-1, 0], d: [1, 0],
  };

  function applyDir(x, y) {
    if (state === 'ready') startGame();
    if (state !== 'playing') return;
    pushDir(x, y);
  }

  window.addEventListener('keydown', (e) => {
    const k = e.key;
    if (k === ' ' || k === 'Spacebar') {
      e.preventDefault();
      if (state === 'ready' || state === 'over' || state === 'win') startGame();
      else togglePause();
      return;
    }
    if (k === 'Enter') {
      e.preventDefault();
      if (state === 'over' || state === 'win' || state === 'ready') startGame();
      else togglePause();
      return;
    }
    if (k === 'r' || k === 'R') {
      reset();
      startGame();
      return;
    }
    const m = DIRS[k] || DIRS[String(k).toLowerCase()];
    if (m) {
      e.preventDefault();
      applyDir(m[0], m[1]);
    }
  }, { passive: false });

  document.querySelectorAll('.dbtn').forEach((btn) => {
    const fire = (ev) => {
      ev.preventDefault();
      const d = DIRS[btn.dataset.dir];
      if (d) applyDir(d[0], d[1]);
    };
    btn.addEventListener('pointerdown', fire);
  });

  /* 触屏滑动 */
  let touch = null;
  canvas.addEventListener('touchstart', (e) => {
    const t = e.changedTouches[0];
    touch = { x: t.clientX, y: t.clientY };
  }, { passive: true });

  canvas.addEventListener('touchend', (e) => {
    if (!touch) return;
    const t = e.changedTouches[0];
    const dx = t.clientX - touch.x;
    const dy = t.clientY - touch.y;
    touch = null;
    if (Math.abs(dx) < 22 && Math.abs(dy) < 22) {
      // 轻点：开始 / 暂停
      if (state === 'ready' || state === 'over' || state === 'win') startGame();
      else togglePause();
      return;
    }
    if (Math.abs(dx) > Math.abs(dy)) applyDir(dx > 0 ? 1 : -1, 0);
    else applyDir(0, dy > 0 ? 1 : -1);
  }, { passive: true });

  ovBtn.addEventListener('click', () => {
    if (overlayAction === 'resume') togglePause();
    else startGame();
  });

  $('restart-btn').addEventListener('click', () => {
    reset();
    startGame();
  });

  muteBtn.addEventListener('click', () => {
    muted = !muted;
    muteBtn.textContent = muted ? '🔇' : '🔊';
    try { localStorage.setItem(KEY.mute, muted ? '1' : '0'); } catch (_) {}
    if (!muted) beep(520, 0.06, 'sine', 0.05);
  });

  document.addEventListener('visibilitychange', () => {
    if (document.hidden && state === 'playing') togglePause();
  });

  /* ---------- 启动 ---------- */
  if (window.ResizeObserver) {
    new ResizeObserver(resize).observe(canvas);
  }
  window.addEventListener('resize', resize);

  resize();
  reset();
  requestAnimationFrame(frame);
})();
