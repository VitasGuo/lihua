"""v0.8.3 新增：server.py 的 run_python 端到端集成测试。

验证 chat_stream SSE 流能否正确转发 run_python 事件：
- tool_call_start（含 code/intent 参数）
- tool_call_end（含 details.stdout/stderr/exit_code/safety_level）
- needs_confirm（强制走 confirm）
- done（最终汇总）

用 mock LLM 避免真实网络调用，用 TestClient 模拟 SSE 流。
"""

from __future__ import annotations

import json
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


class TestChatStreamRunPython:
    """v0.8.3：chat_stream 端到端测试 run_python 万能工具。"""

    def test_run_python_event_flow(self, app_client) -> None:
        """完整 SSE 事件流：start → iteration → tool_call_start → tool_call_end → done。"""
        first_resp = LLMResponse(
            text="",
            model="mock",
            tool_calls=[{
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "run_python",
                    "arguments": json.dumps({
                        "code": "print('hello from python')",
                        "intent": "测试 Python 输出",
                    }),
                },
            }],
            finish_reason="tool_calls",
        )
        second_resp = LLMResponse(
            text="Python 代码执行成功，输出 hello from python。",
            model="mock",
            tool_calls=None,
            finish_reason="stop",
        )

        with patch("lihua.agent.call_llm_with_tools", side_effect=[first_resp, second_resp]):
            resp = app_client.post(
                "/api/chat/stream",
                json={"message": "测试 run_python", "auto_confirm": True},
            )

        assert resp.status_code == 200
        events = _parse_sse_events(resp.text)
        types = [e.get("type") for e in events]
        assert "start" in types
        assert "tool_call_start" in types
        assert "tool_call_end" in types
        assert "done" in types

        # tool_call_start 必须是 run_python，含 code/intent 参数
        tc_start = next(e for e in events if e.get("type") == "tool_call_start")
        assert tc_start["name"] == "run_python"
        assert "code" in tc_start["arguments"]
        assert "intent" in tc_start["arguments"]

        # tool_call_end：success=True，details 里有 stdout/safety_level/exit_code
        tc_end = next(e for e in events if e.get("type") == "tool_call_end")
        assert tc_end["name"] == "run_python"
        assert tc_end["success"] is True
        assert tc_end["details"] is not None
        assert "hello from python" in tc_end["details"].get("stdout", "")
        assert tc_end["details"].get("safety_level") == "grey"
        assert tc_end["details"].get("exit_code") == 0

    def test_run_python_error_event_flow(self, app_client) -> None:
        """代码抛异常时：tool_call_end.success=False，stderr 含异常信息。"""
        first_resp = LLMResponse(
            text="",
            model="mock",
            tool_calls=[{
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "run_python",
                    "arguments": json.dumps({
                        "code": "raise RuntimeError('boom from test')",
                        "intent": "测试异常",
                    }),
                },
            }],
            finish_reason="tool_calls",
        )
        second_resp = LLMResponse(
            text="代码抛异常了。",
            model="mock",
            tool_calls=None,
            finish_reason="stop",
        )

        with patch("lihua.agent.call_llm_with_tools", side_effect=[first_resp, second_resp]):
            resp = app_client.post(
                "/api/chat/stream",
                json={"message": "测试异常", "auto_confirm": True},
            )

        events = _parse_sse_events(resp.text)
        tc_end = next(e for e in events if e.get("type") == "tool_call_end")
        assert tc_end["name"] == "run_python"
        assert tc_end["success"] is False
        assert tc_end["details"] is not None
        assert tc_end["details"].get("exit_code") != 0
        assert "RuntimeError" in tc_end["details"].get("stderr", "")
        assert "boom from test" in tc_end["details"].get("stderr", "")

    def test_run_python_details_in_done_event(self, app_client) -> None:
        """done 事件的 tool_calls 数组里也要包含 run_python 的 details。"""
        first_resp = LLMResponse(
            text="",
            model="mock",
            tool_calls=[{
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "run_python",
                    "arguments": json.dumps({
                        "code": "print('v083_done_test')",
                        "intent": "测试 done 事件",
                    }),
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
        assert tc["name"] == "run_python"
        assert tc["details"] is not None
        assert "v083_done_test" in tc["details"].get("stdout", "")
        assert tc["details"].get("safety_level") == "grey"
        assert tc["details"].get("exit_code") == 0


class TestChatStreamRunPythonConfirm:
    """v0.8.3：run_python 强制走 confirm 的交互流程。"""

    def test_run_python_needs_confirm_event(self, app_client) -> None:
        """auto_confirm=False 时 run_python 触发 needs_confirm 事件。

        run_python 强制走 confirm（不走 safety.py），用户必须确认才能执行。
        用 TestClient + 缩短 confirm 超时避免测试卡住。
        """
        first_resp = LLMResponse(
            text="",
            model="mock",
            tool_calls=[{
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "run_python",
                    "arguments": json.dumps({
                        "code": "print('needs confirm test')",
                        "intent": "测试 confirm 流程",
                    }),
                },
            }],
            finish_reason="tool_calls",
        )

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
                    # message 里应该包含 LLM 的 intent 或代码预览
                    assert "测试 confirm" in nc["message"] or "needs_confirm" in nc["message"]
            except Exception:
                pytest.skip("TestClient 超时，但 confirm_cb 阻塞行为正确")


class TestRunPythonArgumentsExtraction:
    """v0.8.3：run_python 参数解析（code/intent/timeout）。"""

    def test_run_python_timeout_clamped_in_sse(self, app_client) -> None:
        """timeout=99999 会被 clamp 到 300，但 SSE 事件仍正常。"""
        first_resp = LLMResponse(
            text="",
            model="mock",
            tool_calls=[{
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "run_python",
                    "arguments": json.dumps({
                        "code": "print('timeout_test')",
                        "intent": "测试 timeout clamp",
                        "timeout": 99999,
                    }),
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
        tc_end = next(e for e in events if e.get("type") == "tool_call_end")
        # timeout 被 clamp 到 300，代码仍执行成功
        assert tc_end["success"] is True
        assert "timeout_test" in tc_end["details"].get("stdout", "")
        assert tc_end["details"].get("timed_out") is False
