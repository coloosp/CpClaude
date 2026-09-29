from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionContext:
    run_id: str
    goal: str
    max_steps: int
    messages: list[dict[str, Any]] = field(default_factory=list) # 消息历史，是一个列表，列表元素是字典
    step: int = 0
    status: str = "running"  # "running" | "success" | "failed"三种状态
    reason: str | None = None

    # 初始化时将 goal 作为第一条用户消息写入消息历史
    #在dataclass中如果写上__post_init__这个函数就会被自动调用，很神奇吧
    def __post_init__(self) -> None:
        if not self.messages:
            self.messages.append({"role": "user", "content": self.goal}) #所以说列表元素是字典，所以这样加的

    # 将 LLM 响应的 content blocks 追加为 assistant 消息
    def add_assistant_message(self, content: list[Any]) -> None:
        self.messages.append({"role": "assistant", "content": content}) 

    # 将工具调用结果追加为 user 消息；同一步的多个结果共享同一条消息
    def add_tool_result(
        self, tool_use_id: str, content: str, is_error: bool = False
    ) -> None:
        #这只是加了标注的dict，这里message的格式要求和Anthropic API完全一致
        block: dict[str, Any] = {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": content,
        }
        if is_error: # is_error为真时才往这里添加这个字段
            block["is_error"] = True

        #三元表达式，取最后一个元素(python中-1表示倒着取)如果messages非空就取值否则是None
        last = self.messages[-1] if self.messages else None
        #如果最后一条消息是纯粹的user消息格式，直接追加进去，否则要新建一个字典元素追加
        if (
            last is not None
            and last["role"] == "user"
            and isinstance(last["content"], list)
            and last["content"]
            and all(b.get("type") == "tool_result" for b in last["content"])
        ):
            last["content"].append(block)
        else:
            self.messages.append({"role": "user", "content": [block]})

    # 返回 True 表示 loop 应停止（状态不再是 running）
    def is_done(self) -> bool:
        return self.status != "running"

    # 将 run 标记为成功
    def mark_success(self) -> None:
        self.status = "success"

    # 将 run 标记为失败并记录原因
    def mark_failed(self, reason: str) -> None:
        self.status = "failed"
        self.reason = reason
