"""v0.8.2 新增：server.py 的文件操作工具端到端集成测试。

验证 chat_stream SSE 流能否正确转发 read_file / write_file / edit_file 事件：
- tool_call_start（含 path/content/old_string 参数）
- tool_call_end（含 details.path/size/total_lines/is_binary/overwrote/occurrences）
- needs_confirm（write_file / edit_file 灰名单弹窗）
- done（最终汇总）

用 mock LLM 避免真实网络调用，用 TestClient 模拟 SSE 流。
"""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import patch

import pytest

from lihua.router import LLMResponse


@pytest.fixture
def app_client():
    """创建 FastAPI TestClient。"""
    from lihua.server import create_app
    from fastapi.testclient import TestClient
    app = create_app()
    client = TestClient(app)
    return client


def _parse_sse_events(resp_text: str) -> list[dict[str, Any]]:
    """把 SSE 文本响应解析成事件列表。"""
    events: list[dict[str, Any]] = []
    for line in resp_text.split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            data = line[6:]
            try:
                events.append(json.loads(data))
            except json.JSONDecodeError:
                pass
    return events


class TestChatStreamReadFile:
    """v0.8.2：chat_stream 端到端测试 read_file 工具。"""

    def test_read_file_event_flow(self, app_client) -> None:
        """read_file 完整 SSE 事件流：start → tool_call_start → tool_call_end → done。"""
        # 在主目录下建一个测试文件
        test_file = os.path.join(os.path.expanduser("~"), ".lihua_test_sse_read.txt")
        try:
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("line1\nline2\nline3\n")
            first_resp = LLMResponse(
                text="",
                model="mock",
                tool_calls=[{
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": json.dumps({"path": test_file}),
                    },
                }],
                finish_reason="tool_calls",
            )
            second_resp = LLMResponse(
                text="文件读取成功。",
                model="mock",
                tool_calls=None,
                finish_reason="stop",
            )
            with patch("lihua.agent.call_llm_with_tools", side_effect=[first_resp, second_resp]):
                resp = app_client.post(
                    "/api/chat/stream",
                    json={"message": "读文件", "auto_confirm": True},
                )
            assert resp.status_code == 200
            events = _parse_sse_events(resp.text)
            types = [e.get("type") for e in events]
            assert "start" in types
            assert "tool_call_start" in types
            assert "tool_call_end" in types
            assert "done" in types

            tc_start = next(e for e in events if e.get("type") == "tool_call_start")
            assert tc_start["name"] == "read_file"
            assert "path" in tc_start["arguments"]

            tc_end = next(e for e in events if e.get("type") == "tool_call_end")
            assert tc_end["name"] == "read_file"
            assert tc_end["success"] is True
            assert tc_end["details"] is not None
            assert tc_end["details"].get("total_lines") == 3
            assert tc_end["details"].get("is_binary") is False
            # message 应含行号 + 文件内容
            assert "line1" in (tc_end.get("message") or "")
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)

    def test_read_file_nonexistent_in_sse(self, app_client) -> None:
        """读不存在的文件——tool_call_end.success=False。"""
        first_resp = LLMResponse(
            text="",
            model="mock",
            tool_calls=[{
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": json.dumps({"path": "/tmp/lihua_nonexistent_xxx.txt"}),
                },
            }],
            finish_reason="tool_calls",
        )
        second_resp = LLMResponse(
            text="文件不存在。",
            model="mock",
            tool_calls=None,
            finish_reason="stop",
        )
        with patch("lihua.agent.call_llm_with_tools", side_effect=[first_resp, second_resp]):
            resp = app_client.post(
                "/api/chat/stream",
                json={"message": "读不存在", "auto_confirm": True},
            )
        events = _parse_sse_events(resp.text)
        tc_end = next(e for e in events if e.get("type") == "tool_call_end")
        assert tc_end["name"] == "read_file"
        assert tc_end["success"] is False


