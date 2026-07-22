"""自进化模块（v0.8.9 起抽离自 server.py）。

让 LLM 和 CLI 都能触发：
- 重启后端服务（trigger_restart）
- 后台编译桌面端 Tauri 二进制（trigger_build）
- 查询编译/重启状态（read_self_status）
- 一键升级 6 个版本号文件（bump_version）

server.py 的 `/api/self/*` 4 个端点和 cli.py 的 `lihua self` 子命令共用本模块，
避免逻辑重复。

设计：
- build / restart 是"触发即返回"的异步任务：spawn detached bash 脚本，
  状态实时写到状态文件，调用方轮询 read_self_status 获取进度。
- version_bump 是同步操作：正则替换 6 个文件的版本号。
- 状态文件放在 data_dir()（~/.local/share/lihua/），与后端数据同目录。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from lihua import __version__
from lihua.config import data_dir
from lihua.logging_config import get_logger

_log = get_logger(__name__)

# 状态文件目录（与后端数据同目录）
_SELF_STATUS_DIR = Path(data_dir())
_SELF_STATUS_DIR.mkdir(parents=True, exist_ok=True)
BUILD_STATUS_FILE = str(_SELF_STATUS_DIR / "build-status.json")
RESTART_STATUS_FILE = str(_SELF_STATUS_DIR / "restart-status.json")

# 项目根目录：self_evolve.py 在 src/lihua/，向上 3 层即项目根
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _write_status_file(path: str, data: dict) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        _log.warning(f"写状态文件失败 {path}: {e}")


def _read_status_file(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def read_self_status() -> dict[str, Any]:
    """查询编译/重启状态。

    返回：
    - build: 编译状态（running/done/failed/timeout + exit_code + 时间戳）
    - restart: 重启状态（pending/done/failed + old_pid/new_pid + 时间戳）
    - current_pid: 当前进程 PID
    - current_version: 当前版本号
    """
    build = _read_status_file(BUILD_STATUS_FILE)
    restart = _read_status_file(RESTART_STATUS_FILE)

    # 如果编译状态是 running，检查是否超时（10 分钟）
    if build and build.get("status") == "running":
        elapsed = time.time() - build.get("started_at", 0)
        if elapsed > 600:
            build["status"] = "timeout"
            build["message"] = f"编译超时（{elapsed:.0f}s）"
            _write_status_file(BUILD_STATUS_FILE, build)

    return {
        "build": build,
        "restart": restart,
        "current_pid": os.getpid(),
        "current_version": __version__,
    }


def trigger_restart() -> dict[str, Any]:
    """重启后端服务（异步，立即返回）。

    实现原理：
    1. 立即返回响应（不阻塞）
    2. spawn 独立重启脚本（detached，不依赖当前进程）
    3. 脚本 sleep 5s（让 LLM 有时间生成回复 + SSE 流推送 done 事件）
    4. pkill 旧 uvicorn 进程
    5. sleep 3s 等端口释放
    6. nohup spawn 新 uvicorn 进程
    """
    import sys

    # 记录重启状态
    restart_status = {
        "status": "pending",
        "started_at": time.time(),
        "old_pid": os.getpid(),
        "message": "重启脚本已启动，约 8 秒后新后端就绪",
    }
    _write_status_file(RESTART_STATUS_FILE, restart_status)

    # 构造重启脚本
    python_bin = sys.executable  # venv 的 python
    # 用 pkill -f 精准匹配 uvicorn.*lihua.server，避免误杀
    # sleep 5s 让 LLM 有时间生成回复 + SSE 流推送 done 事件
    #   之前 sleep 1s 太短，LLM 调 self_restart 后还在生成回复时后端就被 kill
    #   导致 SSE 流断开，前端显示"连接失败"而非正常显示 LLM 回复
    # 状态文件用 date +%s 在脚本执行时生成时间戳（不依赖 Python）
    restart_script = f"""#!/bin/bash
