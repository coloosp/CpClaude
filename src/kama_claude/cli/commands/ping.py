from __future__ import annotations

import asyncio
import json
import sys
import time

import kama_claude
from kama_claude.core.bus.commands import PongResult
from kama_claude.core.bus.envelope import JsonRpcError, JsonRpcSuccess
from kama_claude.core.config import KamaConfig


# 同步入口：运行 ping 协程，连接失败时打印错误并退出
def cmd_ping(config: KamaConfig) -> None:
    try:
        asyncio.run(_ping(config)) # 虽然是在运行协程，但其实这里是在同步阻塞，等待_ping完成
    except (ConnectionRefusedError, OSError):
        print(f"error: core not running ({config.host}:{config.port})", file=sys.stderr)
        sys.exit(1)


# 向 core 守护进程发送 ping 请求，打印 pong 响应及延迟
async def _ping(config: KamaConfig) -> None:
    t0 = time.monotonic() # 计时起点
    # 建立到daemon的TCP连接
    reader, writer = await asyncio.open_connection(config.host, config.port)
    
    # 拼出JSON-RPC请求体
    req = {
        "jsonrpc": "2.0", #协议版本
        "id": "cli-1", #请求标识
        "method": "core.ping", #对应调试方法
        "params": {"client": f"cli/{kama_claude.__version__}"}, #其他参数
    }
    writer.write((json.dumps(req) + "\n").encode()) #写出请求
    await writer.drain() #等待请求真正送出，等待数据时需要用await实现

    line = await asyncio.wait_for(reader.readline(), timeout=10.0)  #等待一行响应，最多10s
    latency_ms = int((time.monotonic() - t0) * 1000) #计算往返耗时

    writer.close() # 关闭连接
    await writer.wait_closed() #等待真的关闭了连接！

    raw = json.loads(line) # 检查line中返回的是否有error
    if "error" in raw:
        err = JsonRpcError.model_validate(raw)
        print(f"error: {err.error.code} {err.error.message}", file=sys.stderr)
        sys.exit(1)

    resp = JsonRpcSuccess.model_validate(raw) # 检查id，result这些字段是否存在
    result = PongResult.model_validate(resp.result) # 检查业务数据
    # 然后打印出来pong，显示版本号，更新时间与往返时间
    print(f"pong server={result.server_version} uptime={result.uptime_ms}ms latency={latency_ms}ms")
