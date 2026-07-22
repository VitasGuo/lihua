"""v0.8.14 插件架构——让 Lihua 可被第三方扩展而不需要改源码。

二次进化第四支柱。设计目标：
1. **可扩展**：插件通过 `setup(api)` 注册 PromptSection / Skill / 钩子
2. **可塑造**：用户可在 `plugins.toml` 启用/禁用单个插件
3. **可延伸**：新增能力只需放一个 .py 文件到 `~/.config/lihua/plugins/`
4. **错误隔离**：插件抛异常不影响其他插件和主流程
5. **可调试**：通过 `/api/plugin/*` 接口查看插件状态

## 插件目录结构

```
~/.config/lihua/plugins/
├── my_plugin.py           # 单文件插件
├── complex_plugin/        # 包形式插件
│   ├── __init__.py        # 必须定义 setup(api)
│   └── helpers.py
└── another_plugin.py
```

## 插件 API

每个插件必须定义 `setup(api: PluginAPI) -> None`，api 提供：
- `api.builder`：PromptBuilder 实例（用于 register_section）
- `api.config`：Config 实例（读配置）
- `api.log`：插件专属 logger
- `api.data_dir`：插件专属数据目录（Path，自动创建）
- `api.register_section(section)`：便捷方法，等价于 `api.builder.register_section(section)`

可选定义：
- `__plugin_meta__ = {"name": "...", "version": "...", "description": "...", "author": "..."}`：元信息
- `teardown(api: PluginAPI) -> None`：卸载时调用（清理资源）

## 配置文件

`~/.config/lihua/plugins.toml`：

```toml
# 启用的插件名列表（为空则加载所有非黑名单插件）
enabled = []

# 禁用的插件名列表（黑名单，优先级高于 enabled）
disabled = ["broken_plugin"]
```

## 加载流程

1. 扫描 `~/.config/lihua/plugins/` 下所有 .py 文件和含 __init__.py 的子目录
2. 读 `plugins.toml` 获取 enabled/disabled 列表
3. 对每个插件：
   - 名字在 disabled → 跳过
   - enabled 非空且名字不在 enabled → 跳过
   - 否则 import 模块，调用 setup(api)
4. 错误隔离：单个插件失败不影响其他
5. 记录已加载插件信息（name / meta / path / status / error）

## 卸载流程

1. 对每个已加载插件（按加载的逆序）：
   - 调用 teardown(api)（如果定义了）
   - 移除该插件注册的所有 PromptSection（通过 tag 匹配）
2. 清空已加载列表
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lihua.config import Config, config_dir
from lihua.logging_config import get_logger
from lihua.prompt_builder import PromptBuilder, PromptSection, get_builder

log = get_logger(__name__)

# 插件注册的 PromptSection 都带这个 tag，卸载时按 tag 批量移除
_PLUGIN_TAG = "plugin"


def plugins_dir() -> Path:
    """插件目录：~/.config/lihua/plugins/"""
    return config_dir() / "plugins"


def plugins_config_path() -> Path:
    """插件配置文件：~/.config/lihua/plugins.toml"""
    return config_dir() / "plugins.toml"


def plugin_data_root() -> Path:
    """插件数据根目录：~/.local/share/lihua/plugin_data/"""
    from lihua.config import data_dir
    return data_dir() / "plugin_data"


@dataclass
class PluginMeta:
    """插件元信息（从 __plugin_meta__ 读取）。"""

    name: str = ""
    version: str = ""
    description: str = ""
    author: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PluginMeta":
        return cls(
            name=str(raw.get("name", "")),
            version=str(raw.get("version", "")),
            description=str(raw.get("description", "")),
            author=str(raw.get("author", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
        }


@dataclass
class PluginInfo:
    """单个插件的运行时信息。"""

    name: str  # 插件名（文件名 stem 或目录名）
    path: str  # 插件文件/目录路径
    status: str  # "loaded" / "disabled" / "error" / "skipped"
    error: str = ""  # status=error 时的错误信息
    meta: PluginMeta = field(default_factory=PluginMeta)
    registered_sections: list[str] = field(default_factory=list)  # 该插件注册的 section 名
    module: Any = None  # 已加载的模块对象（status=loaded 时有值）


class PluginAPI:
    """插件 API：插件 setup() 时收到的对象，提供注册能力。

    每个插件加载时创建一个独立的 API 实例，记录该插件注册的所有 section，
    便于卸载时清理。
    """

    def __init__(self, plugin_name: str, builder: PromptBuilder, config: Config) -> None:
        self.plugin_name = plugin_name
        self.builder = builder
        self.config = config
        self.log = get_logger(f"lihua.plugin.{plugin_name}")
        self._data_dir: Path | None = None
        # 记录该插件注册的 section 名（用于卸载时清理）
        self.registered_sections: list[str] = []

    @property
    def data_dir(self) -> Path:
        """插件专属数据目录（自动创建）。

        路径：~/.local/share/lihua/plugin_data/{plugin_name}/
        """
        if self._data_dir is None:
            self._data_dir = plugin_data_root() / self.plugin_name
            self._data_dir.mkdir(parents=True, exist_ok=True)
        return self._data_dir

    def register_section(self, section: PromptSection) -> "PluginAPI":
        """注册一个 PromptSection。

        自动给 section 加上 "plugin" tag（用于卸载时按 tag 清理）。
        重复注册同名 section 会覆盖。
        """
        # 确保 tag 里有 "plugin" 标记
        if _PLUGIN_TAG not in section.tags:
            section.tags.append(_PLUGIN_TAG)
        # 记录 section 名（去重）
        if section.name not in self.registered_sections:
            self.registered_sections.append(section.name)
        self.builder.register_section(section)
        return self

    def unregister_section(self, name: str) -> "PluginAPI":
        """移除一个 PromptSection。"""
        if name in self.registered_sections:
            self.registered_sections.remove(name)
        self.builder.unregister_section(name)
        return self


class PluginLoader:
    """插件加载器（单例）。

    用法：
        loader = get_loader()
        loader.load_all()  # 启动时调用
        info = loader.list_plugins()  # 查看已加载插件
        loader.reload()  # 热重载
    """

    def __init__(self) -> None:
        self._plugins: dict[str, PluginInfo] = {}
        self._apis: dict[str, PluginAPI] = {}  # plugin_name → API（用于 teardown）
        self._config_cache: dict[str, Any] = {"enabled": [], "disabled": []}

    def _read_config(self) -> tuple[list[str], list[str]]:
        """读 plugins.toml，返回 (enabled, disabled) 列表。

        文件不存在时返回 ([], [])。
        """
        import tomllib

        path = plugins_config_path()
        if not path.exists():
            return [], []
        try:
            with path.open("rb") as f:
                raw = tomllib.load(f)
            enabled = [str(x) for x in raw.get("enabled", [])]
            disabled = [str(x) for x in raw.get("disabled", [])]
            self._config_cache = {"enabled": enabled, "disabled": disabled}
            return enabled, disabled
        except (OSError, tomllib.TOMLDecodeError) as e:
            log.warning(f"读取插件配置失败 ({e})，使用默认（加载所有）")
            return [], []

    def _discover_plugins(self) -> list[tuple[str, Path]]:
        """扫描插件目录，返回 [(name, path), ...]。

        支持两种形式：
        - 单文件：my_plugin.py → name="my_plugin", path=文件路径
        - 包形式：my_plugin/__init__.py → name="my_plugin", path=目录路径
        """
        result: list[tuple[str, Path]] = []
        pdir = plugins_dir()
        if not pdir.exists():
            return result

        try:
            entries = sorted(pdir.iterdir())
        except OSError as e:
            log.warning(f"扫描插件目录失败：{e}")
            return result

        for entry in entries:
            # 跳过隐藏文件 / __pycache__
            if entry.name.startswith(".") or entry.name == "__pycache__":
                continue
            # 单文件 .py
            if entry.is_file() and entry.suffix == ".py":
                result.append((entry.stem, entry))
            # 包形式（目录含 __init__.py）
            elif entry.is_dir() and (entry / "__init__.py").exists():
                result.append((entry.name, entry))
        return result

    def _import_plugin(self, name: str, path: Path) -> Any:
        """动态 import 插件模块。

        单文件：path 是 .py 文件，用 importlib.util.spec_from_file_location
        包形式：path 是目录，spec_from_file_location 用 __init__.py
        """
        module_name = f"_lihua_plugin_{name}"

        if path.is_file():
            spec = importlib.util.spec_from_file_location(module_name, path)
        else:
            init_file = path / "__init__.py"
            spec = importlib.util.spec_from_file_location(module_name, init_file)

        if spec is None or spec.loader is None:
            raise ImportError(f"无法创建模块 spec：{path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    def _load_one(
        self,
        name: str,
        path: Path,
        enabled_list: list[str],
        disabled_list: list[str],
        config: Config,
    ) -> PluginInfo:
        """加载单个插件，返回 PluginInfo。"""
        # 黑名单优先
        if name in disabled_list:
            return PluginInfo(
                name=name,
                path=str(path),
                status="disabled",
                error="在 plugins.toml 的 disabled 列表中",
            )
        # 白名单非空时检查
        if enabled_list and name not in enabled_list:
            return PluginInfo(
                name=name,
                path=str(path),
                status="skipped",
                error="不在 plugins.toml 的 enabled 列表中",
            )

        try:
            module = self._import_plugin(name, path)
        except Exception as e:
            log.error(f"插件 {name} import 失败：{e}", exc_info=True)
            return PluginInfo(
                name=name,
                path=str(path),
                status="error",
                error=f"import 失败：{e}",
            )

        # 读元信息
        meta = PluginMeta()
        if hasattr(module, "__plugin_meta__"):
            try:
                meta = PluginMeta.from_dict(module.__plugin_meta__ or {})
                # 如果 meta.name 为空，用文件名
                if not meta.name:
                    meta.name = name
            except Exception as e:
                log.warning(f"插件 {name} 的 __plugin_meta__ 解析失败：{e}")

        # 检查 setup 函数
        if not hasattr(module, "setup") or not callable(module.setup):
            return PluginInfo(
                name=name,
                path=str(path),
                status="error",
                error="缺少 setup(api) 函数",
                meta=meta,
            )

        # 创建 API + 调 setup
        builder = get_builder()
        api = PluginAPI(plugin_name=name, builder=builder, config=config)
        try:
            module.setup(api)
        except Exception as e:
            log.error(f"插件 {name} setup() 失败：{e}", exc_info=True)
            # 清理已注册的 section
            for sec_name in api.registered_sections:
                builder.unregister_section(sec_name)
            return PluginInfo(
                name=name,
                path=str(path),
                status="error",
                error=f"setup() 失败：{e}",
                meta=meta,
            )

        info = PluginInfo(
            name=name,
            path=str(path),
            status="loaded",
            meta=meta,
            registered_sections=list(api.registered_sections),
            module=module,
        )
        self._apis[name] = api
        log.info(f"插件已加载：{name}（注册 {len(api.registered_sections)} 个 section）")
        return info

    def load_all(self, config: Config | None = None) -> dict[str, PluginInfo]:
        """加载所有插件。

        返回 {name: PluginInfo} 字典。
        已加载的插件会先卸载再重新加载（等同 reload）。
        """
        if self._plugins:
            self.unload_all()

        cfg = config if config is not None else Config.load()
        enabled_list, disabled_list = self._read_config()
        discoveries = self._discover_plugins()

        log.info(
            f"扫描插件目录：发现 {len(discoveries)} 个候选，"
            f"enabled={enabled_list or '(全部)'}, disabled={disabled_list}"
        )

        for name, path in discoveries:
            info = self._load_one(name, path, enabled_list, disabled_list, cfg)
            self._plugins[name] = info

        loaded_count = sum(1 for i in self._plugins.values() if i.status == "loaded")
        error_count = sum(1 for i in self._plugins.values() if i.status == "error")
        log.info(
            f"插件加载完成：{loaded_count} 成功，{error_count} 失败，"
            f"{len(self._plugins) - loaded_count - error_count} 跳过/禁用"
        )
        return dict(self._plugins)

    def unload_all(self) -> None:
        """卸载所有已加载插件。

        1. 对每个已加载插件（逆序）调 teardown(api)（如果定义了）
        2. 移除该插件注册的所有 PromptSection
        3. 清空状态
        """
        # 逆序卸载（后加载的先卸载）
        for name in reversed(list(self._plugins.keys())):
            info = self._plugins[name]
            if info.status != "loaded":
                continue
            api = self._apis.get(name)
            if api is None:
                continue

            # 调 teardown（如果定义了）
            if info.module is not None and hasattr(info.module, "teardown"):
                try:
                    info.module.teardown(api)
                except Exception as e:
                    log.warning(f"插件 {name} teardown() 失败（继续清理）：{e}")

            # 移除注册的 section
            for sec_name in api.registered_sections:
                api.builder.unregister_section(sec_name)

            # 清理 sys.modules 中的插件模块
            module_name = f"_lihua_plugin_{name}"
            sys.modules.pop(module_name, None)

        self._plugins.clear()
        self._apis.clear()
        log.info("所有插件已卸载")

    def reload(self, config: Config | None = None) -> dict[str, PluginInfo]:
        """重新加载所有插件（unload + load）。"""
        self.unload_all()
        return self.load_all(config)

    def list_plugins(self) -> list[PluginInfo]:
        """列出所有已发现的插件（按名字排序）。"""
        return sorted(self._plugins.values(), key=lambda i: i.name)

    def get_plugin(self, name: str) -> PluginInfo | None:
        """获取单个插件信息。"""
        return self._plugins.get(name)

    def enable_plugin(self, name: str) -> tuple[bool, str]:
        """启用单个插件：从 disabled 移除 + 加入 enabled（如果非空）+ 加载。

        返回 (ok, msg)。
        """
        if name not in self._plugins:
            # 可能是未加载的插件，先扫描看是否存在
            discoveries = dict(self._discover_plugins())
            if name not in discoveries:
                return False, f"插件 '{name}' 不存在"
            # 加载这一个
            cfg = Config.load()
            enabled_list, disabled_list = self._read_config()
            # 临时清除 disabled 中的 name
            if name in disabled_list:
                self._set_plugin_state(name, enable=True)
            info = self._load_one(name, discoveries[name], [], [], cfg)
            self._plugins[name] = info
            return info.status == "loaded", f"插件 '{name}' 已加载（status={info.status}）"

        info = self._plugins[name]
        if info.status == "loaded":
            return True, f"插件 '{name}' 已处于加载状态"

        # 更新配置文件
        self._set_plugin_state(name, enable=True)

        # 重新加载这一个
        cfg = Config.load()
        discoveries = dict(self._discover_plugins())
        if name not in discoveries:
            return False, f"插件文件不存在：{name}"

        # 先卸载旧的（如果有）
        if name in self._apis:
            api = self._apis.pop(name)
            for sec_name in api.registered_sections:
                api.builder.unregister_section(sec_name)

        enabled_list, disabled_list = self._read_config()
        new_info = self._load_one(name, discoveries[name], enabled_list, disabled_list, cfg)
        self._plugins[name] = new_info
        if new_info.status == "loaded":
            return True, f"插件 '{name}' 已启用"
        return False, f"插件 '{name}' 启用失败：{new_info.error}"

    def disable_plugin(self, name: str) -> tuple[bool, str]:
        """禁用单个插件：加入 disabled + 卸载。

        返回 (ok, msg)。
        """
        if name not in self._plugins:
            # 插件不在已加载列表，直接写配置
            self._set_plugin_state(name, enable=False)
            return True, f"插件 '{name}' 已加入黑名单"

        info = self._plugins[name]
        if info.status != "loaded":
            # 已经是禁用/出错状态，只需更新配置
            self._set_plugin_state(name, enable=False)
            return True, f"插件 '{name}' 已禁用（原本未加载）"

        # 卸载
        api = self._apis.pop(name, None)
        if api is not None:
            # 调 teardown
            if info.module is not None and hasattr(info.module, "teardown"):
                try:
                    info.module.teardown(api)
                except Exception as e:
                    log.warning(f"插件 {name} teardown() 失败（继续禁用）：{e}")
            for sec_name in api.registered_sections:
                api.builder.unregister_section(sec_name)

        # 更新状态
        info.status = "disabled"
        info.error = "用户手动禁用"
        info.registered_sections = []
        info.module = None

        # 更新配置文件
        self._set_plugin_state(name, enable=False)
        return True, f"插件 '{name}' 已禁用"

    def _set_plugin_state(self, name: str, enable: bool) -> None:
        """更新 plugins.toml 中的 enabled/disabled 列表。

        enable=True：从 disabled 移除 name
        enable=False：从 enabled 移除 name，加入 disabled
        """
        import tomllib

        path = plugins_config_path()
        enabled, disabled = self._read_config()

        if enable:
            if name in disabled:
                disabled.remove(name)
            # 不主动加入 enabled（空 enabled 表示加载所有）
        else:
            if name in enabled:
                enabled.remove(name)
            if name not in disabled:
                disabled.append(name)

        # 写 toml
        lines: list[str] = []
        lines.append("# Lihua 插件配置")
        lines.append("# enabled: 启用的插件名列表（为空则加载所有非黑名单插件）")
        lines.append("# disabled: 禁用的插件名列表（黑名单，优先级高于 enabled）")
        lines.append("")
        if enabled:
            lines.append("enabled = [" + ", ".join(f'"{x}"' for x in enabled) + "]")
        else:
            lines.append("enabled = []")
        if disabled:
            lines.append("disabled = [" + ", ".join(f'"{x}"' for x in disabled) + "]")
        else:
            lines.append("disabled = []")
        lines.append("")

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(lines), encoding="utf-8")
            self._config_cache = {"enabled": enabled, "disabled": disabled}
        except OSError as e:
            log.error(f"写入插件配置失败：{e}")

    def stats(self) -> dict[str, Any]:
        """返回加载器统计信息。"""
        plugins = self.list_plugins()
        return {
            "total": len(plugins),
            "loaded": sum(1 for p in plugins if p.status == "loaded"),
            "disabled": sum(1 for p in plugins if p.status == "disabled"),
            "error": sum(1 for p in plugins if p.status == "error"),
            "skipped": sum(1 for p in plugins if p.status == "skipped"),
            "plugins_dir": str(plugins_dir()),
            "config_file": str(plugins_config_path()),
            "plugins": [
                {
                    "name": p.name,
                    "status": p.status,
                    "error": p.error,
                    "path": p.path,
                    "meta": p.meta.to_dict(),
                    "registered_sections": list(p.registered_sections),
                }
                for p in plugins
            ],
        }


# ─── 全局单例 ─────────────────────────────────────────────────────

_loader: PluginLoader | None = None


def get_loader() -> PluginLoader:
    """获取全局 PluginLoader 单例。"""
    global _loader
    if _loader is None:
        _loader = PluginLoader()
    return _loader


def reset_loader() -> PluginLoader:
    """重置全局 loader（卸载所有插件 + 创建新实例）。"""
    global _loader
    if _loader is not None:
        _loader.unload_all()
    _loader = PluginLoader()
    return _loader
