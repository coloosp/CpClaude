from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ToolResult:
    content: str  #工具输出内容，只会输出字符串
    is_error: bool = False  # 如果结果出错则为True,下面是错误类型
    error_type: str | None = None  # "runtime_error" | "timeout" | "schema_error"


class BaseTool(ABC):
    name: str  #工具名 
    description: str #工具描述
    input_schema: dict[str, object] #输出参数格式定义

    # 执行工具调用，返回结果或错误
    @abstractmethod
    async def invoke(self, params: dict[str, object]) -> ToolResult: ...
