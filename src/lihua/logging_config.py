"""Lihua 日志系统（v0.7.7+）。

设计目标：
  1. 结构化日志：JSON 格式写入文件，人类可读格式输出到 stderr
  2. 文件轮转：10MB × 5 份，避免无限增长
  3. 分级控制：DEBUG / INFO / WARNING / ERROR / CRITICAL
  4. 模块隔离：每个模块 `logger = logging.getLogger(__name__)`
  5. 运行时调整：通过 /api/logs/level 动态修改级别
  6. 历史查询：/api/logs?level=INFO&n=100 读最近 N 条
  7. 实时推送：/api/logs/stream SSE 流式推送

日志文件：
  - ~/.local/share/lihua/lihua.log（当前）
  - ~/.local/share/lihua/lihua.log.1（轮转后的旧日志）
  - ~/.local/share/lihua/lihua.log.2 ... .log.5

日志格式（文件，JSON 单行）：
  {"ts": "2026-07-19 12:34:56.789", "level": "INFO", "logger": "lihua.agent",
   "module": "agent", "line": 123, "msg": "用户输入「装QQ」", "extra": {...}}

日志格式（stderr，人类可读）：
  2026-07-19 12:34:56 INFO  [lihua.agent] 用户输入「装QQ」
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import data_dir

# === 常量 ===

LOGGER_NAME = "lihua"  # 根 logger 名
DEFAULT_LEVEL = "INFO"
DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10MB
DEFAULT_BACKUP_COUNT = 5  # 保留 5 份轮转日志

# 全局日志缓冲区（最近 N 条），供 /api/logs 查询
_RING_BUFFER: list[dict[str, Any]] = []
_RING_BUFFER_MAX = 1000

# SSE 订阅者列表（用于 /api/logs/stream 推送）
_SSE_SUBSCRIBERS: list[Any] = []


# === 自定义 Formatter ===


class _JsonFormatter(logging.Formatter):
    """JSON 单行格式，写入文件。"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "line": record.lineno,
            "msg": record.getMessage(),
        }
        # 异常信息
        if record.exc_info:
            log_entry["exc"] = self.formatException(record.exc_info)
        # 额外字段（extra=... 传入的）
        for k, v in record.__dict__.items():
            if k not in {
                "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
                "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
                "created", "msecs", "relativeCreated", "thread", "threadName",
                "processName", "process", "message", "taskName",
            }:
                try:
                    json.dumps(v)  # 测试可序列化
                    log_entry.setdefault("extra", {})[k] = v
                except (TypeError, ValueError):
                    log_entry.setdefault("extra", {})[k] = str(v)
        return json.dumps(log_entry, ensure_ascii=False)


class _HumanFormatter(logging.Formatter):
    """人类可读格式，输出到 stderr。"""

    _COLORS = {
        "DEBUG": "\033[36m",     # 青色
        "INFO": "\033[32m",      # 绿色
        "WARNING": "\033[33m",   # 黄色
        "ERROR": "\033[31m",     # 红色
        "CRITICAL": "\033[35m",  # 紫色
    }
    _RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        level = record.levelname
        color = self._COLORS.get(level, "")
        reset = self._RESET if color else ""
        msg = record.getMessage()
        # 模块名去掉 lihua. 前缀，更简洁
        logger_name = record.name
        if logger_name.startswith("lihua."):
            logger_name = logger_name[6:]
        line = f"{ts} {color}{level:<7}{reset} [{logger_name}] {msg}"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


# === 自定义 Handler ===


