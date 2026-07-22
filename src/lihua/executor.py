"""命令执行器：subprocess 包装 + 实时输出 + 超时控制。

设计原则：
1. 永远不直接用 shell=True 跑用户输入（注入风险）
2. 但 Skill YAML 里的命令模板本身就是受控的，可以走 shell
3. 实时捕获 stdout/stderr，行级回调
4. 失败返回结构化结果，不抛异常（让上层决策重试/放弃）
"""

from __future__ import annotations

import json
import os
import re
import select
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from lihua.config import audit_log_path
from lihua.safety import SafetyDecision, classify, parse_args

# 进度回调类型：接收 (stream_name, line_text)
ProgressCallback = Callable[[str, str], None]


@dataclass
class ExecResult:
    """命令执行结果。"""

    success: bool
    exit_code: int
    stdout: str
    stderr: str
    duration: float
    command: str
    timed_out: bool = False
    cancelled: bool = False

    @property
    def output(self) -> str:
        """合并的 stdout + stderr。"""
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            parts.append(self.stderr)
        return "\n".join(parts).rstrip()

    def short_output(self, max_lines: int = 20) -> str:
        """给用户看的简短输出（最后 N 行）。"""
        if not self.output:
            return ""
        lines = self.output.splitlines()
        if len(lines) <= max_lines:
            return self.output
        return "...\n" + "\n".join(lines[-max_lines:])


@dataclass
class ExecOptions:
    """执行参数。"""

    cwd: Path | str | None = None
    env: dict[str, str] | None = None
    timeout: float | None = None
    shell: bool = False
    stdin: str | None = None
    # 是否在审计日志里记录命令原文（灰名单确认后应记录）
    audit: bool = True
    # 进度回调
    on_progress: ProgressCallback | None = None


@dataclass
class AuditEntry:
    """审计日志条目。"""

    timestamp: float
    command: str
    safety_level: str
    success: bool
    exit_code: int
    duration: float
    user_input: str | None = None
    decision_reason: str | None = None

    def format(self) -> str:
        """人类可读格式（旧文本格式，向后兼容）。"""
        from datetime import datetime

        ts = datetime.fromtimestamp(self.timestamp).strftime("%Y-%m-%d %H:%M:%S")
        status = "OK" if self.success else "FAIL"
        line = (
            f"[{ts}] {status} exit={self.exit_code} "
            f"safety={self.safety_level} duration={self.duration:.2f}s "
            f"cmd={self.command!r}"
        )
        if self.user_input:
            line += f" user_input={self.user_input!r}"
        if self.decision_reason:
            line += f" reason={self.decision_reason!r}"
        return line

    def to_dict(self) -> dict[str, Any]:
        """序列化为 dict（用于 JSON 行存储）。"""
        from datetime import datetime
        return {
            "ts": datetime.fromtimestamp(self.timestamp).strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": self.timestamp,
            "command": self.command,
            "safety_level": self.safety_level,
            "success": self.success,
            "exit_code": self.exit_code,
            "duration": round(self.duration, 3),
            "user_input": self.user_input,
            "decision_reason": self.decision_reason,
        }


def parse_audit_line(line: str) -> dict[str, Any] | None:
    """解析一行审计日志。

    支持两种格式：
    1. JSON 行（v0.7.10+ 新格式）：{"ts": "...", "command": "...", ...}
    2. 旧文本格式：[2026-07-19 17:36:52] OK exit=0 safety=white duration=0.05s cmd='...'

    解析失败返回 None。
    """
    line = line.strip()
    if not line:
        return None

    # 优先尝试 JSON
    if line.startswith("{"):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            pass

    # 旧文本格式解析
    # [ts] STATUS exit=N safety=LEVEL duration=Xs cmd='...' [user_input='...'] [reason='...']
    m = re.match(
        r"^\[(?P<ts>[^\]]+)\]\s+"
        r"(?P<status>OK|FAIL)\s+"
        r"exit=(?P<exit>-?\d+)\s+"
        r"safety=(?P<safety>\w+)\s+"
        r"duration=(?P<duration>[\d.]+)s\s+"
        r"cmd=(?P<cmd>.+?)(?:\s+user_input=(?P<ui>.+?))?(?:\s+reason=(?P<reason>.+))?$",
        line,
    )
    if not m:
        return {"raw": line}

    # 解析 cmd/user_input/reason（用了 repr() 格式，带引号）
    def unrepr(s: str | None) -> str:
        if not s:
            return ""
        s = s.strip()
        # repr 输出带单引号或双引号
        if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
            # 简单反转义（不完美但够用）
            inner = s[1:-1]
            return inner.replace("\\'", "'").replace('\\"', '"').replace("\\\\", "\\")
        return s

    return {
        "ts": m.group("ts"),
        "success": m.group("status") == "OK",
        "exit_code": int(m.group("exit")),
        "safety_level": m.group("safety"),
        "duration": float(m.group("duration")),
        "command": unrepr(m.group("cmd")),
        "user_input": unrepr(m.group("ui")) if m.group("ui") else None,
        "decision_reason": unrepr(m.group("reason")) if m.group("reason") else None,
    }


def write_audit(entry: AuditEntry) -> None:
    """追加审计日志（JSON 行格式）。失败不抛异常（审计是 best-effort）。"""
    try:
        path = audit_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
    except OSError:
        pass