sleep 5
pkill -f "uvicorn.*lihua.server" 2>/dev/null
sleep 3
nohup {python_bin} -m uvicorn lihua.server:create_app --factory --host 127.0.0.1 --port 7531 --log-level warning > /tmp/lihua-backend.log 2>&1 &
new_pid=$!
cat > {RESTART_STATUS_FILE} << EOF
{{"status": "done", "new_pid": "$new_pid", "finished_at": $(date +%s)}}
EOF
"""
    # 写脚本到临时文件并执行（detached）
    script_path = "/tmp/lihua-restart.sh"
    with open(script_path, "w") as f:
        f.write(restart_script)
    os.chmod(script_path, 0o755)

    # 启动 detached 重启脚本
    try:
        subprocess.Popen(
            ["bash", script_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,  # detached，不依赖当前进程
        )
    except OSError as e:
        _log.error(f"启动重启脚本失败: {e}")
        _write_status_file(RESTART_STATUS_FILE, {
            "status": "failed",
            "error": str(e),
            "finished_at": time.time(),
        })
        return {"ok": False, "error": f"启动重启脚本失败: {e}"}

    _log.warning(f"自重启已触发，当前 PID={os.getpid()}，5 秒后将被 kill，8 秒后新后端就绪")

    return {
        "ok": True,
        "message": "重启已启动，约 8 秒后新后端就绪",
        "old_pid": os.getpid(),
        "status_file": RESTART_STATUS_FILE,
    }


def trigger_build() -> dict[str, Any]:
    """后台编译桌面端 Tauri 二进制（异步，立即返回）。

    长时间任务（30-60s），异步执行：
    1. 立即返回响应
    2. spawn 后台编译脚本
    3. 编译状态实时写到 build-status.json
    4. 调用方轮询 read_self_status 获取进度

    编译完成后需要重启桌面端才能生效（新二进制替换旧进程）。
    """
    # 检查是否已有编译在跑
    old_status = _read_status_file(BUILD_STATUS_FILE)
    if old_status and old_status.get("status") == "running":
        started_at = old_status.get("started_at", 0)
        elapsed = time.time() - started_at
        if elapsed < 600:  # 10 分钟内认为还在跑
            return {
                "ok": False,
                "error": f"已有编译在跑（{elapsed:.0f}s 前启动），请等完成后再试",
                "status": old_status,
            }

    # 记录编译状态
    started_at = time.time()
    build_status = {
        "status": "running",
        "started_at": started_at,
        "finished_at": None,
        "exit_code": None,
        "message": "编译已启动",
    }
    _write_status_file(BUILD_STATUS_FILE, build_status)

    # 构造编译脚本
    project_root = str(_PROJECT_ROOT / "desktop")
    build_log = "/tmp/lihua-build.log"
    build_script = f"""#!/bin/bash
