"""LLM Agent 主循环：LLM 主导 + 工具调用 + 多轮对话。

设计思路：
1. 用户输入 → LLM 决策（看工具列表选合适的 skill）
2. LLM 返回 tool_calls → 执行对应的 skill → 结果回传给 LLM
3. LLM 看到结果后继续决策（可能继续调用工具，或给出最终回复）
4. 重复直到 LLM 不再调用工具，返回最终文本回复

特点：
- 真正的智能助手：LLM 理解自然语言，不需要 trigger 关键词
- 支持多轮对话：LLM 可以追问澄清
- 支持组合任务：LLM 可以连续调用多个工具
- 安全：skill 执行时仍走 safety.py（黑名单 ban / 灰名单确认）
- 可降级：无 LLM 或 LLM 失败时回退到规则匹配（intent.understand）
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from lihua.config import Config
from lihua.intent import Intent
from lihua.logging_config import get_logger
from lihua.router import LLMError, call_llm_with_tools
from lihua.skill_runner import RunResult, run_skill
from lihua.skills import SkillRegistry
from lihua.tool_defs import build_tool_defs, build_tool_index

log = get_logger(__name__)


@dataclass
class ToolCallRecord:
    """一次工具调用的记录。"""

    tool_name: str
    arguments: dict[str, Any]
    success: bool
    result_message: str = ""
    result_details: dict[str, Any] | None = None
    error: str = ""


@dataclass
class AgentResponse:
    """Agent 执行结果。"""

    text: str = ""  # LLM 最终给用户的中文回复
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    success: bool = True
    error: str = ""
    raw_messages: list[dict[str, Any]] = field(default_factory=list)  # 完整对话历史（调试用）

    @property
    def matched(self) -> bool:
        """是否匹配到任何工具或给出了回复。"""
        return bool(self.tool_calls) or bool(self.text)


# 进度回调类型
ProgressCallback = Callable[[str, str], None]
# 确认回调类型（灰名单用）
# v0.8.6：返回值从 bool 改成 str，区分"用户取消"和"超时"
#   "confirmed"：用户点击确认
#   "denied"：用户点击取消
#   "timeout"：超时未响应
ConfirmCallback = Callable[[str, str], str]


def _execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    cfg: Config,
    registry: SkillRegistry,
    confirm: ConfirmCallback | None,
    on_progress: ProgressCallback | None,
    dry_run: bool = False,
    user_text: str = "",
) -> ToolCallRecord:
    """执行一个工具调用。

    v0.8.0 改造：
    - tool_name == "run_shell" → 走自由命令执行（_execute_run_shell）
    - 其他 tool_name → 走预定义 skill（run_skill）

    v0.8.2 改造：
    - tool_name == "read_file" / "write_file" / "edit_file" → 走文件操作（_execute_file_op）

    v0.8.3 改造：
    - tool_name == "run_python" → 走 Python 代码执行（_execute_run_python）
    """
    # v0.8.0: run_shell 万能兜底工具
    if tool_name == "run_shell":
        return _execute_run_shell(arguments, cfg, confirm, on_progress, dry_run)

    # v0.8.2: 文件操作工具
    if tool_name in ("read_file", "write_file", "edit_file"):
        return _execute_file_op(tool_name, arguments, cfg, confirm, on_progress, dry_run)

    # v0.8.3: run_python 万能兜底工具
    if tool_name == "run_python":
        return _execute_run_python(arguments, cfg, confirm, on_progress, dry_run)

    # v0.8.7: read_log 日志查看工具（自我诊断）
    if tool_name == "read_log":
        import time as _t
        return _execute_read_log(arguments, on_progress, dry_run, _t.perf_counter())

    # v0.8.9: 自进化工具——重启后端 / 编译桌面端 / 查状态
    if tool_name == "self_restart":
        import time as _t
        return _execute_self_restart(arguments, cfg, confirm, on_progress, dry_run, _t.perf_counter())
    if tool_name == "self_build":
        import time as _t
        return _execute_self_build(arguments, cfg, confirm, on_progress, dry_run, _t.perf_counter())
    if tool_name == "self_status":
        import time as _t
        return _execute_self_status(arguments, on_progress, dry_run, _t.perf_counter())
    if tool_name == "self_version_bump":
        import time as _t
        return _execute_self_version_bump(arguments, cfg, confirm, on_progress, dry_run, _t.perf_counter())

    # v0.8.11: 记忆系统——检索历史经验（只读）
    if tool_name == "memory_recall":
        import time as _t
        return _execute_memory_recall(arguments, on_progress, dry_run, _t.perf_counter())

    # v0.8.12: 技能自生成——把工具链固化成 YAML 技能（走 confirm）
    if tool_name == "create_skill":
        import time as _t
        return _execute_create_skill(arguments, cfg, confirm, on_progress, dry_run, _t.perf_counter())

    # v0.8.15: 自监控分析——LLM 自省，查看自己的运行数据（只读）
    if tool_name == "self_analyze":
        return _execute_self_analyze(arguments, on_progress, dry_run)
    # v0.8.17: Skill 规则提升——从 usage_log 提炼规则写入 skill YAML
    if tool_name == "skill_evolve":
        import time as _t
        return _execute_skill_evolve(arguments, cfg, confirm, on_progress, dry_run, _t.perf_counter())
    # v0.8.17: 记忆归档——把旧 episodes 移到 archive/ 目录
    if tool_name == "memory_archive":
        import time as _t
        return _execute_memory_archive(arguments, on_progress, dry_run, _t.perf_counter())
    # v0.8.18: 踩坑记录——trap_search（只读）/ trap_update（走 confirm）
    if tool_name == "trap_search":
        import time as _t
        return _execute_trap_search(arguments, on_progress, dry_run, _t.perf_counter())
    if tool_name == "trap_update":
        import time as _t
        return _execute_trap_update(arguments, cfg, confirm, on_progress, dry_run, _t.perf_counter())

    import time as _time
    t0 = _time.perf_counter()
    log.info(f"调用工具 {tool_name}", extra={"arguments": arguments, "dry_run": dry_run})
    tool_index = build_tool_index(registry)
    skill = tool_index.get(tool_name)
    if not skill:
        log.warning(f"工具不存在：{tool_name}")
        return ToolCallRecord(
            tool_name=tool_name,
            arguments=arguments,
            success=False,
            error=f"工具不存在：{tool_name}",
        )

    if on_progress:
        on_progress(tool_name, f"调用工具 {tool_name}")

    # 构造 Intent 对象，调用 run_skill
    params = {k: str(v) if v is not None else "" for k, v in arguments.items()}
    intent = Intent(
        skill_name=tool_name,
        params=params,
        raw_text=f"[agent] {tool_name}({arguments})",
        source="agent",
        confidence=1.0,
        skill=skill,
        explanation=f"Agent 调用 {tool_name}",
    )

    if dry_run:
        log.debug(f"dry-run 工具 {tool_name} 参数 {arguments}")
        return ToolCallRecord(
            tool_name=tool_name,
            arguments=arguments,
            success=True,
            result_message=f"[dry-run] 工具 {tool_name} 参数 {arguments}",
        )

    try:
        result: RunResult = run_skill(
            intent, cfg, confirm=confirm, on_progress=on_progress,
            user_input=user_text or None,  # v0.8.16: 传用户原始输入给 usage_log
        )
        elapsed = _time.perf_counter() - t0
        details = {
            "final_message": result.final_message,
            "success": result.success,
            "steps_count": len(result.steps),
            "steps": [
                {
                    "name": sr.step.name,
                    "type": sr.step.type,
                    "success": sr.success,
                    "skipped": sr.skipped,
                    "output": (sr.output or "")[:500],
                    "error": sr.error or "",
                }
                for sr in result.steps
            ],
        }
        log.info(
            f"工具 {tool_name} {'成功' if result.success else '失败'}（{elapsed:.2f}s）",
            extra={"steps": len(result.steps), "final": result.final_message[:200]},
        )
        return ToolCallRecord(
            tool_name=tool_name,
            arguments=arguments,
            success=result.success,
            result_message=result.final_message,
            result_details=details,
            error="" if result.success else result.final_message,
        )
    except Exception as e:  # noqa: BLE001
        log.exception(f"工具 {tool_name} 执行异常：{e}")
        return ToolCallRecord(
            tool_name=tool_name,
            arguments=arguments,
            success=False,
            error=f"工具执行异常: {e}",
        )


def _execute_run_shell(
    arguments: dict[str, Any],
    cfg: Config,
    confirm: ConfirmCallback | None,
    on_progress: ProgressCallback | None,
    dry_run: bool = False,
) -> ToolCallRecord:
    """v0.8.0 新增：执行 LLM 生成的任意 shell 命令。

    v0.8.1 改造：
    - 加 cwd 控制：默认在用户主目录执行，避免 LLM 在 / 乱搞
    - 加 max_calls 限制：由调用方传入，超限直接拒绝（防 LLM 无限循环）

    流程：
    1. 提取 command / intent / timeout 参数
    2. 走 safety.py 分类
    3. 黑名单 → 拒绝
    4. 灰名单 → 交互式 confirm（intent + command 给用户看）
    5. 执行（execute_safely 会写审计日志）—— v0.8.1 在用户主目录执行
    6. 完整 stdout/stderr 回传 LLM（截断防爆 token）

    安全保证：
    - 黑名单由 safety.py 拦截（rm -rf /、dd、mkfs、curl|sh、find / -delete 等）
    - 灰名单由 confirm 拦截（sudo/pkexec、apt purge、改 /etc 等）
    - 白名单自动执行（ls/cat/grep/find/ps/df/echo 等只读/无害命令）
    - timeout 上限 600s，防止 LLM 调 sleep 10000
    - v0.8.1: 默认 cwd = 用户主目录，LLM 要操作系统目录必须显式 cd 或用绝对路径
    """
    import os as _os
    import time as _time
    from lihua.executor import ExecOptions, execute_safely
    from lihua.safety import classify

    t0 = _time.perf_counter()

    cmd = str(arguments.get("command", "")).strip()
    intent = str(arguments.get("intent", "")).strip()
    try:
        # v0.8.6：默认 300s（5 分钟）。原 60s 对 apt install / pip install 太短
        # 上限 1800s（30 分钟），覆盖大型下载/编译场景
        timeout_arg = int(arguments.get("timeout", 300))
    except (TypeError, ValueError):
        timeout_arg = 300
    timeout = max(1, min(timeout_arg, 1800))  # 1s ~ 1800s

    # v0.8.1: 默认 cwd = 用户主目录（避免 LLM 在 / 或其他系统目录乱搞）
    # 如果命令里显式有 cd /xxx，shell 会切换目录，这是 LLM 的主动选择
    default_cwd = _os.path.expanduser("~")

    log.info(f"调用 run_shell", extra={
        "command": cmd[:200], "intent": intent, "timeout": timeout,
        "dry_run": dry_run, "cwd": default_cwd,
    })

    if not cmd:
        return ToolCallRecord(
            tool_name="run_shell",
            arguments=arguments,
            success=False,
            error="command 参数为空",
            result_message="❌ 命令为空",
        )

    if on_progress:
        on_progress("run_shell", f"执行：{cmd[:80]}")

    if dry_run:
        return ToolCallRecord(
            tool_name="run_shell",
            arguments=arguments,
            success=True,
            result_message=f"[dry-run] 会执行：{cmd}",
        )

    # 安全分类
    decision = classify(cmd)
    if decision.level == "black":
        log.warning(f"run_shell 被黑名单拒绝：{decision.reason}", extra={"command": cmd[:200]})
        return ToolCallRecord(
            tool_name="run_shell",
            arguments=arguments,
            success=False,
            error=f"安全引擎拒绝：{decision.reason}",
            result_message=f"❌ 拒绝执行：{decision.human_message or decision.reason}",
            result_details={
                "safety_level": "black",
                "rule": decision.rule,
                "command": cmd,
            },
        )

    # 灰名单 → 交互式确认
    if decision.level == "grey":
        # 确认信息：LLM 的中文 intent + 原始命令 + 安全引擎的人类语言描述
        confirm_parts = []
        if intent:
            confirm_parts.append(intent)
        elif decision.human_message:
            confirm_parts.append(decision.human_message)
        else:
            confirm_parts.append("需要执行一条命令")
        confirm_parts.append(f"\n命令：{cmd}")
        msg = "\n".join(confirm_parts)

        if cfg.always_confirm_grey:
            if confirm is None:
                log.warning("run_shell 灰名单但无 confirm_cb，拒绝")
                return ToolCallRecord(
                    tool_name="run_shell",
                    arguments=arguments,
                    success=False,
                    error="需要确认但未提供确认回调",
                    result_message="❌ 需要确认但未提供确认回调",
                    result_details={
                        "safety_level": "grey",
                        "command": cmd,
                        "needs_confirm": True,
                    },
                )
            confirm_decision = confirm(msg, cmd)
            if confirm_decision != "confirmed":
                # v0.8.6：区分"用户取消"和"超时"
                is_timeout = confirm_decision == "timeout"
                log.info(f"run_shell {'超时' if is_timeout else '用户取消'}：{cmd[:100]}")
                return ToolCallRecord(
                    tool_name="run_shell",
                    arguments=arguments,
                    success=False,
                    error="确认超时" if is_timeout else "用户取消",
                    result_message="❌ 确认超时（10 分钟内未响应）" if is_timeout else "❌ 用户取消了执行",
                    result_details={
                        "safety_level": "grey",
                        "command": cmd,
                        "cancelled": True,
                        "timeout": is_timeout,
                    },
                )

    # 执行——v0.8.1: 在用户主目录执行
    opts = ExecOptions(shell=True, timeout=float(timeout), audit=True, cwd=default_cwd)
    r = execute_safely(cmd, opts)
    elapsed = _time.perf_counter() - t0

    log.info(
        f"run_shell {'成功' if r.success else '失败'}（{elapsed:.2f}s, exit={r.exit_code}）",
        extra={
            "command": cmd[:200],
            "stdout_len": len(r.stdout),
            "stderr_len": len(r.stderr),
            "safety": decision.level,
            "cwd": default_cwd,
        },
    )

    # 给 LLM 看的 result_message：成功时取 stdout 尾部，失败时取 stderr
    if r.success:
        result_msg = r.short_output(max_lines=30) or "(命令执行成功，无输出)"
    else:
        result_msg = f"exit={r.exit_code}" + (f"\n{r.stderr}" if r.stderr else "")

    # result_details：完整 stdout/stderr（截断防爆 token）+ 安全级别 + exit_code + cwd
    details = {
        "success": r.success,
        "exit_code": r.exit_code,
        "stdout": r.stdout[:4000],  # 防止超长输出爆 token
        "stderr": r.stderr[:2000],
        "duration": round(r.duration, 3),
        "safety_level": decision.level,
        "safety_reason": decision.reason,
        "timed_out": r.timed_out,
        "command": cmd,
        "cwd": default_cwd,  # v0.8.1: 告诉 LLM 当前工作目录
    }

    return ToolCallRecord(
        tool_name="run_shell",
        arguments=arguments,
        success=r.success,
        result_message=result_msg,
        result_details=details,
        error="" if r.success else (r.stderr or f"exit={r.exit_code}"),
    )


# v0.8.1: run_shell 速率限制——单次对话最多调用 30 次，防止 LLM 无限循环
# v0.8.7: 从 15 提升到 30——诊断场景需要多次跑命令（看日志、查进程、读配置）
MAX_RUN_SHELL_CALLS = 30

# v0.8.3: run_python 速率限制——比 run_shell 更严（Python 能做更多事，单次对话最多 10 次）
MAX_RUN_PYTHON_CALLS = 10


def _execute_run_python(
    arguments: dict[str, Any],
    cfg: Config,
    confirm: ConfirmCallback | None,
    on_progress: ProgressCallback | None,
    dry_run: bool = False,
) -> ToolCallRecord:
    """v0.8.3 新增：执行 LLM 生成的 Python 3 代码。

    流程：
    1. 提取 code / intent / timeout 参数
    2. 走灰名单 confirm（Python 代码能做任何事，必须用户确认）
    3. 用 venv 的 python（sys.executable）跑代码，stdin 传 code（避免 shell 转义）
    4. 完整 stdout/stderr/exit_code 回传 LLM（截断防爆 token）
    5. 写审计日志（记录代码前 500 字符 + intent）

    安全保证：
    - 不走 safety.py（Python 代码不是 shell 命令，没法用正则分类）
    - 强制走 confirm——用户看到 intent + 代码预览（前 500 字符）才决定
    - timeout 上限 300s，防止 LLM 写死循环
    - 默认 cwd = 用户主目录
    - 用 venv 的 python（能 import 已装的库，但不会污染系统 python）

    为什么不用沙箱：
    - 沙箱化是 v0.9 的事（bwrap/firejail）
    - 当前阶段信任 LLM + 用户 confirm，速率限制防无限循环
    """
    import os as _os
    import subprocess as _sp
    import sys as _sys
    import time as _time
    from lihua.executor import write_audit, AuditEntry

    t0 = _time.perf_counter()

    code = str(arguments.get("code", ""))
    intent = str(arguments.get("intent", "")).strip()
    try:
        timeout_arg = int(arguments.get("timeout", 30))
    except (TypeError, ValueError):
        timeout_arg = 30
    timeout = max(1, min(timeout_arg, 300))  # 1s ~ 300s

    # v0.8.3: 默认 cwd = 用户主目录
    default_cwd = _os.path.expanduser("~")

    log.info(f"调用 run_python", extra={
        "code_len": len(code), "intent": intent, "timeout": timeout,
        "dry_run": dry_run, "cwd": default_cwd,
    })

    if not code.strip():
        return ToolCallRecord(
            tool_name="run_python",
            arguments=arguments,
            success=False,
            error="code 参数为空",
            result_message="❌ 代码为空",
        )

    if on_progress:
        on_progress("run_python", f"执行 Python：{intent[:60] or '无意图'}")

    if dry_run:
        return ToolCallRecord(
            tool_name="run_python",
            arguments=arguments,
            success=True,
            result_message=f"[dry-run] 会执行 Python 代码（{len(code)} 字符）：{intent}",
        )

    # 强制走 confirm——Python 代码能做任何事，必须用户确认
    if cfg.always_confirm_grey:
        # 构造确认信息：intent + 代码预览（前 500 字符）
        code_preview = code if len(code) <= 500 else code[:500] + f"\n... (共 {len(code)} 字符，已截断)"
        confirm_parts = []
        if intent:
            confirm_parts.append(intent)
        else:
            confirm_parts.append("需要执行一段 Python 代码")
        confirm_parts.append(f"\n代码（{len(code)} 字符）：\n```python\n{code_preview}\n```")
        msg = "\n".join(confirm_parts)

        if confirm is None:
            log.warning("run_python 无 confirm_cb，拒绝")
            return ToolCallRecord(
                tool_name="run_python",
                arguments=arguments,
                success=False,
                error="需要确认但未提供确认回调",
                result_message="❌ 需要确认但未提供确认回调",
                result_details={
                    "safety_level": "grey",
                    "needs_confirm": True,
                },
            )
        confirm_decision = confirm(msg, code)
        if confirm_decision != "confirmed":
            # v0.8.6：区分"用户取消"和"超时"
            is_timeout = confirm_decision == "timeout"
            log.info(f"run_python {'超时' if is_timeout else '用户取消'}：{intent[:100]}")
            return ToolCallRecord(
                tool_name="run_python",
                arguments=arguments,
                success=False,
                error="确认超时" if is_timeout else "用户取消",
                result_message="❌ 确认超时（10 分钟内未响应）" if is_timeout else "❌ 用户取消了执行",
                result_details={
                    "safety_level": "grey",
                    "cancelled": True,
                    "timeout": is_timeout,
                },
            )

    # 执行——用 venv 的 python，通过 stdin 传代码（避免 shell 转义问题）
    try:
        proc = _sp.run(
            [_sys.executable, "-"],  # 从 stdin 读代码
            input=code,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=default_cwd,
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        exit_code = proc.returncode
        timed_out = False
        success = exit_code == 0
    except _sp.TimeoutExpired as e:
        stdout = e.stdout or "" if isinstance(e.stdout, str) else (e.stdout.decode("utf-8", errors="replace") if e.stdout else "")
        stderr = (e.stderr or "") if isinstance(e.stderr, str) else (e.stderr.decode("utf-8", errors="replace") if e.stderr else "")
        stderr = (stderr + f"\n⏱️ 超时（{timeout}s）被强制终止").strip()
        exit_code = -1
        timed_out = True
        success = False
    except Exception as e:
        stdout = ""
        stderr = f"执行异常：{e}"
        exit_code = -2
        timed_out = False
        success = False

    elapsed = _time.perf_counter() - t0

    log.info(
        f"run_python {'成功' if success else '失败'}（{elapsed:.2f}s, exit={exit_code}）",
        extra={
            "code_len": len(code),
            "stdout_len": len(stdout),
            "stderr_len": len(stderr),
            "cwd": default_cwd,
        },
    )

    # 写审计日志（v0.8.3: 不走 execute_safely，需要手动写）
    try:
        write_audit(AuditEntry(
            timestamp=_time.time(),
            command=f"run_python: {intent or '(无意图)'}\n{code[:500]}",
            safety_level="grey",  # Python 代码统一标记为 grey
            success=success,
            exit_code=exit_code,
            duration=elapsed,
            user_input=intent,
            decision_reason="run_python 工具，用户已确认",
        ))
    except Exception as audit_err:
        log.warning(f"run_python 审计日志写入失败：{audit_err}")

    # 给 LLM 看的 result_message
    if success:
        # 成功时取 stdout 尾部 30 行
        out_lines = stdout.splitlines()
        if len(out_lines) > 30:
            result_msg = "...\n" + "\n".join(out_lines[-30:])
        else:
            result_msg = stdout or "(代码执行成功，无输出)"
    else:
        # 失败时取 stderr
        result_msg = f"exit={exit_code}" + (f"\n{stderr}" if stderr else "")

    # result_details：完整 stdout/stderr（截断防爆 token）+ exit_code + cwd
    details = {
        "success": success,
        "exit_code": exit_code,
        "stdout": stdout[:4000],  # 防止超长输出爆 token
        "stderr": stderr[:2000],
        "duration": round(elapsed, 3),
        "safety_level": "grey",  # Python 代码统一标记为 grey
        "timed_out": timed_out,
        "code_length": len(code),
        "cwd": default_cwd,
        "python": _sys.executable,  # 告诉 LLM 用的哪个 python
    }

    return ToolCallRecord(
        tool_name="run_python",
        arguments=arguments,
        success=success,
        result_message=result_msg,
        result_details=details,
        error="" if success else (stderr or f"exit={exit_code}"),
    )


def _is_path_in_home(path: str) -> bool:
    """v0.8.2: 检查路径是否在用户主目录内（防止 LLM 改系统文件）。

    write_file / edit_file 只允许在 ~ 下操作。
    """
    import os as _os
    abs_path = _os.path.abspath(_os.path.expanduser(path))
    home = _os.path.expanduser("~")
    return abs_path == home or abs_path.startswith(home + _os.sep)


def _execute_file_op(
    tool_name: str,
    arguments: dict[str, Any],
    cfg: Config,
    confirm: ConfirmCallback | None,
    on_progress: ProgressCallback | None,
    dry_run: bool = False,
) -> ToolCallRecord:
    """v0.8.2 新增：执行文件操作工具（read_file / write_file / edit_file）。

    设计原则：
    - read_file：只读，不走 confirm，自动带行号，长文件截断 200 行
    - write_file：覆盖模式，走 confirm，路径必须在 ~ 下，自动 mkdir -p
    - edit_file：精确替换，走 confirm，old_string 必须唯一存在，路径必须在 ~ 下

    安全保证：
    - write_file / edit_file 路径必须在用户主目录内（防 LLM 改 /etc /usr 等）
    - write_file / edit_file 走灰名单 confirm（用户看到 intent + 路径 + 内容预览）
    - read_file 无路径限制（只读，可以读 /etc/nginx/nginx.conf 等）
    """
    import os as _os
    import time as _time

    t0 = _time.perf_counter()

    if tool_name == "read_file":
        return _execute_read_file(arguments, on_progress, dry_run, t0)
    if tool_name == "write_file":
        return _execute_write_file(arguments, cfg, confirm, on_progress, dry_run, t0)
    if tool_name == "edit_file":
        return _execute_edit_file(arguments, cfg, confirm, on_progress, dry_run, t0)

    return ToolCallRecord(
        tool_name=tool_name,
        arguments=arguments,
        success=False,
        error=f"未知文件操作：{tool_name}",
    )


def _execute_read_log(
    arguments: dict[str, Any],
    on_progress: ProgressCallback | None,
    dry_run: bool,
    t0: float,
) -> ToolCallRecord:
    """v0.8.7: 读日志文件——自我诊断的利器。

    读 Lihua 自己的日志（默认 ~/.local/share/lihua/lihua.log）或系统日志，
    支持按 level 过滤、读最后 N 行。

    不走 confirm（只读操作）。
    """
    import os as _os
    import time as _time
    from collections import deque

    # 参数解析
    try:
        lines = max(1, min(int(arguments.get("lines", 100)), 500))
    except (TypeError, ValueError):
        lines = 100
    level = str(arguments.get("level", "")).strip().upper()
    if level and level not in ("ERROR", "WARNING", "INFO", "DEBUG"):
        level = ""  # 无效值视为不过滤
    log_file = str(arguments.get("log_file", "")).strip()
    if not log_file:
        log_file = "~/.local/share/lihua/lihua.log"
    abs_path = _os.path.abspath(_os.path.expanduser(log_file))

    if on_progress:
        on_progress("read_log", f"读日志：{abs_path}（最后 {lines} 行{f'，过滤 {level}' if level else ''}）")

    if dry_run:
        return ToolCallRecord(
            tool_name="read_log",
            arguments=arguments,
            success=True,
            result_message=f"[dry-run] 会读 {abs_path} 最后 {lines} 行" + (f"，过滤 {level}" if level else ""),
        )

    if not _os.path.exists(abs_path):
        return ToolCallRecord(
            tool_name="read_log",
            arguments=arguments,
            success=False,
            error=f"日志文件不存在：{abs_path}",
            result_message=f"❌ 日志文件不存在：{abs_path}",
        )

    if _os.path.isdir(abs_path):
        return ToolCallRecord(
            tool_name="read_log",
            arguments=arguments,
            success=False,
            error=f"是目录不是文件：{abs_path}",
            result_message=f"❌ 是目录：{abs_path}",
        )

    try:
        # 高效读最后 N 行（deque(maxlen=lines)）
        # 如果指定 level，过滤
        # Lihua 日志格式：{"ts": "...", "level": "INFO", ...}，level 在 JSON 字段里
        # 系统日志格式：Jul 20 23:24:20 host process[pid]: message，level 不一定有
        last_lines: deque[str] = deque(maxlen=lines)
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.rstrip("\n")
                if level:
                    # 简单关键字匹配——覆盖 JSON 格式（"level": "ERROR"）和普通格式
                    if f'"level": "{level}"' not in line and f' {level} ' not in line:
                        continue
                last_lines.append(line)

        # 加行号显示
        # 行号基于"过滤后的最后 N 行"重新编号，避免行号过大
        numbered = []
        for i, line in enumerate(last_lines, start=1):
            numbered.append(f"{i:>5}→{line}")

        content = "\n".join(numbered)
        total_shown = len(numbered)
        elapsed = _time.perf_counter() - t0

        header = f"📄 {abs_path}（最后 {total_shown} 行"
        if level:
            header += f"，过滤 {level}"
        header += f"，{elapsed:.2f}s）\n"

        log.info(
            f"read_log 成功：{abs_path}（{total_shown}/{lines} 行"
            f"{f'，过滤 {level}' if level else ''}，{elapsed:.3f}s）"
        )

        return ToolCallRecord(
            tool_name="read_log",
            arguments=arguments,
            success=True,
            result_message=header + (content or "(空)"),
            result_details={
                "path": abs_path,
                "lines_requested": lines,
                "lines_shown": total_shown,
                "level_filter": level or None,
                "size": _os.path.getsize(abs_path),
            },
        )
    except PermissionError as e:
        return ToolCallRecord(
            tool_name="read_log",
            arguments=arguments,
            success=False,
            error=f"权限不足：{e}",
            result_message=f"❌ 权限不足：{abs_path}（系统日志可能需要 sudo，用 run_shell + sudo journalctl 替代）",
        )
    except OSError as e:
        return ToolCallRecord(
            tool_name="read_log",
            arguments=arguments,
            success=False,
            error=f"读取失败：{e}",
            result_message=f"❌ 读取失败：{e}",
        )


def _execute_read_file(
    arguments: dict[str, Any],
    on_progress: ProgressCallback | None,
    dry_run: bool,
    t0: float,
) -> ToolCallRecord:
    """v0.8.2: 读文件——带行号，长文件截断 200 行。"""
    import os as _os
    import time as _time

    path = str(arguments.get("path", "")).strip()
    try:
        start_line = max(1, int(arguments.get("start_line", 1)))
    except (TypeError, ValueError):
        start_line = 1
    try:
        end_line = int(arguments.get("end_line", 0))
    except (TypeError, ValueError):
        end_line = 0

    if not path:
        return ToolCallRecord(
            tool_name="read_file",
            arguments=arguments,
            success=False,
            error="path 参数为空",
            result_message="❌ 路径为空",
        )

    abs_path = _os.path.abspath(_os.path.expanduser(path))

    if on_progress:
        on_progress("read_file", f"读取：{abs_path}")

    if dry_run:
        return ToolCallRecord(
            tool_name="read_file",
            arguments=arguments,
            success=True,
            result_message=f"[dry-run] 会读取：{abs_path}",
        )

    if not _os.path.exists(abs_path):
        return ToolCallRecord(
            tool_name="read_file",
            arguments=arguments,
            success=False,
            error=f"文件不存在：{abs_path}",
            result_message=f"❌ 文件不存在：{abs_path}",
        )

    if _os.path.isdir(abs_path):
        return ToolCallRecord(
            tool_name="read_file",
            arguments=arguments,
            success=False,
            error=f"是目录不是文件：{abs_path}",
            result_message=f"❌ 是目录：{abs_path}",
        )

    try:
        # 检测二进制文件
        with open(abs_path, "rb") as f:
            raw = f.read(2048)
        if b"\x00" in raw:
            return ToolCallRecord(
                tool_name="read_file",
                arguments=arguments,
                success=True,
                result_message=f"⚠️ 二进制文件，不显示内容：{abs_path}（size={_os.path.getsize(abs_path)} bytes）",
                result_details={
                    "path": abs_path,
                    "is_binary": True,
                    "size": _os.path.getsize(abs_path),
                },
            )

        # 读取文本（自动检测编码）
        for encoding in ("utf-8", "gbk", "latin-1"):
            try:
                with open(abs_path, "r", encoding=encoding) as f:
                    all_lines = f.readlines()
                break
            except UnicodeDecodeError:
                continue
        else:
            return ToolCallRecord(
                tool_name="read_file",
                arguments=arguments,
                success=False,
                error="无法解码文件（不是 UTF-8/GBK/Latin-1）",
                result_message="❌ 无法解码文件",
            )

        total_lines = len(all_lines)
        # 截断到 200 行（防 token 爆炸）
        max_lines = 200
        if end_line <= 0 or end_line > total_lines:
            end_line = total_lines
        end_line = min(end_line, start_line + max_lines - 1)

        selected = all_lines[max(0, start_line - 1):end_line]
        # 带行号输出
        numbered = []
        for i, line in enumerate(selected, start=start_line):
            numbered.append(f"{i:>5}→{line.rstrip()}")

        content = "\n".join(numbered)
        if end_line < total_lines:
            content += f"\n\n（显示 {start_line}-{end_line} 行，共 {total_lines} 行，用 start_line={end_line + 1} 继续读）"

        elapsed = _time.perf_counter() - t0
        log.info(f"read_file 成功：{abs_path}（{len(selected)}/{total_lines} 行，{elapsed:.3f}s）")

        return ToolCallRecord(
            tool_name="read_file",
            arguments=arguments,
            success=True,
            result_message=content or "(空文件)",
            result_details={
                "path": abs_path,
                "total_lines": total_lines,
                "shown_lines": [start_line, end_line],
                "size": _os.path.getsize(abs_path),
                "is_binary": False,
            },
        )
    except PermissionError as e:
        return ToolCallRecord(
            tool_name="read_file",
            arguments=arguments,
            success=False,
            error=f"权限不足：{e}",
            result_message=f"❌ 权限不足：{abs_path}",
        )
    except OSError as e:
        return ToolCallRecord(
            tool_name="read_file",
            arguments=arguments,
            success=False,
            error=f"读取失败：{e}",
            result_message=f"❌ 读取失败：{e}",
        )


def _execute_write_file(
    arguments: dict[str, Any],
    cfg: Config,
    confirm: ConfirmCallback | None,
    on_progress: ProgressCallback | None,
    dry_run: bool,
    t0: float,
) -> ToolCallRecord:
    """v0.8.2: 写文件——覆盖模式，路径必须在 ~ 下，走 confirm。"""
    import os as _os
    import time as _time

    path = str(arguments.get("path", "")).strip()
    content = str(arguments.get("content", ""))
    intent = str(arguments.get("intent", "")).strip()

    if not path:
        return ToolCallRecord(
            tool_name="write_file",
            arguments=arguments,
            success=False,
            error="path 参数为空",
            result_message="❌ 路径为空",
        )

    abs_path = _os.path.abspath(_os.path.expanduser(path))

    # 路径限制：必须在用户主目录内
    if not _is_path_in_home(abs_path):
        return ToolCallRecord(
            tool_name="write_file",
            arguments=arguments,
            success=False,
            error=f"路径不在用户主目录内：{abs_path}（write_file 只允许写 ~ 下，系统目录请用 run_shell + pkexec）",
            result_message=f"❌ 路径越界：{abs_path} 不在用户主目录内",
            result_details={"path": abs_path, "in_home": False},
        )

    if on_progress:
        on_progress("write_file", f"写入：{abs_path}")

    if dry_run:
        return ToolCallRecord(
            tool_name="write_file",
            arguments=arguments,
            success=True,
            result_message=f"[dry-run] 会写入：{abs_path}（{len(content)} 字符）",
        )

    # 走 confirm（写文件是不可逆操作）
    file_exists = _os.path.exists(abs_path)
    confirm_parts = []
    if intent:
        confirm_parts.append(intent)
    else:
        confirm_parts.append("写入文件")
    confirm_parts.append(f"\n路径：{abs_path}")
    if file_exists:
        confirm_parts.append(f"⚠️ 文件已存在，会被覆盖（原大小 {_os.path.getsize(abs_path)} bytes）")
    confirm_parts.append(f"新内容大小：{len(content)} 字符")
    # 内容预览（前 200 字符）
    preview = content[:200]
    if len(content) > 200:
        preview += "..."
    confirm_parts.append(f"\n内容预览：\n{preview}")
    msg = "\n".join(confirm_parts)

    if cfg.always_confirm_grey:
        if confirm is None:
            return ToolCallRecord(
                tool_name="write_file",
                arguments=arguments,
                success=False,
                error="需要确认但未提供确认回调",
                result_message="❌ 需要确认但未提供确认回调",
                result_details={"path": abs_path, "needs_confirm": True},
            )
        confirm_decision = confirm(msg, f"write_file: {abs_path}")
        if confirm_decision != "confirmed":
            # v0.8.6：区分"用户取消"和"超时"
            is_timeout = confirm_decision == "timeout"
            return ToolCallRecord(
                tool_name="write_file",
                arguments=arguments,
                success=False,
                error="确认超时" if is_timeout else "用户取消",
                result_message="❌ 确认超时（10 分钟内未响应）" if is_timeout else "❌ 用户取消了写入",
                result_details={"path": abs_path, "cancelled": True, "timeout": is_timeout},
            )

    try:
        # 自动创建父目录
        parent = _os.path.dirname(abs_path)
        if parent and not _os.path.exists(parent):
            _os.makedirs(parent, exist_ok=True)

        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)

        elapsed = _time.perf_counter() - t0
        log.info(f"write_file 成功：{abs_path}（{len(content)} 字符，{elapsed:.3f}s）")

        return ToolCallRecord(
            tool_name="write_file",
            arguments=arguments,
            success=True,
            result_message=f"✅ 已写入：{abs_path}（{len(content)} 字符）",
            result_details={
                "path": abs_path,
                "size": len(content),
                "created_parent_dir": not _os.path.exists(parent) if parent else False,
                "overwrote": file_exists,
            },
        )
    except PermissionError as e:
        return ToolCallRecord(
            tool_name="write_file",
            arguments=arguments,
            success=False,
            error=f"权限不足：{e}",
            result_message=f"❌ 权限不足：{abs_path}",
        )
    except OSError as e:
        return ToolCallRecord(
            tool_name="write_file",
            arguments=arguments,
            success=False,
            error=f"写入失败：{e}",
            result_message=f"❌ 写入失败：{e}",
        )


def _execute_edit_file(
    arguments: dict[str, Any],
    cfg: Config,
    confirm: ConfirmCallback | None,
    on_progress: ProgressCallback | None,
    dry_run: bool,
    t0: float,
) -> ToolCallRecord:
    """v0.8.2: 编辑文件——old_string → new_string 精确替换，路径必须在 ~ 下。"""
    import os as _os
    import time as _time

    path = str(arguments.get("path", "")).strip()
    old_string = str(arguments.get("old_string", ""))
    new_string = str(arguments.get("new_string", ""))
    intent = str(arguments.get("intent", "")).strip()

    if not path:
        return ToolCallRecord(
            tool_name="edit_file",
            arguments=arguments,
            success=False,
            error="path 参数为空",
            result_message="❌ 路径为空",
        )

    if not old_string:
        return ToolCallRecord(
            tool_name="edit_file",
            arguments=arguments,
            success=False,
            error="old_string 参数为空",
            result_message="❌ old_string 不能为空",
        )

    abs_path = _os.path.abspath(_os.path.expanduser(path))

    # 路径限制
    if not _is_path_in_home(abs_path):
        return ToolCallRecord(
            tool_name="edit_file",
            arguments=arguments,
            success=False,
            error=f"路径不在用户主目录内：{abs_path}",
            result_message=f"❌ 路径越界：{abs_path} 不在用户主目录内",
            result_details={"path": abs_path, "in_home": False},
        )

    if on_progress:
        on_progress("edit_file", f"编辑：{abs_path}")

    if dry_run:
        return ToolCallRecord(
            tool_name="edit_file",
            arguments=arguments,
            success=True,
            result_message=f"[dry-run] 会编辑：{abs_path}",
        )

    if not _os.path.exists(abs_path):
        return ToolCallRecord(
            tool_name="edit_file",
            arguments=arguments,
            success=False,
            error=f"文件不存在：{abs_path}",
            result_message=f"❌ 文件不存在：{abs_path}",
        )

    try:
        # 读取原文件
        for encoding in ("utf-8", "gbk", "latin-1"):
            try:
                with open(abs_path, "r", encoding=encoding) as f:
                    content = f.read()
                break
            except UnicodeDecodeError:
                continue
        else:
            return ToolCallRecord(
                tool_name="edit_file",
                arguments=arguments,
                success=False,
                error="无法解码文件",
                result_message="❌ 无法解码文件",
            )

        # 检查 old_string 唯一性
        occurrences = content.count(old_string)
        if occurrences == 0:
            return ToolCallRecord(
                tool_name="edit_file",
                arguments=arguments,
                success=False,
                error=f"old_string 在文件中未找到：{abs_path}",
                result_message=f"❌ 未找到要替换的内容",
                result_details={"path": abs_path, "occurrences": 0},
            )
        if occurrences > 1:
            return ToolCallRecord(
                tool_name="edit_file",
                arguments=arguments,
                success=False,
                error=f"old_string 在文件中出现 {occurrences} 次，必须唯一（请提供更多上下文）",
                result_message=f"❌ old_string 不唯一（{occurrences} 处匹配），需要更多上下文",
                result_details={"path": abs_path, "occurrences": occurrences},
            )

        # 走 confirm
        confirm_parts = []
        if intent:
            confirm_parts.append(intent)
        else:
            confirm_parts.append("编辑文件")
        confirm_parts.append(f"\n路径：{abs_path}")
        confirm_parts.append(f"\n--- old ---\n{old_string}")
        confirm_parts.append(f"\n--- new ---\n{new_string}")
        msg = "\n".join(confirm_parts)

        if cfg.always_confirm_grey:
            if confirm is None:
                return ToolCallRecord(
                    tool_name="edit_file",
                    arguments=arguments,
                    success=False,
                    error="需要确认但未提供确认回调",
                    result_message="❌ 需要确认但未提供确认回调",
                    result_details={"path": abs_path, "needs_confirm": True},
                )
            confirm_decision = confirm(msg, f"edit_file: {abs_path}")
            if confirm_decision != "confirmed":
                # v0.8.6：区分"用户取消"和"超时"
                is_timeout = confirm_decision == "timeout"
                return ToolCallRecord(
                    tool_name="edit_file",
                    arguments=arguments,
                    success=False,
                    error="确认超时" if is_timeout else "用户取消",
                    result_message="❌ 确认超时（10 分钟内未响应）" if is_timeout else "❌ 用户取消了编辑",
                    result_details={"path": abs_path, "cancelled": True, "timeout": is_timeout},
                )

        # 执行替换
        new_content = content.replace(old_string, new_string, 1)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        elapsed = _time.perf_counter() - t0
        log.info(f"edit_file 成功：{abs_path}（替换 {len(old_string)} → {len(new_string)} 字符，{elapsed:.3f}s）")

        return ToolCallRecord(
            tool_name="edit_file",
            arguments=arguments,
            success=True,
            result_message=f"✅ 已编辑：{abs_path}（{len(old_string)} → {len(new_string)} 字符）",
            result_details={
                "path": abs_path,
                "old_len": len(old_string),
                "new_len": len(new_string),
                "occurrences": 1,
            },
        )
    except PermissionError as e:
        return ToolCallRecord(
            tool_name="edit_file",
            arguments=arguments,
            success=False,
            error=f"权限不足：{e}",
            result_message=f"❌ 权限不足：{abs_path}",
        )
    except OSError as e:
        return ToolCallRecord(
            tool_name="edit_file",
            arguments=arguments,
            success=False,
            error=f"编辑失败：{e}",
            result_message=f"❌ 编辑失败：{e}",
        )


def _format_tool_result_for_llm(record: ToolCallRecord) -> str:
    """把工具执行结果格式化成 LLM 能理解的文本。

    v0.8.0 改造：run_shell 工具的特殊处理——把完整 stdout/stderr/exit_code 都回传 LLM。
    预定义 skill 仍然只回传 final_message + steps 摘要（避免 token 爆炸）。
    """
    parts: list[str] = []
    if record.success:
        parts.append(f"工具 {record.tool_name} 执行成功。")
    else:
        parts.append(f"工具 {record.tool_name} 执行失败。")

    # v0.8.0: run_shell 特殊处理——完整 stdout/stderr 回传 LLM
    if record.tool_name == "run_shell" and record.result_details:
        d = record.result_details
        parts.append(f"exit_code: {d.get('exit_code', '?')}")
        parts.append(f"safety: {d.get('safety_level', '?')}")
        if d.get("timed_out"):
            parts.append("⚠️ 命令超时被强制终止")
        stdout = d.get("stdout", "")
        stderr = d.get("stderr", "")
        if stdout:
            parts.append(f"stdout:\n{stdout}")
        if stderr:
            parts.append(f"stderr:\n{stderr}")
        if not stdout and not stderr:
            parts.append("(无输出)")
        if record.error and not record.success:
            parts.append(f"错误：{record.error}")
        return "\n".join(parts)

    # 预定义 skill 的常规处理
    if record.result_message:
        parts.append(f"结果：{record.result_message}")
    if record.result_details and record.result_details.get("steps"):
        steps_summary = []
        for s in record.result_details["steps"]:
            if s.get("skipped"):
                continue
            status = "✓" if s.get("success") else "✗"
            out = s.get("output") or s.get("error") or ""
            if out:
                out = out[:200]
            steps_summary.append(f"  {status} {s['name']}: {out}")
        if steps_summary:
            parts.append("步骤：\n" + "\n".join(steps_summary))
    if record.error and not record.success:
        parts.append(f"错误：{record.error}")
    return "\n".join(parts)


def run_agent(
    user_text: str,
    cfg: Config,
    registry: SkillRegistry,
    confirm: ConfirmCallback | None = None,
    on_progress: ProgressCallback | None = None,
    dry_run: bool = False,
    max_iterations: int = 12,
    history: list[dict[str, str]] | None = None,
    session_id: str = "",  # v0.8.20: 会话 ID，用于 episode 聚合 + 历史对话调取
) -> AgentResponse:
    """LLM Agent 主循环。

    流程：
    1. 构造系统 prompt + 工具定义
    2. 发送给 LLM
    3. LLM 返回 tool_calls → 执行每个工具 → 结果回传 LLM
    4. 重复直到 LLM 不再调用工具或达到 max_iterations
    5. 返回最终回复

    Args:
        user_text: 用户输入
        cfg: 配置（含 LLM 配置）
        registry: Skill 注册表
        confirm: 灰名单确认回调
        on_progress: 进度回调
        dry_run: 只解析不执行
        max_iterations: 最大工具调用轮数（v0.7.14: 8→12，防止无限循环 + 给诊断类任务留足空间）
        history: 多轮对话历史（[{"role": "user"/"assistant", "content": "..."}]）

    Returns:
        AgentResponse
    """
    if not cfg.llm.enabled:
        log.warning("LLM 未启用，无法使用 Agent 模式")
        return AgentResponse(
            text="",
            success=False,
            error="LLM 未启用，无法使用 Agent 模式",
        )

    # 构造工具定义
    tools = build_tool_defs(registry)
    if not tools:
        log.warning("没有可用的 Skill")
        return AgentResponse(
            text="",
            success=False,
            error="没有可用的 Skill",
        )

    log.info(
        f"Agent 启动：用户输入「{user_text[:80]}」",
        extra={"tools_count": len(tools), "max_iter": max_iterations, "dry_run": dry_run,
               "history_len": len(history) if history else 0},
    )

    # 构造系统 prompt
    from lihua.tool_defs import build_skill_catalog_for_prompt
    catalog = build_skill_catalog_for_prompt(registry)
    # v0.8.11: 注入记忆上下文（可能为空字符串；cfg.memory.inject_context=False 时不注入）
    memory_context = ""
    if cfg.memory.enabled and cfg.memory.inject_context:
        try:
            from lihua.memory import get_memory_store
            memory_context = get_memory_store().get_context_for_prompt(user_text)
        except Exception as e:
            log.debug(f"记忆上下文注入失败（忽略）：{e}")
    # v0.8.13: 用模块化 PromptBuilder 构造 system prompt（替代 _SYSTEM_PROMPT.format）
    # PromptBuilder 支持插件注册 section、动态启用/禁用、按 priority 排序
    from lihua.prompt_builder import build_system_prompt
    system_prompt = build_system_prompt(
        skill_count=len(registry.all()),
        skill_catalog=catalog,
        memory_context=memory_context,
    )

    # 对话历史（system + history + 当前 user）
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    if history:
        for msg in history[-20:]:  # 最多保留最近 20 条，避免 token 爆炸
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_text})

    all_tool_calls: list[ToolCallRecord] = []
    # v0.7.14: 重复调用检测（tool_name + args_str → 次数）
    call_history: dict[str, int] = {}
    # v0.8.1: run_shell 速率限制计数器
    run_shell_count = 0
    # v0.8.3: run_python 速率限制计数器
    run_python_count = 0
    # v0.8.11: 记录起始时间（episode 用）
    _t0_episode = time.perf_counter()

    for iteration in range(max_iterations):
        try:
            log.debug(f"迭代 {iteration + 1}/{max_iterations}：调用 LLM")
            resp = call_llm_with_tools(cfg.llm, messages, tools=tools)
        except LLMError as e:
            log.error(f"LLM 调用失败（迭代 {iteration + 1}）：{e}")
            _resp = AgentResponse(
                text="",
                success=False,
                error=f"LLM 调用失败: {e}",
                tool_calls=all_tool_calls,
                raw_messages=messages,
            )
            _record_episode(user_text, _resp, _t0_episode, session_id=session_id, cfg=cfg)
            return _resp

        # 把 LLM 的回复加入对话历史
        assistant_msg: dict[str, Any] = {"role": "assistant"}
        if resp.text:
            assistant_msg["content"] = resp.text
        if resp.tool_calls:
            assistant_msg["tool_calls"] = resp.tool_calls
        messages.append(assistant_msg)

        # 如果没有工具调用，说明 LLM 给出了最终回复
        if not resp.has_tool_calls:
            log.info(
                f"Agent 完成：迭代 {iteration + 1}，工具 {len(all_tool_calls)} 个，回复 {len(resp.text or '')} 字"
            )
            _resp = AgentResponse(
                text=resp.text or "",
                success=True,
                tool_calls=all_tool_calls,
                raw_messages=messages,
            )
            _record_episode(
                user_text, _resp, _t0_episode,
                session_id=session_id, cfg=cfg,
                reasoning=getattr(resp, "reasoning_content", "") or "",
            )
            return _resp

        log.debug(f"迭代 {iteration + 1}：LLM 请求调用 {len(resp.tool_calls)} 个工具")

        # 执行每个工具调用
        for tc in resp.tool_calls:
            func = tc.get("function", {})
            tool_name = func.get("name", "")
            args_str = func.get("arguments", "{}")
            try:
                arguments = json.loads(args_str) if isinstance(args_str, str) else (args_str or {})
            except json.JSONDecodeError:
                arguments = {"_raw": args_str}

            # v0.7.14: 重复调用检测
            call_key = f"{tool_name}:{args_str}"
            call_count = call_history.get(call_key, 0) + 1
            call_history[call_key] = call_count

            # v0.8.1: run_shell 速率限制——超过 MAX_RUN_SHELL_CALLS 次直接拒绝
            if tool_name == "run_shell":
                run_shell_count += 1
                if run_shell_count > MAX_RUN_SHELL_CALLS:
                    log.warning(
                        f"run_shell 速率限制：第 {run_shell_count} 次调用超过上限 {MAX_RUN_SHELL_CALLS}，拒绝"
                    )
                    reject_msg = (
                        f"⚠️ run_shell 已经调用了 {MAX_RUN_SHELL_CALLS} 次，达到上限。"
                        f"请基于已有信息总结发现 + 给用户下一步建议，不要继续调 run_shell。"
                    )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "name": tool_name,
                        "content": reject_msg,
                    })
                    all_tool_calls.append(ToolCallRecord(
                        tool_name=tool_name,
                        arguments=arguments,
                        success=False,
                        error="run_shell 速率限制",
                        result_message=f"❌ run_shell 已达上限 {MAX_RUN_SHELL_CALLS} 次",
                        result_details={
                            "safety_level": "rate_limited",
                            "run_shell_count": run_shell_count,
                            "max_calls": MAX_RUN_SHELL_CALLS,
                        },
                    ))
                    continue

            # v0.8.3: run_python 速率限制——超过 MAX_RUN_PYTHON_CALLS 次直接拒绝
            if tool_name == "run_python":
                run_python_count += 1
                if run_python_count > MAX_RUN_PYTHON_CALLS:
                    log.warning(
                        f"run_python 速率限制：第 {run_python_count} 次调用超过上限 {MAX_RUN_PYTHON_CALLS}，拒绝"
                    )
                    reject_msg = (
                        f"⚠️ run_python 已经调用了 {MAX_RUN_PYTHON_CALLS} 次，达到上限。"
                        f"请基于已有信息总结发现 + 给用户下一步建议，不要继续调 run_python。"
                    )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "name": tool_name,
                        "content": reject_msg,
                    })
                    all_tool_calls.append(ToolCallRecord(
                        tool_name=tool_name,
                        arguments=arguments,
                        success=False,
                        error="run_python 速率限制",
                        result_message=f"❌ run_python 已达上限 {MAX_RUN_PYTHON_CALLS} 次",
                        result_details={
                            "safety_level": "rate_limited",
                            "run_python_count": run_python_count,
                            "max_calls": MAX_RUN_PYTHON_CALLS,
                        },
                    ))
                    continue

            if call_count >= 3:
                # 第 3 次相同调用：拒绝 + 注入提醒
                log.warning(f"工具 {tool_name} 第 {call_count} 次相同调用，拒绝执行")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "name": tool_name,
                    "content": f"⚠️ 这个工具调用你已经做过 {call_count - 1} 次了，结果都一样。请换不同参数或换不同工具，或者直接给用户总结当前发现 + 下一步建议。",
                })
                continue

            if call_count == 2:
                # 第 2 次相同调用：执行但注入提醒
                log.info(f"工具 {tool_name} 第 2 次相同调用，执行但提醒 LLM")
                messages.append({
                    "role": "system",
                    "content": f"提醒：工具 {tool_name}({args_str}) 你已经调过一次了，这是第 2 次。如果结果还是不够，请换不同参数或换不同工具，不要原样重试第 3 次。",
                })

            if on_progress:
                on_progress(tool_name, f"执行 {tool_name}({arguments})")

            record = _execute_tool(
                tool_name=tool_name,
                arguments=arguments,
                cfg=cfg,
                registry=registry,
                confirm=confirm,
                on_progress=on_progress,
                dry_run=dry_run,
                user_text=user_text,  # v0.8.16: 传用户原始输入给 usage_log
            )
            all_tool_calls.append(record)

            # 把工具结果作为 tool 消息回传给 LLM
            result_text = _format_tool_result_for_llm(record)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", ""),
                "name": tool_name,
                "content": result_text,
            })

            if on_progress:
                status = "✓" if record.success else "✗"
                on_progress(tool_name, f"{status} {record.result_message or record.error}")

    # v0.7.14: 达到 max_iterations 时让 LLM 总结（而不是机械返回固定文案）
    log.warning(f"达到最大迭代次数 {max_iterations}，让 LLM 总结当前发现")
    summary = _summarize_on_max_iterations(cfg, messages, all_tool_calls)
    _resp = AgentResponse(
        text=summary,
        success=True,
        tool_calls=all_tool_calls,
        raw_messages=messages,
        error=f"达到最大迭代次数 {max_iterations}",
    )
    _record_episode(user_text, _resp, _t0_episode, session_id=session_id, cfg=cfg)
    return _resp


def _summarize_on_max_iterations(
    cfg: Config,
    messages: list[dict[str, Any]],
    all_tool_calls: list[ToolCallRecord],
) -> str:
    """v0.7.14: 达到 max_iterations 时让 LLM 总结当前发现。

    再调一次 LLM（不带 tools），让它看完整对话历史，输出：
    - 已收集的信息
    - 已排除的原因
    - 下一步建议
    """
    if not all_tool_calls:
        return "已经处理了多步操作，但可能还需要继续。请告诉我下一步。"

    # 构造总结 prompt（不带 tools，让 LLM 只输出文本）
    summary_prompt = (
        "你已经调用了多个工具但未给出最终回复。请基于以上工具调用历史，"
        "用中文给用户总结：\n"
        "1. 已收集到的关键信息\n"
        "2. 已排除的可能原因\n"
        "3. 还需要进一步检查的方向 + 下一步建议\n\n"
        "注意：不要机械说\"请告诉我下一步\"，要具体说明发现了什么、建议怎么继续。"
    )
    messages.append({"role": "user", "content": summary_prompt})

    try:
        resp = call_llm_with_tools(cfg.llm, messages, tools=[])
        if resp.text:
            return resp.text
    except LLMError as e:
        log.warning(f"总结 LLM 调用失败：{e}")

    # 兜底：根据工具调用历史生成简单总结
    successful = [tc for tc in all_tool_calls if tc.success]
    failed = [tc for tc in all_tool_calls if not tc.success]
    parts = [
        f"已经调用了 {len(all_tool_calls)} 个工具（成功 {len(successful)} / 失败 {len(failed)}），",
        "但未完成完整诊断。可以告诉我：",
        "1. 你希望我重点检查哪个方向？",
        "2. 或者把具体的报错信息贴给我，我帮你分析。",
    ]
    if failed:
        parts.append(f"\n\n失败的工具：{', '.join(tc.tool_name for tc in failed)}")
    return "".join(parts)


def run_agent_streaming(
    user_text: str,
    cfg: Config,
    registry: SkillRegistry,
    confirm: ConfirmCallback | None = None,
    dry_run: bool = False,
    max_iterations: int = 12,
    history: list[dict[str, str]] | None = None,
    session_id: str = "",  # v0.8.20: 会话 ID，用于 episode 聚合 + 历史对话调取
) -> Iterator[dict[str, Any]]:
    """LLM Agent 流式生成器：yield SSE 事件。

    v0.7.14 改造：
    - 迭代次数 8 → 12（给诊断类任务留足空间）
    - 加重复调用检测（同工具+同参数 第 2 次提醒 / 第 3 次拒绝）
    - 达到 max_iterations 时让 LLM 总结（而不是机械返回固定文案）

    事件类型：
        {"type": "start", "tools_count": N}
        {"type": "iteration", "n": 1, "max": 12}
        {"type": "text", "content": "..."}  # LLM 本轮返回的文本（可能是中间思考）
        {"type": "tool_call_start", "name": "install_app", "arguments": {...}}
        {"type": "tool_call_end", "name": "install_app", "success": true, "message": "...", "details": {...}}
        {"type": "done", "text": "...", "success": true, "tool_calls": [...]}
        {"type": "error", "message": "..."}

    最后一必定是 done 或 error，前端据此结束流。
    """
    if not cfg.llm.enabled:
        yield {"type": "error", "message": "LLM 未启用，无法使用 Agent 模式"}
        return

    tools = build_tool_defs(registry)
    if not tools:
        yield {"type": "error", "message": "没有可用的 Skill"}
        return

    log.info(
        f"Agent 流式启动：用户输入「{user_text[:80]}」",
        extra={"tools_count": len(tools), "max_iter": max_iterations, "dry_run": dry_run,
               "history_len": len(history) if history else 0},
    )

    from lihua.tool_defs import build_skill_catalog_for_prompt
    catalog = build_skill_catalog_for_prompt(registry)
    # v0.8.11: 注入记忆上下文（可能为空字符串；cfg.memory.inject_context=False 时不注入）
    memory_context = ""
    if cfg.memory.enabled and cfg.memory.inject_context:
        try:
            from lihua.memory import get_memory_store
            memory_context = get_memory_store().get_context_for_prompt(user_text)
        except Exception as e:
            log.debug(f"记忆上下文注入失败（忽略）：{e}")
    # v0.8.13: 用模块化 PromptBuilder 构造 system prompt
    from lihua.prompt_builder import build_system_prompt
    system_prompt = build_system_prompt(
        skill_count=len(registry.all()),
        skill_catalog=catalog,
        memory_context=memory_context,
    )

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    if history:
        for msg in history[-20:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_text})

    all_tool_calls: list[ToolCallRecord] = []
    # v0.7.14: 重复调用检测（tool_name + args_str → 次数）
    call_history: dict[str, int] = {}
    # v0.8.1: run_shell 速率限制计数器
    run_shell_count = 0
    # v0.8.3: run_python 速率限制计数器
    run_python_count = 0
    # v0.8.11: 记录起始时间（episode 用）
    _t0_episode = time.perf_counter()

    yield {"type": "start", "tools_count": len(tools)}

    for iteration in range(max_iterations):
        yield {"type": "iteration", "n": iteration + 1, "max": max_iterations}
        log.debug(f"流式迭代 {iteration + 1}/{max_iterations}：调用 LLM")

        try:
            resp = call_llm_with_tools(cfg.llm, messages, tools=tools)
        except LLMError as e:
            log.error(f"LLM 调用失败（迭代 {iteration + 1}）：{e}")
            yield {"type": "error", "message": f"LLM 调用失败: {e}"}
            return

        # 加入对话历史
        assistant_msg: dict[str, Any] = {"role": "assistant"}
        if resp.text:
            assistant_msg["content"] = resp.text
        if resp.tool_calls:
            assistant_msg["tool_calls"] = resp.tool_calls
        messages.append(assistant_msg)

        # v0.8.20: 提取思考链（不回传给 LLM，OpenAI 协议不支持 assistant 消息带此字段）
        current_reasoning = getattr(resp, "reasoning_content", "") or ""

        # 推送 LLM 文本（如果有）
        if resp.text:
            yield {"type": "text", "content": resp.text}
        # v0.8.20: 推送思考链（如果有）
        if current_reasoning:
            yield {"type": "reasoning", "content": current_reasoning}

        # 没有工具调用 → 最终回复
        if not resp.has_tool_calls:
            log.info(f"Agent 流式完成：迭代 {iteration + 1}，工具 {len(all_tool_calls)} 个，回复 {len(resp.text or '')} 字")
            _record_episode_streaming(
                user_text, resp.text or "", all_tool_calls, True, _t0_episode,
                session_id=session_id, cfg=cfg, reasoning=current_reasoning,
            )
            yield {
                "type": "done",
                "text": resp.text or "",
                "success": True,
                "tool_calls": [
                    {
                        "name": tc.tool_name,
                        "arguments": tc.arguments,
                        "success": tc.success,
                        "message": tc.result_message,
                        "details": tc.result_details,
                        "error": tc.error,
                    }
                    for tc in all_tool_calls
                ],
            }
            return

        # 执行工具调用
        for tc in resp.tool_calls:
            func = tc.get("function", {})
            tool_name = func.get("name", "")
            args_str = func.get("arguments", "{}")
            try:
                arguments = json.loads(args_str) if isinstance(args_str, str) else (args_str or {})
            except json.JSONDecodeError:
                arguments = {"_raw": args_str}

            # v0.7.14: 重复调用检测
            call_key = f"{tool_name}:{args_str}"
            call_count = call_history.get(call_key, 0) + 1
            call_history[call_key] = call_count

            # v0.8.1: run_shell 速率限制——超过 MAX_RUN_SHELL_CALLS 次直接拒绝
            if tool_name == "run_shell":
                run_shell_count += 1
                if run_shell_count > MAX_RUN_SHELL_CALLS:
                    log.warning(
                        f"流式：run_shell 速率限制：第 {run_shell_count} 次调用超过上限 {MAX_RUN_SHELL_CALLS}，拒绝"
                    )
                    reject_msg = (
                        f"⚠️ run_shell 已经调用了 {MAX_RUN_SHELL_CALLS} 次，达到上限。"
                        f"请基于已有信息总结发现 + 给用户下一步建议，不要继续调 run_shell。"
                    )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "name": tool_name,
                        "content": reject_msg,
                    })
                    yield {
                        "type": "tool_call_start",
                        "name": tool_name,
                        "arguments": arguments,
                    }
                    yield {
                        "type": "tool_call_end",
                        "name": tool_name,
                        "success": False,
                        "message": f"速率限制：run_shell 已达上限 {MAX_RUN_SHELL_CALLS} 次",
                        "details": {
                            "safety_level": "rate_limited",
                            "run_shell_count": run_shell_count,
                            "max_calls": MAX_RUN_SHELL_CALLS,
                        },
                        "error": "run_shell 速率限制",
                    }
                    all_tool_calls.append(ToolCallRecord(
                        tool_name=tool_name,
                        arguments=arguments,
                        success=False,
                        error="run_shell 速率限制",
                        result_message=f"❌ run_shell 已达上限 {MAX_RUN_SHELL_CALLS} 次",
                        result_details={
                            "safety_level": "rate_limited",
                            "run_shell_count": run_shell_count,
                            "max_calls": MAX_RUN_SHELL_CALLS,
                        },
                    ))
                    continue

            # v0.8.3: run_python 速率限制——超过 MAX_RUN_PYTHON_CALLS 次直接拒绝
            if tool_name == "run_python":
                run_python_count += 1
                if run_python_count > MAX_RUN_PYTHON_CALLS:
                    log.warning(
                        f"流式：run_python 速率限制：第 {run_python_count} 次调用超过上限 {MAX_RUN_PYTHON_CALLS}，拒绝"
                    )
                    reject_msg = (
                        f"⚠️ run_python 已经调用了 {MAX_RUN_PYTHON_CALLS} 次，达到上限。"
                        f"请基于已有信息总结发现 + 给用户下一步建议，不要继续调 run_python。"
                    )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "name": tool_name,
                        "content": reject_msg,
                    })
                    yield {
                        "type": "tool_call_start",
                        "name": tool_name,
                        "arguments": arguments,
                    }
                    yield {
                        "type": "tool_call_end",
                        "name": tool_name,
                        "success": False,
                        "message": f"速率限制：run_python 已达上限 {MAX_RUN_PYTHON_CALLS} 次",
                        "details": {
                            "safety_level": "rate_limited",
                            "run_python_count": run_python_count,
                            "max_calls": MAX_RUN_PYTHON_CALLS,
                        },
                        "error": "run_python 速率限制",
                    }
                    all_tool_calls.append(ToolCallRecord(
                        tool_name=tool_name,
                        arguments=arguments,
                        success=False,
                        error="run_python 速率限制",
                        result_message=f"❌ run_python 已达上限 {MAX_RUN_PYTHON_CALLS} 次",
                        result_details={
                            "safety_level": "rate_limited",
                            "run_python_count": run_python_count,
                            "max_calls": MAX_RUN_PYTHON_CALLS,
                        },
                    ))
                    continue

            if call_count >= 3:
                # 第 3 次相同调用：拒绝 + 注入提醒
                log.warning(f"流式：工具 {tool_name} 第 {call_count} 次相同调用，拒绝执行")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "name": tool_name,
                    "content": f"⚠️ 这个工具调用你已经做过 {call_count - 1} 次了，结果都一样。请换不同参数或换不同工具，或者直接给用户总结当前发现 + 下一步建议。",
                })
                # 推送一个失败事件让前端知道
                yield {
                    "type": "tool_call_start",
                    "name": tool_name,
                    "arguments": arguments,
                }
                yield {
                    "type": "tool_call_end",
                    "name": tool_name,
                    "success": False,
                    "message": f"重复调用第 {call_count} 次，已拒绝",
                    "details": None,
                    "error": "重复调用被拒绝",
                }
                continue

            if call_count == 2:
                # 第 2 次相同调用：执行但注入提醒
                log.info(f"流式：工具 {tool_name} 第 2 次相同调用，执行但提醒 LLM")
                messages.append({
                    "role": "system",
                    "content": f"提醒：工具 {tool_name}({args_str}) 你已经调过一次了，这是第 2 次。如果结果还是不够，请换不同参数或换不同工具，不要原样重试第 3 次。",
                })

            yield {
                "type": "tool_call_start",
                "name": tool_name,
                "arguments": arguments,
            }

            record = _execute_tool(
                tool_name=tool_name,
                arguments=arguments,
                cfg=cfg,
                registry=registry,
                confirm=confirm,
                on_progress=None,
                dry_run=dry_run,
                user_text=user_text,  # v0.8.16: 传用户原始输入给 usage_log
            )
            all_tool_calls.append(record)

            yield {
                "type": "tool_call_end",
                "name": tool_name,
                "success": record.success,
                "message": record.result_message,
                "details": record.result_details,
                "error": record.error,
            }

            # 工具结果回传 LLM
            result_text = _format_tool_result_for_llm(record)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", ""),
                "name": tool_name,
                "content": result_text,
            })

    # v0.7.14: 达到 max_iterations 时让 LLM 总结
    log.warning(f"流式达到最大迭代次数 {max_iterations}，让 LLM 总结当前发现")
    yield {"type": "text", "content": "\n\n---\n\n*达到迭代上限，正在总结当前发现...*"}
    summary = _summarize_on_max_iterations(cfg, messages, all_tool_calls)

    _record_episode_streaming(
        user_text, summary, all_tool_calls, True, _t0_episode,
        session_id=session_id, cfg=cfg, reasoning="",
    )
    yield {
        "type": "done",
        "text": summary,
        "success": True,
        "tool_calls": [
            {
                "name": tc.tool_name,
                "arguments": tc.arguments,
                "success": tc.success,
                "message": tc.result_message,
                "details": tc.result_details,
                "error": tc.error,
            }
            for tc in all_tool_calls
        ],
        "error": f"达到最大迭代次数 {max_iterations}",
    }


# ---------------------------------------------------------------------------
# v0.8.9: 自进化工具——让 LLM 能重启后端、编译桌面端、查状态
# ---------------------------------------------------------------------------

# 后端 API 基址（自进化工具通过 HTTP 调自己的接口）
_SELF_API_BASE = "http://127.0.0.1:7531"


def _http_post(url: str, timeout: float = 10.0, body: dict | None = None) -> dict:
    """同步 HTTP POST 请求（自进化工具用）。

    v0.8.9: 新增 body 参数支持发送 JSON（self_version_bump 用）。
    """
    import urllib.request
    import urllib.error
    if body is not None:
        import json as _json
        data = _json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url, method="POST", data=data,
            headers={"Content-Type": "application/json"},
        )
    else:
        req = urllib.request.Request(url, method="POST", data=b"")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            import json as _json
            return _json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as e:
        return {"ok": False, "error": f"HTTP 请求失败: {e}"}
    except Exception as e:
        return {"ok": False, "error": f"异常: {e}"}


def _http_get(url: str, timeout: float = 10.0) -> dict:
    """同步 HTTP GET 请求（自进化工具用）。"""
    import urllib.request
    import urllib.error
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            import json as _json
            return _json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as e:
        return {"ok": False, "error": f"HTTP 请求失败: {e}"}
    except Exception as e:
        return {"ok": False, "error": f"异常: {e}"}


def _execute_self_restart(
    arguments: dict[str, Any],
    cfg: Config,
    confirm: ConfirmCallback | None,
    on_progress: ProgressCallback | None,
    dry_run: bool,
    t0: float,
) -> ToolCallRecord:
    """v0.8.9: 重启后端服务——让 LLM 改完代码后能重启让代码生效。

    走 confirm（会中断当前 SSE 流，用户必须知道）。
    调 /api/self/restart 接口，接口 spawn 独立重启脚本，立即返回。
    """
    import time as _time

    intent = str(arguments.get("intent", "")).strip()
    if not intent:
        intent = "重启后端让代码改动生效"

    if on_progress:
        on_progress("self_restart", "重启后端服务")

    if dry_run:
        return ToolCallRecord(
            tool_name="self_restart",
            arguments=arguments,
            success=True,
            result_message="[dry-run] 会重启后端服务（约 8 秒不可用）",
        )

    # 走 confirm（重启会中断当前会话）
    if cfg.always_confirm_grey:
        if confirm is None:
            return ToolCallRecord(
                tool_name="self_restart",
                arguments=arguments,
                success=False,
                error="需要确认但未提供确认回调",
                result_message="❌ 需要确认但未提供确认回调",
            )
        msg = (
            f"{intent}\n\n"
            "⚠️ 重启后端会导致当前对话中断，约 8 秒后新后端就绪。\n"
            "新后端启动后，需要重新发起对话。"
        )
        confirm_decision = confirm(msg, "self_restart")
        if confirm_decision != "confirmed":
            is_timeout = confirm_decision == "timeout"
            return ToolCallRecord(
                tool_name="self_restart",
                arguments=arguments,
                success=False,
                error="确认超时" if is_timeout else "用户取消",
                result_message="❌ 确认超时（10 分钟内未响应）" if is_timeout else "❌ 用户取消了重启",
            )

    # 调重启接口
    result = _http_post(f"{_SELF_API_BASE}/api/self/restart", timeout=5.0)

    elapsed = _time.perf_counter() - t0
    if result.get("ok"):
        log.warning(f"self_restart 已触发（{elapsed:.2f}s）：{result.get('message', '')}")
        return ToolCallRecord(
            tool_name="self_restart",
            arguments=arguments,
            success=True,
            result_message=(
                f"✅ 重启已触发：{result.get('message', '')}\n"
                "约 8 秒后新后端就绪，请重新发起对话。"
            ),
            result_details={
                "old_pid": result.get("old_pid"),
                "status_file": result.get("status_file"),
            },
        )
    else:
        return ToolCallRecord(
            tool_name="self_restart",
            arguments=arguments,
            success=False,
            error=result.get("error", "重启失败"),
            result_message=f"❌ 重启失败：{result.get('error', '未知错误')}",
        )


def _execute_self_build(
    arguments: dict[str, Any],
    cfg: Config,
    confirm: ConfirmCallback | None,
    on_progress: ProgressCallback | None,
    dry_run: bool,
    t0: float,
) -> ToolCallRecord:
    """v0.8.9: 后台编译桌面端——让 LLM 改完 Rust 代码后能重新编译。

    走 confirm（长时间任务，CPU 占用高）。
    调 /api/self/build 接口，接口 spawn 后台编译脚本，立即返回。
    编译完成后用 self_status 查结果。
    """
    import time as _time

    intent = str(arguments.get("intent", "")).strip()
    if not intent:
        intent = "编译桌面端让 Rust 代码改动生效"

    if on_progress:
        on_progress("self_build", "后台编译桌面端 Tauri 二进制")

    if dry_run:
        return ToolCallRecord(
            tool_name="self_build",
            arguments=arguments,
            success=True,
            result_message="[dry-run] 会启动后台编译（约 30-60 秒）",
        )

    # 走 confirm
    if cfg.always_confirm_grey:
        if confirm is None:
            return ToolCallRecord(
                tool_name="self_build",
                arguments=arguments,
                success=False,
                error="需要确认但未提供确认回调",
                result_message="❌ 需要确认但未提供确认回调",
            )
        msg = (
            f"{intent}\n\n"
            "⚠️ 编译桌面端约需 30-60 秒，CPU 占用较高。\n"
            "编译在后台执行，不阻塞当前对话。\n"
            "编译完成后用 self_status 查结果，需要重启桌面端才生效。"
        )
        confirm_decision = confirm(msg, "self_build")
        if confirm_decision != "confirmed":
            is_timeout = confirm_decision == "timeout"
            return ToolCallRecord(
                tool_name="self_build",
                arguments=arguments,
                success=False,
                error="确认超时" if is_timeout else "用户取消",
                result_message="❌ 确认超时（10 分钟内未响应）" if is_timeout else "❌ 用户取消了编译",
            )

    # 调编译接口
    result = _http_post(f"{_SELF_API_BASE}/api/self/build", timeout=5.0)

    elapsed = _time.perf_counter() - t0
    if result.get("ok"):
        log.info(f"self_build 已启动（{elapsed:.2f}s）：{result.get('message', '')}")
        return ToolCallRecord(
            tool_name="self_build",
            arguments=arguments,
            success=True,
            result_message=(
                f"✅ 编译已启动（后台）：{result.get('message', '')}\n"
                "用 self_status 查编译进度，编译完成后需要重启桌面端生效。"
            ),
            result_details={
                "status_file": result.get("status_file"),
                "build_log": result.get("build_log"),
            },
        )
    else:
        return ToolCallRecord(
            tool_name="self_build",
            arguments=arguments,
            success=False,
            error=result.get("error", "启动编译失败"),
            result_message=f"❌ 启动编译失败：{result.get('error', '未知错误')}",
        )


def _execute_self_status(
    arguments: dict[str, Any],
    on_progress: ProgressCallback | None,
    dry_run: bool,
    t0: float,
) -> ToolCallRecord:
    """v0.8.9: 查询编译/重启状态——只读，不走 confirm。"""
    import time as _time
    import json as _json

    if on_progress:
        on_progress("self_status", "查询编译/重启状态")

    if dry_run:
        return ToolCallRecord(
            tool_name="self_status",
            arguments=arguments,
            success=True,
            result_message="[dry-run] 会查询编译/重启状态",
        )

    # 调状态接口
    result = _http_get(f"{_SELF_API_BASE}/api/self/status", timeout=5.0)

    elapsed = _time.perf_counter() - t0
    if "error" in result and not result.get("build"):
        return ToolCallRecord(
            tool_name="self_status",
            arguments=arguments,
            success=False,
            error=result.get("error", "查询失败"),
            result_message=f"❌ 查询状态失败：{result.get('error', '未知错误')}",
        )

    # 格式化状态信息给 LLM
    build = result.get("build") or {}
    restart = result.get("restart") or {}
    current_pid = result.get("current_pid")
    current_version = result.get("current_version")

    status_lines = [
        f"当前后端 PID: {current_pid}",
        f"当前版本: {current_version}",
        "",
        "编译状态:",
    ]
    if build:
        b_status = build.get("status", "unknown")
        if b_status == "running":
            started_at = build.get("started_at", 0)
            import time as _t
            elapsed_b = _t.time() - started_at
            status_lines.append(f"  状态: 编译中（已 {elapsed_b:.0f}s）")
        elif b_status == "done":
            exit_code = build.get("exit_code")
            status_lines.append(f"  状态: 编译完成（exit_code={exit_code}）")
            if exit_code == 0:
                status_lines.append("  ✓ 编译成功，重启桌面端后生效")
            else:
                status_lines.append("  ✗ 编译失败，查看 /tmp/lihua-build.log")
        elif b_status == "failed":
            status_lines.append(f"  状态: 编译失败（{build.get('error', '未知')}）")
        else:
            status_lines.append(f"  状态: {b_status}")
    else:
        status_lines.append("  状态: 无编译记录")

    status_lines.append("")
    status_lines.append("重启状态:")
    if restart:
        r_status = restart.get("status", "unknown")
        if r_status == "done":
            new_pid = restart.get("new_pid")
            status_lines.append(f"  状态: 已重启（新 PID={new_pid}）")
        elif r_status == "pending":
            status_lines.append("  状态: 重启中")
        else:
            status_lines.append(f"  状态: {r_status}")
    else:
        status_lines.append("  状态: 无重启记录")

    status_text = "\n".join(status_lines)
    log.info(f"self_status 查询完成（{elapsed:.2f}s）")

    return ToolCallRecord(
        tool_name="self_status",
        arguments=arguments,
        success=True,
        result_message=status_text,
        result_details=result,
    )


def _execute_self_version_bump(
    arguments: dict[str, Any],
    cfg: Config,
    confirm: ConfirmCallback | None,
    on_progress: ProgressCallback | None,
    dry_run: bool,
    t0: float,
) -> ToolCallRecord:
    """v0.8.9: 一键升级 6 个版本号文件。

    让 LLM 改完代码后能一键升级版本号，避免手动改 6 个文件容易遗漏。
    走 confirm（修改项目文件，用户应该知道）。
    调 /api/self/version_bump 接口，接口同步替换 6 个文件并返回结果。

    参数：
    - version（可选）：指定新版本号（如 "0.8.10a0"），为空则自动 patch +1
    - intent（可选）：说明为什么升级版本号
    """
    import time as _time

    intent = str(arguments.get("intent", "")).strip()
    if not intent:
        intent = "升级版本号（代码改动后）"
    version_arg = str(arguments.get("version", "")).strip()

    if on_progress:
        on_progress("self_version_bump", f"升级版本号（→ {version_arg or 'patch+1'}）")

    if dry_run:
        return ToolCallRecord(
            tool_name="self_version_bump",
            arguments=arguments,
            success=True,
            result_message=f"[dry-run] 会升级 6 个版本号文件（目标: {version_arg or 'patch+1'}）",
        )

    # 走 confirm（修改 6 个项目文件，用户应该知道）
    if cfg.always_confirm_grey:
        if confirm is None:
            return ToolCallRecord(
                tool_name="self_version_bump",
                arguments=arguments,
                success=False,
                error="需要确认但未提供确认回调",
                result_message="❌ 需要确认但未提供确认回调",
            )
        version_hint = version_arg if version_arg else "自动 patch+1"
        msg = (
            f"{intent}\n\n"
            f"即将升级 6 个版本号文件（目标版本: {version_hint}）：\n"
            "- src/lihua/__init__.py\n"
            "- pyproject.toml\n"
            "- desktop/package.json\n"
            "- desktop/src-tauri/Cargo.toml\n"
            "- desktop/src-tauri/tauri.conf.json\n"
            "- desktop/src-tauri/src/lib.rs\n\n"
            "升级后 Python 代码需 self_restart 生效，桌面端需 self_build + 重启生效。"
        )
        confirm_decision = confirm(msg, "self_version_bump")
        if confirm_decision != "confirmed":
            is_timeout = confirm_decision == "timeout"
            return ToolCallRecord(
                tool_name="self_version_bump",
                arguments=arguments,
                success=False,
                error="确认超时" if is_timeout else "用户取消",
                result_message="❌ 确认超时（10 分钟内未响应）" if is_timeout else "❌ 用户取消了版本号升级",
            )

    # 调版本升级接口
    body = {"version": version_arg} if version_arg else {}
    result = _http_post(f"{_SELF_API_BASE}/api/self/version_bump", timeout=10.0, body=body)

    elapsed = _time.perf_counter() - t0
    if result.get("ok"):
        old_v = result.get("old_version", "?")
        new_v = result.get("new_version", "?")
        files_updated = result.get("files_updated", [])
        log.info(f"self_version_bump 完成（{elapsed:.2f}s）：{old_v} → {new_v}（{len(files_updated)}/6 文件）")
        return ToolCallRecord(
            tool_name="self_version_bump",
            arguments=arguments,
            success=True,
            result_message=(
                f"✅ 版本号升级完成：{old_v} → {new_v}\n"
                f"已更新 {len(files_updated)}/6 个文件：\n"
                + "\n".join(f"  - {f}" for f in files_updated)
                + "\n\n下一步：self_restart 让 Python 版本号生效；self_build + 重启桌面端让 Rust 版本号生效。"
            ),
            result_details=result,
        )
    else:
        # 部分失败也算返回了结果，把失败文件列表给 LLM
        files_failed = result.get("files_failed", [])
        files_updated = result.get("files_updated", [])
        if files_failed:
            detail = (
                f"⚠️ 部分失败：{len(files_updated)}/6 成功，{len(files_failed)} 失败\n"
                f"失败文件：\n"
                + "\n".join(f"  - {f['file']}: {f['error']}" for f in files_failed)
            )
        else:
            detail = result.get("error", "未知错误")
        log.warning(f"self_version_bump 失败（{elapsed:.2f}s）：{detail}")
        return ToolCallRecord(
            tool_name="self_version_bump",
            arguments=arguments,
            success=False,
            error=result.get("error", "版本号升级失败"),
            result_message=f"❌ 版本号升级失败：{detail}",
            result_details=result,
        )


# ---------------------------------------------------------------------------
# v0.8.11: 记忆系统——让 LLM 主动检索历史经验
# ---------------------------------------------------------------------------


def _execute_self_analyze(
    arguments: dict[str, Any],
    on_progress: ProgressCallback | None,
    dry_run: bool,
) -> ToolCallRecord:
    """v0.8.15: self_analyze 工具——LLM 自省，查看自己的运行数据，只读不走 confirm。

    从 analytics 模块获取分析报告：
    1. 总览（总交互数、成功率、平均耗时）
    2. 工具使用统计（每个工具的调用次数、成功率）
    3. 错误分析（失败模式、错误分类）
    4. 改进建议（基于数据的优化建议）

    返回人类可读的文本报告给 LLM 阅读后决策。
    """
    if on_progress:
        on_progress("self_analyze", "生成自监控分析报告")

    if dry_run:
        return ToolCallRecord(
            tool_name="self_analyze",
            arguments=arguments,
            success=True,
            result_message="[dry-run] 会生成自监控分析报告",
        )

    try:
        from lihua.analytics import generate_text_report, generate_report
        text_report = generate_text_report()
        detail = generate_report()
    except Exception as e:
        log.error(f"self_analyze 生成报告失败：{e}", exc_info=True)
        return ToolCallRecord(
            tool_name="self_analyze",
            arguments=arguments,
            success=False,
            error=f"生成报告失败：{e}",
        )

    return ToolCallRecord(
        tool_name="self_analyze",
        arguments=arguments,
        success=True,
        result_message=text_report,
        result_details=detail,
    )


# ---------------------------------------------------------------------------
# v0.8.17: Skill 规则提升——从 usage_log 提炼规则写入 skill YAML
# ---------------------------------------------------------------------------


def _execute_skill_evolve(
    arguments: dict[str, Any],
    cfg: Config,
    confirm: ConfirmCallback | None,
    on_progress: ProgressCallback | None,
    dry_run: bool,
    t0: float,
) -> ToolCallRecord:
    """v0.8.17: skill_evolve 工具——从 usage_log 提炼规则写入 skill YAML。

    参考 OpenClaw "实践即认识" 设计：
    1. 读 skill 的 usage_log（最近 50 条）+ 现有 rules
    2. 调 LLM 总结：成功模式 → 提升为规则；失败模式 → 降级为"避免"规则
    3. dry_run=false 时走 confirm + 写入 skill YAML 的 rules 字段
    4. dry_run=true 时只返回建议规则列表

    走 confirm（修改 skill 文件，用户应该知道）。
    """
    import json as _json
    import time as _time

    skill_name = str(arguments.get("skill_name", "")).strip()
    intent = str(arguments.get("intent", "")).strip()
    arg_dry_run = bool(arguments.get("dry_run", False))
    effective_dry_run = dry_run or arg_dry_run

    if not skill_name:
        return ToolCallRecord(
            tool_name="skill_evolve",
            arguments=arguments,
            success=False,
            error="缺少必填参数 skill_name",
            result_message="❌ 缺少必填参数 skill_name",
        )

    if on_progress:
        on_progress("skill_evolve", f"进化 skill「{skill_name}」")

    # 从 registry 查 skill
    from lihua.skills import get_registry, update_skill_rules
    registry = get_registry()
    registry.ensure_loaded()
    skill = registry.get(skill_name)
    if skill is None:
        return ToolCallRecord(
            tool_name="skill_evolve",
            arguments=arguments,
            success=False,
            error=f"skill「{skill_name}」不存在",
            result_message=f"❌ skill「{skill_name}」不存在",
        )

    # 只对 user / auto source 的 skill 生效（builtin 在安装目录无写权限）
    if skill.source not in ("user", "auto"):
        return ToolCallRecord(
            tool_name="skill_evolve",
            arguments=arguments,
            success=False,
            error=f"builtin skill「{skill_name}」无写权限（只支持 user / auto）",
            result_message=f"❌ builtin skill「{skill_name}」无写权限，只能进化 user / auto 技能",
        )

    if skill.file_path is None:
        return ToolCallRecord(
            tool_name="skill_evolve",
            arguments=arguments,
            success=False,
            error=f"skill「{skill_name}」无 file_path",
            result_message=f"❌ skill「{skill_name}」无 file_path",
        )

    # usage_log 为空时直接返回
    if not skill.usage_log:
        return ToolCallRecord(
            tool_name="skill_evolve",
            arguments=arguments,
            success=True,
            result_message=(
                f"ℹ️ skill「{skill_name}」暂无使用记录（usage_log 为空）。\n"
                "先用几次 skill 积累经验，再调 skill_evolve 提炼规则。"
            ),
            result_details={"usage_log_count": 0, "skill_name": skill_name},
        )

    if on_progress:
        on_progress("skill_evolve", f"调 LLM 总结规则（{len(skill.usage_log)} 条记录）")

    # 调 LLM 总结新 rules 列表
    if not cfg.llm.enabled:
        return ToolCallRecord(
            tool_name="skill_evolve",
            arguments=arguments,
            success=False,
            error="LLM 未启用，skill_evolve 需要 LLM 总结规则",
            result_message="❌ LLM 未启用，skill_evolve 需要 LLM 总结规则",
        )

    # 构造 LLM prompt
    usage_log_summary = []
    total = len(skill.usage_log)
    success_count = sum(1 for r in skill.usage_log if r.get("success"))
    for i, r in enumerate(skill.usage_log[-20:]):  # 最多给 LLM 20 条防 token 爆炸
        usage_log_summary.append({
            "idx": i + 1,
            "success": r.get("success", False),
            "user_input": str(r.get("user_input", ""))[:100],
            "notes": str(r.get("notes", ""))[:100],
            "params": {str(k): str(v)[:50] for k, v in (r.get("params") or {}).items()},
        })

    existing_rules_summary = []
    for r in skill.rules:
        existing_rules_summary.append({
            "condition": r.get("condition", ""),
            "action": r.get("action", ""),
            "reason": r.get("reason", ""),
            "confidence": r.get("confidence", 0.5),
        })

    llm_prompt = (
        f"你是 Lihua 狸花猫的 skill 进化引擎。请根据 skill 的使用记录（usage_log）"
        f"总结出「已验证稳定规则」，写入 rules 字段。\n\n"
        f"# Skill 信息\n"
        f"- name: {skill.name}\n"
        f"- description: {skill.description}\n"
        f"- triggers: {skill.triggers}\n"
        f"- parameters: {[p.name for p in skill.parameters]}\n\n"
        f"# 使用统计\n"
        f"- 总次数: {total}\n"
        f"- 成功: {success_count}\n"
        f"- 失败: {total - success_count}\n"
        f"- 成功率: {success_count / total:.0%}\n\n"
        f"# 最近使用记录（最多 20 条）\n"
        f"{_json.dumps(usage_log_summary, ensure_ascii=False, indent=2)}\n\n"
        f"# 现有规则（如有）\n"
        f"{_json.dumps(existing_rules_summary, ensure_ascii=False, indent=2) if existing_rules_summary else '无'}\n\n"
        f"# 规则提炼原则\n"
        f"1. **提升**：usage_log 反复验证的参数模式 / 前置条件 → 提炼为「建议」规则\n"
        f"2. **降级**：某参数组合反复失败 → 提炼为「避免」规则\n"
        f"3. **保留**：现有规则仍被新 usage_log 支持 → 保留（可调高 confidence）\n"
        f"4. **删除**：现有规则被新 usage_log 证伪 → 不出现在新 rules 里\n"
        f"5. **精简**：规则总数控制在 5-10 条，避免噪音\n"
        f"6. **置信度**：根据样本数 + 一致性估 0.5-0.9（少样本 / 有冲突 → 0.5-0.6）\n\n"
        f"# 输出格式（严格 JSON，不要 markdown 代码块）\n"
        f"{{\n"
        f'  "rules": [\n'
        f'    {{\n'
        f'      "condition": "触发条件（自然语言，如 target 是 chrome）",\n'
        f'      "action": "建议动作（如 prefer_flatpak / avoid_apt）",\n'
        f'      "reason": "规则来源（如 usage_log 5 次成功率 100%）",\n'
        f'      "confidence": 0.8\n'
        f'    }}\n'
        f'  ],\n'
        f'  "summary": "本次进化的一句话总结（中文）"\n'
        f"}}\n"
    )

    try:
        from lihua.router import call_llm, LLMError
        resp = call_llm(cfg.llm, [
            {"role": "system", "content": "你是 skill 进化引擎，只返回 JSON。"},
            {"role": "user", "content": llm_prompt},
        ])
        text = resp.text.strip()
        # 提取 JSON（兼容 markdown 代码块包裹）
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return ToolCallRecord(
                tool_name="skill_evolve",
                arguments=arguments,
                success=False,
                error=f"LLM 返回非 JSON：{text[:200]}",
                result_message=f"❌ LLM 返回非 JSON：{text[:200]}",
            )
        data = _json.loads(text[start:end+1])
        new_rules = list(data.get("rules", []) or [])
        summary = str(data.get("summary", "")).strip()
    except (LLMError, ValueError, KeyError) as e:
        log.error(f"skill_evolve LLM 调用失败：{e}", exc_info=True)
        return ToolCallRecord(
            tool_name="skill_evolve",
            arguments=arguments,
            success=False,
            error=f"LLM 调用失败：{e}",
            result_message=f"❌ LLM 调用失败：{e}",
        )

    # 加 added_at 时间戳
    now = _time.time()
    for r in new_rules:
        r["added_at"] = now

    # dry_run 模式只返回建议
    if effective_dry_run:
        return ToolCallRecord(
            tool_name="skill_evolve",
            arguments=arguments,
            success=True,
            result_message=(
                f"[dry-run] skill「{skill_name}」建议规则（{len(new_rules)} 条）：\n"
                + "\n".join(
                    f"  - [{r.get('confidence', 0.5):.0%}] {r.get('condition', '')} → "
                    f"{r.get('action', '')}（{r.get('reason', '')}）"
                    for r in new_rules
                )
                + f"\n\n总结：{summary}"
            ),
            result_details={
                "skill_name": skill_name,
                "dry_run": True,
                "suggested_rules": new_rules,
                "summary": summary,
                "usage_log_count": total,
                "success_rate": success_count / total if total else 0.0,
            },
        )

    # 走 confirm（修改 skill 文件）
    if cfg.always_confirm_grey:
        if confirm is None:
            return ToolCallRecord(
                tool_name="skill_evolve",
                arguments=arguments,
                success=False,
                error="需要确认但未提供确认回调",
                result_message="❌ 需要确认但未提供确认回调",
            )
        rules_preview = "\n".join(
            f"  - [{r.get('confidence', 0.5):.0%}] {r.get('condition', '')} → "
            f"{r.get('action', '')}（{r.get('reason', '')}）"
            for r in new_rules
        )
        msg = (
            f"{intent}\n\n"
            f"📝 即将进化 skill「{skill_name}」：\n"
            f"- usage_log: {total} 条记录，成功率 {success_count}/{total}\n"
            f"- 新规则（{len(new_rules)} 条）：\n{rules_preview}\n"
            f"- 文件：{skill.file_path}\n"
            f"- 会备份 .yaml.bak 后写入 rules 字段"
        )
        confirm_decision = confirm(msg, "skill_evolve")
        if confirm_decision != "confirmed":
            is_timeout = confirm_decision == "timeout"
            return ToolCallRecord(
                tool_name="skill_evolve",
                arguments=arguments,
                success=False,
                error="确认超时" if is_timeout else "用户取消",
                result_message=(
                    "❌ 确认超时（10 分钟内未响应）" if is_timeout
                    else "❌ 用户取消了 skill 进化"
                ),
            )

    # 写入 skill YAML
    if on_progress:
        on_progress("skill_evolve", f"写入 rules 到 {skill.file_path.name}")
    ok, msg = update_skill_rules(skill.file_path, new_rules)
    if not ok:
        return ToolCallRecord(
            tool_name="skill_evolve",
            arguments=arguments,
            success=False,
            error=msg,
            result_message=f"❌ {msg}",
        )

    # reload registry 让新 rules 生效
    try:
        registry.reload()
    except Exception as e:
        log.warning(f"skill_evolve reload registry 失败（不影响写入）：{e}")

    elapsed = _time.perf_counter() - t0
    log.info(
        f"skill_evolve 完成（{elapsed:.2f}s）：{skill_name} 写入 {len(new_rules)} 条规则",
        extra={"skill_name": skill_name, "rules_count": len(new_rules)},
    )

    return ToolCallRecord(
        tool_name="skill_evolve",
        arguments=arguments,
        success=True,
        result_message=(
            f"✅ skill「{skill_name}」已进化：写入 {len(new_rules)} 条规则\n\n"
            f"新规则：\n"
            + "\n".join(
                f"  - [{r.get('confidence', 0.5):.0%}] {r.get('condition', '')} → "
                f"{r.get('action', '')}（{r.get('reason', '')}）"
                for r in new_rules
            )
            + f"\n\n总结：{summary}\n"
            f"文件：{skill.file_path}\n"
            f"下次调用此 skill 时，LLM 会自动看到这些规则。"
        ),
        result_details={
            "skill_name": skill_name,
            "rules_written": len(new_rules),
            "rules": new_rules,
            "summary": summary,
            "usage_log_count": total,
            "success_rate": success_count / total if total else 0.0,
            "file_path": str(skill.file_path),
        },
    )


# ---------------------------------------------------------------------------
# v0.8.17: 记忆归档——把旧 episodes 按月分组移到 archive/ 目录
# ---------------------------------------------------------------------------


def _execute_memory_archive(
    arguments: dict[str, Any],
    on_progress: ProgressCallback | None,
    dry_run: bool,
    t0: float,
) -> ToolCallRecord:
    """v0.8.17: memory_archive 工具——触发记忆归档，只读不走 confirm。

    参考 OpenClaw "每月末压缩上月日志到 memory/archive/YYYY-MM.md" 设计：
    - 把 N 天前的 episodes 按月分组移到 archive/episodes_YYYY-MM.jsonl
    - 主 episodes.jsonl 只保留近期数据（减少 L2/L3 扫描成本）
    - 归档不丢数据（只是移到 archive/ 目录）

    不走 confirm（数据归档不丢失）。
    """
    import time as _time

    days_arg = arguments.get("days")
    days = int(days_arg) if days_arg is not None else None

    if on_progress:
        on_progress("memory_archive", f"归档 {days or '默认'} 天前的 episodes")

    if dry_run:
        return ToolCallRecord(
            tool_name="memory_archive",
            arguments=arguments,
            success=True,
            result_message=f"[dry-run] 会归档 {days or '默认 30'} 天前的 episodes 到 archive/ 目录",
        )

    try:
        from lihua.memory import get_memory_store
        store = get_memory_store()
        result = store.archive_old_episodes(days)
    except Exception as e:
        log.error(f"memory_archive 失败：{e}", exc_info=True)
        return ToolCallRecord(
            tool_name="memory_archive",
            arguments=arguments,
            success=False,
            error=f"归档失败：{e}",
            result_message=f"❌ 归档失败：{e}",
        )

    elapsed = _time.perf_counter() - t0
    archived = result.get("archived_count", 0)
    remaining = result.get("remaining_count", 0)
    archive_files = result.get("archive_files", [])
    archive_dir = result.get("archive_dir", "")

    if archived == 0:
        msg = (
            f"ℹ️ 没有可归档的 episodes（cutoff 前 0 条）\n"
            f"主文件剩余：{remaining} 条\n"
            f"归档目录：{archive_dir}"
        )
    else:
        files_str = " / ".join(archive_files) if archive_files else "无"
        msg = (
            f"✅ 归档完成（{elapsed:.2f}s）：\n"
            f"- 归档条数：{archived}\n"
            f"- 主文件剩余：{remaining} 条\n"
            f"- 归档文件：{files_str}\n"
            f"- 归档目录：{archive_dir}\n\n"
            f"归档后的 episodes 不再被 memory_recall 检索（L4 冷数据）。"
        )

    log.info(
        f"memory_archive 完成（{elapsed:.2f}s）：归档 {archived} 条，主文件剩余 {remaining} 条",
        extra={"archived": archived, "remaining": remaining, "archive_files": archive_files},
    )

    return ToolCallRecord(
        tool_name="memory_archive",
        arguments=arguments,
        success=True,
        result_message=msg,
        result_details=result,
    )


# ---------------------------------------------------------------------------
# v0.8.18: 踩坑记录——trap_search（搜坑）+ trap_update（填根因/标记修复）
# ---------------------------------------------------------------------------


def _execute_trap_search(
    arguments: dict[str, Any],
    on_progress: ProgressCallback | None,
    dry_run: bool,
    t0: float,
) -> ToolCallRecord:
    """v0.8.18: trap_search 工具——搜索踩坑记录，只读不走 confirm。

    参考 trae 工作流的 traps.md：失败案例结构化记录（现象→根因→解决方案）。
    LLM 遇到似曾相识的问题时调 trap_search 看有没有踩过同样的坑。
    """
    import time as _time

    query = str(arguments.get("query", "")).strip()
    status = str(arguments.get("status", "")).strip() or None
    if status == "":
        status = None

    if on_progress:
        on_progress("trap_search", f"搜索 traps: query='{query}' status={status or 'all'}")

    try:
        from lihua.memory import get_memory_store, _extract_keywords
        store = get_memory_store()
        if query:
            keywords = _extract_keywords(query)
            traps = store.search_traps(keywords, status=status, limit=10)
        else:
            traps = store.get_traps(status=status)[:10]
    except Exception as e:
        log.error(f"trap_search 失败：{e}", exc_info=True)
        return ToolCallRecord(
            tool_name="trap_search",
            arguments=arguments,
            success=False,
            error=f"搜索失败：{e}",
            result_message=f"❌ 搜索失败：{e}",
        )

    if not traps:
        msg = (
            f"ℹ️ 没有匹配的 traps"
            f"（query='{query}', status={status or 'all'}）"
        )
    else:
        lines = [f"找到 {len(traps)} 条踩坑记录：\n"]
        for t in traps:
            status_emoji = {"open": "🔴", "fixed": "🟢", "workaround": "🟡"}.get(t.status, "⚪")
            root_cause_str = f"\n   根因：{t.root_cause}" if t.root_cause else ""
            solution_str = f"\n   解决：{t.solution}" if t.solution else ""
            occurrence_str = f"（出现 {t.occurrence_count} 次）" if t.occurrence_count > 1 else ""
            skills_str = f" [{', '.join(t.related_skills)}]" if t.related_skills else ""
            lines.append(
                f"{status_emoji} T{t.id:03d}{skills_str} {occurrence_str}: "
                f"{t.symptom[:150]}{root_cause_str}{solution_str}"
            )
        msg = "\n".join(lines)

    elapsed = _time.perf_counter() - t0
    log.info(
        f"trap_search 完成（{elapsed:.2f}s）：找到 {len(traps)} 条",
        extra={"query": query, "status": status, "found": len(traps)},
    )

    return ToolCallRecord(
        tool_name="trap_search",
        arguments=arguments,
        success=True,
        result_message=msg,
        result_details={
            "query": query,
            "status": status,
            "found_count": len(traps),
            "traps": [t.to_dict() for t in traps],
        },
    )


def _execute_trap_update(
    arguments: dict[str, Any],
    cfg: Config,
    confirm: ConfirmCallback | None,
    on_progress: ProgressCallback | None,
    dry_run: bool,
    t0: float,
) -> ToolCallRecord:
    """v0.8.18: trap_update 工具——更新踩坑记录，走 confirm。

    LLM 诊断出根因 + 解决方案后调 trap_update 填充，下次同类问题就能避免。
    """
    import time as _time

    try:
        trap_id = int(arguments.get("trap_id", 0))
    except (TypeError, ValueError):
        trap_id = 0
    if trap_id <= 0:
        return ToolCallRecord(
            tool_name="trap_update",
            arguments=arguments,
            success=False,
            error="缺少必填参数 trap_id（或 trap_id 无效）",
            result_message="❌ 缺少必填参数 trap_id（或 trap_id 无效）",
        )

    intent = str(arguments.get("intent", "")).strip()
    root_cause = arguments.get("root_cause")
    solution = arguments.get("solution")
    status = arguments.get("status")
    fix_verified = arguments.get("fix_verified")

    # 构造 updates dict（只包含提供的字段）
    updates: dict[str, Any] = {}
    if root_cause is not None:
        updates["root_cause"] = str(root_cause)
    if solution is not None:
        updates["solution"] = str(solution)
    if status is not None:
        updates["status"] = str(status)
    if fix_verified is not None:
        updates["fix_verified"] = bool(fix_verified)

    if not updates:
        return ToolCallRecord(
            tool_name="trap_update",
            arguments=arguments,
            success=False,
            error="没有提供要更新的字段（root_cause / solution / status / fix_verified 至少一个）",
            result_message="❌ 没有提供要更新的字段",
        )

    if on_progress:
        on_progress("trap_update", f"更新 trap T{trap_id:03d}")

    # 先查 trap 存在 + 看当前内容
    try:
        from lihua.memory import get_memory_store
        store = get_memory_store()
        existing = store.get_trap(trap_id)
        if existing is None:
            return ToolCallRecord(
                tool_name="trap_update",
                arguments=arguments,
                success=False,
                error=f"trap T{trap_id:03d} 不存在",
                result_message=f"❌ trap T{trap_id:03d} 不存在",
            )
    except Exception as e:
        log.error(f"trap_update 查询失败：{e}", exc_info=True)
        return ToolCallRecord(
            tool_name="trap_update",
            arguments=arguments,
            success=False,
            error=f"查询失败：{e}",
            result_message=f"❌ 查询失败：{e}",
        )

    # dry_run 模式
    if dry_run:
        return ToolCallRecord(
            tool_name="trap_update",
            arguments=arguments,
            success=True,
            result_message=(
                f"[dry-run] 会更新 trap T{trap_id:03d}：\n"
                f"  当前：{existing.symptom[:100]}\n"
                f"  状态：{existing.status}\n"
                f"  更新字段：{list(updates.keys())}"
            ),
            result_details={
                "trap_id": trap_id,
                "dry_run": True,
                "updates": updates,
                "current": existing.to_dict(),
            },
        )

    # 走 confirm
    if cfg.always_confirm_grey:
        if confirm is None:
            return ToolCallRecord(
                tool_name="trap_update",
                arguments=arguments,
                success=False,
                error="需要确认但未提供确认回调",
                result_message="❌ 需要确认但未提供确认回调",
            )
        # 构造预览
        preview_lines = [f"📝 即将更新 trap T{trap_id:03d}：\n"]
        preview_lines.append(f"现象：{existing.symptom[:120]}")
        preview_lines.append(f"当前状态：{existing.status}")
        if existing.root_cause:
            preview_lines.append(f"当前根因：{existing.root_cause[:120]}")
        if existing.solution:
            preview_lines.append(f"当前解决：{existing.solution[:120]}")
        preview_lines.append("\n更新内容：")
        if "root_cause" in updates:
            preview_lines.append(f"  根因 → {updates['root_cause'][:120]}")
        if "solution" in updates:
            preview_lines.append(f"  解决 → {updates['solution'][:120]}")
        if "status" in updates:
            preview_lines.append(f"  状态 → {updates['status']}")
        if "fix_verified" in updates:
            preview_lines.append(f"  已验证 → {updates['fix_verified']}")
        msg = f"{intent}\n\n" + "\n".join(preview_lines)
        confirm_decision = confirm(msg, "trap_update")
        if confirm_decision != "confirmed":
            is_timeout = confirm_decision == "timeout"
            return ToolCallRecord(
                tool_name="trap_update",
                arguments=arguments,
                success=False,
                error="确认超时" if is_timeout else "用户取消",
                result_message=(
                    "❌ 确认超时（10 分钟内未响应）" if is_timeout
                    else "❌ 用户取消了 trap 更新"
                ),
            )

    # 执行更新
    try:
        ok, msg, updated_trap = store.update_trap(trap_id, updates)
        if not ok:
            return ToolCallRecord(
                tool_name="trap_update",
                arguments=arguments,
                success=False,
                error=msg,
                result_message=f"❌ {msg}",
            )
    except Exception as e:
        log.error(f"trap_update 执行失败：{e}", exc_info=True)
        return ToolCallRecord(
            tool_name="trap_update",
            arguments=arguments,
            success=False,
            error=f"更新失败：{e}",
            result_message=f"❌ 更新失败：{e}",
        )

    elapsed = _time.perf_counter() - t0
    log.info(
        f"trap_update 完成（{elapsed:.2f}s）：T{trap_id:03d} 更新字段 {list(updates.keys())}",
        extra={"trap_id": trap_id, "updates": list(updates.keys())},
    )

    # 构造结果消息
    status_emoji = {"open": "🔴", "fixed": "🟢", "workaround": "🟡"}.get(
        updated_trap.status if updated_trap else "open", "⚪"
    )
    result_lines = [f"✅ trap T{trap_id:03d} 已更新 {status_emoji}\n"]
    result_lines.append(f"现象：{updated_trap.symptom[:120]}")
    if updated_trap.root_cause:
        result_lines.append(f"根因：{updated_trap.root_cause[:120]}")
    if updated_trap.solution:
        result_lines.append(f"解决：{updated_trap.solution[:120]}")
    result_lines.append(f"状态：{updated_trap.status}")
    if updated_trap.fix_verified:
        result_lines.append("（修复已验证）")

    return ToolCallRecord(
        tool_name="trap_update",
        arguments=arguments,
        success=True,
        result_message="\n".join(result_lines),
        result_details={
            "trap_id": trap_id,
            "updates_applied": list(updates.keys()),
            "trap": updated_trap.to_dict() if updated_trap else None,
        },
    )


def _execute_memory_recall(
    arguments: dict[str, Any],
    on_progress: ProgressCallback | None,
    dry_run: bool,
    t0: float,
) -> ToolCallRecord:
    """v0.8.11: memory_recall 工具——检索历史经验，只读不走 confirm。

    从记忆系统查询：
    1. 相关知识（问题→工具链→成功率）
    2. 历史情景案例（用户输入 + 工具调用 + 结果）

    返回格式化文本给 LLM 阅读后决策。
    """
    import time as _time

    query = str(arguments.get("query", "")).strip()
    limit = int(arguments.get("limit", 5))
    limit = max(1, min(limit, 20))  # 限制 1-20

    if on_progress:
        on_progress("memory_recall", f"检索记忆：{query[:40]}")

    if dry_run:
        return ToolCallRecord(
            tool_name="memory_recall",
            arguments=arguments,
            success=True,
            result_message=f"[dry-run] 会检索记忆：{query}",
        )

    if not query:
        return ToolCallRecord(
            tool_name="memory_recall",
            arguments=arguments,
            success=False,
            error="query 不能为空",
            result_message="❌ 检索失败：query 不能为空",
        )

    # 延迟导入避免循环依赖
    from lihua.memory import get_memory_store, _extract_keywords

    store = get_memory_store()

    # 1. 检索相关知识（问题→工具链）
    knowledge = store.get_relevant_knowledge(query, limit=5)

    # 2. 检索历史情景案例（先提取关键词再查）
    keywords = _extract_keywords(query)
    episodes = store.query_episodes(keywords, limit=limit) if keywords else []

    elapsed = _time.perf_counter() - t0

    # 格式化结果给 LLM
    lines: list[str] = []
    lines.append(f"## 记忆检索结果（query: {query}，耗时 {elapsed:.2f}s）")
    lines.append("")

    if knowledge:
        lines.append("### 历史经验（问题→工具链→成功率）")
        for p in knowledge:
            tools_str = " → ".join(p.tool_chain)
            lines.append(
                f"- 工具链: {tools_str}\n"
                f"  成功率: {p.success_rate:.0%}（成功 {p.success_count} / 失败 {p.fail_count}，"
                f"共 {p.total_count} 次）\n"
                f"  关键词: {', '.join(p.keywords[:6])}"
            )
        lines.append("")
    else:
        lines.append("### 历史经验")
        lines.append("（无相关知识记录）")
        lines.append("")

    if episodes:
        lines.append(f"### 相关案例（{len(episodes)} 条）")
        for i, ep in enumerate(episodes, 1):
            status = "✓" if ep.success else "✗"
            tools = ", ".join(tc.get("name", "?") for tc in ep.tool_calls) or "(无工具)"
            lines.append(
                f"{i}. {status} 用户: \"{ep.user_input[:80]}\"\n"
                f"   工具: {tools}\n"
                f"   结果: {ep.agent_response[:100] if ep.agent_response else '(无回复)'}"
            )
        lines.append("")
    else:
        lines.append("### 相关案例")
        lines.append("（无相关历史案例）")
        lines.append("")

    if not knowledge and not episodes:
        lines.append("（记忆系统中无相关经验，按常规流程处理即可）")

    result_text = "\n".join(lines)
    log.info(f"memory_recall 完成（{elapsed:.2f}s）：{len(knowledge)} 知识 / {len(episodes)} 案例")

    return ToolCallRecord(
        tool_name="memory_recall",
        arguments=arguments,
        success=True,
        result_message=result_text,
        result_details={
            "knowledge_count": len(knowledge),
            "episodes_count": len(episodes),
            "query": query,
        },
    )


def _execute_create_skill(
    arguments: dict[str, Any],
    cfg: Config,
    confirm: ConfirmCallback | None,
    on_progress: ProgressCallback | None,
    dry_run: bool,
    t0: float,
) -> ToolCallRecord:
    """v0.8.12: 执行 create_skill 工具——把工具链固化成 YAML 技能。

    流程：
    1. 从 arguments 解析技能定义（name/description/triggers/steps/...）
    2. validate_skill_name + validate_skill_steps 做基本检查
    3. check_name_conflict 检查不覆盖内置技能
    4. 走 confirm（让用户看到技能内容后决定）
    5. save_skill 写入 ~/.config/lihua/skills/auto_generated/{name}.yaml
    6. reload_registry 让新技能立即生效
    7. 返回结果给 LLM

    用户拒绝/超时时返回失败记录，不写文件。
    """
    from lihua.skill_generator import (
        GeneratedSkill,
        validate_skill_name,
        validate_skill_steps,
        check_name_conflict,
        save_skill,
        reload_registry,
    )

    if on_progress:
        on_progress("create_skill", "正在生成新技能")

    # 解析参数
    name = str(arguments.get("name", "")).strip()
    description = str(arguments.get("description", "")).strip()
    triggers = [str(t) for t in arguments.get("triggers", []) if t]
    steps = list(arguments.get("steps", []) or [])
    examples = [str(e) for e in arguments.get("examples", []) if e]
    parameters_schema = list(arguments.get("parameters_schema", []) or [])
    allow_overwrite = bool(arguments.get("allow_overwrite", False))

    # 基本字段检查
    if not name:
        return ToolCallRecord(
            tool_name="create_skill",
            arguments=arguments,
            success=False,
            error="参数 name 不能为空",
        )
    if not description:
        return ToolCallRecord(
            tool_name="create_skill",
            arguments=arguments,
            success=False,
            error="参数 description 不能为空",
        )
    if not triggers:
        return ToolCallRecord(
            tool_name="create_skill",
            arguments=arguments,
            success=False,
            error="参数 triggers 不能为空（至少 1 个触发词）",
        )

    # 验证技能名
    ok, msg = validate_skill_name(name)
    if not ok:
        return ToolCallRecord(
            tool_name="create_skill",
            arguments=arguments,
            success=False,
            error=f"技能名不合法：{msg}",
        )

    # 验证 steps 安全性
    ok, msg = validate_skill_steps(steps)
    if not ok:
        return ToolCallRecord(
            tool_name="create_skill",
            arguments=arguments,
            success=False,
            error=f"steps 不安全：{msg}",
        )

    # 检查与内置/用户技能冲突
    # check_name_conflict 内部对 auto 技能豁免（允许覆盖 auto 技能）
    # allow_overwrite 只用于控制"覆盖已存在的 auto 技能文件"
    if check_name_conflict(name):
        return ToolCallRecord(
            tool_name="create_skill",
            arguments=arguments,
            success=False,
            error=f"技能名 '{name}' 与内置/用户技能冲突，不能覆盖。请换个名字",
        )

    # 构造 GeneratedSkill 对象
    skill = GeneratedSkill(
        name=name,
        description=description,
        triggers=triggers,
        parameters=parameters_schema,
        steps=steps,
        examples=examples,
        category="auto",
        version="0.1",
    )

    # dry-run：只展示不写入
    if dry_run:
        return ToolCallRecord(
            tool_name="create_skill",
            arguments=arguments,
            success=True,
            result_message=f"[dry-run] 将创建技能 {name}：\n{skill.to_yaml()}",
        )

    # 走 confirm（让用户看到技能内容）
    if confirm:
        preview = skill.to_yaml()
        if len(preview) > 2000:
            preview = preview[:2000] + "\n... (截断)"
        confirm_msg = (
            f"创建新技能：{name}\n"
            f"描述：{description}\n"
            f"触发词：{', '.join(triggers)}\n"
            f"步骤数：{len(steps)}\n\n"
            f"技能内容预览：\n```yaml\n{preview}\n```"
        )
        decision = confirm(confirm_msg, f"# create_skill: {name}")
        if decision != "confirmed":
            return ToolCallRecord(
                tool_name="create_skill",
                arguments=arguments,
                success=False,
                error=f"用户{('取消' if decision == 'denied' else '超时')}了创建技能操作",
            )

    # 保存技能
    ok, msg, file_path = save_skill(skill, allow_overwrite=allow_overwrite)
    if not ok:
        return ToolCallRecord(
            tool_name="create_skill",
            arguments=arguments,
            success=False,
            error=f"保存技能失败：{msg}",
        )

    # reload registry 让新技能立即生效
    ok, reload_msg, skill_count = reload_registry()

    import time as _t
    elapsed = _t.perf_counter() - t0
    result_text = (
        f"技能 {name} 创建成功！\n"
        f"文件：{file_path}\n"
        f" SkillRegistry 已重新加载，当前共 {skill_count} 个技能。\n"
        f"下次用户提到 {triggers} 时会自动匹配这个新技能。"
    )
    log.info(f"create_skill 成功：name={name} file={file_path} elapsed={elapsed:.2f}s")
    if on_progress:
        on_progress("create_skill", f"技能 {name} 已创建并生效")

    return ToolCallRecord(
        tool_name="create_skill",
        arguments=arguments,
        success=True,
        result_message=result_text,
        result_details={
            "skill_name": name,
            "file_path": str(file_path) if file_path else None,
            "skill_count": skill_count,
            "elapsed": round(elapsed, 3),
        },
    )


def _record_episode(
    user_text: str,
    response: "AgentResponse",
    t0: float,
    session_id: str = "",
    cfg: "Config | None" = None,
    reasoning: str = "",  # v0.8.20: LLM 思考链
) -> None:
    """v0.8.11: 记录一次完整交互到记忆系统。

    在 run_agent / run_agent_streaming 的返回点调用，把用户输入 + 工具调用链 +
    最终回复 + 成功/失败存入 episodes.jsonl，供下次类似问题时检索。
    失败则忽略，不影响主流程。cfg.memory.enabled=False 时不记录。

    v0.8.20: 新增 reasoning 参数记录 LLM 思考链。
    """
    if cfg is not None and not cfg.memory.enabled:
        return
    try:
        from lihua.memory import get_memory_store, Episode
        # 判断整体成功：response.success + 所有工具调用都成功
        overall_success = response.success and all(tc.success for tc in response.tool_calls)
        episode = Episode(
            user_input=user_text,
            tool_calls=[
                {
                    "name": tc.tool_name,
                    "arguments": tc.arguments,
                    "success": tc.success,
                    "error": tc.error,
                }
                for tc in response.tool_calls
            ],
            success=overall_success,
            agent_response=response.text,
            session_id=session_id,
            duration=time.perf_counter() - t0,
            reasoning=reasoning,
        )
        get_memory_store().record_episode(episode)
    except Exception as e:
        log.debug(f"记录 episode 失败（忽略）：{e}")


def _record_episode_streaming(
    user_text: str,
    final_text: str,
    tool_calls: list[ToolCallRecord],
    success: bool,
    t0: float,
    session_id: str = "",
    cfg: "Config | None" = None,
    reasoning: str = "",  # v0.8.20: LLM 思考链
) -> None:
    """v0.8.11: 流式版本——从 done 事件参数构造并记录 episode。

    v0.8.20: 新增 reasoning 参数记录 LLM 思考链。
    """
    if cfg is not None and not cfg.memory.enabled:
        return
    try:
        from lihua.memory import get_memory_store, Episode
        overall_success = success and all(tc.success for tc in tool_calls)
        episode = Episode(
            user_input=user_text,
            tool_calls=[
                {
                    "name": tc.tool_name,
                    "arguments": tc.arguments,
                    "success": tc.success,
                    "error": tc.error,
                }
                for tc in tool_calls
            ],
            success=overall_success,
            agent_response=final_text,
            session_id=session_id,
            duration=time.perf_counter() - t0,
            reasoning=reasoning,
        )
        get_memory_store().record_episode(episode)
    except Exception as e:
        log.debug(f"记录 episode 失败（忽略）：{e}")
