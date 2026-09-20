from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Discriminator

# 定义core.ping这个命令的参数格式
class PingCommand(BaseModel):
    type: Literal["core.ping"] = "core.ping" #阶段0锁死core.ping
    client: str

# 定义core.ping的返回值
class PongResult(BaseModel):
    server_version: str #daemon的版本号
    uptime_ms: int
    received_at: str  # ISO 8601


# 根据 type 字段决定命令类型的判别联合
# 声明命令是个联合类型，用type字段决定具体按哪个模型解析
Command = Annotated[
    PingCommand,
    Discriminator("type"), # 校验时先读type的值，再挑选对应模型，目前只有PingCommand
]
