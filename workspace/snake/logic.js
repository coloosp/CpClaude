// 纯逻辑：浏览器下挂到 window.SnakeLogic，Node 下可 module.exports（便于测试）
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SnakeLogic = api;
})(typeof self !== "undefined" ? self : this, function () {
  const DIRS = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };
  const OPP = { up: "down", down: "up", left: "right", right: "left" };

  function createState(cols, rows, rng) {
    rng = rng || Math.random;
    const s = {
      cols: cols, rows: rows, rng: rng,
      snake: [{ x: 3, y: 2 }, { x: 2, y: 2 }, { x: 1, y: 2 }], // 头在前
      dir: "right", queue: [], food: null, score: 0, over: false, eaten: false
    };
    s.food = spawnFood(s);
    return s;
  }

  function spawnFood(s) {
    const free = [];
    for (let y = 0; y < s.rows; y++)
      for (let x = 0; x < s.cols; x++)
        if (!s.snake.some(function (p) { return p.x === x && p.y === y; })) free.push({ x: x, y: y });
    if (!free.length) return null;
    return free[Math.floor(s.rng() * free.length) % free.length];
  }

  function turn(s, d) {
    if (!DIRS[d]) return;
    const last = s.queue.length ? s.queue[s.queue.length - 1] : s.dir;
    if (d === last || d === OPP[last]) return; // 忽略重复与反向
    if (s.queue.length < 2) s.queue.push(d);
  }

  function step(s) {
    s.eaten = false;
    if (s.over) return s;
    if (s.queue.length) s.dir = s.queue.shift();
    const d = DIRS[s.dir];
    const head = { x: s.snake[0].x + d[0], y: s.snake[0].y + d[1] };

    if (head.x < 0 || head.y < 0 || head.x >= s.cols || head.y >= s.rows) { s.over = true; return s; }
    const grow = !!s.food && head.x === s.food.x && head.y === s.food.y;
    // 不成长时尾巴会移开，不算撞自己
    const body = grow ? s.snake : s.snake.slice(0, -1);
    if (body.some(function (p) { return p.x === head.x && p.y === head.y; })) { s.over = true; return s; }

    s.snake.unshift(head);
    if (grow) { s.score++; s.eaten = true; s.food = spawnFood(s); if (!s.food) s.over = true; }
    else s.snake.pop();
    return s;
  }

  return { DIRS: DIRS, createState: createState, turn: turn, step: step };
});
