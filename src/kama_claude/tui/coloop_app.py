from __future__ import annotations

import asyncio
import json
from typing import Any

from rich.markup import escape
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Label, RichLog, Static

from kama_claude.core.transport.socket_client import IpcError, SocketClient


class ColoopTuiApp(App[None]):
    """Coloop 增强终端 UI：展示事件流、运行概览并支持历史回放。"""

    TITLE = "Coloop TUI"
    BINDINGS = [
        Binding("q", "quit", "退出"),
        Binding("c", "clear_log", "清空日志"),
        Binding("space", "toggle_follow", "切换跟随"),
    ]
    CSS = """
    Screen {
        layout: vertical;
        background: #0a101a;
        color: #d5dfed;
    }
    #masthead {
        height: 4;
        padding: 1 2 0 2;
    }
    #identity { width: 1fr; }
    #brand {
        height: 1;
        color: #83e5dc;
        text-style: bold;
    }
    #tagline { height: 1; color: #70839f; }
    #mode {
        width: auto;
        height: 1;
        color: #bca6ff;
        background: #202039;
        padding: 0 1;
    }
    #connection {
        height: 1;
        margin: 0 2 1 2;
    }
    #status {
        width: 1fr;
        height: 1;
        color: #83e5dc;
    }
    #endpoint { width: auto; color: #70839f; }
    #workspace { height: 1fr; padding: 0 2 1 2; }
    #log {
        width: 1fr;
        height: 1fr;
        border: round #29384e;
        border-title-color: #a8bbd3;
        border-subtitle-color: #70839f;
        background: #101a28;
        padding: 1 2;
        scrollbar-background: #101a28;
        scrollbar-color: #344a66;
    }
    #inspector {
        width: 30;
        height: 1fr;
        margin-left: 2;
        border: round #29384e;
        border-title-color: #a8bbd3;
        background: #101a28;
        padding: 1 2;
    }
    .section-label {
        height: 1;
        color: #70839f;
        text-style: bold;
    }
    #phase { height: 1; margin-bottom: 1; }
    .field-label { height: 1; color: #70839f; }
    #run-id { height: auto; margin-bottom: 1; }
    #goal { height: auto; max-height: 6; margin-bottom: 2; }
    #counters { height: auto; margin-bottom: 2; }
    #usage { height: auto; }
    Screen.compact #inspector { display: none; }
    Screen.compact #tagline { display: none; }
    Screen.compact #masthead { height: 3; }
    Footer {
        background: #141e2d;
        color: #9dafc7;
    }
    """

    # 初始化连接参数和 token 缓冲区
    def __init__(self, host: str, port: int, replay_run_id: str | None = None) -> None:
        super().__init__()
        self._host = host
        self._port = port
        self._replay_run_id = replay_run_id
        self._token_buf = ""
        self._active_run_id = replay_run_id or "—"
        self._goal = "在另一个终端提交任务，运行信息将在这里更新。"
        self._phase = "等待任务"
        self._phase_color = "#83e5dc"
        self._step = 0
        self._tool_calls = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._cache_tokens = 0
        self._following = True

    # 构建标题、连接状态、事件流、运行概览和快捷键栏
    def compose(self) -> ComposeResult:
        with Horizontal(id="masthead"):
            with Vertical(id="identity"):
                yield Static("◈  COLOOP  /  AGENT OBSERVER", id="brand")
                yield Static("让每一步执行，都清晰可见。", id="tagline")
            yield Label("REPLAY" if self._replay_run_id else "LIVE", id="mode")
        with Horizontal(id="connection"):
            yield Label("● 正在连接守护进程…", id="status")
            yield Label(f"{self._host}:{self._port}", id="endpoint", markup=False)
        with Horizontal(id="workspace"):
            yield RichLog(id="log", wrap=True, min_width=1, highlight=False, markup=True)
            with Vertical(id="inspector"):
                yield Static("CURRENT RUN", classes="section-label")
                yield Static(self._phase, id="phase")
                yield Static("运行编号", classes="field-label")
                yield Static(self._active_run_id, id="run-id", markup=False)
                yield Static("当前目标", classes="field-label")
                yield Static(self._goal, id="goal", markup=False)
                yield Static("ACTIVITY", classes="section-label")
                yield Static("", id="counters")
                yield Static("TOKEN USAGE", classes="section-label")
                yield Static("", id="usage")
        yield Footer()

    # 挂载后启动 socket 连接 worker
    # 可以理解为asyncio.create_task()，在后台运行 socket 连接和事件处理循环
    def on_mount(self) -> None:
        log = self.query_one("#log", RichLog)
        log.border_title = "事件流"
        log.border_subtitle = "自动跟随"
        self.query_one("#inspector", Vertical).border_title = "运行概览"
        self.screen.set_class(self.size.width < 100, "compact")
        self.call_after_refresh(self._refresh_inspector)
        self._write_welcome(log)
        self.run_worker(self._socket_loop(), exclusive=True, name="socket")

    # 在窄终端隐藏侧栏，将可用宽度留给事件正文
    def on_resize(self, event: events.Resize) -> None:
        self.screen.set_class(event.size.width < 100, "compact")

    # 在没有事件时展示简短的使用提示
    def _write_welcome(self, log: RichLog) -> None:
        log.write("[bold #83e5dc]◈  观察已就绪[/]")
        if self._replay_run_id:
            log.write("[#70839f]正在等待连接，随后回放指定运行的历史事件。[/]")
        else:
            log.write("[#70839f]等待新的运行事件。在另一个终端提交任务即可开始。[/]")
        log.write("")

    # 清空可见日志，保留连接和当前运行状态
    def action_clear_log(self) -> None:
        log = self.query_one("#log", RichLog)
        log.clear()
        self._write_welcome(log)

    # 切换日志自动滚动，方便查看历史内容
    def action_toggle_follow(self) -> None:
        self._following = not self._following
        log = self.query_one("#log", RichLog)
        log.auto_scroll = self._following
        log.border_subtitle = "自动跟随" if self._following else "浏览历史 · 空格恢复跟随"
        if self._following:
            log.scroll_end(animate=False)

    # 将当前运行状态和累计用量同步到概览组件
    def _refresh_inspector(self) -> None:
        if not self.is_running:
            return
        self.query_one("#phase", Static).update(f"[bold {self._phase_color}]● {self._phase}[/]")
        self.query_one("#run-id", Static).update(self._active_run_id)
        self.query_one("#goal", Static).update(self._goal)
        self.query_one("#counters", Static).update(
            f"步骤   [bold #d5dfed]{self._step}[/]\n工具   [bold #d5dfed]{self._tool_calls}[/]"
        )
        self.query_one("#usage", Static).update(
            f"输入   [#d5dfed]{self._input_tokens:,}[/]\n"
            f"输出   [#d5dfed]{self._output_tokens:,}[/]\n"
            f"缓存   [#83e5dc]{self._cache_tokens:,}[/]"
        )

    # 从事件更新运行概览，中途接入时也能识别当前运行
    def _track_event(self, event: dict[str, Any]) -> None:
        t = event.get("type", "")
        if t not in {
            "run.started",
            "run.finished",
            "step.started",
            "step.finished",
            "tool.call_started",
            "tool.call_finished",
            "tool.call_failed",
            "llm.token",
            "llm.usage",
        }:
            return
        run_id = event.get("run_id")
        new_run = t == "run.started" or (run_id and run_id != self._active_run_id)
        if new_run:
            self._active_run_id = str(run_id or "—")
            self._goal = str(event.get("goal") or "中途接入，正在观察后续事件。")
            self._step = self._tool_calls = 0
            self._input_tokens = self._output_tokens = self._cache_tokens = 0

        if t == "run.started":
            self._phase, self._phase_color = "运行已启动", "#83e5dc"
        elif t == "step.started":
            self._step = int(event.get("step", 0))
            self._phase, self._phase_color = "规划下一步", "#7fc8ff"
        elif t == "llm.token":
            if self._phase == "生成回复" and not new_run:
                return
            self._phase, self._phase_color = "生成回复", "#bca6ff"
        elif t == "tool.call_started":
            self._tool_calls += 1
            self._phase, self._phase_color = "执行工具", "#f0c779"
        elif t == "tool.call_failed":
            self._phase, self._phase_color = "工具返回错误", "#f09b9b"
        elif t == "step.finished":
            self._phase, self._phase_color = "步骤完成", "#7fc8ff"
        elif t == "run.finished":
            self._step = int(event.get("steps", self._step))
            success = event.get("status") == "success"
            self._phase = "运行完成" if success else "运行未完成"
            self._phase_color = "#83e5dc" if success else "#f09b9b"
        elif t == "llm.usage":
            self._input_tokens += int(event.get("input_tokens", 0))
            self._output_tokens += int(event.get("output_tokens", 0))
            self._cache_tokens += int(event.get("cache_read_input_tokens", 0))
        self._refresh_inspector()

    # 管理 SocketClient 生命周期：连接、订阅、接收事件、断线重连
    async def _socket_loop(self) -> None:
        # 取得之前挂载的日志框与状态栏组件
        log = self.query_one("#log", RichLog)
        status = self.query_one("#status", Label)

        while True:
            # 创建客户端 SocketClient 并尝试连接到 daemon
            client = SocketClient(self._host, self._port)
            try:
                await client.connect()
            except (ConnectionRefusedError, OSError):
                # 连接失败，更新状态栏并等待 2 秒后重试
                status.update("[#f0c779]● 尚未连接 · 2 秒后重试[/]")
                await asyncio.sleep(2)
                continue

            status.update("[#83e5dc]● 已连接 · 正在订阅事件[/]")
            # 建立时间循环任务，这是客户端的循环监听TCP连接，接收到事件后会调用on_event
            loop_task = asyncio.create_task(client.run_event_loop())

            # 将客户端收到的事件交给 TUI 日志处理器
            async def on_event(event: dict[str, Any]) -> None:
                self._handle_event(event, log)

            # 这里的on_event在上面，而不是在SocketClient中
            # 收到事件后调用 _handle_event，将内容写入日志框
            client.on_event(on_event)

            try:
                params: dict[str, Any] = {
                    "topics": [
                        "run.*",
                        "step.*",
                        "tool.*",
                        "llm.token",
                        "llm.usage",
                        "log.*",
                    ],
                    "scope": "global",
                }
                if self._replay_run_id is not None:
                    params["replay_from_run"] = self._replay_run_id
                # 只会注册事件订阅，而没有agent.run的命令，agent.run的命令是通过cli端启动的
                await client.send_command("event.subscribe", params)
                status.update("[#83e5dc]● 已连接 · 正在监听运行事件[/]")
                await loop_task
            except IpcError as e:
                status.update(f"[#f09b9b]● 订阅失败 · {escape(str(e))}[/]")
            finally:
                if not loop_task.done():
                    loop_task.cancel()
                self._flush_tokens(log)
                await client.close()

            status.update("[#f0c779]● 连接已断开 · 2 秒后重试[/]")
            await asyncio.sleep(2)

    # 将 llm.token 累积缓冲区写入日志并清空
    def _flush_tokens(self, log: RichLog) -> None:
        if self._token_buf:
            log.write(f"[#d5dfed]{escape(self._token_buf)}[/]")
            self._token_buf = ""

    # 根据事件 type 字段格式化并写入 RichLog，llm.token 累积后整体写入
    # 根据不同事件执行对应操作，我就懒得看了
    def _handle_event(self, event: dict[str, Any], log: RichLog) -> None:
        t = event.get("type", "")
        self._track_event(event)

        if t == "llm.token":
            self._token_buf += event.get("token", "")
            # 连续文本只进入缓冲，下一条非 token 事件触发整体显示
            return

        self._flush_tokens(log)

        if t == "run.started":
            log.write("")
            log.write(f"[bold #83e5dc]╭ RUN[/]  [#70839f]{escape(str(event.get('run_id', '')))}[/]")
            log.write(f"[bold]{escape(str(event.get('goal', '')))}[/]")
        elif t == "step.started":
            log.write("")
            log.write(f"[bold #7fc8ff]◆ STEP {event.get('step')}[/]  [dim]规划下一步[/]")
        elif t == "tool.call_started":
            params_str = json.dumps(event.get("params", {}), ensure_ascii=False)
            log.write(f"[#f0c779]↳ TOOL[/]  [bold]{escape(str(event.get('tool_name', '')))}[/]")
            log.write(f"[dim]  {escape(params_str)}[/]")
        elif t == "tool.call_finished":
            log.write(
                f"[green]  ✓ {escape(str(event.get('tool_name', '')))}[/]  "
                f"[dim]{event.get('elapsed_ms')} ms[/]"
            )
        elif t == "tool.call_failed":
            log.write(
                f"[red]  ✗ {escape(str(event.get('tool_name', '')))}[/]  "
                f"{escape(str(event.get('error_message', '')))}"
            )
        elif t == "step.finished":
            log.write(f"[dim]  └ step {event.get('step')} completed[/]")
        elif t == "run.finished":
            s = event.get("status", "")
            color = "green" if s == "success" else "red"
            log.write("")
            log.write(
                f"[bold {color}]■ {escape(str(s)).upper()}[/]  [dim]{event.get('steps')} steps[/]"
            )
            if event.get("reason"):
                log.write(f"[dim]{escape(str(event['reason']))}[/]")
        elif t == "llm.usage":
            log.write(
                f"[dim]  tokens · in {event.get('input_tokens')} "
                f"/ out {event.get('output_tokens')} "
                f"/ cache {event.get('cache_read_input_tokens')}[/]"
            )
        elif t == "log.line":
            level = event.get("level", "INFO")
            log.write(
                f"[dim]{escape(str(level))} · {escape(str(event.get('source', '')))}[/]  "
                f"{escape(str(event.get('message', '')))}"
            )