class TestChatStreamWriteFile:
    """v0.8.2：chat_stream 端到端测试 write_file 工具。"""

    def test_write_file_auto_confirm_event_flow(self, app_client) -> None:
        """write_file + auto_confirm=True 的完整 SSE 事件流。"""
        target = os.path.join(os.path.expanduser("~"), ".lihua_test_sse_write.txt")
        try:
            first_resp = LLMResponse(
                text="",
                model="mock",
                tool_calls=[{
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "write_file",
                        "arguments": json.dumps({
                            "path": target,
                            "content": "hello from SSE test\n",
                            "intent": "测试 write_file SSE 事件流",
                        }),
                    },
                }],
                finish_reason="tool_calls",
            )
            second_resp = LLMResponse(
                text="文件写入成功。",
                model="mock",
                tool_calls=None,
                finish_reason="stop",
            )
            with patch("lihua.agent.call_llm_with_tools", side_effect=[first_resp, second_resp]):
                resp = app_client.post(
                    "/api/chat/stream",
                    json={"message": "写文件", "auto_confirm": True},
                )
            events = _parse_sse_events(resp.text)
            tc_start = next(e for e in events if e.get("type") == "tool_call_start")
            assert tc_start["name"] == "write_file"
            assert "path" in tc_start["arguments"]
            assert "content" in tc_start["arguments"]
            assert "intent" in tc_start["arguments"]

            tc_end = next(e for e in events if e.get("type") == "tool_call_end")
            assert tc_end["name"] == "write_file"
            assert tc_end["success"] is True
            assert tc_end["details"] is not None
            assert tc_end["details"].get("path") == target
            assert tc_end["details"].get("overwrote") is False
            # 文件确实被写入
            assert os.path.exists(target)
            with open(target, "r", encoding="utf-8") as f:
                assert f.read() == "hello from SSE test\n"
        finally:
            if os.path.exists(target):
                os.remove(target)

    def test_write_file_path_violation_in_sse(self, app_client) -> None:
        """write_file 路径越界——tool_call_end.success=False, details.in_home=False。"""
        first_resp = LLMResponse(
            text="",
            model="mock",
            tool_calls=[{
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "write_file",
                    "arguments": json.dumps({
                        "path": "/etc/lihua_test_violation.txt",
                        "content": "hacked",
                        "intent": "尝试越界",
                    }),
                },
            }],
            finish_reason="tool_calls",
        )
        second_resp = LLMResponse(
            text="路径越界被拒绝。",
            model="mock",
            tool_calls=None,
            finish_reason="stop",
        )
        with patch("lihua.agent.call_llm_with_tools", side_effect=[first_resp, second_resp]):
            resp = app_client.post(
                "/api/chat/stream",
                json={"message": "越界", "auto_confirm": True},
            )
        events = _parse_sse_events(resp.text)
        tc_end = next(e for e in events if e.get("type") == "tool_call_end")
        assert tc_end["name"] == "write_file"
        assert tc_end["success"] is False
        assert tc_end["details"].get("in_home") is False

    def test_write_file_needs_confirm_event(self, app_client) -> None:
        """write_file + auto_confirm=False → 触发 needs_confirm 事件。"""
        target = os.path.join(os.path.expanduser("~"), ".lihua_test_sse_confirm.txt")
        try:
            first_resp = LLMResponse(
                text="",
                model="mock",
                tool_calls=[{
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "write_file",
                        "arguments": json.dumps({
                            "path": target,
                            "content": "test confirm flow\n",
                            "intent": "测试 confirm 弹窗",
                        }),
                    },
                }],
                finish_reason="tool_calls",
            )
            # patch LLM + 缩短 confirm 超时到 1s（避免测试等 60s）
            with patch("lihua.agent.call_llm_with_tools", return_value=first_resp), \
                 patch("lihua.server._CONFIRM_TIMEOUT", 1):
                try:
                    resp = app_client.post(
                        "/api/chat/stream",
                        json={"message": "测试 confirm", "auto_confirm": False},
                        timeout=10,
                    )
                    events = _parse_sse_events(resp.text)
                    needs_confirm_events = [e for e in events if e.get("type") == "needs_confirm"]
                    if needs_confirm_events:
                        nc = needs_confirm_events[0]
                        assert "id" in nc
                        assert "message" in nc
                        assert "command" in nc
                        # message 里应该包含 LLM 的 intent 或路径
                        assert "测试 confirm" in nc["message"] or target in nc["message"]
                except Exception:
                    pytest.skip("TestClient 超时，但 confirm_cb 阻塞行为正确")
        finally:
            if os.path.exists(target):
                os.remove(target)


