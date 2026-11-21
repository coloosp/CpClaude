from __future__ import annotations

import asyncio
import sys
from typing import Any

from kama_claude.core.config import KamaConfig
from kama_claude.core.transport.socket_client import IpcError, SocketClient


class ChatPrinter:
    # 初始化 chat 模式的流式输出状态
    def __init__(self) -> None:
        self._inline = False

    # 若当前 LLM token 尚未换行，则补一个换行
    def _ensure_newline(self) -> None:
        if self._inline:
            print()
            self._inline = False

    # 按事件类型打印 chat 输出和等待提示
    async def handle(self, event: dict[str, Any]) -> None:
        t = event.get("type", "")
        if t == "llm.token":
            print(event.get("token", ""), end="", flush=True)
            self._inline = True
        elif t == "tool.call_started":
            self._ensure_newline()
            print(f"[tool] {event.get('tool_name', '')}")
        elif t == "session.waiting_for_input":
            self._ensure_newline()
            print("[waiting for input]")
        elif t == "session.closed":
            self._ensure_newline()
            print("session closed.")


# 在线程池中读取 stdin，避免阻塞 socket event loop
# 如果直接调用input()，会阻塞 asyncio 的事件循环，导致无法处理来自守护进程的事件
async def _readline(prompt: str) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, input, prompt) #读取工作在线程池中，避免阻塞事件循环


# 异步核心：创建 chat session，循环读取用户输入并发送到 daemon
async def _chat_async(config: KamaConfig) -> int:
    client = SocketClient(config.host, config.port)
    try:
        await client.connect() #连接守护进程
    except (ConnectionRefusedError, OSError):
        print(f"error: core not running ({config.host}:{config.port})", file=sys.stderr)
        return 1

    printer = ChatPrinter() #会话打印器
    client.on_event(printer.handle) #注册事件处理器
    loop_task = asyncio.create_task(client.run_event_loop()) #读取循环，这是后台任务，很眼熟吧

    try:
        # 首先是订阅IPC事件广播
        await client.send_command(
            "event.subscribe",
            {
                "topics": ["session.*", "run.*", "tool.*", "llm.token"],
                "scope": "global",
            },
        )
        # 这是之前的 run 命令里没有的，创建一个 chat session
        created = await client.send_command("session.create", {"mode": "chat"})
        session_id = str(created["session_id"])
        print(f"[session: {session_id}]") #打印本次会话的 session_id，方便后续调试

        while True:
            try:
                line = await _readline("> ") #打印>提示符并读取后续用户输入
            except (EOFError, KeyboardInterrupt):
                break
            content = line.strip() #过滤空输入或者空格消息，如果是空消息就跳过
            if not content:
                continue
            # 新命令：发送消息到 daemon
            await client.send_command(
                "session.send_message",
                {"session_id": session_id, "content": content},
            )
        # 新命令：关闭会话
        await client.send_command("session.close", {"session_id": session_id})
    # 处理IPC错误，打印错误信息并返回1，在捕获异常之后会让e指向异常对象
    except IpcError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        loop_task.cancel()
        try:
            await loop_task #等待后台任务结束，避免未处理的异常
        except asyncio.CancelledError:
            pass
        await client.close()
    return 0


# 执行 kama chat 命令
def cmd_chat(config: KamaConfig) -> None:
    try:
        exit_code = asyncio.run(_chat_async(config))
    except KeyboardInterrupt:
        sys.exit(130)
    sys.exit(exit_code)
