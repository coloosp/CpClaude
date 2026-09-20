from __future__ import annotations

# 把sys.argv解析成结构化的args
import argparse
import sys

from kama_claude.cli.commands.ping import cmd_ping
from kama_claude.cli.commands.version import cmd_version
from kama_claude.core.config import get_config
from kama_claude.core.logging_setup import setup_logging


# CLI 主入口：解析命令行参数并分发到对应子命令
def main() -> None:
    # 创建命令行解析器，prog决定帮助和报错信息里显示的命令名，description是简介
    parser = argparse.ArgumentParser(prog="kama", description="KamaClaude CLI")
    # 登记规则，认识--version开关
    parser.add_argument("--version", action="store_true", help="Print version and exit")
    # 声明这个命令有子命令，决定将子命令存到args.command
    subparsers = parser.add_subparsers(dest="command")
    # 登记ping子命令
    subparsers.add_parser("ping", help="Ping the core daemon")
    # 读取sys.argv[1:],把结果装入Namespace对象
    # parse_args找到并加工数据返回给args
    args = parser.parse_args()

    if args.version:
        # 打印版本号
        cmd_version()
        return
    if args.command == "ping":
        # 解析运行配置，产出唯一的配置对象。按照顺序内置默认值，toml，.env，系统环境变量后者覆盖前者
        config = get_config()
        # 决定日志的写入位置，格式与级别
        setup_logging(config)
        # 向daemon发一次ping
        cmd_ping(config)
    else: 
        parser.print_help() # 参数合法但没给子命令的情况下
        sys.exit(1)
