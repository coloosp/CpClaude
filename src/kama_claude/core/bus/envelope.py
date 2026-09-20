from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# 定义客户端发来的请求格式
class JsonRpcRequest(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0" # 2.0是行业标准JSON-RPC的版本
    id: str
    method: str
    params: dict[str, Any] = Field(default_factory=dict)

# 成功时发回客户端的响应就是这种格式
class JsonRpcSuccess(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: str
    result: Any

# 描述错误结构，当出现错误时，返回的标准结构，被1嵌套在下方的JsonRpcError
class JsonRpcErrorObject(BaseModel):
    code: int
    message: str
    data: Any = None

# 定义失败时发给客户端的响应，失败的响应与成功的响应最大的区别就是读不到id
class JsonRpcError(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | None = None #类型联合，可以是字符串或者None
    error: JsonRpcErrorObject


PARSE_ERROR = -32700      # 解析错误
INVALID_REQUEST = -32600  # 请求格式错误
METHOD_NOT_FOUND = -32601 # 方法不存在
INVALID_PARAMS = -32602   # 参数错误
INTERNAL_ERROR = -32603   # 服务器内部错误


# 构造一个 JSON-RPC 错误响应对象
def make_error(id: str | None, code: int, message: str, data: Any = None) -> JsonRpcError:
    return JsonRpcError(id=id, error=JsonRpcErrorObject(code=code, message=message, data=data))