def execute(command: str, opts: ExecOptions | None = None) -> ExecResult:
    """执行一条命令。

    - 默认 shell=False，用 shlex 拆参数
    - opts.shell=True 时整条命令交给 bash -c（用于 YAML 模板里的管道/重定向）
    - 实时读 stdout/stderr（select），行级回调 on_progress
    - 超时返回 timed_out=True
    """
    opts = opts or ExecOptions()
    start = time.monotonic()

    # 安全分类（用于审计）
    decision: SafetyDecision = classify(command)

    env = os.environ.copy()
    if opts.env:
        env.update(opts.env)

    # 强制非交互（避免 apt 等卡在 prompt）
    env.setdefault("DEBIAN_FRONTEND", "noninteractive")
    env.setdefault("NEEDRESTART_MODE", "a")
    env.setdefault("NEEDRESTART_SUSPEND", "1")

    args: list[str] | str
    if opts.shell:
        args = ["bash", "-c", command]
    else:
        args = parse_args(command)
        if not args:
            return ExecResult(
                success=False, exit_code=-1, stdout="", stderr="空命令",
                duration=0.0, command=command,
            )

    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE if opts.stdin is not None else None,
            cwd=str(opts.cwd) if opts.cwd else None,
            env=env,
            text=True,
            bufsize=1,  # 行缓冲
        )
    except FileNotFoundError as e:
        result = ExecResult(
            success=False, exit_code=127, stdout="", stderr=str(e),
            duration=time.monotonic() - start, command=command,
        )
        if opts.audit:
            write_audit(AuditEntry(
                timestamp=time.time(), command=command,
                safety_level=decision.level, success=False,
                exit_code=127, duration=result.duration,
            ))
        return result
    except Exception as e:  # noqa: BLE001
        result = ExecResult(
            success=False, exit_code=-1, stdout="", stderr=f"启动失败: {e}",
            duration=time.monotonic() - start, command=command,
        )
        if opts.audit:
            write_audit(AuditEntry(
                timestamp=time.time(), command=command,
                safety_level=decision.level, success=False,
                exit_code=-1, duration=result.duration,
            ))
        return result

    # 写 stdin
    if opts.stdin is not None and proc.stdin:
        try:
            proc.stdin.write(opts.stdin)
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    timed_out = False

    # select 实时读
    pipes = []
    if proc.stdout:
        pipes.append(proc.stdout)
    if proc.stderr:
        pipes.append(proc.stderr)
    pipe_names = {id(proc.stdout): "stdout", id(proc.stderr): "stderr"} if pipes else {}

    deadline = (start + opts.timeout) if opts.timeout else None

    while pipes:
        if deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            timeout = min(remaining, 0.5)
        else:
            timeout = 0.5

        try:
            readable, _, _ = select.select(pipes, [], [], timeout)
        except (OSError, ValueError):
            break

        if not readable:
            # select 超时，检查进程是否已退出
            if proc.poll() is not None:
                # 读光剩余
                for p in list(pipes):
                    try:
                        rest = p.read()
                    except Exception:  # noqa: BLE001
                        rest = ""
                    if rest:
                        name = pipe_names.get(id(p), "stdout")
                        target = stdout_lines if name == "stdout" else stderr_lines
                        for line in rest.splitlines():
                            target.append(line)
                            if opts.on_progress:
                                try:
                                    opts.on_progress(name, line)
                                except Exception:  # noqa: BLE001
                                    pass
                    pipes.remove(p)
                break
            continue

        for p in readable:
            try:
                line = p.readline()
            except Exception:  # noqa: BLE001
                line = ""
            if not line:
                pipes.remove(p)
                continue
            line_text = line.rstrip("\n")
            name = pipe_names.get(id(p), "stdout")
            target = stdout_lines if name == "stdout" else stderr_lines
            target.append(line_text)
            if opts.on_progress:
                try:
                    opts.on_progress(name, line_text)
                except Exception:  # noqa: BLE001
                    pass

    if timed_out:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.terminate()

    exit_code = proc.wait() if proc.poll() is None else proc.returncode
    duration = time.monotonic() - start

    # 关闭管道
    for p in (proc.stdout, proc.stderr, proc.stdin):
        if p:
            try:
                p.close()
            except Exception:  # noqa: BLE001
                pass

    result = ExecResult(
        success=(exit_code == 0 and not timed_out),
        exit_code=exit_code if not timed_out else -1,
        stdout="\n".join(stdout_lines),
        stderr="\n".join(stderr_lines),
        duration=duration,
        command=command,
        timed_out=timed_out,
    )

    if opts.audit:
        write_audit(AuditEntry(
            timestamp=time.time(), command=command,
            safety_level=decision.level, success=result.success,
            exit_code=result.exit_code, duration=result.duration,
            decision_reason=decision.reason,
        ))

    return result


def execute_safely(
    command: str,
    opts: ExecOptions | None = None,
    user_input: str | None = None,
) -> ExecResult:
    """带安全检查的执行。

    - 黑名单：拒绝，返回失败结果
    - 其他级别：直接执行（白名单 / 灰名单已经由上层确认过）
    """
    decision = classify(command)
    if decision.level == "black":
        return ExecResult(
            success=False,
            exit_code=-2,
            stdout="",
            stderr=f"安全引擎拒绝：{decision.reason}",
            duration=0.0,
            command=command,
        )

    opts = opts or ExecOptions()
    result = execute(command, opts)

    # 补充审计条目（带用户输入）
    if opts.audit:
        write_audit(AuditEntry(
            timestamp=time.time(), command=command,
            safety_level=decision.level, success=result.success,
            exit_code=result.exit_code, duration=result.duration,
            user_input=user_input, decision_reason=decision.reason,
        ))
    return result


def which(program: str) -> str | None:
    """查找程序路径（兼容 PATH）。"""
    from shutil import which as _which
    return _which(program)


def command_exists(program: str) -> bool:
    return which(program) is not None
