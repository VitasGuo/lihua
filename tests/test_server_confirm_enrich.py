"""v0.8.4 新增：server.py 的 _enrich_confirm_event 单元测试。

验证 confirm msg 能被正确解析成结构化字段：
- run_python：```python 代码块标记 → tool_name / intent / code
- run_shell："\n命令：" 前缀 → tool_name / intent / command_text
- file_op：关键词匹配 → tool_name
- 默认：不加额外字段
"""

from __future__ import annotations

from lihua.server import _enrich_confirm_event


class TestEnrichConfirmEventRunPython:
    """v0.8.4：run_python 的 confirm msg 解析。"""

    def test_run_python_basic(self) -> None:
        """含 ```python 代码块标记的 msg 解析出 tool_name / intent / code。"""
        msg = "测试 print\n代码（25 字符）：\n```python\nprint('hello')\n```"
        event: dict = {"type": "needs_confirm", "id": "x", "message": msg, "command": "print('hello')"}
        _enrich_confirm_event(event, msg, "print('hello')")
        assert event["tool_name"] == "run_python"
        assert event["intent"] == "测试 print\n代码（25 字符）："
        assert event["code"] == "print('hello')\n"

    def test_run_python_multiline_code(self) -> None:
        """多行 Python 代码正确提取。"""
        code = "import json\nprint(json.dumps({'a': 1}))\nfor i in range(3):\n    print(i)"
        msg = f"格式化 JSON\n代码（{len(code)} 字符）：\n```python\n{code}\n```"
        event: dict = {"type": "needs_confirm", "id": "x", "message": msg, "command": code}
        _enrich_confirm_event(event, msg, code)
        assert event["tool_name"] == "run_python"
        assert "格式化 JSON" in event["intent"]
        assert event["code"] == code + "\n"

    def test_run_python_no_intent(self) -> None:
        """msg 没有 intent 部分（直接以 ```python 开头）时 intent 字段不设置。"""
        msg = "需要执行一段 Python 代码\n代码（10 字符）：\n```python\nprint(1)\n```"
        event: dict = {"type": "needs_confirm", "id": "x", "message": msg, "command": "print(1)"}
        _enrich_confirm_event(event, msg, "print(1)")
        assert event["tool_name"] == "run_python"
        assert "intent" in event
        assert "需要执行" in event["intent"]

    def test_run_python_truncated_code(self) -> None:
        """代码被截断（含 '共 XXX 字符，已截断' 提示）时仍能正确提取。"""
        code_preview = "print('long code')\n... (共 1000 字符，已截断)"
        msg = f"测试\n代码（1000 字符）：\n```python\n{code_preview}\n```"
        event: dict = {"type": "needs_confirm", "id": "x", "message": msg, "command": "full code"}
        _enrich_confirm_event(event, msg, "full code")
        assert event["tool_name"] == "run_python"
        assert event["code"] == code_preview + "\n"


class TestEnrichConfirmEventRunShell:
    """v0.8.4：run_shell 的 confirm msg 解析。"""

    def test_run_shell_basic(self) -> None:
        """含 "\n命令：" 前缀的 msg 解析出 tool_name / intent / command_text。"""
        msg = "查看端口占用\n命令：lsof -i:8080"
        event: dict = {"type": "needs_confirm", "id": "x", "message": msg, "command": "lsof -i:8080"}
        _enrich_confirm_event(event, msg, "lsof -i:8080")
        assert event["tool_name"] == "run_shell"
        assert event["intent"] == "查看端口占用"
        assert event["command_text"] == "lsof -i:8080"

    def test_run_shell_multiline_command(self) -> None:
        """多行命令正确提取。"""
        cmd = "cd /tmp && ls -la | grep test"
        msg = f"查找测试文件\n命令：{cmd}"
        event: dict = {"type": "needs_confirm", "id": "x", "message": msg, "command": cmd}
        _enrich_confirm_event(event, msg, cmd)
        assert event["tool_name"] == "run_shell"
        assert event["intent"] == "查找测试文件"
        assert event["command_text"] == cmd

    def test_run_shell_no_intent(self) -> None:
        """msg 没有意图部分（直接以 "命令：" 开头）时 intent 字段不设置。"""
        msg = "\n命令：ls"
        event: dict = {"type": "needs_confirm", "id": "x", "message": msg, "command": "ls"}
        _enrich_confirm_event(event, msg, "ls")
        assert event["tool_name"] == "run_shell"
        # intent 是空字符串 strip 后为空，不设置
        assert "intent" not in event or event.get("intent") == ""
        assert event["command_text"] == "ls"


class TestEnrichConfirmEventFileOp:
    """v0.8.4：文件操作的 confirm msg 解析。"""

    def test_file_op_write(self) -> None:
        """含 "写入文件" 关键词的 msg 标记为 file_op。"""
        msg = "写入文件 ~/test.txt\n路径：/home/user/test.txt\n内容预览：hello"
        event: dict = {"type": "needs_confirm", "id": "x", "message": msg, "command": ""}
        _enrich_confirm_event(event, msg, "")
        assert event["tool_name"] == "file_op"

    def test_file_op_edit(self) -> None:
        """含 "编辑文件" 关键词的 msg 标记为 file_op。"""
        msg = "编辑文件 ~/config.yml\nold: port: 8080\nnew: port: 9090"
        event: dict = {"type": "needs_confirm", "id": "x", "message": msg, "command": ""}
        _enrich_confirm_event(event, msg, "")
        assert event["tool_name"] == "file_op"

    def test_file_op_path_keyword(self) -> None:
        """含 "路径：" 关键词的 msg 标记为 file_op。"""
        msg = "路径：/home/user/.bashrc"
        event: dict = {"type": "needs_confirm", "id": "x", "message": msg, "command": ""}
        _enrich_confirm_event(event, msg, "")
        assert event["tool_name"] == "file_op"


class TestEnrichConfirmEventDefault:
    """v0.8.4：默认情况（纯文本 msg）不加结构化字段。"""

    def test_default_no_tool_name(self) -> None:
        """不含任何关键词的 msg 不加 tool_name。"""
        msg = "即将执行 apt install nginx"
        event: dict = {"type": "needs_confirm", "id": "x", "message": msg, "command": "apt install nginx"}
        _enrich_confirm_event(event, msg, "apt install nginx")
        assert "tool_name" not in event
        assert "intent" not in event
        assert "code" not in event
        assert "command_text" not in event

    def test_default_preserves_original_fields(self) -> None:
        """默认情况不修改原有字段。"""
        msg = "普通灰名单操作"
        event: dict = {"type": "needs_confirm", "id": "abc", "message": msg, "command": "some cmd"}
        _enrich_confirm_event(event, msg, "some cmd")
        assert event["type"] == "needs_confirm"
        assert event["id"] == "abc"
        assert event["message"] == msg
        assert event["command"] == "some cmd"

    def test_run_python_takes_precedence_over_shell(self) -> None:
        """msg 同时含 ```python 和 "命令：" 时，优先识别为 run_python。"""
        msg = "测试\n命令：python -c '...'\n```python\nprint(1)\n```"
        event: dict = {"type": "needs_confirm", "id": "x", "message": msg, "command": "python"}
        _enrich_confirm_event(event, msg, "python")
        # 应该优先识别为 run_python（因为 ```python 标记更明确）
        assert event["tool_name"] == "run_python"