cd {project_root} || exit 1
npx tauri build --no-bundle > {build_log} 2>&1
exit_code=$?
cat > {BUILD_STATUS_FILE} << EOF
{{"status": "done", "started_at": {started_at}, "finished_at": $(date +%s), "exit_code": $exit_code, "message": "编译完成（exit=$exit_code）"}}
EOF
"""
    script_path = "/tmp/lihua-build.sh"
    with open(script_path, "w") as f:
        f.write(build_script)
    os.chmod(script_path, 0o755)

    # 启动 detached 编译脚本
    try:
        subprocess.Popen(
            ["bash", script_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as e:
        _log.error(f"启动编译脚本失败: {e}")
        _write_status_file(BUILD_STATUS_FILE, {
            "status": "failed",
            "error": str(e),
            "finished_at": time.time(),
        })
        return {"ok": False, "error": f"启动编译脚本失败: {e}"}

    _log.info("桌面端编译已启动（后台），状态写到 " + BUILD_STATUS_FILE)

    return {
        "ok": True,
        "message": "编译已启动（后台），约 30-60 秒完成",
        "status_file": BUILD_STATUS_FILE,
        "build_log": build_log,
    }


# 6 个版本号文件的替换规则：(相对路径, 正则模式, 替换模板)
# bump_version 用 base_version/py/rust_code 三种格式填充
def _version_files(new_version_py: str, base_version: str, rust_code_version: str):
    """返回 6 个版本号文件的 (相对路径, 正则, 替换, 描述) 列表。"""
    return [
        (
            "src/lihua/__init__.py",
            r'(__version__\s*=\s*")[^"]+(")',
            f'\\g<1>{new_version_py}\\g<2>',
            f'__version__ = "{new_version_py}"',
        ),
        (
            "pyproject.toml",
            r'(^version\s*=\s*")[^"]+(")',
            f'\\g<1>{new_version_py}\\g<2>',
            f'version = "{new_version_py}"',
        ),
        (
            "desktop/package.json",
            r'("version"\s*:\s*")[^"]+(")',
            f'\\g<1>{new_version_py}\\g<2>',
            f'"version": "{new_version_py}"',
        ),
        (
            "desktop/src-tauri/Cargo.toml",
            r'(^version\s*=\s*")[^"]+(")',
            f'\\g<1>{base_version}\\g<2>',
            f'version = "{base_version}"',
        ),
        (
            "desktop/src-tauri/tauri.conf.json",
            r'("version"\s*:\s*")[^"]+(")',
            f'\\g<1>{base_version}\\g<2>',
            f'"version": "{base_version}"',
        ),
        (
            "desktop/src-tauri/src/lib.rs",
            r'(const APP_VERSION:\s*&str\s*=\s*")[^"]+(")',
            f'\\g<1>{rust_code_version}\\g<2>',
            f'const APP_VERSION: &str = "{rust_code_version}";',
        ),
    ]


def bump_version(new_version: str = "") -> dict[str, Any]:
    """一键升级 6 个版本号文件。

    支持 LLM/CLI 改完代码后自动升级版本号，避免手动改 6 个文件容易遗漏。

    6 个文件：
    1. src/lihua/__init__.py: __version__ = "0.8.9a0"
    2. pyproject.toml: version = "0.8.9a0"
    3. desktop/package.json: "version": "0.8.9a0"
    4. desktop/src-tauri/Cargo.toml: version = "0.8.9"
    5. desktop/src-tauri/tauri.conf.json: "version": "0.8.9"
    6. desktop/src-tauri/src/lib.rs: const APP_VERSION: &str = "0.8.9-alpha";

    版本号格式：
    - Python（3 个文件）：带 alpha 后缀，如 "0.8.10a0"
    - Rust JSON/TOML（2 个文件）：无后缀，如 "0.8.10"
    - Rust 代码（1 个文件）：带 -alpha 后缀，如 "0.8.10-alpha"

    参数：
    - new_version: 新版本号（如 "0.8.10a0"），为空则自动 patch +1
    """
    old_version = __version__  # 如 "0.8.9a0"

    # 计算新版本号
    if new_version:
        new_version_py = new_version
    else:
        # 自动 patch +1：0.8.9a0 → 0.8.10a0
        m = re.match(r"^(\d+)\.(\d+)\.(\d+)", old_version)
        if not m:
            return {"ok": False, "error": f"无法解析当前版本号: {old_version}"}
        major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
        new_version_py = f"{major}.{minor}.{patch + 1}a0"

    # 从 Python 版本号派生其他格式
    # "0.8.10a0" → "0.8.10"（Rust JSON/TOML）→ "0.8.10-alpha"（Rust code）
    base_version = re.sub(r"[a-z]\d*$", "", new_version_py)  # 去掉 alpha 后缀
    rust_code_version = f"{base_version}-alpha"

    files_to_update = _version_files(new_version_py, base_version, rust_code_version)

    updated_files = []
    failed_files = []

    for rel_path, pattern, replacement, expected_line in files_to_update:
        abs_path = _PROJECT_ROOT / rel_path
        try:
            content = abs_path.read_text(encoding="utf-8")
            new_content = re.sub(pattern, replacement, content, count=1, flags=re.MULTILINE)

            if new_content == content:
                failed_files.append({"file": rel_path, "error": "未找到版本号模式"})
                continue

            abs_path.write_text(new_content, encoding="utf-8")
            updated_files.append(rel_path)
        except OSError as e:
            failed_files.append({"file": rel_path, "error": str(e)})

    _log.info(
        f"version_bump: {old_version} → {new_version_py} "
        f"(成功 {len(updated_files)}/6, 失败 {len(failed_files)})"
    )

    return {
        "ok": len(failed_files) == 0,
        "old_version": old_version,
        "new_version": new_version_py,
        "new_version_rust": base_version,
        "new_version_rust_code": rust_code_version,
        "files_updated": updated_files,
        "files_failed": failed_files,
        "message": (
            f"版本号升级: {old_version} → {new_version_py}（{len(updated_files)}/6 文件更新）"
            if not failed_files
            else f"部分失败: {len(updated_files)}/6 成功, {len(failed_files)} 失败"
        ),
    }
