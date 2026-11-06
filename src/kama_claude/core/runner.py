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
        bus: EventBus | None = None,
        provider: LLMProvider | None = None,
        extra_handlers: list[EventHandler] | None = None,
        runs_dir: Path | None = None,
    ) -> None:
        self._config = config
        self._bus = bus
        self._provider = provider
        self._extra_handlers: list[EventHandler] = extra_handlers or []
        self._runs_dir = runs_dir or RUNS_DIR

    # 执行一次完整的 agent run：接线事件总线、驱动 AgentLoop、写 events.jsonl
    async def run(self, goal: str, *, run_id: str | None = None) -> None:
        run_id = run_id or new_run_id()
        run_path = self._runs_dir / run_id
        run_path.mkdir(parents=True, exist_ok=True)
        # 事件总线，没有就新建一个
        bus = self._bus if self._bus is not None else EventBus()
        # 额外需要订阅的handler，也注册到事件总线中
        for h in self._extra_handlers:
            bus.subscribe(h)

        # 上下文对象，包含 run_id、goal、最大步数等信息
        context = ExecutionContext(
            run_id=run_id,
            goal=goal,
            max_steps=self._config.agent.max_steps,
        )

        async with EventWriter(run_path / "events.jsonl") as writer:
            writer.subscribe(bus) # 将writer订阅到事件总线中，所有事件都会写入对应路径的 events.jsonl 文件
            await bus.publish(RunStartedEvent(run_id=run_id, goal=goal, ts=_now()))

            # 组装 LLMProvider、ToolRegistry、AgentLoop，执行 run
            provider = self._provider or AnthropicProvider(self._config.llm.default_model)
            registry = ToolRegistry()
            registry.register(ReadFileTool()) # 这个阶段只有 ReadFileTool 工具可用
            loop = AgentLoop(provider, registry, bus)

            cancelled = False
            try:
                await loop.run(context)
            except asyncio.CancelledError:
                cancelled = True
                if not context.is_done():
                    context.mark_failed("cancelled")

            # 发布RunFinishedEvent事件
            await bus.publish(
                RunFinishedEvent(
                    run_id=run_id,
                    status=context.status,
                    reason=context.reason,
                    steps=context.step,
                    ts=_now(),
                )
            )

        if cancelled:
            raise asyncio.CancelledError()
