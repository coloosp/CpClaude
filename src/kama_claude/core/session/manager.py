from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from kama_claude.core.bus.envelope import HandlerError
from kama_claude.core.bus.events import (
    SessionClosedEvent,
    SessionCreatedEvent,
    SessionMessageReceivedEvent,
    SessionResumedEvent,
    SessionWaitingForInputEvent,
)
from kama_claude.core.events.bus import EventBus
from kama_claude.core.runs import new_run_id
from kama_claude.core.session.model import Session, SessionMode
from kama_claude.core.session.store import SessionStore

if TYPE_CHECKING:
    from kama_claude.core.runner import AgentRunner

SESSION_NOT_FOUND = -32010
SESSION_CLOSED = -32011
SESSION_BUSY = -32012


# 返回当前 UTC 时间的 ISO 8601 字符串
def _now() -> str:
    return datetime.now(UTC).isoformat()


class SessionManager:
    # 初始化会话管理器，接入文件存储、runner 工厂和事件总线
    def __init__(
        self,
        store: SessionStore,
        runner_factory: Callable[[], AgentRunner],
        bus: EventBus,
    ) -> None:
        self._store = store #会话文件存储器
        self._runner_factory = runner_factory #工厂函数，用于创建新的 AgentRunner 实例
        self._bus = bus
        self._sessions: dict[str, Session] = {} #内存中会话索引
        self._locks: dict[str, asyncio.Lock] = {} #每个会话的锁，避免并发操作

    # 创建新 session 并写入 meta.json
    async def create(self, mode: SessionMode, title: str = "") -> Session:
        sid = f"sess-{uuid.uuid4().hex[:12]}"
        ts = _now()
        session = Session(
            id=sid,
            mode=mode,
            status="active",
            title=title,
            created_at=ts,
            updated_at=ts,
            run_ids=[],
        )
        self._sessions[sid] = session #在会话索引中添加
        self._locks[sid] = asyncio.Lock() #为新会话创建一个锁
        self._store.write_meta(session) #将当前会话元数据写入 meta.json
        await self._bus.publish(SessionCreatedEvent(session_id=sid, mode=mode, ts=ts))
        return session

    # 处理用户消息，追加 thread 并启动一次 agent run
    async def send_message(self, sid: str, content: str, *, run_id: str | None = None) -> str:
        session = self._get_session(sid)
        lock = self._locks[sid]
        # 当前session正在处理一轮消息时，如果还没运行完就又来了新的消息，就会抛出 SESSION_BUSY 错误，避免并发冲突
        if lock.locked():
            print(f"session {sid} 很忙啊，请等它处理完再发新消息")
            raise HandlerError(SESSION_BUSY, "session busy")

        async with lock:
            #会话已经关闭，不能再发送消息了
            if session.status == "closed":
                raise HandlerError(SESSION_CLOSED, "session already closed")
            #会话处于等待用户输入状态，说明之前的 run 已经完成，可以继续处理新消息
            if session.status == "waiting_for_input":
                await self._bus.publish(SessionResumedEvent(session_id=sid, ts=_now()))
            #将之前发出的命令content作为user消息写入thread.jsonl
            self._store.append_message(sid, "user", content)
            #通知外部已收到消息
            await self._bus.publish(
                SessionMessageReceivedEvent(session_id=sid, content=content, ts=_now())
            )

            if not session.title:
                session.title = content[:40]
            # 确定并登记本轮执行ID
            run_id = run_id or new_run_id()
            session.run_ids.append(run_id)
            session.updated_at = _now()
            #保存本轮run的登记信息
            self._store.write_meta(session)
            # 创建runner，使用我们之前说的工厂函数
            runner = self._runner_factory()
            await runner.run_and_capture(
                content,
                run_id=run_id,
                session=session,
                store=self._store,
            )

            session.updated_at = _now()
            # 如果作为goal时只会执行一次对话，否则持续执行
            if session.mode == "one_shot":
                session.status = "closed"
                await self._bus.publish(SessionClosedEvent(session_id=sid, ts=session.updated_at))
            else:
                session.status = "waiting_for_input"
                await self._bus.publish(
                    SessionWaitingForInputEvent(
                        session_id=sid,
                        last_run_id=run_id,
                        ts=session.updated_at,
                    )
                )
            # 覆盖更新保存本轮结束后的会话状态
            self._store.write_meta(session)
            return run_id

    # 关闭指定 session 并更新 meta.json
    async def close(self, sid: str) -> None:
        session = self._get_session(sid)
        lock = self._locks[sid]
        if lock.locked():
            raise HandlerError(SESSION_BUSY, "session busy")
        async with lock:
            session.status = "closed"
            session.updated_at = _now()
            self._store.write_meta(session)
            await self._bus.publish(SessionClosedEvent(session_id=sid, ts=session.updated_at))

    # 读取指定 session 的完整 thread 历史
    async def get_history(self, sid: str) -> list[dict[str, Any]]:
        self._get_session(sid)
        return self._store.read_messages(sid)

    # 从内存索引取 session，不存在时抛 JSON-RPC 结构化错误
    def _get_session(self, sid: str) -> Session:
        session = self._sessions.get(sid)
        if session is None:
            raise HandlerError(SESSION_NOT_FOUND, "session not found")
        return session
