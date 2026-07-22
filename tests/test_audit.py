"""审计日志测试（v0.7.10+）。

覆盖：
- parse_audit_line：JSON 行格式 + 旧文本格式 + 空行/无效行
- AuditEntry.to_dict() 序列化
- write_audit 写入 JSON 行
- /api/audit 基本查询 + success/safety/q 过滤
- /api/audit/export 下载
- /api/audit DELETE 清空 + 备份
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from lihua.config import audit_log_path
from lihua.executor import (
    AuditEntry,
    parse_audit_line,
    write_audit,
)


# ---------------------------------------------------------------------------
# parse_audit_line 单元测试
# ---------------------------------------------------------------------------


class TestParseAuditLine:
    """审计日志行解析。"""

    def test_parse_json_line(self) -> None:
        """JSON 行格式（v0.7.10+ 新格式）。"""
        line = json.dumps({
            "ts": "2026-07-19 17:36:52",
            "timestamp": 1721391412.0,
            "command": "apt install -y firefox",
            "safety_level": "grey",
            "success": True,
            "exit_code": 0,
            "duration": 5.23,
            "user_input": "装 firefox",
            "decision_reason": "needs user confirm",
        })
        result = parse_audit_line(line)
        assert result is not None
        assert result["command"] == "apt install -y firefox"
        assert result["safety_level"] == "grey"
        assert result["success"] is True
        assert result["exit_code"] == 0
        assert result["duration"] == 5.23
        assert result["user_input"] == "装 firefox"

    def test_parse_old_text_format_simple(self) -> None:
        """旧文本格式（v0.7.10 之前）—— 无 user_input/reason。"""
        line = "[2026-07-19 17:36:52] OK exit=0 safety=white duration=0.05s cmd='echo hello'"
        result = parse_audit_line(line)
        assert result is not None
        assert result["ts"] == "2026-07-19 17:36:52"
        assert result["success"] is True
        assert result["exit_code"] == 0
        assert result["safety_level"] == "white"
        assert result["duration"] == 0.05
        assert result["command"] == "echo hello"
        assert result.get("user_input") is None

    def test_parse_old_text_format_with_user_input(self) -> None:
        """旧文本格式带 user_input。"""
        line = (
            "[2026-07-19 17:36:52] FAIL exit=1 safety=grey duration=2.5s "
            "cmd='flatpak install com.qq.QQ' user_input='装QQ'"
        )
        result = parse_audit_line(line)
        assert result is not None
        assert result["success"] is False
        assert result["exit_code"] == 1
        assert result["safety_level"] == "grey"
        assert result["duration"] == 2.5
        assert result["command"] == "flatpak install com.qq.QQ"
        assert result["user_input"] == "装QQ"

    def test_parse_old_text_format_with_reason(self) -> None:
        """旧文本格式带 user_input 和 reason。"""
        line = (
            "[2026-07-19 17:36:52] OK exit=0 safety=white duration=0.1s "
            "cmd='ls -la' user_input='列出文件' reason='safe command'"
        )
        result = parse_audit_line(line)
        assert result is not None
        assert result["command"] == "ls -la"
        assert result["user_input"] == "列出文件"
        assert result["decision_reason"] == "safe command"

    def test_parse_empty_line(self) -> None:
        """空行返回 None。"""
        assert parse_audit_line("") is None
        assert parse_audit_line("   ") is None
        assert parse_audit_line("\n") is None

    def test_parse_invalid_line_returns_raw(self) -> None:
        """完全无法解析的行返回 {"raw": line}。"""
        line = "this is garbage not a log line"
        result = parse_audit_line(line)
        assert result is not None
        assert result.get("raw") == line

    def test_parse_invalid_json_falls_back(self) -> None:
        """以 { 开头但 JSON 解析失败 → 尝试旧文本格式 → 失败则 raw。"""
        line = "{invalid json"
        result = parse_audit_line(line)
        assert result is not None
        assert result.get("raw") == line


# ---------------------------------------------------------------------------
# AuditEntry.to_dict()
# ---------------------------------------------------------------------------


class TestAuditEntryToDict:
    """AuditEntry 序列化。"""

    def test_to_dict_contains_all_fields(self) -> None:
        entry = AuditEntry(
            timestamp=1721391412.0,
            command="apt install -y firefox",
            safety_level="grey",
            success=True,
            exit_code=0,
            duration=5.234,
            user_input="装 firefox",
            decision_reason="needs confirm",
        )
        d = entry.to_dict()
        assert d["command"] == "apt install -y firefox"
        assert d["safety_level"] == "grey"
        assert d["success"] is True
        assert d["exit_code"] == 0
        assert d["duration"] == 5.234  # 不四舍五入到 3 位？看实现
        assert d["user_input"] == "装 firefox"
        assert d["decision_reason"] == "needs confirm"
        assert d["ts"]  # 时间戳应被格式化
        assert d["timestamp"] == 1721391412.0

    def test_to_dict_optional_fields_none(self) -> None:
        """user_input 和 decision_reason 为 None 时仍能序列化。"""
        entry = AuditEntry(
            timestamp=1721391412.0,
            command="ls",
            safety_level="white",
            success=True,
            exit_code=0,
            duration=0.01,
        )
        d = entry.to_dict()
        assert d["user_input"] is None
        assert d["decision_reason"] is None


# ---------------------------------------------------------------------------
# write_audit 集成测试
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_audit_file(tmp_path: Path):
    """临时审计日志文件，避免污染真实文件。"""
    fake_path = tmp_path / "audit.log"
    with patch("lihua.executor.audit_log_path", return_value=fake_path):
        yield fake_path


class TestWriteAudit:
    """write_audit 写入。"""

    def test_write_creates_file(self, temp_audit_file: Path) -> None:
        entry = AuditEntry(
            timestamp=1721391412.0,
            command="echo test",
            safety_level="white",
            success=True,
            exit_code=0,
            duration=0.01,
        )
        write_audit(entry)
        assert temp_audit_file.exists()
        content = temp_audit_file.read_text(encoding="utf-8").strip()
        data = json.loads(content)
        assert data["command"] == "echo test"

    def test_write_appends_to_existing(self, temp_audit_file: Path) -> None:
        entry1 = AuditEntry(
            timestamp=1721391412.0,
            command="cmd1",
            safety_level="white",
            success=True,
            exit_code=0,
            duration=0.01,
        )
        entry2 = AuditEntry(
            timestamp=1721391413.0,
            command="cmd2",
            safety_level="grey",
            success=False,
            exit_code=1,
            duration=0.02,
        )
        write_audit(entry1)
        write_audit(entry2)
        lines = temp_audit_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        first = json.loads(lines[0])
        second = json.loads(lines[1])
        assert first["command"] == "cmd1"
        assert second["command"] == "cmd2"


# ---------------------------------------------------------------------------
# /api/audit 端点测试
# ---------------------------------------------------------------------------


def _make_audit_json(
    cmd: str,
    safety: str = "white",
    success: bool = True,
    exit_code: int = 0,
    duration: float = 0.1,
    user_input: str | None = None,
    ts: str = "2026-07-19 17:36:52",
) -> str:
    """构造一行 JSON 审计日志。"""
    return json.dumps({
        "ts": ts,
        "timestamp": 1721391412.0,
        "command": cmd,
        "safety_level": safety,
        "success": success,
        "exit_code": exit_code,
        "duration": duration,
        "user_input": user_input,
        "decision_reason": None,
    }, ensure_ascii=False)


@pytest.fixture
def app_client(tmp_path: Path):
    """创建 FastAPI TestClient + patch audit_log_path。"""
    fake_audit = tmp_path / "audit.log"
    # 写入几条测试数据
    fake_audit.write_text("\n".join([
        _make_audit_json("apt install -y firefox", "grey", True, 0, 5.2, "装 firefox"),
        _make_audit_json("rm -rf /tmp/cache", "white", True, 0, 0.05, "清理缓存"),
        _make_audit_json("flatpak install com.qq.QQ", "grey", False, 1, 2.5, "装QQ"),
        _make_audit_json("ls -la", "white", True, 0, 0.01),
    ]) + "\n", encoding="utf-8")

    # patch 多个位置的 audit_log_path
    with patch("lihua.config.audit_log_path", return_value=fake_audit), \
         patch("lihua.executor.audit_log_path", return_value=fake_audit), \
         patch("lihua.server.audit_log_path", return_value=fake_audit):
        from lihua.server import create_app
        from fastapi.testclient import TestClient
        app = create_app()
        client = TestClient(app)
        yield client, fake_audit


class TestAuditEndpoint:
    """/api/audit 端点。"""

    def test_audit_returns_all_entries(self, app_client) -> None:
        client, _ = app_client
        resp = client.get("/api/audit?n=100")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 4
        assert len(data["entries"]) == 4
        # 最新在前（reversed）
        assert data["entries"][0]["command"] == "ls -la"
        assert data["entries"][-1]["command"] == "apt install -y firefox"

    def test_audit_filter_by_success_true(self, app_client) -> None:
        client, _ = app_client
        resp = client.get("/api/audit?success=true")
        assert resp.status_code == 200
        data = resp.json()
        # 3 条成功：apt install firefox, rm -rf /tmp/cache, ls -la
        assert data["count"] == 3
        for e in data["entries"]:
            assert e["success"] is True

    def test_audit_filter_by_success_false(self, app_client) -> None:
        client, _ = app_client
        resp = client.get("/api/audit?success=false")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["entries"][0]["command"] == "flatpak install com.qq.QQ"
        assert data["entries"][0]["success"] is False

    def test_audit_filter_by_safety(self, app_client) -> None:
        client, _ = app_client
        resp = client.get("/api/audit?safety=grey")
        assert resp.status_code == 200
        data = resp.json()
        # 2 条 grey: apt install firefox, flatpak install com.qq.QQ
        assert data["count"] == 2
        for e in data["entries"]:
            assert e["safety_level"] == "grey"

    def test_audit_search_by_command(self, app_client) -> None:
        client, _ = app_client
        resp = client.get("/api/audit?q=flatpak")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert "flatpak" in data["entries"][0]["command"]

    def test_audit_search_by_user_input(self, app_client) -> None:
        """搜索关键词应匹配 user_input。"""
        client, _ = app_client
        resp = client.get("/api/audit?q=装QQ")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["entries"][0]["user_input"] == "装QQ"

    def test_audit_search_case_insensitive(self, app_client) -> None:
        client, _ = app_client
        resp = client.get("/api/audit?q=FLATPAK")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1

    def test_audit_combined_filters(self, app_client) -> None:
        """组合过滤：success=true + safety=grey。"""
        client, _ = app_client
        resp = client.get("/api/audit?success=true&safety=grey")
        assert resp.status_code == 200
        data = resp.json()
        # 只有 apt install firefox 符合
        assert data["count"] == 1
        assert data["entries"][0]["command"] == "apt install -y firefox"

    def test_audit_n_limit(self, app_client) -> None:
        """n 限制返回数量。"""
        client, _ = app_client
        resp = client.get("/api/audit?n=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["entries"]) == 2
        # count 是返回数量，不是总数
        assert data["count"] == 2

    def test_audit_returns_log_file_path(self, app_client) -> None:
        client, fake_path = app_client
        resp = client.get("/api/audit")
        assert resp.status_code == 200
        data = resp.json()
        assert data["log_file"] == str(fake_path)

    def test_audit_file_not_exists(self, tmp_path: Path) -> None:
        """审计日志文件不存在时返回空。"""
        fake_path = tmp_path / "nonexistent.log"
        with patch("lihua.config.audit_log_path", return_value=fake_path), \
             patch("lihua.executor.audit_log_path", return_value=fake_path), \
             patch("lihua.server.audit_log_path", return_value=fake_path):
            from lihua.server import create_app
            from fastapi.testclient import TestClient
            client = TestClient(create_app())
            resp = client.get("/api/audit")
            assert resp.status_code == 200
            data = resp.json()
            assert data["count"] == 0
            assert data["entries"] == []


# ---------------------------------------------------------------------------
# /api/audit/export 端点测试
# ---------------------------------------------------------------------------


class TestAuditExportEndpoint:
    """/api/audit/export 下载。"""

    def test_export_returns_file_content(self, app_client) -> None:
        client, _ = app_client
        resp = client.get("/api/audit/export")
        assert resp.status_code == 200
        # 内容应包含所有 4 行
        content = resp.text
        assert "apt install -y firefox" in content
        assert "flatpak install com.qq.QQ" in content
        # Content-Disposition 应是附件
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert "lihua-audit-" in resp.headers.get("content-disposition", "")

    def test_export_file_not_exists(self, tmp_path: Path) -> None:
        fake_path = tmp_path / "nonexistent.log"
        with patch("lihua.config.audit_log_path", return_value=fake_path), \
             patch("lihua.executor.audit_log_path", return_value=fake_path), \
             patch("lihua.server.audit_log_path", return_value=fake_path):
            from lihua.server import create_app
            from fastapi.testclient import TestClient
            client = TestClient(create_app())
            resp = client.get("/api/audit/export")
            assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /api/audit DELETE 端点测试
# ---------------------------------------------------------------------------


class TestAuditClearEndpoint:
    """DELETE /api/audit 清空。"""

    def test_clear_creates_backup_and_empties(self, app_client) -> None:
        client, fake_path = app_client
        # 原文件存在且有内容
        assert fake_path.exists()
        original_size = fake_path.stat().st_size
        assert original_size > 0

        resp = client.delete("/api/audit")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "备份" in data["message"]

        # 原文件应被清空（变成 0 字节）
        assert fake_path.exists()
        assert fake_path.stat().st_size == 0

        # 备份文件应存在且有内容
        backup = fake_path.with_suffix(".log.bak")
        assert backup.exists()
        assert backup.stat().st_size == original_size

    def test_clear_file_not_exists(self, tmp_path: Path) -> None:
        fake_path = tmp_path / "nonexistent.log"
        with patch("lihua.config.audit_log_path", return_value=fake_path), \
             patch("lihua.executor.audit_log_path", return_value=fake_path), \
             patch("lihua.server.audit_log_path", return_value=fake_path):
            from lihua.server import create_app
            from fastapi.testclient import TestClient
            client = TestClient(create_app())
            resp = client.delete("/api/audit")
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is True
            assert "不存在" in data["message"]

    def test_clear_twice_keeps_latest_backup(self, app_client) -> None:
        """二次清空：备份会被覆盖（只保留最新一份）。"""
        client, fake_path = app_client
        # 第一次清空
        resp1 = client.delete("/api/audit")
        assert resp1.status_code == 200
        backup = fake_path.with_suffix(".log.bak")
        first_backup_size = backup.stat().st_size

        # 重新写入一些数据
        fake_path.write_text(_make_audit_json("new cmd", "white", True) + "\n", encoding="utf-8")

        # 第二次清空
        resp2 = client.delete("/api/audit")
        assert resp2.status_code == 200
        # 备份应是第二次的数据（new cmd），不是第一次的
        backup_content = backup.read_text(encoding="utf-8")
        assert "new cmd" in backup_content
        # 第一次的内容应在第二次备份里被覆盖
        # 注意：first_backup_size 可能不等于第二次的 size
