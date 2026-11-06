from __future__ import annotations

import asyncio
import datetime
import fnmatch
import json
import logging
import signal
import time
from typing import Any

import kama_claude
from kama_claude.core.bus.commands import (
    AgentRunCommand,
    AgentRunResult,
    EventSubscribeCommand,
    EventSubscribeResult,
    PongResult,
)
from kama_claude.core.bus.envelope import EventPushEnvelope
from kama_claude.core.config import KamaConfig, get_config
from kama_claude.core.events.bus import EventBus
from kama_claude.core.logging_setup import setup_logging
from kama_claude.core.runner import AgentRunner
from kama_claude.core.runs import events_file, new_run_id
from kama_claude.core.transport.ipc_broadcaster import IpcEventBroadcaster
from kama_claude.core.transport.socket_server import SocketServer, get_connection_writer

logger = logging.getLogger(__name__)


class CoreApp:
    def __init__(self) -> None:
        self._start_time = time.monotonic()
        self._bus = EventBus()
        self._broadcaster = IpcEventBroadcaster()
        self._bus.subscribe(self._broadcaster.handle) #为事件总线订阅一个处理器，将事件广播到所有订阅的客户端
        self._current_run_task: asyncio.Task[None] | None = None
        self._config: KamaConfig | None = None

    # 处理 core.ping 请求，返回服务版本、运行时长和接收时间
    async def _ping_handler(self, params: dict[str, Any]) -> PongResult:
        client = params.get("client", "unknown")
        logger.debug("ping from %s", client)
        return PongResult(
            server_version=kama_claude.__version__,
            uptime_ms=int((time.monotonic() - self._start_time) * 1000),
            received_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )

    # 启动一次 agent run：立即返回 run_id，后台 task 执行 runner.run()
    async def _agent_run_handler(self, params: dict[str, Any]) -> AgentRunResult:
        # 断言 self._config is not None，确保在调用此方法时，self._config 已经被初始化
        assert self._config is not None
        # 检验参数是否符合 AgentRunCommand 的要求
        cmd = AgentRunCommand.model_validate(params)

        # 有正在运行的任务尚未完成就不能再启动新的run。但如果上一个 run 已经完成了，也允许启动新的 run
        if self._current_run_task is not None and not self._current_run_task.done():
            raise RuntimeError("a run is already in progress")

        run_id = new_run_id() #获取任务id
        runner = AgentRunner(self._config, bus=self._bus) # 获取runner实例，传入配置和事件总线，别忘记我们之前学过这个
        # 创建新的异步任务执行runner.run()
        self._current_run_task = asyncio.create_task(
            runner.run(cmd.goal, run_id=run_id)
        )
        return AgentRunResult(run_id=run_id)

    # 注册客户端事件订阅，可选先回放 events.jsonl 历史再接收实时流
    async def _subscribe_handler(self, params: dict[str, Any]) -> EventSubscribeResult:
        cmd = EventSubscribeCommand.model_validate(params)
        writer = get_connection_writer()

        # 回放某一次指定run_id对应日志中事件
        replayed_count = 0
        if cmd.replay_from_run is not None:
            replayed_count = await self._replay_events(
                cmd.replay_from_run, writer, cmd.topics
            )

        sub_id = self._broadcaster.subscribe(writer, cmd.topics, cmd.scope)
        return EventSubscribeResult(subscription_id=sub_id, replayed_count=replayed_count)

    # 从 events.jsonl 向 writer 回放匹配 topic 的历史事件，返回已回放条数
    async def _replay_events(
        self,
        run_id: str,
        writer: asyncio.StreamWriter,
        topics: list[str],
    ) -> int:
        # 填入的run_id就是上面上传的cmd.replay_from_run
        path = events_file(run_id) # 找到对应run_id的event.json路径
        if not path.exists():
            return 0

        count = 0
        # 逐行解析事件
        for line in path.read_text().splitlines():
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_type: str = event.get("type", "") # 获取事件类型
            #如果不是用户要求的事件类型就跳过
            if not any(fnmatch.fnmatch(event_type, p) for p in topics):
                continue
            envelope = EventPushEnvelope(event=event)
            # 将对应历史事件包装成推送消息写入客户端
            writer.write(envelope.model_dump_json().encode() + b"\n")
            count += 1

        # 完成写入并返回数量，并进行流量控制
        if count:
            await writer.drain()
        return count 

    # 启动守护进程：加载配置、初始化日志、启动 TCP 服务器，并等待退出信号
    async def run(self) -> None:
        self._start_time = time.monotonic()
        self._config = get_config()
        setup_logging(self._config)

        #构造serve对象
        server = SocketServer(self._config.host, self._config.port, self._broadcaster) 
        #给serve注册三个命令，对于方法名->handler处理函数
        server.register("core.ping", self._ping_handler)
        server.register("agent.run", self._agent_run_handler)
        server.register("event.subscribe", self._subscribe_handler)

        addr = await server.start()
        logger.info("kama-core %s listening addr=%s", kama_claude.__version__, addr)
        logger.info("config: %s", self._config)

        loop = asyncio.get_running_loop()
        shutdown = asyncio.Event()
        loop.add_signal_handler(signal.SIGINT, shutdown.set)
        loop.add_signal_handler(signal.SIGTERM, shutdown.set)

        await shutdown.wait()

        logger.info("shutting down")
        await server.stop()


# 同步入口：启动 CoreApp 事件循环
def run() -> None:
    asyncio.run(CoreApp().run())
