from __future__ import annotations

from pathlib import Path

from kama_claude.core.tools.base import BaseTool, ToolResult

_MAX_BYTES = 512 * 1024  # 512 KB


class ReadFileTool(BaseTool):
    name = "read_file"
    # 工具描述：读取文件的文本内容。路径必须相对于当前工作目录。大于 512 KB 的文件将被截断
    description = (
        "Read the text content of a file. "
        "Path must be relative to the current working directory. "
        "Files larger than 512 KB are truncated."
    )
    # 工具输入参数格式定义：path是必填参数，表示文件路径
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path to the file (relative to current working directory).",
            }
        },
        "required": ["path"],
    }

    # 读取文件内容；超 512KB 截断；禁止 .. 路径遍历
    #ToolResult在base.py中定义，表示工具调用结果，包含content、is_error、error_type三个属性
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        path_str = str(params["path"]) #获取参数

        if ".." in Path(path_str).parts: #还有..路径遍历的情况，禁止。所以说要给出具体路径啊
            raise PermissionError(f"path traversal not allowed: {path_str}")

        path = Path(path_str) #转换成Path对象
        raw = path.read_bytes()  # 文件不存在会抛异常，交给上层处理
        truncated = len(raw) > _MAX_BYTES
        text = raw[:_MAX_BYTES].decode("utf-8", errors="replace") #解码为UTF-8字符串
        if truncated: #判断是否被截断
            text += "\n[truncated]" #这里截断就是告诉大模型内容不完整，避免大模型误以为内容完整

        return ToolResult(content=text)
