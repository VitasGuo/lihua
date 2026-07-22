"""agent.py 单元测试：LLM Agent 主循环。

用 mock LLM 避免真实网络调用。
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest

from lihua.agent import (
    AgentResponse,
    ToolCallRecord,
    _execute_tool,
    _format_tool_result_for_llm,
    run_agent,
    run_agent_streaming,
)
from lihua.config import Config
from lihua.router import LLMResponse
from lihua.skills import SkillRegistry, get_registry


@pytest.fixture
def registry() -> SkillRegistry:
    reg = get_registry()
    reg.reload()
    return reg


@pytest.fixture
def disabled_cfg() -> Config:
    """LLM 关闭的配置（用于测试无 LLM 时的回退）。"""
    cfg = Config.load()
    cfg.llm.enabled = False
    return cfg


class TestExecuteTool:
    """工具执行（不依赖 LLM）。"""

    def test_unknown_tool(self, registry: SkillRegistry) -> None:
        from lihua.config import Config
        cfg = Config.load()
        record = _execute_tool(
            tool_name="nonexistent_tool",
            arguments={},
            cfg=cfg,
            registry=registry,
            confirm=None,
            on_progress=None,
        )
        assert not record.success
        assert "不存在" in record.error

    def test_dry_run_does_not_execute(self, registry: SkillRegistry) -> None:
        """dry_run 模式下不实际执行 skill。"""
        from lihua.config import Config
        cfg = Config.load()
        record = _execute_tool(
            tool_name="install_app",
            arguments={"target": "QQ"},
            cfg=cfg,
            registry=registry,
            confirm=None,
            on_progress=None,
            dry_run=True,
        )
        assert record.success
        assert "dry-run" in record.result_message

    def test_known_tool_no_dry_run(self, registry: SkillRegistry) -> None:
        """已知工具不 dry_run 时会真执行（这里 install_app 会失败因为没有 target 别名匹配）。"""
        from lihua.config import Config
        cfg = Config.load()
        # 用 cpu_monitor 这种只读 skill 来测试，避免真执行写操作
        record = _execute_tool(
            tool_name="cpu_monitor",
            arguments={},
            cfg=cfg,
            registry=registry,
            confirm=None,
            on_progress=None,
        )
        # cpu_monitor 应该能执行（它只是 top -bn1）
        assert isinstance(record, ToolCallRecord)
        assert record.tool_name == "cpu_monitor"


class TestExecuteRunShell:
    """v0.8.0 新增：run_shell 万能兜底工具执行测试。"""

    def test_run_shell_whitelist_auto_execute(self, registry: SkillRegistry) -> None:
        """白名单命令（ls/echo）自动执行，不需要确认。"""
        from lihua.config import Config
        cfg = Config.load()
        record = _execute_tool(
            tool_name="run_shell",
            arguments={"command": "echo hello_v080", "intent": "测试 echo"},
            cfg=cfg,
            registry=registry,
            confirm=None,  # 白名单不需要 confirm
            on_progress=None,
        )
        assert record.success
        assert record.tool_name == "run_shell"
        assert "hello_v080" in record.result_message
        # details 里有完整 stdout
        assert record.result_details is not None
        assert "hello_v080" in record.result_details.get("stdout", "")
        assert record.result_details.get("exit_code") == 0
        assert record.result_details.get("safety_level") == "white"

    def test_run_shell_empty_command_rejected(self, registry: SkillRegistry) -> None:
        """空命令直接拒绝。"""
        from lihua.config import Config
        cfg = Config.load()
        record = _execute_tool(
            tool_name="run_shell",
            arguments={"command": "   ", "intent": "空命令测试"},
            cfg=cfg,
            registry=registry,
            confirm=None,
            on_progress=None,
        )
        assert not record.success
        assert "空" in record.error or "空" in record.result_message

    def test_run_shell_blacklist_rejected(self, registry: SkillRegistry) -> None:
        """黑名单命令（rm -rf /）直接拒绝，不弹确认。"""
        from lihua.config import Config
        cfg = Config.load()
        record = _execute_tool(
            tool_name="run_shell",
            arguments={"command": "rm -rf /", "intent": "试图删根目录"},
            cfg=cfg,
            registry=registry,
            confirm=None,  # 即使有 confirm 也会被黑名单先拦
            on_progress=None,
        )
        assert not record.success
        assert "拒绝" in record.result_message or "安全引擎" in record.error
        assert record.result_details is not None
        assert record.result_details.get("safety_level") == "black"

    def test_run_shell_grey_no_confirm_rejected(self, registry: SkillRegistry) -> None:
        """灰名单命令 + 无 confirm_cb → 拒绝（保守策略）。"""
        from lihua.config import Config
        cfg = Config.load()
        # always_confirm_grey=True 时，灰名单必须走 confirm
        cfg.always_confirm_grey = True
        record = _execute_tool(
            tool_name="run_shell",
            arguments={"command": "pkexec apt purge -y somepkg", "intent": "卸载包"},
            cfg=cfg,
            registry=registry,
            confirm=None,  # 无 confirm_cb → 拒绝
            on_progress=None,
        )
        assert not record.success
        assert "确认" in record.error or "确认" in record.result_message
        assert record.result_details is not None
        assert record.result_details.get("safety_level") == "grey"

    def test_run_shell_grey_confirm_accepted(self, registry: SkillRegistry) -> None:
        """灰名单命令 + 用户确认 → 执行（这里用 mock confirm）。"""
        from lihua.config import Config
        cfg = Config.load()
        cfg.always_confirm_grey = True
        # confirm_cb 返回 True，但实际命令也会执行——用一条无害的灰名单命令
        # 用 pkexec true（pkexec 走灰名单，但 true 不会真做事）
        # 但 pkexec 会弹系统密码框，这里改成 mock：直接测 confirm 被调用
        confirmed_calls: list[str] = []

        def mock_confirm(msg: str, cmd: str) -> bool:
            confirmed_calls.append(cmd)
            return False  # 用户取消，避免真执行 pkexec

        record = _execute_tool(
            tool_name="run_shell",
            arguments={"command": "pkexec true", "intent": "测试灰名单"},
            cfg=cfg,
            registry=registry,
            confirm=mock_confirm,
            on_progress=None,
        )
        # 用户取消 → 失败
        assert not record.success
        assert "取消" in record.error or "取消" in record.result_message
        # confirm 被调用过
        assert len(confirmed_calls) == 1
        assert "pkexec true" in confirmed_calls[0]

    def test_run_shell_dry_run(self, registry: SkillRegistry) -> None:
        """dry_run 模式下不实际执行。"""
        from lihua.config import Config
        cfg = Config.load()
        record = _execute_tool(
            tool_name="run_shell",
            arguments={"command": "ls /", "intent": "dry-run 测试"},
            cfg=cfg,
            registry=registry,
            confirm=None,
            on_progress=None,
            dry_run=True,
        )
        assert record.success
        assert "dry-run" in record.result_message
        assert "ls /" in record.result_message

    def test_run_shell_timeout_clamped(self, registry: SkillRegistry) -> None:
        """timeout 上限 600s，超出会被截断。"""
        from lihua.config import Config
        cfg = Config.load()
        # 用 echo 测，timeout=99999 会被截断到 600
        record = _execute_tool(
            tool_name="run_shell",
            arguments={"command": "echo test_timeout", "intent": "测试", "timeout": 99999},
            cfg=cfg,
            registry=registry,
            confirm=None,
            on_progress=None,
        )
        assert record.success
        # 实际 timeout 在 _execute_run_shell 内部 clamp，这里只验证不报错
        assert "test_timeout" in record.result_message

    def test_format_run_shell_result_includes_stdout(self) -> None:
        """v0.8.0 关键：run_shell 的 _format_tool_result_for_llm 必须包含完整 stdout。"""
        record = ToolCallRecord(
            tool_name="run_shell",
            arguments={"command": "ls /", "intent": "测试"},
            success=True,
            result_message="bin\nboot\netc",
            result_details={
                "exit_code": 0,
                "stdout": "bin\nboot\netc\nhome\nlib",
                "stderr": "",
                "safety_level": "white",
                "timed_out": False,
            },
        )
        text = _format_tool_result_for_llm(record)
        # stdout 必须出现在 LLM 看到的文本里
        assert "bin" in text
        assert "boot" in text
        assert "exit_code: 0" in text
        assert "safety: white" in text

    def test_format_run_shell_failure_includes_stderr(self) -> None:
        """run_shell 失败时 stderr 必须回传 LLM。"""
        record = ToolCallRecord(
            tool_name="run_shell",
            arguments={"command": "ls /nonexistent", "intent": "测试"},
            success=False,
            error="exit=2",
            result_message="exit=2",
            result_details={
                "exit_code": 2,
                "stdout": "",
                "stderr": "ls: cannot access '/nonexistent': No such file or directory",
                "safety_level": "white",
                "timed_out": False,
            },
        )
        text = _format_tool_result_for_llm(record)
        assert "执行失败" in text
        assert "No such file or directory" in text
        assert "exit_code: 2" in text


class TestRunShellSafetyV081:
    """v0.8.1 新增：safety.py 黑名单扩展 + run_shell 速率限制 + cwd 控制。"""

    def test_blacklist_find_delete(self, registry: SkillRegistry) -> None:
        """v0.8.1: find / -delete 被黑名单拒绝。"""
        from lihua.config import Config
        cfg = Config.load()
        record = _execute_tool(
            tool_name="run_shell",
            arguments={"command": "find / -name '*.tmp' -delete", "intent": "删临时文件"},
            cfg=cfg,
            registry=registry,
            confirm=None,
            on_progress=None,
        )
        assert not record.success
        assert record.result_details is not None
        assert record.result_details.get("safety_level") == "black"

    def test_blacklist_find_exec_rm(self, registry: SkillRegistry) -> None:
        """v0.8.1: find / -exec rm 被黑名单拒绝。"""
        from lihua.config import Config
        cfg = Config.load()
        record = _execute_tool(
            tool_name="run_shell",
            arguments={"command": "find / -exec rm -rf {} +", "intent": "删根"},
            cfg=cfg,
            registry=registry,
            confirm=None,
            on_progress=None,
        )
        assert not record.success
        assert record.result_details.get("safety_level") == "black"

    def test_blacklist_mv_to_dev_null(self, registry: SkillRegistry) -> None:
        """v0.8.1: mv file /dev/null 被黑名单拒绝。"""
        from lihua.config import Config
        cfg = Config.load()
        record = _execute_tool(
            tool_name="run_shell",
            arguments={"command": "mv important.txt /dev/null", "intent": "删文件"},
            cfg=cfg,
            registry=registry,
            confirm=None,
            on_progress=None,
        )
        assert not record.success
        assert record.result_details.get("safety_level") == "black"

    def test_blacklist_chmod_777_home(self, registry: SkillRegistry) -> None:
        """v0.8.1: chmod -R 777 ~ 被黑名单拒绝。"""
        from lihua.config import Config
        cfg = Config.load()
        record = _execute_tool(
            tool_name="run_shell",
            arguments={"command": "chmod -R 777 ~", "intent": "改权限"},
            cfg=cfg,
            registry=registry,
            confirm=None,
            on_progress=None,
        )
        assert not record.success
        assert record.result_details.get("safety_level") == "black"

    def test_blacklist_chmod_777_etc_passwd(self, registry: SkillRegistry) -> None:
        """v0.8.1: chmod 777 /etc/passwd 被黑名单拒绝。"""
        from lihua.config import Config
        cfg = Config.load()
        record = _execute_tool(
            tool_name="run_shell",
            arguments={"command": "chmod 777 /etc/passwd", "intent": "改权限"},
            cfg=cfg,
            registry=registry,
            confirm=None,
            on_progress=None,
        )
        assert not record.success
        assert record.result_details.get("safety_level") == "black"

    def test_blacklist_shutdown(self, registry: SkillRegistry) -> None:
        """v0.8.1: shutdown 被黑名单拒绝。"""
        from lihua.config import Config
        cfg = Config.load()
        record = _execute_tool(
            tool_name="run_shell",
            arguments={"command": "shutdown -h now", "intent": "关机"},
            cfg=cfg,
            registry=registry,
            confirm=None,
            on_progress=None,
        )
        assert not record.success
        assert record.result_details.get("safety_level") == "black"

    def test_blacklist_reboot(self, registry: SkillRegistry) -> None:
        """v0.8.1: reboot 被黑名单拒绝。"""
        from lihua.config import Config
        cfg = Config.load()
        record = _execute_tool(
            tool_name="run_shell",
            arguments={"command": "reboot", "intent": "重启"},
            cfg=cfg,
            registry=registry,
            confirm=None,
            on_progress=None,
        )
        assert not record.success
        assert record.result_details.get("safety_level") == "black"

    def test_blacklist_iptables_flush(self, registry: SkillRegistry) -> None:
        """v0.8.1: iptables -F 被黑名单拒绝。"""
        from lihua.config import Config
        cfg = Config.load()
        record = _execute_tool(
            tool_name="run_shell",
            arguments={"command": "iptables -F", "intent": "清防火墙"},
            cfg=cfg,
            registry=registry,
            confirm=None,
            on_progress=None,
        )
        assert not record.success
        assert record.result_details.get("safety_level") == "black"

    def test_blacklist_systemctl_stop_ssh(self, registry: SkillRegistry) -> None:
        """v0.8.1: systemctl stop sshd 被黑名单拒绝。"""
        from lihua.config import Config
        cfg = Config.load()
        record = _execute_tool(
            tool_name="run_shell",
            arguments={"command": "systemctl stop sshd", "intent": "停 SSH"},
            cfg=cfg,
            registry=registry,
            confirm=None,
            on_progress=None,
        )
        assert not record.success
        assert record.result_details.get("safety_level") == "black"

    def test_run_shell_cwd_is_home(self, registry: SkillRegistry) -> None:
        """v0.8.1: run_shell 默认在用户主目录执行。"""
        from lihua.config import Config
        import os
        cfg = Config.load()
        record = _execute_tool(
            tool_name="run_shell",
            arguments={"command": "pwd", "intent": "查看当前目录"},
            cfg=cfg,
            registry=registry,
            confirm=None,
            on_progress=None,
        )
        assert record.success
        assert record.result_details is not None
        # cwd 字段应该是用户主目录
        assert record.result_details.get("cwd") == os.path.expanduser("~")
        # pwd 命令的 stdout 应该是用户主目录路径
        stdout = record.result_details.get("stdout", "")
        assert os.path.expanduser("~") in stdout


class TestRunShellRateLimit:
    """v0.8.1 新增：run_shell 速率限制测试。"""

    def test_max_run_shell_calls_constant(self) -> None:
        """MAX_RUN_SHELL_CALLS 常量存在且为正整数。"""
        from lihua.agent import MAX_RUN_SHELL_CALLS
        assert isinstance(MAX_RUN_SHELL_CALLS, int)
        assert MAX_RUN_SHELL_CALLS > 0
        assert MAX_RUN_SHELL_CALLS == 30  # v0.8.1 从 15 提升到 30


class TestRunPythonRateLimit:
    """v0.8.3 新增：run_python 速率限制测试。"""

    def test_max_run_python_calls_constant(self) -> None:
        """MAX_RUN_PYTHON_CALLS 常量存在且为正整数（比 run_shell 更严）。"""
        from lihua.agent import MAX_RUN_PYTHON_CALLS
        assert isinstance(MAX_RUN_PYTHON_CALLS, int)
        assert MAX_RUN_PYTHON_CALLS > 0
        assert MAX_RUN_PYTHON_CALLS == 10

    def test_run_python_count_in_streaming(self, registry: SkillRegistry) -> None:
        """流式模式 run_python 超过 MAX_RUN_PYTHON_CALLS 次会被拒绝。"""
        cfg = Config.load()
        cfg.llm.enabled = True

        # 模拟 LLM 反复调 run_python
        loop_resp = LLMResponse(
            text="",
            model="mock",
            tool_calls=[{
                "id": "call_x",
                "type": "function",
                "function": {
                    "name": "run_python",
                    "arguments": json.dumps({"code": "print(1)", "intent": "测试"}),
                },
            }],
            finish_reason="tool_calls",
        )
        # 最后一次 LLM 不再调工具，给最终回复
        final_resp = LLMResponse(
            text="结束",
            model="mock",
            tool_calls=None,
            finish_reason="stop",
        )

        with patch("lihua.agent.call_llm_with_tools", side_effect=[loop_resp] * 12 + [final_resp]):
            events = list(run_agent_streaming(
                "跑 Python", cfg, registry,
                confirm=lambda intent, cmd: "confirmed",
                max_iterations=15,
            ))

        # 应该至少有一个 tool_call_end 的 details.safety_level == "rate_limited"
        rate_limited_ends = [
            e for e in events
            if e["type"] == "tool_call_end"
            and e.get("details")
            and e["details"].get("safety_level") == "rate_limited"
        ]
        assert len(rate_limited_ends) >= 1
        # done 事件
        assert events[-1]["type"] == "done"


class TestIsPathInHome:
    """v0.8.2 新增：_is_path_in_home 路径检查。"""

    def test_home_itself_is_in_home(self) -> None:
        from lihua.agent import _is_path_in_home
        import os
        assert _is_path_in_home("~") is True
        assert _is_path_in_home(os.path.expanduser("~")) is True

    def test_subdir_of_home_is_in_home(self) -> None:
        from lihua.agent import _is_path_in_home
        assert _is_path_in_home("~/Documents/foo.txt") is True
        assert _is_path_in_home("~/.config/lihua/config.toml") is True

    def test_system_dir_not_in_home(self) -> None:
        from lihua.agent import _is_path_in_home
        assert _is_path_in_home("/etc/passwd") is False
        assert _is_path_in_home("/usr/bin/python3") is False
        assert _is_path_in_home("/boot/vmlinuz") is False

    def test_path_traversal_blocked(self) -> None:
        """~/../etc 不应通过——abspath 会规范化路径。"""
        from lihua.agent import _is_path_in_home
        assert _is_path_in_home("~/../etc/passwd") is False


class TestExecuteReadFile:
    """v0.8.2 新增：read_file 工具执行测试。"""

    def test_read_text_file_with_line_numbers(self, tmp_path) -> None:
        """读文本文件，结果带行号。"""
        from lihua.config import Config
        cfg = Config.load()
        test_file = tmp_path / "sample.txt"
        test_file.write_text("hello\nworld\n", encoding="utf-8")
        record = _execute_tool(
            tool_name="read_file",
            arguments={"path": str(test_file)},
            cfg=cfg,
            registry=None,  # read_file 不需要 registry
            confirm=None,
            on_progress=None,
        )
        assert record.success
        # 行号格式：右对齐 5 位 + →
        assert "    1→hello" in record.result_message
        assert "    2→world" in record.result_message
        assert record.result_details is not None
        assert record.result_details["total_lines"] == 2
        assert record.result_details["is_binary"] is False

    def test_read_nonexistent_file(self, tmp_path) -> None:
        """读不存在的文件应失败。"""
        from lihua.config import Config
        cfg = Config.load()
        record = _execute_tool(
            tool_name="read_file",
            arguments={"path": str(tmp_path / "nonexistent.txt")},
            cfg=cfg,
            registry=None,
            confirm=None,
            on_progress=None,
        )
        assert not record.success
        assert "不存在" in record.error

    def test_read_directory_fails(self, tmp_path) -> None:
        """读目录应失败。"""
        from lihua.config import Config
        cfg = Config.load()
        record = _execute_tool(
            tool_name="read_file",
            arguments={"path": str(tmp_path)},
            cfg=cfg,
            registry=None,
            confirm=None,
            on_progress=None,
        )
        assert not record.success
        assert "目录" in record.error or "目录" in record.result_message

    def test_read_empty_path_rejected(self) -> None:
        """空路径应失败。"""
        from lihua.config import Config
        cfg = Config.load()
        record = _execute_tool(
            tool_name="read_file",
            arguments={"path": ""},
            cfg=cfg,
            registry=None,
            confirm=None,
            on_progress=None,
        )
        assert not record.success
        assert "为空" in record.error or "为空" in record.result_message

    def test_read_binary_file_detected(self, tmp_path) -> None:
        """二进制文件应返回提示，不返回乱码。"""
        from lihua.config import Config
        cfg = Config.load()
        binary_file = tmp_path / "data.bin"
        binary_file.write_bytes(b"\x00\x01\x02\x03binary\xff\xfe")
        record = _execute_tool(
            tool_name="read_file",
            arguments={"path": str(binary_file)},
            cfg=cfg,
            registry=None,
            confirm=None,
            on_progress=None,
        )
        assert record.success
        assert record.result_details is not None
        assert record.result_details["is_binary"] is True
        assert "二进制" in record.result_message

    def test_read_long_file_truncated(self, tmp_path) -> None:
        """长文件应截断到 200 行，并提示用 start_line 续读。"""
        from lihua.config import Config
        cfg = Config.load()
        long_file = tmp_path / "long.txt"
        long_file.write_text("\n".join(f"line{i}" for i in range(1, 301)) + "\n", encoding="utf-8")
        record = _execute_tool(
            tool_name="read_file",
            arguments={"path": str(long_file)},
            cfg=cfg,
            registry=None,
            confirm=None,
            on_progress=None,
        )
        assert record.success
        # 截断提示
        assert "共 300 行" in record.result_message
        assert "start_line=201" in record.result_message
        assert record.result_details["total_lines"] == 300
        assert record.result_details["shown_lines"] == [1, 200]

    def test_read_with_start_line(self, tmp_path) -> None:
        """用 start_line 从中间开始读。"""
        from lihua.config import Config
        cfg = Config.load()
        test_file = tmp_path / "multi.txt"
        test_file.write_text("\n".join(f"line{i}" for i in range(1, 21)) + "\n", encoding="utf-8")
        record = _execute_tool(
            tool_name="read_file",
            arguments={"path": str(test_file), "start_line": 10, "end_line": 12},
            cfg=cfg,
            registry=None,
            confirm=None,
            on_progress=None,
        )
        assert record.success
        assert "   10→line10" in record.result_message
        assert "   12→line12" in record.result_message
        # 不应含前 9 行
        assert "line1→" not in record.result_message
        assert "   1→line1" not in record.result_message

    def test_read_file_dry_run(self, tmp_path) -> None:
        """dry_run 模式不实际读取。"""
        from lihua.config import Config
        cfg = Config.load()
        record = _execute_tool(
            tool_name="read_file",
            arguments={"path": str(tmp_path / "any.txt")},
            cfg=cfg,
            registry=None,
            confirm=None,
            on_progress=None,
            dry_run=True,
        )
        assert record.success
        assert "dry-run" in record.result_message

    def test_read_path_expansion(self, tmp_path, monkeypatch) -> None:
        """~ 应被展开。"""
        from lihua.config import Config
        cfg = Config.load()
        # 在主目录下建一个文件
        import os
        home = os.path.expanduser("~")
        test_file = os.path.join(home, ".lihua_test_read_path_expansion.txt")
        try:
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("home content\n")
            record = _execute_tool(
                tool_name="read_file",
                arguments={"path": "~/.lihua_test_read_path_expansion.txt"},
                cfg=cfg,
                registry=None,
                confirm=None,
                on_progress=None,
            )
            assert record.success
            assert "home content" in record.result_message
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)


class TestExecuteWriteFile:
    """v0.8.2 新增：write_file 工具执行测试。"""

    def test_write_new_file_in_home(self, tmp_path) -> None:
        """在主目录下写新文件。"""
        from lihua.config import Config
        cfg = Config.load()
        # tmp_path 在 /tmp 下，不在 home 里——直接 mock _is_path_in_home
        # 或者把 tmp_path 当作 home 的子目录测试
        # 更简单：直接调 _execute_tool 测越界，单独用 _execute_write_file 测正常逻辑
        from lihua.agent import _execute_write_file
        import os
        # 用主目录下的临时文件
        target = os.path.join(os.path.expanduser("~"), ".lihua_test_write_new.txt")
        try:
            t0 = 0.0
            record = _execute_write_file(
                arguments={"path": target, "content": "hello lihua\n", "intent": "测试写文件"},
                cfg=cfg,
                confirm=lambda msg, cmd: "confirmed",  # 用户同意（v0.8.6 返回 str）
                on_progress=None,
                dry_run=False,
                t0=t0,
            )
            assert record.success
            assert os.path.exists(target)
            with open(target, "r", encoding="utf-8") as f:
                assert f.read() == "hello lihua\n"
        finally:
            if os.path.exists(target):
                os.remove(target)

    def test_write_path_outside_home_rejected(self) -> None:
        """路径越界（/etc/...）应被拒绝。"""
        from lihua.config import Config
        cfg = Config.load()
        record = _execute_tool(
            tool_name="write_file",
            arguments={"path": "/etc/lihua_test_etc.txt", "content": "hacked\n", "intent": "尝试改系统文件"},
            cfg=cfg,
            registry=None,
            confirm=None,
            on_progress=None,
        )
        assert not record.success
        assert "主目录" in record.error or "主目录" in record.result_message
        assert record.result_details is not None
        assert record.result_details.get("in_home") is False

    def test_write_empty_path_rejected(self) -> None:
        from lihua.config import Config
        cfg = Config.load()
        record = _execute_tool(
            tool_name="write_file",
            arguments={"path": "", "content": "x", "intent": "测试"},
            cfg=cfg,
            registry=None,
            confirm=None,
            on_progress=None,
        )
        assert not record.success
        assert "为空" in record.error or "为空" in record.result_message

    def test_write_no_confirm_rejected(self) -> None:
        """灰名单 + always_confirm_grey=True + confirm_cb=None → 拒绝。"""
        from lihua.config import Config
        import os
        cfg = Config.load()
        cfg.always_confirm_grey = True
        target = os.path.join(os.path.expanduser("~"), ".lihua_test_no_confirm.txt")
        try:
            record = _execute_tool(
                tool_name="write_file",
                arguments={"path": target, "content": "x", "intent": "测试"},
                cfg=cfg,
                registry=None,
                confirm=None,
                on_progress=None,
            )
            assert not record.success
            assert "确认" in record.error or "确认" in record.result_message
            assert record.result_details.get("needs_confirm") is True
        finally:
            if os.path.exists(target):
                os.remove(target)

    def test_write_confirm_cancelled(self) -> None:
        """confirm 返回 False → 用户取消，不写文件。"""
        from lihua.config import Config
        import os
        cfg = Config.load()
        cfg.always_confirm_grey = True
        target = os.path.join(os.path.expanduser("~"), ".lihua_test_cancel.txt")
        try:
            record = _execute_tool(
                tool_name="write_file",
                arguments={"path": target, "content": "x", "intent": "测试"},
                cfg=cfg,
                registry=None,
                confirm=lambda msg, cmd: "denied",
                on_progress=None,
            )
            assert not record.success
            assert "取消" in record.error or "取消" in record.result_message
            assert not os.path.exists(target)
        finally:
            if os.path.exists(target):
                os.remove(target)

    def test_write_auto_mkdir_parent(self) -> None:
        """写文件时自动创建父目录。"""
        from lihua.config import Config
        import os
        cfg = Config.load()
        parent_dir = os.path.join(os.path.expanduser("~"), ".lihua_test_mkdir_parent")
        target = os.path.join(parent_dir, "sub", "file.txt")
        try:
            record = _execute_tool(
                tool_name="write_file",
                arguments={"path": target, "content": "nested\n", "intent": "测试自动 mkdir"},
                cfg=cfg,
                registry=None,
                confirm=lambda msg, cmd: "confirmed",
                on_progress=None,
            )
            assert record.success
            assert os.path.exists(target)
            with open(target, "r", encoding="utf-8") as f:
                assert f.read() == "nested\n"
        finally:
            if os.path.exists(parent_dir):
                import shutil
                shutil.rmtree(parent_dir, ignore_errors=True)

    def test_write_dry_run(self) -> None:
        """dry_run 模式不实际写文件。"""
        from lihua.config import Config
        import os
        cfg = Config.load()
        target = os.path.join(os.path.expanduser("~"), ".lihua_test_dry_run.txt")
        try:
            record = _execute_tool(
                tool_name="write_file",
                arguments={"path": target, "content": "x", "intent": "测试"},
                cfg=cfg,
                registry=None,
                confirm=None,
                on_progress=None,
                dry_run=True,
            )
            assert record.success
            assert "dry-run" in record.result_message
            assert not os.path.exists(target)
        finally:
            if os.path.exists(target):
                os.remove(target)


class TestExecuteEditFile:
    """v0.8.2 新增：edit_file 工具执行测试。"""

    def test_edit_replace_unique_string(self) -> None:
        """old_string 唯一存在时精确替换。"""
        from lihua.config import Config
        import os
        cfg = Config.load()
        target = os.path.join(os.path.expanduser("~"), ".lihua_test_edit_unique.txt")
        try:
            with open(target, "w", encoding="utf-8") as f:
                f.write("port: 8080\nhost: localhost\n")
            record = _execute_tool(
                tool_name="edit_file",
                arguments={
                    "path": target,
                    "old_string": "port: 8080",
                    "new_string": "port: 9090",
                    "intent": "改端口",
                },
                cfg=cfg,
                registry=None,
                confirm=lambda msg, cmd: "confirmed",
                on_progress=None,
            )
            assert record.success
            with open(target, "r", encoding="utf-8") as f:
                content = f.read()
            assert "port: 9090" in content
            assert "port: 8080" not in content
            assert "host: localhost" in content  # 未被替换的部分保持不变
        finally:
            if os.path.exists(target):
                os.remove(target)

    def test_edit_old_string_not_found(self) -> None:
        """old_string 不存在时报错。"""
        from lihua.config import Config
        import os
        cfg = Config.load()
        target = os.path.join(os.path.expanduser("~"), ".lihua_test_edit_not_found.txt")
        try:
            with open(target, "w", encoding="utf-8") as f:
                f.write("hello world\n")
            record = _execute_tool(
                tool_name="edit_file",
                arguments={
                    "path": target,
                    "old_string": "nonexistent string",
                    "new_string": "replacement",
                    "intent": "测试",
                },
                cfg=cfg,
                registry=None,
                confirm=lambda msg, cmd: "confirmed",
                on_progress=None,
            )
            assert not record.success
            assert "未找到" in record.error or "未找到" in record.result_message
            assert record.result_details.get("occurrences") == 0
        finally:
            if os.path.exists(target):
                os.remove(target)

    def test_edit_old_string_not_unique(self) -> None:
        """old_string 出现多次时报错。"""
        from lihua.config import Config
        import os
        cfg = Config.load()
        target = os.path.join(os.path.expanduser("~"), ".lihua_test_edit_not_unique.txt")
        try:
            with open(target, "w", encoding="utf-8") as f:
                f.write("foo\nfoo\nfoo\n")
            record = _execute_tool(
                tool_name="edit_file",
                arguments={
                    "path": target,
                    "old_string": "foo",
                    "new_string": "bar",
                    "intent": "测试",
                },
                cfg=cfg,
                registry=None,
                confirm=lambda msg, cmd: "confirmed",
                on_progress=None,
            )
            assert not record.success
            assert "唯一" in record.error or "唯一" in record.result_message or "3 次" in record.error
            assert record.result_details.get("occurrences") == 3
        finally:
            if os.path.exists(target):
                os.remove(target)

    def test_edit_path_outside_home_rejected(self) -> None:
        """路径越界（/etc/...）应被拒绝。"""
        from lihua.config import Config
        cfg = Config.load()
        record = _execute_tool(
            tool_name="edit_file",
            arguments={
                "path": "/etc/passwd",
                "old_string": "x",
                "new_string": "y",
                "intent": "尝试改系统文件",
            },
            cfg=cfg,
            registry=None,
            confirm=None,
            on_progress=None,
        )
        assert not record.success
        assert "主目录" in record.error or "主目录" in record.result_message

    def test_edit_nonexistent_file(self) -> None:
        """文件不存在时报错。"""
        from lihua.config import Config
        import os
        cfg = Config.load()
        target = os.path.join(os.path.expanduser("~"), ".lihua_test_edit_nonexistent.txt")
        record = _execute_tool(
            tool_name="edit_file",
            arguments={
                "path": target,
                "old_string": "x",
                "new_string": "y",
                "intent": "测试",
            },
            cfg=cfg,
            registry=None,
            confirm=lambda msg, cmd: "confirmed",
            on_progress=None,
        )
        assert not record.success
        assert "不存在" in record.error or "不存在" in record.result_message

    def test_edit_empty_old_string_rejected(self) -> None:
        """old_string 为空时报错。"""
        from lihua.config import Config
        cfg = Config.load()
        record = _execute_tool(
            tool_name="edit_file",
            arguments={
                "path": "~/whatever.txt",
                "old_string": "",
                "new_string": "x",
                "intent": "测试",
            },
            cfg=cfg,
            registry=None,
            confirm=None,
            on_progress=None,
        )
        assert not record.success
        assert "old_string" in record.error or "old_string" in record.result_message

    def test_edit_confirm_cancelled(self) -> None:
        """confirm 返回 False → 用户取消，不改文件。"""
        from lihua.config import Config
        import os
        cfg = Config.load()
        cfg.always_confirm_grey = True
        target = os.path.join(os.path.expanduser("~"), ".lihua_test_edit_cancel.txt")
        try:
            with open(target, "w", encoding="utf-8") as f:
                f.write("original\n")
            record = _execute_tool(
                tool_name="edit_file",
                arguments={
                    "path": target,
                    "old_string": "original",
                    "new_string": "modified",
                    "intent": "测试",
                },
                cfg=cfg,
                registry=None,
                confirm=lambda msg, cmd: "denied",
                on_progress=None,
            )
            assert not record.success
            assert "取消" in record.error or "取消" in record.result_message
            # 文件内容应未变
            with open(target, "r", encoding="utf-8") as f:
                assert f.read() == "original\n"
        finally:
            if os.path.exists(target):
                os.remove(target)

    def test_edit_dry_run(self) -> None:
        """dry_run 模式不实际编辑文件。"""
        from lihua.config import Config
        import os
        cfg = Config.load()
        target = os.path.join(os.path.expanduser("~"), ".lihua_test_edit_dry.txt")
        try:
            with open(target, "w", encoding="utf-8") as f:
                f.write("foo\n")
            record = _execute_tool(
                tool_name="edit_file",
                arguments={
                    "path": target,
                    "old_string": "foo",
                    "new_string": "bar",
                    "intent": "测试",
                },
                cfg=cfg,
                registry=None,
                confirm=None,
                on_progress=None,
                dry_run=True,
            )
            assert record.success
            assert "dry-run" in record.result_message
            # 文件内容应未变
            with open(target, "r", encoding="utf-8") as f:
                assert f.read() == "foo\n"
        finally:
            if os.path.exists(target):
                os.remove(target)


class TestFormatFileOpResultForLLM:
    """v0.8.2 新增：read_file / write_file / edit_file 结果格式化测试。"""

    def test_format_read_file_includes_content(self) -> None:
        """read_file 的内容必须回传 LLM（让 LLM 能基于内容继续决策）。"""
        record = ToolCallRecord(
            tool_name="read_file",
            arguments={"path": "/etc/hostname"},
            success=True,
            result_message="    1→my-pc",
            result_details={
                "path": "/etc/hostname",
                "total_lines": 1,
                "shown_lines": [1, 1],
                "size": 6,
                "is_binary": False,
            },
        )
        text = _format_tool_result_for_llm(record)
        assert "执行成功" in text
        # 文件内容必须出现在 LLM 看到的文本里
        assert "my-pc" in text
        assert "1→" in text

    def test_format_read_binary_file(self) -> None:
        """二进制文件返回提示，不让 LLM 看到乱码。"""
        record = ToolCallRecord(
            tool_name="read_file",
            arguments={"path": "/bin/ls"},
            success=True,
            result_message="⚠️ 二进制文件，不显示内容：/bin/ls（size=138304 bytes）",
            result_details={"path": "/bin/ls", "is_binary": True, "size": 138304},
        )
        text = _format_tool_result_for_llm(record)
        assert "二进制" in text
        # 不应含乱码
        assert "\\x00" not in text

    def test_format_write_file_success(self) -> None:
        """write_file 成功消息回传 LLM。"""
        record = ToolCallRecord(
            tool_name="write_file",
            arguments={"path": "~/test.sh", "content": "echo hi", "intent": "测试"},
            success=True,
            result_message="✅ 已写入：~/test.sh（8 字符）",
            result_details={"path": "~/test.sh", "size": 8, "overwrote": False},
        )
        text = _format_tool_result_for_llm(record)
        assert "执行成功" in text
        assert "已写入" in text

    def test_format_edit_file_success(self) -> None:
        """edit_file 成功消息回传 LLM。"""
        record = ToolCallRecord(
            tool_name="edit_file",
            arguments={"path": "~/config.yml", "old_string": "x", "new_string": "y", "intent": "测试"},
            success=True,
            result_message="✅ 已编辑：~/config.yml（1 → 1 字符）",
            result_details={"path": "~/config.yml", "old_len": 1, "new_len": 1, "occurrences": 1},
        )
        text = _format_tool_result_for_llm(record)
        assert "执行成功" in text
        assert "已编辑" in text

    def test_format_write_file_path_violation(self) -> None:
        """write_file 越界拒绝时 LLM 能看到原因。"""
        record = ToolCallRecord(
            tool_name="write_file",
            arguments={"path": "/etc/passwd", "content": "hacked", "intent": "尝试"},
            success=False,
            error="路径不在用户主目录内：/etc/passwd",
            result_message="❌ 路径越界：/etc/passwd 不在用户主目录内",
            result_details={"path": "/etc/passwd", "in_home": False},
        )
        text = _format_tool_result_for_llm(record)
        assert "执行失败" in text
        assert "主目录" in text


class TestExecuteRunPython:
    """v0.8.3 新增：run_python 工具执行测试。"""

    def test_run_simple_print(self) -> None:
        """执行简单的 print 语句，stdout 回传 LLM。"""
        from lihua.config import Config
        cfg = Config.load()
        cfg.always_confirm_grey = True
        record = _execute_tool(
            tool_name="run_python",
            arguments={"code": "print('hello from python')", "intent": "测试 print"},
            cfg=cfg,
            registry=None,
            confirm=lambda intent, cmd: "confirmed",
            on_progress=None,
        )
        assert record.success
        assert record.result_details is not None
        assert "hello from python" in record.result_details.get("stdout", "")
        assert record.result_details.get("exit_code") == 0
        assert record.result_details.get("safety_level") == "grey"

    def test_run_python_with_import(self) -> None:
        """执行需要 import 标准库的代码。"""
        from lihua.config import Config
        cfg = Config.load()
        cfg.always_confirm_grey = True
        code = "import json\nprint(json.dumps({'a': 1, 'b': 2}, sort_keys=True))"
        record = _execute_tool(
            tool_name="run_python",
            arguments={"code": code, "intent": "测试 json"},
            cfg=cfg,
            registry=None,
            confirm=lambda intent, cmd: "confirmed",
            on_progress=None,
        )
        assert record.success
        assert '{"a": 1, "b": 2}' in record.result_details.get("stdout", "")

    def test_run_python_error_stderr(self) -> None:
        """代码抛异常时，stderr 含 traceback，exit_code != 0。"""
        from lihua.config import Config
        cfg = Config.load()
        cfg.always_confirm_grey = True
        code = "raise ValueError('boom')"
        record = _execute_tool(
            tool_name="run_python",
            arguments={"code": code, "intent": "测试异常"},
            cfg=cfg,
            registry=None,
            confirm=lambda intent, cmd: "confirmed",
            on_progress=None,
        )
        assert not record.success
        assert record.result_details is not None
        assert record.result_details.get("exit_code") != 0
        assert "ValueError" in record.result_details.get("stderr", "")
        assert "boom" in record.result_details.get("stderr", "")

    def test_run_python_empty_code(self) -> None:
        """空代码应失败。"""
        from lihua.config import Config
        cfg = Config.load()
        cfg.always_confirm_grey = True
        record = _execute_tool(
            tool_name="run_python",
            arguments={"code": "", "intent": "空代码"},
            cfg=cfg,
            registry=None,
            confirm=lambda intent, cmd: "confirmed",
            on_progress=None,
        )
        assert not record.success
        assert "code" in record.error.lower() or "空" in record.error

    def test_run_python_confirm_rejected(self) -> None:
        """用户拒绝 confirm 时不执行。"""
        from lihua.config import Config
        cfg = Config.load()
        cfg.always_confirm_grey = True
        record = _execute_tool(
            tool_name="run_python",
            arguments={"code": "print('should not run')", "intent": "测试拒绝"},
            cfg=cfg,
            registry=None,
            confirm=lambda intent, cmd: "denied",  # 用户拒绝
            on_progress=None,
        )
        assert not record.success
        assert record.result_details is not None
        # 实现里拒绝时标记 cancelled=True（safety_level 仍是 grey）
        assert record.result_details.get("cancelled") is True

    def test_run_python_no_confirm_callback(self) -> None:
        """无 confirm 回调时拒绝执行（强制走 confirm）。"""
        from lihua.config import Config
        cfg = Config.load()
        cfg.always_confirm_grey = True
        record = _execute_tool(
            tool_name="run_python",
            arguments={"code": "print(1)", "intent": "测试"},
            cfg=cfg,
            registry=None,
            confirm=None,
            on_progress=None,
        )
        assert not record.success
        assert "confirm" in record.error.lower() or "确认" in record.error

    def test_run_python_dry_run(self) -> None:
        """dry_run 模式不实际执行。"""
        from lihua.config import Config
        cfg = Config.load()
        cfg.always_confirm_grey = True
        record = _execute_tool(
            tool_name="run_python",
            arguments={"code": "print('dry')", "intent": "测试"},
            cfg=cfg,
            registry=None,
            confirm=lambda intent, cmd: "confirmed",
            on_progress=None,
            dry_run=True,
        )
        assert record.success
        assert "dry-run" in record.result_message.lower() or "dry" in record.result_message.lower()

    def test_run_python_timeout_clamped(self) -> None:
        """timeout 超过 300 秒会被截断到 300，代码仍能正常执行。"""
        from lihua.config import Config
        cfg = Config.load()
        cfg.always_confirm_grey = True
        record = _execute_tool(
            tool_name="run_python",
            arguments={"code": "print(1)", "intent": "测试", "timeout": 99999},
            cfg=cfg,
            registry=None,
            confirm=lambda intent, cmd: "confirmed",
            on_progress=None,
        )
        # 代码本身能跑完，timeout 不会触发
        assert record.success
        assert record.result_details is not None
        # timed_out 应为 False
        assert record.result_details.get("timed_out") is False

    def test_run_python_writes_audit_log(self, tmp_path, monkeypatch) -> None:
        """run_python 执行后应写审计日志。"""
        from lihua.config import Config
        import json as _json
        # 把审计日志重定向到 tmp_path
        fake_log = tmp_path / "audit.jsonl"
        monkeypatch.setattr("lihua.executor.audit_log_path", lambda: fake_log)

        cfg = Config.load()
        cfg.always_confirm_grey = True
        record = _execute_tool(
            tool_name="run_python",
            arguments={"code": "print('audit test')", "intent": "审计测试"},
            cfg=cfg,
            registry=None,
            confirm=lambda intent, cmd: "confirmed",
            on_progress=None,
        )
        assert record.success
        # 审计日志应该有内容
        assert fake_log.exists()
        lines = fake_log.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) >= 1
        entry = _json.loads(lines[-1])
        assert "run_python" in entry.get("command", "")
        assert entry.get("safety_level") == "grey"


class TestFormatToolResultForLLM:
    """工具结果格式化。"""

    def test_success_record(self) -> None:
        record = ToolCallRecord(
            tool_name="install_app",
            arguments={"target": "QQ"},
            success=True,
            result_message="QQ 已安装",
        )
        text = _format_tool_result_for_llm(record)
        assert "执行成功" in text
        assert "QQ 已安装" in text

    def test_failure_record(self) -> None:
        record = ToolCallRecord(
            tool_name="install_app",
            arguments={"target": "nonexistent"},
            success=False,
            error="包不存在",
        )
        text = _format_tool_result_for_llm(record)
        assert "执行失败" in text
        assert "包不存在" in text

    def test_with_steps(self) -> None:
        record = ToolCallRecord(
            tool_name="install_app",
            arguments={"target": "QQ"},
            success=True,
            result_message="完成",
            result_details={
                "steps": [
                    {"name": "resolve", "success": True, "skipped": False, "output": "found"},
                    {"name": "install", "success": True, "skipped": False, "output": "done"},
                ],
            },
        )
        text = _format_tool_result_for_llm(record)
        assert "resolve" in text
        assert "install" in text
        assert "✓" in text


class TestRunAgentNoLLM:
    """无 LLM 时的回退。"""

    def test_returns_error_when_llm_disabled(
        self, disabled_cfg: Config, registry: SkillRegistry
    ) -> None:
        resp = run_agent(
            user_text="装QQ",
            cfg=disabled_cfg,
            registry=registry,
        )
        assert not resp.success
        assert "LLM 未启用" in resp.error
        assert resp.tool_calls == []


class TestRunAgentWithMockLLM:
    """用 mock LLM 测试 Agent 主循环。"""

    def test_text_only_response(self, registry: SkillRegistry) -> None:
        """LLM 直接返回文本（不调用工具），Agent 返回该文本。"""
        cfg = Config.load()
        cfg.llm.enabled = True

        mock_resp = LLMResponse(
            text="你好，我是狸花猫，可以帮你装应用、切输入法、清缓存等。",
            model="mock",
            tool_calls=None,
            finish_reason="stop",
        )

        with patch("lihua.agent.call_llm_with_tools", return_value=mock_resp):
            resp = run_agent("你好", cfg, registry)

        assert resp.success
        assert "狸花猫" in resp.text
        assert resp.tool_calls == []

    def test_single_tool_call(self, registry: SkillRegistry) -> None:
        """LLM 调用一次工具后给出最终回复。"""
        cfg = Config.load()
        cfg.llm.enabled = True

        # 第一次调用：LLM 决定调用 cpu_monitor 工具
        first_resp = LLMResponse(
            text="",
            model="mock",
            tool_calls=[{
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "cpu_monitor",
                    "arguments": "{}",
                },
            }],
            finish_reason="tool_calls",
        )
        # 第二次调用：LLM 看到工具结果后给出最终回复
        second_resp = LLMResponse(
            text="当前 CPU 使用率正常。",
            model="mock",
            tool_calls=None,
            finish_reason="stop",
        )

        with patch("lihua.agent.call_llm_with_tools", side_effect=[first_resp, second_resp]):
            resp = run_agent("看下 CPU", cfg, registry)

        assert resp.success
        assert "CPU" in resp.text
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].tool_name == "cpu_monitor"

    def test_llm_error_handled(self, registry: SkillRegistry) -> None:
        """LLM 调用失败时返回 error。"""
        from lihua.router import LLMError

        cfg = Config.load()
        cfg.llm.enabled = True

        with patch("lihua.agent.call_llm_with_tools", side_effect=LLMError("network error")):
            resp = run_agent("装QQ", cfg, registry)

        assert not resp.success
        assert "LLM 调用失败" in resp.error
        assert "network error" in resp.error

    def test_unknown_tool_called(self, registry: SkillRegistry) -> None:
        """LLM 调用了不存在的工具，应该返回失败记录。"""
        cfg = Config.load()
        cfg.llm.enabled = True

        first_resp = LLMResponse(
            text="",
            model="mock",
            tool_calls=[{
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "nonexistent_tool_xyz",
                    "arguments": "{}",
                },
            }],
            finish_reason="tool_calls",
        )
        second_resp = LLMResponse(
            text="抱歉，这个操作我暂时不会。",
            model="mock",
            tool_calls=None,
            finish_reason="stop",
        )

        with patch("lihua.agent.call_llm_with_tools", side_effect=[first_resp, second_resp]):
            resp = run_agent("做点奇怪的事", cfg, registry)

        assert resp.success  # Agent 本身没崩
        assert len(resp.tool_calls) == 1
        assert not resp.tool_calls[0].success
        assert "不存在" in resp.tool_calls[0].error

    def test_max_iterations_limit(self, registry: SkillRegistry) -> None:
        """达到 max_iterations 时优雅退出。"""
        cfg = Config.load()
        cfg.llm.enabled = True

        # 每次都返回工具调用，模拟 LLM 死循环
        loop_resp = LLMResponse(
            text="",
            model="mock",
            tool_calls=[{
                "id": "call_x",
                "type": "function",
                "function": {
                    "name": "cpu_monitor",
                    "arguments": "{}",
                },
            }],
            finish_reason="tool_calls",
        )

        with patch("lihua.agent.call_llm_with_tools", return_value=loop_resp):
            resp = run_agent("看 CPU", cfg, registry, max_iterations=2)

        assert resp.success
        assert len(resp.tool_calls) == 2  # 达到 max_iterations
        assert "达到最大迭代次数" in resp.error

    def test_dry_run_mode(self, registry: SkillRegistry) -> None:
        """dry_run=True 时工具不实际执行。"""
        cfg = Config.load()
        cfg.llm.enabled = True

        first_resp = LLMResponse(
            text="",
            model="mock",
            tool_calls=[{
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "install_app",
                    "arguments": '{"target": "QQ"}',
                },
            }],
            finish_reason="tool_calls",
        )
        second_resp = LLMResponse(
            text="准备装 QQ。",
            model="mock",
            tool_calls=None,
            finish_reason="stop",
        )

        with patch("lihua.agent.call_llm_with_tools", side_effect=[first_resp, second_resp]):
            resp = run_agent("装QQ", cfg, registry, dry_run=True)

        assert resp.success
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].success
        assert "dry-run" in resp.tool_calls[0].result_message

    def test_multiple_tool_calls_in_one_response(self, registry: SkillRegistry) -> None:
        """LLM 一次返回多个 tool_calls，应该都执行。"""
        cfg = Config.load()
        cfg.llm.enabled = True

        first_resp = LLMResponse(
            text="",
            model="mock",
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "cpu_monitor", "arguments": "{}"},
                },
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {"name": "memory_monitor", "arguments": "{}"},
                },
            ],
            finish_reason="tool_calls",
        )
        second_resp = LLMResponse(
            text="CPU 和内存都正常。",
            model="mock",
            tool_calls=None,
            finish_reason="stop",
        )

        with patch("lihua.agent.call_llm_with_tools", side_effect=[first_resp, second_resp]):
            resp = run_agent("看下系统状态", cfg, registry)

        assert resp.success
        assert len(resp.tool_calls) == 2
        tool_names = [tc.tool_name for tc in resp.tool_calls]
        assert "cpu_monitor" in tool_names
        assert "memory_monitor" in tool_names

    def test_invalid_json_arguments(self, registry: SkillRegistry) -> None:
        """LLM 返回的 arguments 不是合法 JSON，应该容错处理。"""
        cfg = Config.load()
        cfg.llm.enabled = True

        first_resp = LLMResponse(
            text="",
            model="mock",
            tool_calls=[{
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "cpu_monitor",
                    "arguments": "not json {{{",
                },
            }],
            finish_reason="tool_calls",
        )
        second_resp = LLMResponse(
            text="好的",
            model="mock",
            tool_calls=None,
            finish_reason="stop",
        )

        with patch("lihua.agent.call_llm_with_tools", side_effect=[first_resp, second_resp]):
            resp = run_agent("看 CPU", cfg, registry)

        # 不应该崩溃
        assert resp.success
        assert len(resp.tool_calls) == 1
        # arguments 里应该有 _raw 字段（容错）
        assert "_raw" in resp.tool_calls[0].arguments


class TestAgentResponse:
    """AgentResponse 数据类。"""

    def test_matched_with_text(self) -> None:
        resp = AgentResponse(text="hello", success=True)
        assert resp.matched

    def test_matched_with_tool_calls(self) -> None:
        resp = AgentResponse(
            text="",
            tool_calls=[ToolCallRecord("test", {}, True)],
        )
        assert resp.matched

    def test_not_matched_empty(self) -> None:
        resp = AgentResponse(text="", tool_calls=[])
        assert not resp.matched


class TestRunAgentStreaming:
    """run_agent_streaming 流式生成器测试（v0.7.9）。"""

    def test_streaming_no_llm(self, disabled_cfg: Config, registry: SkillRegistry) -> None:
        """无 LLM 时第一个事件就是 error。"""
        events = list(run_agent_streaming("你好", disabled_cfg, registry))
        assert len(events) == 1
        assert events[0]["type"] == "error"
        assert "LLM 未启用" in events[0]["message"]

    def test_streaming_text_only(self, registry: SkillRegistry) -> None:
        """LLM 直接返回文本，事件流：start → iteration → text → done。"""
        cfg = Config.load()
        cfg.llm.enabled = True

        mock_resp = LLMResponse(
            text="你好呀",
            model="mock",
            tool_calls=None,
            finish_reason="stop",
        )

        with patch("lihua.agent.call_llm_with_tools", return_value=mock_resp):
            events = list(run_agent_streaming("你好", cfg, registry))

        types = [e["type"] for e in events]
        assert "start" in types
        assert "iteration" in types
        assert "text" in types
        assert types[-1] == "done"
        text_event = next(e for e in events if e["type"] == "text")
        assert text_event["content"] == "你好呀"
        done_event = events[-1]
        assert done_event["success"] is True
        assert done_event["text"] == "你好呀"
        assert done_event["tool_calls"] == []

    def test_streaming_with_tool_call(self, registry: SkillRegistry) -> None:
        """LLM 调用工具后给出最终回复，事件流包含 tool_call_start/end。"""
        cfg = Config.load()
        cfg.llm.enabled = True

        first_resp = LLMResponse(
            text="",
            model="mock",
            tool_calls=[{
                "id": "call_1",
                "type": "function",
                "function": {"name": "cpu_monitor", "arguments": "{}"},
            }],
            finish_reason="tool_calls",
        )
        second_resp = LLMResponse(
            text="CPU 正常",
            model="mock",
            tool_calls=None,
            finish_reason="stop",
        )

        with patch("lihua.agent.call_llm_with_tools", side_effect=[first_resp, second_resp]):
            events = list(run_agent_streaming("看 CPU", cfg, registry))

        types = [e["type"] for e in events]
        assert "tool_call_start" in types
        assert "tool_call_end" in types
        assert types[-1] == "done"

        start_event = next(e for e in events if e["type"] == "tool_call_start")
        assert start_event["name"] == "cpu_monitor"

        end_event = next(e for e in events if e["type"] == "tool_call_end")
        assert end_event["name"] == "cpu_monitor"
        assert "success" in end_event

        done_event = events[-1]
        assert len(done_event["tool_calls"]) == 1
        assert done_event["tool_calls"][0]["name"] == "cpu_monitor"

    def test_streaming_llm_error(self, registry: SkillRegistry) -> None:
        """LLM 调用失败时事件流以 error 结束。"""
        from lihua.router import LLMError

        cfg = Config.load()
        cfg.llm.enabled = True

        with patch("lihua.agent.call_llm_with_tools", side_effect=LLMError("network error")):
            events = list(run_agent_streaming("装QQ", cfg, registry))

        # start + iteration + error
        assert events[0]["type"] == "start"
        assert events[-1]["type"] == "error"
        assert "network error" in events[-1]["message"]

    def test_streaming_with_history(self, registry: SkillRegistry) -> None:
        """流式模式支持多轮对话历史。"""
        cfg = Config.load()
        cfg.llm.enabled = True

        # 用 side_effect 捕获每次调用时的 messages 快照（避免 list 引用被后续 append 污染）
        captured_messages_snapshots: list[list[dict]] = []

        def fake_call(cfg_, messages, tools=None, tool_choice="auto"):
            # 拷贝快照
            captured_messages_snapshots.append([dict(m) for m in messages])
            return LLMResponse(
                text="好的",
                model="mock",
                tool_calls=None,
                finish_reason="stop",
            )

        history = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好呀"},
        ]

        with patch("lihua.agent.call_llm_with_tools", side_effect=fake_call):
            events = list(run_agent_streaming("还有问题", cfg, registry, history=history))

        assert events[-1]["type"] == "done"
        # 应该只调用一次 LLM
        assert len(captured_messages_snapshots) == 1
        msgs = captured_messages_snapshots[0]
        # system + history[0] + history[1] + 当前 user = 4 条
        assert len(msgs) == 4
        assert msgs[0]["role"] == "system"
        assert msgs[1]["content"] == "你好"
        assert msgs[2]["content"] == "你好呀"
        assert msgs[3]["content"] == "还有问题"

    def test_streaming_max_iterations(self, registry: SkillRegistry) -> None:
        """达到 max_iterations 时优雅退出。"""
        cfg = Config.load()
        cfg.llm.enabled = True

        loop_resp = LLMResponse(
            text="",
            model="mock",
            tool_calls=[{
                "id": "call_x",
                "type": "function",
                "function": {"name": "cpu_monitor", "arguments": "{}"},
            }],
            finish_reason="tool_calls",
        )

        with patch("lihua.agent.call_llm_with_tools", return_value=loop_resp):
            events = list(run_agent_streaming("看 CPU", cfg, registry, max_iterations=2))

        # 应该有 2 个 tool_call_end 事件
        tool_ends = [e for e in events if e["type"] == "tool_call_end"]
        assert len(tool_ends) == 2
        assert events[-1]["type"] == "done"
