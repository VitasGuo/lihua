"""v0.8.24: 测试 lihua gui 启动前的自检逻辑 _check_binary_ready。

覆盖 4 种场景：
  1. 二进制不存在 → 不就绪
  2. 版本号不匹配（Python vs Rust APP_VERSION）→ 不就绪
  3. 前端/Rust 源码比二进制新 → 不就绪
  4. 全部就绪 → 就绪
"""

from __future__ import annotations

import importlib
import os
import time
from pathlib import Path
from unittest import mock

import pytest


def _make_desktop_tree(tmp_path: Path) -> Path:
    """在临时目录里创建最小化的 desktop/ 目录结构。"""
    desktop = tmp_path / "desktop"
    (desktop / "src").mkdir(parents=True)
    (desktop / "src-tauri" / "src").mkdir(parents=True)
    (desktop / "src-tauri" / "target" / "release").mkdir(parents=True)
    return desktop


def _write_binary(desktop: Path, mtime_offset: float = 0.0) -> Path:
    """写入一个假的二进制文件，返回路径。mtime_offset 负数表示更旧。"""
    binary = desktop / "src-tauri" / "target" / "release" / "lihua-desktop"
    binary.write_bytes(b"\x7fELF fake binary")
    if mtime_offset:
        ts = time.time() + mtime_offset
        os.utime(binary, (ts, ts))
    return binary


def _write_lib_rs(desktop: Path, app_version: str = "0.8.24-alpha") -> Path:
    """写入带 APP_VERSION 的 lib.rs。"""
    lib_rs = desktop / "src-tauri" / "src" / "lib.rs"
    lib_rs.write_text(f'const APP_VERSION: &str = "{app_version}";\n', encoding="utf-8")
    return lib_rs


def _write_fe_source(desktop: Path, name: str = "App.tsx") -> Path:
    """写入一个前端源文件。"""
    src = desktop / "src" / name
    src.write_text("// fake source\n", encoding="utf-8")
    return src


def _reload_cli_with_version(version: str):
    """重新加载 lihua 模块，让 __version__ 生效为指定值。

    _check_binary_ready 内部 `from lihua import __version__` 是函数内 import，
    每次 call 都会读到最新值，所以只需 patch lihua.__version__。
    """
    import lihua
    return mock.patch.object(lihua, "__version__", version)


# ---------------------------------------------------------------------------
# 场景 1：二进制不存在
# ---------------------------------------------------------------------------

def test_no_binary(tmp_path: Path):
    desktop = _make_desktop_tree(tmp_path)
    _write_lib_rs(desktop)
    with _reload_cli_with_version("0.8.24a0"):
        from lihua.cli import _check_binary_ready
        ready, reason = _check_binary_ready(desktop)
    assert ready is False
    assert "不存在" in reason


# ---------------------------------------------------------------------------
# 场景 2：版本号不匹配
# ---------------------------------------------------------------------------

def test_version_mismatch(tmp_path: Path):
    desktop = _make_desktop_tree(tmp_path)
    _write_binary(desktop, mtime_offset=100)  # 二进制足够新（未来时间）
    _write_lib_rs(desktop, app_version="0.8.23-alpha")  # Rust 是旧版本
    with _reload_cli_with_version("0.8.24a0"):  # Python 是新版本
        from lihua.cli import _check_binary_ready
        ready, reason = _check_binary_ready(desktop)
    assert ready is False
    assert "版本不匹配" in reason
    assert "0.8.23" in reason
    assert "0.8.24" in reason


def test_version_match_but_alpha_suffix(tmp_path: Path):
    """alpha 后缀应被正确忽略：0.8.24a0 == 0.8.24-alpha。"""
    desktop = _make_desktop_tree(tmp_path)
    _write_binary(desktop, mtime_offset=100)
    _write_lib_rs(desktop, app_version="0.8.24-alpha")
    _write_fe_source(desktop)  # 源码也存在，但二进制更新
    with _reload_cli_with_version("0.8.24a0"):
        from lihua.cli import _check_binary_ready
        ready, reason = _check_binary_ready(desktop)
    assert ready is True
    assert reason == ""


# ---------------------------------------------------------------------------
# 场景 3：源码比二进制新
# ---------------------------------------------------------------------------

def test_frontend_source_newer(tmp_path: Path):
    desktop = _make_desktop_tree(tmp_path)
    _write_binary(desktop, mtime_offset=-10)  # 二进制 10 秒前
    _write_lib_rs(desktop)
    # 前端源码刚写入（now），比二进制新
    _write_fe_source(desktop, "App.tsx")
    with _reload_cli_with_version("0.8.24a0"):
        from lihua.cli import _check_binary_ready
        ready, reason = _check_binary_ready(desktop)
    assert ready is False
    assert "前端源代码" in reason


def test_rust_source_newer(tmp_path: Path):
    desktop = _make_desktop_tree(tmp_path)
    _write_binary(desktop, mtime_offset=-10)  # 二进制 10 秒前
    # lib.rs 刚写入（now），比二进制新
    _write_lib_rs(desktop)
    with _reload_cli_with_version("0.8.24a0"):
        from lihua.cli import _check_binary_ready
        ready, reason = _check_binary_ready(desktop)
    assert ready is False
    assert "Rust 源代码" in reason


def test_tauri_config_newer(tmp_path: Path):
    desktop = _make_desktop_tree(tmp_path)
    _write_binary(desktop, mtime_offset=-10)
    _write_lib_rs(desktop, app_version="0.8.24-alpha")
    # 让 lib.rs 也比二进制旧（避免先触发"Rust 源代码已更新"）
    lib_rs = desktop / "src-tauri" / "src" / "lib.rs"
    old_ts = time.time() - 20
    os.utime(lib_rs, (old_ts, old_ts))
    # tauri.conf.json 刚写入（now），比二进制新
    (desktop / "src-tauri" / "tauri.conf.json").write_text("{}", encoding="utf-8")
    with _reload_cli_with_version("0.8.24a0"):
        from lihua.cli import _check_binary_ready
        ready, reason = _check_binary_ready(desktop)
    assert ready is False
    assert "配置" in reason


# ---------------------------------------------------------------------------
# 场景 4：全部就绪
# ---------------------------------------------------------------------------

def test_all_ready(tmp_path: Path):
    desktop = _make_desktop_tree(tmp_path)
    _write_binary(desktop, mtime_offset=100)  # 二进制最新（未来时间）
    _write_lib_rs(desktop, app_version="0.8.24-alpha")
    _write_fe_source(desktop)  # 源码存在但比二进制旧
    with _reload_cli_with_version("0.8.24a0"):
        from lihua.cli import _check_binary_ready
        ready, reason = _check_binary_ready(desktop)
    assert ready is True
    assert reason == ""
