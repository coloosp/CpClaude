from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import Any

from kama_claude.core.config import KamaConfig
from kama_claude.core.transport.socket_client import IpcError, SocketClient


class StdoutPrinter:
    # 接收 dict 格式的事件并将运行进度格式化打印到终端
    def __init__(self) -> None:
        self._inline = False  # True while LLM tokens are mid-line
        self._run_start: float = 0.0

    # 若当前行有未换行的 token，补一个换行符
    def _ensure_newline(self) -> None:
        if self._inline:
            print()
            self._inline = False

    # 根据事件 type 字段分发并格式化打印到 stdout/stderr
    async def handle(self, event: dict[str, Any]) -> None:
        t = event.get("type", "")

        if t == "run.started":
            self._run_start = time.monotonic()
            print(f"[run] {event.get('run_id', '')}")

        elif t == "step.started":
            self._ensure_newline()
            print(f"[step {event.get('step')}] planning...")

        elif t == "llm.token":
            print(event.get("token", ""), end="", flush=True)
            self._inline = True

        elif t == "tool.call_started":
            self._ensure_newline()
            params_str = json.dumps(event.get("params", {}), ensure_ascii=False)
            print(f"[tool] {event.get('tool_name', '')} {params_str}")

        elif t == "tool.call_finished":
            print(f"[tool] {event.get('tool_name', '')} ✓  {event.get('elapsed_ms')}ms")

        elif t == "tool.call_failed":
            print(
                f"[tool] {event.get('tool_name', '')} ✗  {event.get('error_message', '')}",
                file=sys.stderr,
            )

        elif t == "step.finished":
            self._ensure_newline()
            print(f"[step {event.get('step')}] done")

        elif t == "run.finished":
            self._ensure_newline()
            elapsed = time.monotonic() - self._run_start
            print(f"[run] {event.get('status', '')}  {event.get('steps')} steps  {elapsed:.1f}s")


# 异步核心：连接 daemon，订阅事件，触发 run，等待 run.finished
# 接收目标文本和配置，返回一个整数作为进程退出码
async def _run_async(goal: str, config: KamaConfig) -> int:
    # 建立客户端，参数为127.0.0.1和7437，是我们的daemon监听端口
    client = SocketClient(config.host, config.port)
    try:
        await client.connect() # 这里才开始分配给客户端端口以及与daemon连接
    except (ConnectionRefusedError, OSError):
        print(f"error: core not running ({config.host}:{config.port})", file=sys.stderr)
        return 1

    printer = StdoutPrinter()
    finished = asyncio.Event() #完成信号
    exit_code = 0 #退出码

    # 内嵌回调，python就是自由，这个函数是为了解析服务端来的各种推送事件并且打印或者处理结束事件
    async def on_event(event: dict[str, Any]) -> None:
        # nonlocal意思是在嵌套函数里，声明某个变量不是本函数的局部变量，也不是全局变量，而是外层函数作用域里的变量
        # 表明这里的退出码是外层的退出码，并且允许直接修改它
        nonlocal exit_code
        await printer.handle(event) 
        # StdoutPrinter实例返回的run.finished是终局事件
        if event.get("type") == "run.finished":
            # 错误时返回1或者其他错误码，返回0表示 本次调用成功
            if event.get("status") != "success":
                exit_code = 1
            finished.set() #把事件设为已触发，唤醒所有正在 wait() 的协程

    client.on_event(on_event) #加入_event_handlers列表
    loop_task = asyncio.create_task(client.run_event_loop()) #启动一个持续读取消息的任务

    try:
        await client.send_command(
            "event.subscribe",
            {
                "topics": ["run.*", "step.*", "tool.*", "llm.token", "llm.usage"],
                "scope": "global",
            },
        )
        await client.send_command("agent.run", {"goal": goal})
    except IpcError as e:
        print(f"error: {e}", file=sys.stderr)
        loop_task.cancel()
        await client.close()
        return 1

    await finished.wait()

    loop_task.cancel() #关闭循环读取任务
    try:
        await loop_task
    except asyncio.CancelledError:
        pass

    await client.close()
    return exit_code


# 执行 kama run --goal "..." 命令
# 这里已经不是执行runner.run了，执行函数在上面
def cmd_run(goal: str, config: KamaConfig) -> None:
    try:
        # 如果让我们再次理解，这里的asyncio.run创建了事件循环，并且把其中的协程包装成主Task完成
        exit_code = asyncio.run(_run_async(goal, config)) 
    except KeyboardInterrupt:
        sys.exit(130)
    sys.exit(exit_code)
