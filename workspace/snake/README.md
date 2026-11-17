# 贪吃蛇 · Snake

零依赖的网页版贪吃蛇，纯 HTML + CSS + Canvas（无构建、无 CDN、无网络请求）。

## 运行

直接双击 `index.html` 即可（不需要服务器）。
或起一个静态服务：

```bash
cd workspace/snake
python3 -m http.server 8000   # 打开 http://localhost:8000
```

## 玩法

| 操作 | 按键 |
| --- | --- |
| 移动 | `↑` `↓` `←` `→` 或 `W` `A` `S` `D` |
| 暂停 / 继续 | `空格` 或 `Enter` |
| 重新开始 | `R` |
| 手机 | 在棋盘上滑动，或用下方方向键 |

吃到果实 +1 分，蛇身变长，速度随等级提升（每 4 分升 1 级，步长从 145ms 递减到 68ms 下限）。
撞墙或咬到自己即结束，整个棋盘填满则通关。

## 特性

- Canvas 渲染 + 步进插值，移动平滑不卡顿；DPR 自适应，高分屏不模糊
- 转向输入队列（最多缓存 2 次按键），杜绝「一帧内连按导致反向自杀」
- 最高分 / 静音偏好存 `localStorage`，最高分实时落盘（中途关页面也不丢）
- 音效由 Web Audio 实时合成，无外部音频文件
- 触屏滑动 + 方向键 + 轻点暂停，移动端可用
- 切到后台自动暂停

## 目录

```
index.html        页面结构（棋盘、HUD、覆盖层、方向键）
style.css         深色霓虹主题、响应式布局
game.js           全部游戏逻辑（配置 / 流程 / 渲染 / 输入）
test/logic.test.js  Node 无头逻辑测试（DOM/Canvas 桩）
```

## 测试

```bash
node workspace/snake/test/logic.test.js
```

用极简 DOM/Canvas 桩加载 `game.js` 并手动推进 `requestAnimationFrame`，覆盖：
初始状态、开始/暂停、禁止掉头、撞墙判负、重开、自动寻路连续吃 6 个果实、
分数与长度/等级联动、最高分持久化、静音持久化、输入队列上限、滑动输入 + 3000 帧稳定性。

## 可调参数

在 `game.js` 顶部：

```js
const COLS = 20, ROWS = 20;   // 棋盘格数
const BASE_STEP = 145;        // 1 级每步毫秒（越小越快）
const MIN_STEP = 68;          // 速度上限
const STEP_DROP = 7;          // 每级缩短的毫秒
const LEVEL_EVERY = 4;        // 每 N 分升一级
const START_LEN = 3;          // 初始长度
```
