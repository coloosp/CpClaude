from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from kama_claude.core.bus.events import StepFinishedEvent, StepStartedEvent
from kama_claude.core.context import ExecutionContext
from kama_claude.core.events.bus import EventBus
from kama_claude.core.llm.base import LLMProvider
from kama_claude.core.tools.invocation import invoke_tool
from kama_claude.core.tools.registry import ToolRegistry

# 时间戳工具，生成生成符合ISO 8601标准的日期时间字符串
def _now() -> str:
    return datetime.now(UTC).isoformat()


class AgentLoop:
    # 初始化循环所需的三个依赖：LLM provider、工具注册表、事件总线
    # 到这里就必须使用存在的三个属性了
    def __init__(
        self,
        provider: LLMProvider,
        registry: ToolRegistry,
        bus: EventBus,
    ) -> None:
        self._provider = provider #进行绑定
        self._registry = registry
        self._bus = bus

    # 驱动 plan→act→observe 循环直到上下文终止；CancelledError 向上传播
    async def run(self, context: ExecutionContext) -> None:
        while not context.is_done():
            context.step += 1 #步数迭代
            # 在步数开始前需要执行的广播
            await self._bus.publish(
                StepStartedEvent(run_id=context.run_id, step=context.step, ts=_now())
            )

            # [plan] call LLM — API errors terminate the run
            try:
                # 将上下文与工具清单交给provider,拿回一个LlmReponse
                response = await self._provider.chat(
                    messages=context.messages,
                    tool_schemas=self._registry.tool_schemas(),
                    bus=self._bus,
                    run_id=context.run_id,
                )
            except asyncio.CancelledError:
                context.mark_failed("cancelled")
                raise #裸raise,相当于向上抛asyncio.CancelledError的错误，会被runner.run接住，之后的流程你知道的
            except Exception:
                context.mark_failed("llm_error") #不是取消导致的错误应该直接被取消并且标记模型出错
                break

            # [observe] append assistant content blocks to context
            #组装blocks,目前我们的assistant只有两种消息类型
            blocks: list[dict[str, object]] = []
            if response.text:
                blocks.append({"type": "text", "text": response.text})
            for tc in response.tool_calls:
                blocks.append(
                    {"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.input}
                )
            context.add_assistant_message(blocks) #把组装好的消息放入消息历史

            # [act] execute each requested tool; errors become tool results so loop continues
            #根据大模型返回需要调用的工具，逐个执行
            if response.stop_reason == "tool_use":
                for tc in response.tool_calls:
                    #等待工具调用
                    result = await invoke_tool(
                        self._registry, tc, self._bus, context.run_id
                    )
                    #将多条工具结果合并到同一条user消息加入消息历史
                    context.add_tool_result(tc.id, result.content, is_error=result.is_error)

            # Termination check — end_turn wins over max_steps if both hit on same step
            #收到停止步数原因或者步数用尽都会停止
            if response.stop_reason == "end_turn":
                context.mark_success()
            elif context.step >= context.max_steps:
                context.mark_failed("exceeded_max_steps")
            
            #在步数结束时需要执行的广播
            await self._bus.publish(
                StepFinishedEvent(run_id=context.run_id, step=context.step, ts=_now())
            )
