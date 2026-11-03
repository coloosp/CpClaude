from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from kama_claude.core.bus.envelope import JsonRpcRequest

type EventHandler = Callable[[dict[str, Any]], Awaitable[None]]

_MAX_LINE_BYTES = 1 * 1024 * 1024  # 1 MB per frame

# 将服务端返回的JSON-RPC错误包装成python异常
class IpcError(RuntimeError):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code


class SocketClient:
    #将地址与端口初始化，以及reader与write连接初始为None，在具体函数中实现
    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {} #请求编号->等待容器的请求表
        self._event_handlers: list[EventHandler] = []  #存放收到推送事件时要调用哪些函数的列表

    # 建立到 core 守护进程的 TCP 连接
    # reader和writer获取到socket
    async def connect(self) -> None:
        self._reader, self._writer = await asyncio.open_connection(
            self._host, self._port, limit=_MAX_LINE_BYTES
        )


    # 关闭 TCP 连接并等待底层 socket 释放
    async def close(self) -> None:
        # 在连接存在时关闭，否则什么都不做
        if self._writer is not None:
            self._writer.close()
            try:
                await asyncio.wait_for(self._writer.wait_closed(), timeout=1.0)
            except TimeoutError:
                pass

    # 注册服务器推送事件的回调，可多次调用以添加多个 handler
    # 所有客户端的推送事件都加入到这里
    def on_event(self, handler: EventHandler) -> None:
        self._event_handlers.append(handler)

    # 发送 JSON-RPC 命令并等待响应，成功返回 result dict，失败抛出 IpcError
    async def send_command(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        #保证连接存在
        if self._writer is None:
            raise RuntimeError("not connected — call connect() first")
        req_id = str(uuid.uuid4()) #请求id，uuid4的功能是生成一个基于随机数的、全球范围内几乎不可能重复的 128 位标识符
        request = JsonRpcRequest(id=req_id, method=method, params=params) #包装请求JSON-RPC
        fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future() #创建future容器，fut表示当前未完成的请求结果
        self._pending[req_id] = fut #登记到pending中
        self._writer.write(request.model_dump_json().encode() + b"\n") #写入缓存，request.model_dump_json().encode()表示把请求对象变成可写进socket的字节
        await self._writer.drain() #等待写入缓冲区压力降低到水位线
        return await fut

    # 持续读取服务器消息，分发 RPC 响应到 pending future 或事件到 event handler
    async def run_event_loop(self) -> None:
        if self._reader is None:
            raise RuntimeError("not connected — call connect() first")
        try:
            while True:
                try:
                    #逐行读取缓冲区信息
                    line = await self._reader.readline()
                except (ConnectionResetError, OSError):
                    break
                if not line:  #返回空字符串说明到达EOF
                    break
                await self._dispatch(line) #将所有消息交给派遣函数
        finally:
            #遍历pengding字典中的值，也就是fut
            #接收消息的循环已经退出，剩下的请求无法接收所以全部取消
            for fut in self._pending.values():
                if not fut.done():
                    fut.cancel()
            self._pending.clear()

    # 解析单行消息并路由到 pending future（RPC 响应）或 event handler（服务器推送）
    async def _dispatch(self, line: bytes) -> None:
        try:
            msg: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            return

        if "jsonrpc" in msg:
            req_id: str | None = msg.get("id") #从msg字典中取出id对应的值存入req_id如果不存在就获得None
            if req_id and req_id in self._pending:
                fut = self._pending.pop(req_id) #获取请求结果并在请求表中弹出
                if not fut.done():
                    if "error" in msg:
                        err = msg["error"]
                        fut.set_exception(
                            IpcError(err.get("code", -1), err.get("message", "unknown"))
                        )
                    else:
                        fut.set_result(msg.get("result") or {})
        elif msg.get("kind") == "event":
            event_data: dict[str, Any] = msg.get("event", {})
            for handler in self._event_handlers:
                await handler(event_data)