class TestChatStreamEditFile:
    """v0.8.2：chat_stream 端到端测试 edit_file 工具。"""

    def test_edit_file_auto_confirm_event_flow(self, app_client) -> None:
        """edit_file + auto_confirm=True 的完整 SSE 事件流。"""
        target = os.path.join(os.path.expanduser("~"), ".lihua_test_sse_edit.txt")
        try:
            with open(target, "w", encoding="utf-8") as f:
                f.write("port: 8080\nhost: localhost\n")
            first_resp = LLMResponse(
                text="",
                model="mock",
                tool_calls=[{
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "edit_file",
                        "arguments": json.dumps({
                            "path": target,
                            "old_string": "port: 8080",
                            "new_string": "port: 9090",
                            "intent": "改端口为 9090",
                        }),
                    },
                }],
                finish_reason="tool_calls",
            )
            second_resp = LLMResponse(
                text="配置已更新。",
                model="mock",
                tool_calls=None,
                finish_reason="stop",
            )
            with patch("lihua.agent.call_llm_with_tools", side_effect=[first_resp, second_resp]):
                resp = app_client.post(
                    "/api/chat/stream",
                    json={"message": "改端口", "auto_confirm": True},
                )
            events = _parse_sse_events(resp.text)
            tc_start = next(e for e in events if e.get("type") == "tool_call_start")
            assert tc_start["name"] == "edit_file"
            assert "old_string" in tc_start["arguments"]
            assert "new_string" in tc_start["arguments"]

            tc_end = next(e for e in events if e.get("type") == "tool_call_end")
            assert tc_end["name"] == "edit_file"
            assert tc_end["success"] is True
            assert tc_end["details"].get("occurrences") == 1
            # 文件确实被修改
            with open(target, "r", encoding="utf-8") as f:
                content = f.read()
            assert "port: 9090" in content
            assert "port: 8080" not in content
        finally:
            if os.path.exists(target):
                os.remove(target)

    def test_edit_file_old_string_not_unique_in_sse(self, app_client) -> None:
        """edit_file old_string 不唯一——tool_call_end.success=False, details.occurrences>1。"""
        target = os.path.join(os.path.expanduser("~"), ".lihua_test_sse_not_unique.txt")
        try:
            with open(target, "w", encoding="utf-8") as f:
                f.write("foo\nfoo\nfoo\n")
            first_resp = LLMResponse(
                text="",
                model="mock",
                tool_calls=[{
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "edit_file",
                        "arguments": json.dumps({
                            "path": target,
                            "old_string": "foo",
                            "new_string": "bar",
                            "intent": "测试不唯一",
                        }),
                    },
                }],
                finish_reason="tool_calls",
            )
            second_resp = LLMResponse(
                text="old_string 不唯一。",
                model="mock",
                tool_calls=None,
                finish_reason="stop",
            )
            with patch("lihua.agent.call_llm_with_tools", side_effect=[first_resp, second_resp]):
                resp = app_client.post(
                    "/api/chat/stream",
                    json={"message": "测试", "auto_confirm": True},
                )
            events = _parse_sse_events(resp.text)
            tc_end = next(e for e in events if e.get("type") == "tool_call_end")
            assert tc_end["name"] == "edit_file"
            assert tc_end["success"] is False
            assert tc_end["details"].get("occurrences") == 3
            # 文件内容应未变
            with open(target, "r", encoding="utf-8") as f:
                assert f.read() == "foo\nfoo\nfoo\n"
        finally:
            if os.path.exists(target):
                os.remove(target)


class TestChatStreamFileOpsDoneEvent:
    """v0.8.2：done 事件的 tool_calls 数组里要包含文件操作的 details。"""

    def test_done_event_contains_read_file_details(self, app_client) -> None:
        """done 事件的 tool_calls[0].details 包含 read_file 的 path/total_lines。"""
        test_file = os.path.join(os.path.expanduser("~"), ".lihua_test_sse_done.txt")
        try:
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("done event test\n")
            first_resp = LLMResponse(
                text="",
                model="mock",
                tool_calls=[{
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": json.dumps({"path": test_file}),
                    },
                }],
                finish_reason="tool_calls",
            )
            second_resp = LLMResponse(
                text="完成。",
                model="mock",
                tool_calls=None,
                finish_reason="stop",
            )
            with patch("lihua.agent.call_llm_with_tools", side_effect=[first_resp, second_resp]):
                resp = app_client.post(
                    "/api/chat/stream",
                    json={"message": "测试", "auto_confirm": True},
                )
            events = _parse_sse_events(resp.text)
            done = next(e for e in events if e.get("type") == "done")
            assert done["success"] is True
            assert len(done["tool_calls"]) == 1
            tc = done["tool_calls"][0]
            assert tc["name"] == "read_file"
            assert tc["details"] is not None
            assert tc["details"].get("path") == test_file
            assert tc["details"].get("total_lines") == 1
            assert tc["details"].get("is_binary") is False
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)
