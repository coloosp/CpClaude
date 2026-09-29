from __future__ import annotations

from collections.abc import Awaitable, Callable

from pydantic import BaseModel

# 定义了类型别名，规定只有收到事件BaseModel，返回可await的东西才能作为订阅者
type EventHandler = Callable[[BaseModel], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[EventHandler] = [] #准备一个空列表当做订阅者名册的容器

    # 注册一个事件处理函数
    def subscribe(self, handler: EventHandler) -> None:
        self._subscribers.append(handler) #apepend就是将handler追加到容器的队尾

    # 按注册顺序依次调用所有订阅者
    async def publish(self, event: BaseModel) -> None:
        for handler in self._subscribers:
            await handler(event)
