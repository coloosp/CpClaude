from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import cast

from kama_claude.core.bus.events import (
    ToolCallFailedEvent,
    ToolCallFinishedEvent,
    ToolCallStartedEvent,
)
from kama_claude.core.events.bus import EventBus
from kama_claude.core.llm.types import ToolCallBlock
from kama_claude.core.tools.base import ToolResult
from kama_claude.core.tools.registry import ToolRegistry

_DEFAULT_TIMEOUT: float = 10.0


def _now() -> str:
    return datetime.now(UTC).isoformat()


# 发布 ToolCallFailedEvent 并返回对应 ToolResult
# 工具调用失败时发布失败事件
async def _fail(
    bus: EventBus,
    run_id: str,
    tool_call: ToolCallBlock,
    error_type: str,
    error_message: str,
    elapsed_ms: int,
) -> ToolResult:
    await bus.publish(
        ToolCallFailedEvent(
            run_id=run_id,
            tool_use_id=tool_call.id,
            tool_name=tool_call.name,
            error_type=error_type,
            error_message=error_message,
            elapsed_ms=elapsed_ms,
            ts=_now(),
        )
    )
    return ToolResult(content=error_message, is_error=True, error_type=error_type)


# 校验参数、限时调用工具、发布进度事件，返回 ToolResult（不抛异常）
async def invoke_tool(
    registry: ToolRegistry,
    tool_call: ToolCallBlock,
    bus: EventBus,
    run_id: str,
    timeout: float = _DEFAULT_TIMEOUT, 
) -> ToolResult:
    t0 = time.monotonic() #当前时间戳
    
    #发布工具调用开始事件
    await bus.publish(
        ToolCallStartedEvent(
            run_id=run_id,
            tool_use_id=tool_call.id,
            tool_name=tool_call.name,
            params=dict(tool_call.input),
            ts=_now(),
        )
    )

    #我们python可以在函数里面嵌套定义函数，计算从开始到当前过了多少毫秒
    def elapsed() -> int:
        return int((time.monotonic() - t0) * 1000)

    #注册工具，如果不存在工具则返回失败
    tool = registry.get(tool_call.name)
    if tool is None:
        return await _fail(
            bus, run_id, tool_call,
            "runtime_error", f"unknown tool: {tool_call.name}", elapsed(),
        )

    #语义同required = tool.input_schema.get("required", [])，但是类型检查器会报错，所以使用cast
    required: list[str] = cast(list[str], tool.input_schema.get("required", []))
    #required是必填参数，这里是查找有哪些应该填但没有填上的
    missing = [p for p in required if p not in tool_call.input]
    if missing:
        return await _fail(
            bus, run_id, tool_call,
            "schema_error", f"missing required parameters: {', '.join(missing)}", elapsed(),
        )

    try:
        #执行工具，最多等待10s _DEFAULT_TIMEOUT
        result = await asyncio.wait_for(tool.invoke(dict(tool_call.input)), timeout=timeout)
        ms = elapsed() #计算时延
        #工具主动报错
        if result.is_error:
            return await _fail(
                bus, run_id, tool_call,
                result.error_type or "runtime_error", result.content, ms,
            )
        #成功则发布工具调用完成事件
        await bus.publish(
            ToolCallFinishedEvent(
                run_id=run_id,
                tool_use_id=tool_call.id,
                tool_name=tool_call.name,
                elapsed_ms=ms,
                ts=_now(),
            )
        )
        return result
    #超时
    except TimeoutError:
        return await _fail(
            bus, run_id, tool_call,
            "timeout", f"tool timed out after {timeout}s", elapsed(),
        )
    #异常
    except Exception as exc:
        return await _fail(
            bus, run_id, tool_call,
            "runtime_error", str(exc), elapsed(),
        )
