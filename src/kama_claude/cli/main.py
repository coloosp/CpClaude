from __future__ import annotations

import argparse
import sys

from kama_claude.cli.commands.ping import cmd_ping
from kama_claude.cli.commands.run import cmd_run
from kama_claude.cli.commands.version import cmd_version
from kama_claude.core.config import get_config
from kama_claude.core.logging_setup import setup_logging


# CLI 主入口：解析命令行参数并分发到对应子命令
def main() -> None:
    # 与前面相同，构造命令行解析器与注册登记
    parser = argparse.ArgumentParser(prog="kama", description="KamaClaude CLI")
    parser.add_argument("--version", action="store_true", help="Print version and exit")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("ping", help="Ping the core daemon")

    #设置subparsers下的子命令解析器
    run_parser = subparsers.add_parser("run", help="Run an agent task")
    #新规则，总之设置了required=True
    run_parser.add_argument("--goal", required=True, help="Goal for the agent to accomplish")

    args = parser.parse_args()

    if args.version:
        cmd_version()
        return

    #提前配置好
    config = get_config() #负责按优先级加载配置
    setup_logging(config)

    if args.command == "ping":
        cmd_ping(config) #这个上次见过了
    elif args.command == "run":
        cmd_run(args.goal, config) #如果子命令里有run就会触发这个函数，填入args中的goal后面的字符串部分
    else:
        parser.print_help()
        sys.exit(1)
