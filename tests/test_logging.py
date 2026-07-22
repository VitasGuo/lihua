"""日志系统测试（v0.7.7+）。

覆盖：
- setup_logging 初始化（多次调用幂等）
- get_logger 获取子 logger
- 各级别日志写入文件 + 环形缓冲区
- get_recent_logs 查询
- set_level 运行时调整级别
- JSON 格式正确性
- 日志文件轮转
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from lihua.logging_config import (
    DEFAULT_LEVEL,
    _RING_BUFFER,
    _SSE_SUBSCRIBERS,
    get_logger,
    get_recent_logs,
    log_file_path,
    set_level,
    setup_logging,
    subscribe_sse,
    unsubscribe_sse,
)


@pytest.fixture(autouse=True)
def _reset_logging():
    """每个测试前后重置日志系统状态，避免相互影响。"""
    # 测试前
    _RING_BUFFER.clear()
    _SSE_SUBSCRIBERS.clear()
    # 清理 lihua logger 的 handler 和标记
    root = logging.getLogger("lihua")
    old_handlers = list(root.handlers)
    old_level = root.level
    old_configured = getattr(root, "_lihua_configured", False)
    root.handlers = []
    if hasattr(root, "_lihua_configured"):
        del root._lihua_configured

    yield

    # 测试后
    _RING_BUFFER.clear()
    _SSE_SUBSCRIBERS.clear()
    root = logging.getLogger("lihua")
    root.handlers = old_handlers
    root.level = old_level
    if old_configured:
        root._lihua_configured = True  # type: ignore[attr-defined]


@pytest.fixture
def temp_log_dir(tmp_path: Path) -> Path:
    """临时日志目录，避免污染真实日志文件。"""
    with patch("lihua.logging_config.data_dir", return_value=tmp_path):
        yield tmp_path


class TestSetupLogging:
    """日志系统初始化。"""

    def test_setup_returns_logger(self, temp_log_dir: Path) -> None:
        logger = setup_logging("DEBUG", enable_stderr=False)
        assert logger.name == "lihua"
        assert logger.level == logging.DEBUG

    def test_setup_creates_log_file(self, temp_log_dir: Path) -> None:
        setup_logging("INFO", enable_stderr=False)
        log = get_logger(__name__)
        log.info("test message")
        # flush 所有 handler
        for h in logging.getLogger("lihua").handlers:
            h.flush()
        assert log_file_path().exists()

    def test_setup_idempotent(self, temp_log_dir: Path) -> None:
        """多次调用 setup_logging 不应重复添加 handler。"""
        setup_logging("INFO", enable_stderr=False)
        first_count = len(logging.getLogger("lihua").handlers)

        setup_logging("DEBUG", enable_stderr=False)
        second_count = len(logging.getLogger("lihua").handlers)

        assert second_count == first_count
        # 但级别应该更新
        assert logging.getLogger("lihua").level == logging.DEBUG

    def test_setup_with_invalid_level_defaults_to_info(
        self, temp_log_dir: Path
    ) -> None:
        """无效级别应回退到 INFO。"""
        setup_logging("INVALID_LEVEL", enable_stderr=False)
        assert logging.getLogger("lihua").level == logging.INFO


class TestGetLogger:
    """子 logger 获取。"""

    def test_get_logger_with_lihua_prefix(self) -> None:
        log = get_logger("lihua.agent")
        assert log.name == "lihua.agent"

    def test_get_logger_without_prefix_adds_lihua(self) -> None:
        log = get_logger("agent")
        assert log.name == "lihua.agent"

    def test_get_logger_with_dunder_name(self) -> None:
        log = get_logger("__main__")
        assert log.name == "lihua.__main__"


class TestLoggingOutputs:
    """日志输出：文件 + 环形缓冲区。"""

    def test_log_writes_to_ring_buffer(self, temp_log_dir: Path) -> None:
        setup_logging("DEBUG", enable_stderr=False)
        log = get_logger("test")
        log.info("hello world")

        entries = get_recent_logs(n=10)
        assert len(entries) >= 1
        last = entries[0]
        assert last["msg"] == "hello world"
        assert last["level"] == "INFO"
        assert last["logger"] == "lihua.test"

    def test_log_writes_to_file_as_json(self, temp_log_dir: Path) -> None:
        setup_logging("DEBUG", enable_stderr=False)
        log = get_logger("test")
        log.info("file test message")

        # flush
        for h in logging.getLogger("lihua").handlers:
            h.flush()

        content = log_file_path().read_text(encoding="utf-8").strip()
        lines = content.splitlines()
        last_line = lines[-1]
        entry = json.loads(last_line)
        assert entry["msg"] == "file test message"
        assert entry["level"] == "INFO"
        assert entry["logger"] == "lihua.test"
        assert "ts" in entry
        assert "module" in entry
        assert "line" in entry

    def test_extra_fields_preserved(self, temp_log_dir: Path) -> None:
        setup_logging("DEBUG", enable_stderr=False)
        log = get_logger("test")
        log.info("with extra", extra={"user_id": 42, "action": "login"})

        entries = get_recent_logs(n=10)
        last = entries[0]
        assert last["msg"] == "with extra"
        # extra 字段在环形缓冲区里不一定保留，检查文件
        for h in logging.getLogger("lihua").handlers:
            h.flush()
        content = log_file_path().read_text(encoding="utf-8").strip()
        entry = json.loads(content.splitlines()[-1])
        assert entry.get("extra", {}).get("user_id") == 42
        assert entry.get("extra", {}).get("action") == "login"

    def test_exception_info_logged(self, temp_log_dir: Path) -> None:
        setup_logging("DEBUG", enable_stderr=False)
        log = get_logger("test")
        try:
            raise ValueError("test error")
        except ValueError:
            log.exception("caught error")

        entries = get_recent_logs(n=10)
        last = entries[0]
        assert last["msg"] == "caught error"
        assert last["level"] == "ERROR"
        assert "ValueError" in last.get("exc", "")
        assert "test error" in last.get("exc", "")

    def test_all_levels_logged(self, temp_log_dir: Path) -> None:
        """DEBUG 及以上都应被记录（当 level=DEBUG 时）。"""
        setup_logging("DEBUG", enable_stderr=False)
        log = get_logger("test")
        log.debug("debug msg")
        log.info("info msg")
        log.warning("warn msg")
        log.error("error msg")
        log.critical("critical msg")

        entries = get_recent_logs(n=10)
        # 只看我们写的 5 条（排除 setup_logging 的初始化日志）
        our_entries = [e for e in entries if e["msg"].endswith("msg")]
        levels = [e["level"] for e in our_entries]
        assert "DEBUG" in levels
        assert "INFO" in levels
        assert "WARNING" in levels
        assert "ERROR" in levels
        assert "CRITICAL" in levels


class TestGetRecentLogs:
    """日志查询。"""

    def test_get_recent_logs_returns_n_entries(self, temp_log_dir: Path) -> None:
        setup_logging("DEBUG", enable_stderr=False)
        log = get_logger("test")
        for i in range(10):
            log.info(f"msg {i}")

        entries = get_recent_logs(n=5)
        assert len(entries) == 5
        # 最新在前
        assert entries[0]["msg"] == "msg 9"
        assert entries[-1]["msg"] == "msg 5"

    def test_get_recent_logs_filter_by_level(self, temp_log_dir: Path) -> None:
        setup_logging("DEBUG", enable_stderr=False)
        log = get_logger("test")
        log.debug("d")
        log.info("i")
        log.warning("w")
        log.error("e")

        entries = get_recent_logs(n=10, level="WARNING")
        levels = {e["level"] for e in entries}
        assert "DEBUG" not in levels
        assert "INFO" not in levels
        assert "WARNING" in levels
        assert "ERROR" in levels

    def test_get_recent_logs_invalid_level_returns_all(
        self, temp_log_dir: Path
    ) -> None:
        setup_logging("DEBUG", enable_stderr=False)
        log = get_logger("test")
        log.debug("d")
        log.info("i")

        entries = get_recent_logs(n=10, level="INVALID")
        assert len(entries) >= 2

    def test_get_recent_logs_empty_when_no_logs(self, temp_log_dir: Path) -> None:
        setup_logging("DEBUG", enable_stderr=False)
        # setup_logging 会写一条 "日志系统已初始化" 的 DEBUG 日志
        # 排除它后应为空
        entries = get_recent_logs(n=10)
        user_entries = [e for e in entries if "初始化" not in e["msg"]]
        assert user_entries == []


class TestSetLevel:
    """运行时调整级别。"""

    def test_set_level_filters_subsequent_logs(
        self, temp_log_dir: Path
    ) -> None:
        setup_logging("DEBUG", enable_stderr=False)
        log = get_logger("test")

        # 升到 WARNING，DEBUG 和 INFO 不应记录
        set_level("WARNING")
        log.debug("should not appear")
        log.info("should not appear")
        log.warning("should appear")

        entries = get_recent_logs(n=10)
        msgs = [e["msg"] for e in entries]
        assert "should appear" in msgs
        assert "should not appear" not in msgs

    def test_set_level_invalid_falls_back_to_info(
        self, temp_log_dir: Path
    ) -> None:
        setup_logging("DEBUG", enable_stderr=False)
        set_level("INVALID")
        assert logging.getLogger("lihua").level == logging.INFO


class TestSSESubscription:
    """SSE 订阅。"""

    def test_subscribe_returns_queue(self, temp_log_dir: Path) -> None:
        import queue

        setup_logging("DEBUG", enable_stderr=False)
        q = subscribe_sse()
        assert isinstance(q, queue.Queue)

        log = get_logger("test")
        log.info("sse test")
        # 应该能立即从队列拿到
        entry = q.get_nowait()
        assert entry["msg"] == "sse test"

        unsubscribe_sse(q)

    def test_unsubscribe_removes_from_list(self, temp_log_dir: Path) -> None:
        setup_logging("DEBUG", enable_stderr=False)
        q = subscribe_sse()
        assert q in _SSE_SUBSCRIBERS

        unsubscribe_sse(q)
        assert q not in _SSE_SUBSCRIBERS

    def test_multiple_subscribers_all_receive(
        self, temp_log_dir: Path
    ) -> None:
        setup_logging("DEBUG", enable_stderr=False)
        q1 = subscribe_sse()
        q2 = subscribe_sse()

        log = get_logger("test")
        log.info("broadcast")

        assert q1.get_nowait()["msg"] == "broadcast"
        assert q2.get_nowait()["msg"] == "broadcast"

        unsubscribe_sse(q1)
        unsubscribe_sse(q2)


class TestRingBufferLimit:
    """环形缓冲区上限。"""

    def test_ring_buffer_max_1000(self, temp_log_dir: Path) -> None:
        """超过 1000 条后应自动丢弃最旧的。"""
        from lihua.logging_config import _RING_BUFFER_MAX

        assert _RING_BUFFER_MAX == 1000

        setup_logging("DEBUG", enable_stderr=False)
        log = get_logger("test")
        # 写 1100 条
        for i in range(1100):
            log.info(f"msg {i}")

        # 环形缓冲区最多 1000 条
        from lihua.logging_config import _RING_BUFFER
        assert len(_RING_BUFFER) == 1000
        # 最旧的应该是 msg 100
        assert _RING_BUFFER[0]["msg"] == "msg 100"
        # 最新的应该是 msg 1099
        assert _RING_BUFFER[-1]["msg"] == "msg 1099"