class _RingBufferHandler(logging.Handler):
    """把日志写入内存环形缓冲区，供 /api/logs 查询。"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry: dict[str, Any] = {
                "ts": datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                "level": record.levelname,
                "level_no": record.levelno,
                "logger": record.name,
                "module": record.module,
                "line": record.lineno,
                "msg": record.getMessage(),
            }
            if record.exc_info:
                entry["exc"] = self.format(record)
            _RING_BUFFER.append(entry)
            if len(_RING_BUFFER) > _RING_BUFFER_MAX:
                del _RING_BUFFER[: len(_RING_BUFFER) - _RING_BUFFER_MAX]
            # 推送给 SSE 订阅者
            for sub in list(_SSE_SUBSCRIBERS):
                try:
                    sub.put_nowait(entry)
                except Exception:
                    pass
        except Exception:
            self.handleError(record)


# === 公共 API ===


def log_file_path() -> Path:
    """日志文件路径：~/.local/share/lihua/lihua.log"""
    return data_dir() / "lihua.log"


def setup_logging(level: str = DEFAULT_LEVEL, *, enable_stderr: bool = True) -> logging.Logger:
    """初始化日志系统。必须在程序入口（cli.py / server.py）最先调用。

    Args:
        level: 日志级别字符串（DEBUG / INFO / WARNING / ERROR / CRITICAL）
        enable_stderr: 是否输出到 stderr（开发模式用，生产可关闭）

    Returns:
        根 logger 实例（lihua）
    """
    # 确保 data_dir 存在
    log_path = log_file_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger(LOGGER_NAME)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 避免重复添加 handler（多次调用 setup_logging 时）
    if getattr(root, "_lihua_configured", False):
        # 只更新级别
        root.setLevel(getattr(logging, level.upper(), logging.INFO))
        return root

    # 1. 文件 handler（JSON 格式 + 轮转）
    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=DEFAULT_MAX_BYTES,
        backupCount=DEFAULT_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(_JsonFormatter())
    file_handler.setLevel(logging.DEBUG)  # 文件记录所有级别（受 root level 控制）
    root.addHandler(file_handler)

    # 2. stderr handler（人类可读 + 彩色）
    if enable_stderr:
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setFormatter(_HumanFormatter())
        stderr_handler.setLevel(logging.DEBUG)
        root.addHandler(stderr_handler)

    # 3. 环形缓冲 handler（供 /api/logs 查询 + SSE 推送）
    ring_handler = _RingBufferHandler()
    ring_handler.setLevel(logging.DEBUG)
    root.addHandler(ring_handler)

    # 标记已配置
    root._lihua_configured = True  # type: ignore[attr-defined]

    root.debug(
        "日志系统已初始化",
        extra={"log_file": str(log_path), "level": level, "stderr": enable_stderr},
    )
    return root


def get_logger(name: str) -> logging.Logger:
    """获取子 logger。推荐用法：`logger = get_logger(__name__)`"""
    if not name.startswith(LOGGER_NAME):
        name = f"{LOGGER_NAME}.{name}"
    return logging.getLogger(name)


def set_level(level: str) -> None:
    """运行时调整日志级别（供 /api/logs/level 调用）。"""
    root = logging.getLogger(LOGGER_NAME)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def get_recent_logs(n: int = 100, level: str | None = None) -> list[dict[str, Any]]:
    """获取最近 N 条日志（供 /api/logs 调用）。

    Args:
        n: 返回条数（从最新往前数）
        level: 过滤级别（DEBUG / INFO / WARNING / ERROR / CRITICAL），None 表示全部
    """
    if not level:
        return list(reversed(_RING_BUFFER[-n:]))

    level_no = getattr(logging, level.upper(), 0)
    if level_no == 0:
        return list(reversed(_RING_BUFFER[-n:]))

    filtered = [e for e in _RING_BUFFER if e.get("level_no", 0) >= level_no]
    return list(reversed(filtered[-n:]))


def subscribe_sse() -> Any:
    """订阅 SSE 日志推送。返回一个 queue.Queue，调用方 get() 获取新日志。"""
    import queue

    q: queue.Queue = queue.Queue()
    _SSE_SUBSCRIBERS.append(q)
    return q


def unsubscribe_sse(q: Any) -> None:
    """取消 SSE 订阅。"""
    if q in _SSE_SUBSCRIBERS:
        _SSE_SUBSCRIBERS.remove(q)
