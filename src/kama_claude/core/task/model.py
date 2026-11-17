from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

TaskStatus = Literal["pending", "in_progress", "completed"]


@dataclass
class Task:
    id: int #任务编号
    subject: str #任务标题
    description: str #详细要求
    status: TaskStatus #进度或状态，三种状态为等待，进行中，已完成
    blocked_by: list[int] #依赖或者阻塞的任务编号
    created_at: str #创建时间
    updated_at: str #最近更新时间

    # 序列化为 dict，字段名与 JSON 文件格式一致
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "subject": self.subject,
            "description": self.description,
            "status": self.status,
            "blocked_by": self.blocked_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    # 从 dict 构造 Task
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        return cls(
            id=int(data["id"]),
            subject=str(data["subject"]),
            description=str(data.get("description", "")),
            status=data.get("status", "pending"),
            blocked_by=[int(x) for x in data.get("blocked_by", [])],
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
        )
