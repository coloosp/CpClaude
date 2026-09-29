from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from kama_claude.core.bus.events import RunFinishedEvent, RunStartedEvent
from kama_claude.core.config import KamaConfig
from kama_claude.core.context import ExecutionContext
from kama_claude.core.events.bus import EventBus, EventHandler
from kama_claude.core.events.writer import EventWriter
from kama_claude.core.llm.base import LLMProvider
from kama_claude.core.llm.provider import AnthropicProvider
from kama_claude.core.loop import AgentLoop
from kama_claude.core.runs import RUNS_DIR, new_run_id
from kama_claude.core.tools.builtin.read_file import ReadFileTool
from kama_claude.core.tools.registry import ToolRegistry


def _now() -> str:
    return datetime.now(UTC).isoformat()


class AgentRunner:
    # 组装所有运行时依赖，准备执行一次完整的 agent run
    def __init__(
        self,
        config: KamaConfig,
        *,
        provider: LLMProvider | None = None, #可以接受一开始为空
        extra_handlers: list[EventHandler] | None = None,
        runs_dir: Path | None = None,
    ) -> None:
        self._config = config
        self._provider = provider #AgentLoop唯一直接依赖的LLM接口，负责把messages发给模型与获取响应
        self._extra_handlers: list[EventHandler] = extra_handlers or [] #想要额外订阅的处理函数列表
        self._runs_dir = runs_dir or RUNS_DIR #本次run产物放置的位置

    # 执行一次完整的 agent run：生成 run_id、接线事件总线、驱动 AgentLoop
    async def run(self, goal: str) -> None:
        #本次run的身份与落盘位置
        run_id = new_run_id()
        run_path = self._runs_dir / run_id
        run_path.mkdir(parents=True, exist_ok=True) #即使父目录缺失也可以创建，这是幂等建目录的写法

        #通过EventBus创建私有的事件总线bus，从而订阅所有监听者
        bus = EventBus()
        for h in self._extra_handlers: #前面说的StdoutPrinter就是从这里订阅的
            bus.subscribe(h)

        #如果没创建接口就先做(因为一开始是None)
        provider = self._provider or AnthropicProvider(self._config.llm.default_model)
        registry = ToolRegistry() #创建工具注册表
        registry.register(ReadFileTool()) #并注册，因为我们这个阶段只有readfile一个工具
        loop = AgentLoop(provider, registry, bus) #循环控制器，输入以上三个参数

        #上下文对象，注册当前run的身份，把第一条信息注册为我们输入的goal，现在最大步数就是最新的
        context = ExecutionContext(
            run_id=run_id,
            goal=goal,
            max_steps=self._config.agent.max_steps,
        )
        
        #和你认识的文件操作很像，这其实是一种可以在结束时自动收尾的语法糖
        async with EventWriter(run_path / "events.jsonl") as writer:
            writer.subscribe(bus) #把writer的handle注册进总线，其实和bus.subscribe(writer.handle)是一样的意思
            await bus.publish(RunStartedEvent(run_id=run_id, goal=goal, ts=_now())) #发出第一条事件，标记run开始

            cancelled = False #给下面的逻辑进行判断的，这里说明
            try:
                await loop.run(context) # 交给loop让它把任务跑完，经典的协程对吧
            except asyncio.CancelledError: # 被请求协程终止，比如使用了Ctrl+C
                cancelled = True
                if not context.is_done(): #其实表示正在运行时，因为run被取消但是status还停留在running
                    context.mark_failed("cancelled") #把status=failed

            await bus.publish(  #等待最后一条事件，把最终状态、原因和步数写入
                RunFinishedEvent(
                    run_id=run_id,
                    status=context.status,
                    reason=context.reason,
                    steps=context.step,
                    ts=_now(),
                )
            )

        if cancelled: 
            raise asyncio.CancelledError() #抛出异常，会停止当前函数，将异常抛给上个文件run.py中的KeyboardInterrupt
