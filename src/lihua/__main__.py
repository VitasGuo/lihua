"""支持 `python -m lihua` 和 `lihua` 调用 CLI。

预处理 sys.argv：如果第一个参数不是已知子命令，就插入 "run"，
让 `lihua "装QQ"` 等价于 `lihua run "装QQ"`。
"""

from __future__ import annotations

import sys

# 已知的子命令名（cli.py 里定义的全部）
# v0.8.22: 新增 memory / self / skill-auto / plugin / prompt / analytics
_KNOWN_SUBCOMMANDS = {
    "run", "ask", "chat", "skills", "config", "doctor",
    "serve", "gui", "install", "uninstall-service", "history", "audit",
    "memory", "self", "skill-auto", "plugin", "prompt", "analytics",
    "--help", "-h", "--version", "-V",
    "help",
}


def _preprocess_argv() -> None:
    args = sys.argv[1:]
    if not args:
        return
    # 第一个参数是子命令
    first = args[0]
    if first in _KNOWN_SUBCOMMANDS or first.startswith("-"):
        return
    # 否则视为 message，插入 "run"
    sys.argv.insert(1, "run")


def main() -> None:
    _preprocess_argv()
    from lihua.cli import app
    app()


if __name__ == "__main__":
    main()
