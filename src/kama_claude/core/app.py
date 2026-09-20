from __future__ import annotations

import asyncio
import datetime
import logging
import signal
import time
from typing import Any

import kama_claude
from kama_claude.core.bus.commands import PongResult
from kama_claude.core.config import get_config
from kama_claude.core.logging_setup import setup_logging
from kama_claude.core.transport.socket_server import SocketServer

logger = logging.getLogger(__name__) # 日志记录器


class CoreApp:
    # 记录启动时间
    def __init__(self) -> None:
        self._start_time = time.monotonic()

    # 处理 core.ping 请求，返回服务版本、运行时长和接收时间
    async def _ping_handler(self, params: dict[str, Any]) -> PongResult:
        client = params.get("client", "unknown")
        logger.debug("ping from %s", client) # 打印debug日志
        # 返回pong的结果对象
        return PongResult(
            server_version=kama_claude.__version__,
            uptime_ms=int((time.monotonic() - self._start_time) * 1000),
            received_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )

    # 启动守护进程：加载配置、初始化日志、启动 TCP 服务器，并等待退出信号
    async def run(self) -> None:
        self._start_time = time.monotonic()
        config = get_config()
        setup_logging(config) # 按配置装好日志的输出日志和格式

        server = SocketServer(config.host, config.port) # TCP服务器对象
        server.register("core.ping", self._ping_handler) #注册绑定方法名与处理函数

        # 启动服务器并且返回地址
        addr = await server.start() 
        logger.info("kama-core %s listening addr=%s", kama_claude.__version__, addr)
        logger.info("config: %s", config)

        loop = asyncio.get_running_loop() # 拿到当前正在运行的时间循环对象
        shutdown = asyncio.Event() # 可以想象为一个开关事件
        # 把Ctrl+C绑定在打开开关上，表达意思是收到Ctrl+C时调用shutdown.set
        loop.add_signal_handler(signal.SIGINT, shutdown.set) 
        loop.add_signal_handler(signal.SIGTERM, shutdown.set) # kill也绑定在打开开关上

        await shutdown.wait() # 等待退出信号，也就是Ctrl+C或者kill

        logger.info("shutting down")
        await server.stop()


# 同步入口：启动 CoreApp 事件循环
def run() -> None:
    asyncio.run(CoreApp().run()) # 协程运行CoreApp实例中的run协程函数，这里确实构造了一个匿名实例来运行
