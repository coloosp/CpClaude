from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class TraceRecord(BaseModel):
    ts: str #记录时间戳
    direction: Literal[
        "CLIENT→CORE",
        "CORE→CLIENT",
        "CORE",
        "CORE→LLM",
        "LLM→CORE",
    ]
    layer: Literal["ipc", "event", "llm"] #所属层，trace系统根据系统在不同位置观察信息区分层
    kind: str  # command / response / error / push / event / api_call / api_response
    run_id: str | None = None #关联的运行实例ID
    step: int | None = None #关联的运行步骤序号
    client_id: str | None = None
    data: dict[str, Any] #获取到的具体信息
