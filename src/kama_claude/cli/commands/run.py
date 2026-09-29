from __future__ import annotations

import asyncio
import json
import sys
import time

from pydantic import BaseModel

from kama_claude.core.bus.events import (
    LlmTokenEvent,
    RunFinishedEvent,
    RunStartedEvent,
    StepFinishedEvent,
    StepStartedEvent,
    ToolCallFailedEvent,
    ToolCallFinishedEvent,
    ToolCallStartedEvent,
)
from kama_claude.core.config import KamaConfig
from kama_claude.core.runner import AgentRunner


class StdoutPrinter:
    # 订阅事件总线并将运行进度格式化打印到终端
    def __init__(self) -> None:
        self._inline = False  #当前光标是否停在一行中间
        self._run_start: float = 0.0 

    def _ensure_newline(self) -> None:
        if self._inline: #如果真的停在一行中间
            print() #那就先换行
            self._inline = False

    # 判断事件种类打印对应命令，isinstance类型检查器
    async def handle(self, event: BaseModel) -> None:
        if isinstance(event, RunStartedEvent):
            self._run_start = time.monotonic() #记录起点时间
            print(f"[run] {event.run_id}")

        elif isinstance(event, StepStartedEvent):
            self._ensure_newline()#确认换行
            print(f"[step {event.step}] planning...")

        elif isinstance(event, LlmTokenEvent):
            print(event.token, end="", flush=True) #这是流式输出的关键，也就是不攒缓冲，一个一个往外打
            self._inline = True

        elif isinstance(event, ToolCallStartedEvent):#换行后打印工具名和参数，当需要调用工具时才会有这个
            self._ensure_newline()
            params_str = json.dumps(event.params, ensure_ascii=False)
            print(f"[tool] {event.tool_name} {params_str}")

        elif isinstance(event, ToolCallFinishedEvent):#打印上面的工具成功，打印耗时
            print(f"[tool] {event.tool_name} ✓  {event.elapsed_ms}ms")

        elif isinstance(event, ToolCallFailedEvent):#打印上面的工具失败，打印错误信息
            print(
                f"[tool] {event.tool_name} ✗  {event.error_message}",
                file=sys.stderr,
            )

        elif isinstance(event, StepFinishedEvent):#说明步数与该轮结束
            self._ensure_newline()
            print(f"[step {event.step}] done")

        elif isinstance(event, RunFinishedEvent):#打印运行状态，总部署，总耗时
            self._ensure_newline()
            elapsed = time.monotonic() - self._run_start
            print(f"[run] {event.status}  {event.steps} steps  {elapsed:.1f}s")


# 执行 kama run --goal "..." 命令，str来自--goal
def cmd_run(goal: str, config: KamaConfig) -> None:
    printer = StdoutPrinter() # 打印器对象，就在上面定义↑
    runner = AgentRunner(config, extra_handlers=[printer.handle]) #组装runner对象,打印器登记为额外的事件订阅器
    try:
        asyncio.run(runner.run(goal))# 协程异步调度run
    except KeyboardInterrupt: #其实是Ctrl+C的键盘输入
        sys.exit(130)
