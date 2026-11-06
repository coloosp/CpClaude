from __future__ import annotations

import argparse

from kama_claude.core.config import get_config
from kama_claude.tui.coloop_app import ColoopTuiApp


# coloop-tui 入口：解析历史回放参数后启动增强版终端界面
def main() -> None:
    parser = argparse.ArgumentParser(prog="coloop-tui", description="Coloop Agent Observer")
    parser.add_argument(
        "--replay",
        metavar="RUN_ID",
        help="Replay events from a past run on connect",
    )
    args = parser.parse_args()

    config = get_config()
    app = ColoopTuiApp(config.host, config.port, replay_run_id=args.replay)
    app.run()


if __name__ == "__main__":
    main()
