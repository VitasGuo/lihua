"""用户配置与路径管理。"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir, user_data_dir, user_state_dir

APP_NAME = "lihua"
APP_AUTHOR = "lihua"


def config_dir() -> Path:
    """~/.config/lihua"""
    return Path(user_config_dir(APP_NAME, APP_AUTHOR))


def data_dir() -> Path:
    """~/.local/share/lihua"""
    return Path(user_data_dir(APP_NAME, APP_AUTHOR))


def state_dir() -> Path:
    """~/.local/state/lihua"""
    return Path(user_state_dir(APP_NAME, APP_AUTHOR))


def skills_user_dir() -> Path:
    """用户自定义 Skill 目录：~/.config/lihua/skills"""
    return config_dir() / "skills"


def audit_log_path() -> Path:
    return data_dir() / "audit.log"


def history_path() -> Path:
    return data_dir() / "history.json"


def config_file_path() -> Path:
    return config_dir() / "config.toml"


@dataclass
class LLMConfig:
    """LLM 路由配置。"""

    enabled: bool = False
    provider: str = "deepseek"
    api_key: str = ""
    api_base: str | None = None
    model: str = "deepseek-chat"
    fallback_model: str | None = None
    timeout: float = 30.0
    temperature: float = 0.3
    max_tokens: int = 1024


@dataclass
class MemoryConfig:
    """v0.8.11: 记忆系统配置。"""

    enabled: bool = True  # 是否启用记忆系统（记录 episode + 注入上下文）
    max_episodes: int = 1000  # 情景记忆最大保留条数
    max_knowledge_patterns: int = 500  # 知识库最大保留模式数
    inject_context: bool = True  # 是否在 system prompt 注入记忆上下文
    # v0.8.16: 记忆分层加载（参考 OpenClaw L0-L4 设计，减少 token + 记忆衰减）
    hot_days: int = 3       # L2 热：最近 3 天 episodes（每次注入 context）
    warm_days: int = 7      # L3 温：7 天内 episodes（memory_recall 检索范围）
    archive_days: int = 30  # L4 冷：30 天前的 episodes（归档到 archive/，P1-2 实现）


@dataclass
class Config:
    """全局配置。"""

    llm: LLMConfig = field(default_factory=LLMConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    always_confirm_grey: bool = True
    auto_execute_whitelist: bool = True
    audit_log: bool = True
    language: str = "zh"
    log_level: str = "INFO"  # v0.7.7: 日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls) -> "Config":
        """加载配置：环境变量 > config.toml > 默认值。"""
        cfg = cls()
        path = config_file_path()
        if path.exists():
            try:
                with path.open("rb") as f:
                    raw = tomllib.load(f)
                cfg = cls._from_dict(raw)
            except (OSError, tomllib.TOMLDecodeError) as e:
                # 配置损坏不致命，记录到 stderr 由调用方处理
                import sys

                print(f"[lihua] 配置加载失败 ({e})，使用默认配置", file=sys.stderr)
        # 环境变量覆盖
        if (key := os.environ.get("DEEPSEEK_API_KEY")) and not cfg.llm.api_key:
            cfg.llm.api_key = key
            cfg.llm.provider = "deepseek"
            cfg.llm.model = "deepseek-chat"
            cfg.llm.enabled = True
        if (key := os.environ.get("OPENAI_API_KEY")) and not cfg.llm.api_key:
            cfg.llm.api_key = key
            cfg.llm.provider = "openai"
            cfg.llm.model = "gpt-4o-mini"
            cfg.llm.enabled = True
        if (key := os.environ.get("ANTHROPIC_API_KEY")) and not cfg.llm.api_key:
            cfg.llm.api_key = key
            cfg.llm.provider = "anthropic"
            cfg.llm.model = "claude-3-5-haiku-latest"
            cfg.llm.enabled = True
        if (base := os.environ.get("LIHUA_LLM_BASE")) and not cfg.llm.api_base:
            cfg.llm.api_base = base
        if (model := os.environ.get("LIHUA_LLM_MODEL")):
            cfg.llm.model = model
            cfg.llm.enabled = True
        return cfg

    @classmethod
    def _from_dict(cls, raw: dict[str, Any]) -> "Config":
        llm_raw = raw.get("llm", {}) or {}
        memory_raw = raw.get("memory", {}) or {}
        # 兼容 [general] 子表和顶层平铺两种写法
        general = raw.get("general", {}) or {}
        for k in ("always_confirm_grey", "auto_execute_whitelist", "audit_log", "language", "log_level"):
            if k in raw and k not in general:
                general[k] = raw[k]
        llm = LLMConfig(
            enabled=bool(llm_raw.get("enabled", False)),
            provider=str(llm_raw.get("provider", "deepseek")),
            api_key=str(llm_raw.get("api_key", "")),
            api_base=llm_raw.get("api_base"),
            model=str(llm_raw.get("model", "deepseek-chat")),
            fallback_model=llm_raw.get("fallback_model"),
            timeout=float(llm_raw.get("timeout", 30.0)),
            temperature=float(llm_raw.get("temperature", 0.3)),
            max_tokens=int(llm_raw.get("max_tokens", 1024)),
        )
        memory = MemoryConfig(
            enabled=bool(memory_raw.get("enabled", True)),
            max_episodes=int(memory_raw.get("max_episodes", 1000)),
            max_knowledge_patterns=int(memory_raw.get("max_knowledge_patterns", 500)),
            inject_context=bool(memory_raw.get("inject_context", True)),
            hot_days=int(memory_raw.get("hot_days", 3)),
            warm_days=int(memory_raw.get("warm_days", 7)),
            archive_days=int(memory_raw.get("archive_days", 30)),
        )
        return cls(
            llm=llm,
            memory=memory,
            always_confirm_grey=bool(general.get("always_confirm_grey", True)),
            auto_execute_whitelist=bool(general.get("auto_execute_whitelist", True)),
            audit_log=bool(general.get("audit_log", True)),
            language=str(general.get("language", "zh")),
            log_level=str(general.get("log_level", "INFO")).upper(),
            extras={
                k: v for k, v in raw.items()
                if k not in {"llm", "general", "memory"}
            },
        )

    def ensure_dirs(self) -> None:
        """确保运行时目录存在。"""
        for p in (config_dir(), data_dir(), state_dir(), skills_user_dir()):
            p.mkdir(parents=True, exist_ok=True)

    def to_toml(self) -> str:
        """序列化为 TOML 文本（用于持久化到 config.toml）。"""
        lines: list[str] = []
        lines.append("# Lihua 狸花猫 配置文件")
        lines.append("# 文档：https://github.com/lihua/lihua")
        lines.append("")
        lines.append("[llm]")
        lines.append(f"enabled = {'true' if self.llm.enabled else 'false'}")
        lines.append(f"provider = \"{self.llm.provider}\"")
        lines.append(f"api_key = \"{self.llm.api_key}\"")
        if self.llm.api_base:
            lines.append(f"api_base = \"{self.llm.api_base}\"")
        lines.append(f"model = \"{self.llm.model}\"")
        if self.llm.fallback_model:
            lines.append(f"fallback_model = \"{self.llm.fallback_model}\"")
        lines.append(f"timeout = {self.llm.timeout}")
        lines.append(f"temperature = {self.llm.temperature}")
        lines.append(f"max_tokens = {self.llm.max_tokens}")
        lines.append("")
        lines.append("[memory]")
        lines.append(f"enabled = {'true' if self.memory.enabled else 'false'}")
        lines.append(f"max_episodes = {self.memory.max_episodes}")
        lines.append(f"max_knowledge_patterns = {self.memory.max_knowledge_patterns}")
        lines.append(f"inject_context = {'true' if self.memory.inject_context else 'false'}")
        lines.append(f"hot_days = {self.memory.hot_days}  # L2 热数据天数")
        lines.append(f"warm_days = {self.memory.warm_days}  # L3 温数据天数")
        lines.append(f"archive_days = {self.memory.archive_days}  # L4 冷数据归档阈值")
        lines.append("")
        lines.append("[general]")
        lines.append(f"always_confirm_grey = {'true' if self.always_confirm_grey else 'false'}")
        lines.append(f"auto_execute_whitelist = {'true' if self.auto_execute_whitelist else 'false'}")
        lines.append(f"audit_log = {'true' if self.audit_log else 'false'}")
        lines.append(f"language = \"{self.language}\"")
        lines.append(f"log_level = \"{self.log_level}\"")
        lines.append("")
        return "\n".join(lines)

    def save(self) -> None:
        """保存到 ~/.config/lihua/config.toml。"""
        self.ensure_dirs()
        path = config_file_path()
        path.write_text(self.to_toml(), encoding="utf-8")

    def update_llm(
        self,
        *,
        enabled: bool | None = None,
        provider: str | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> None:
        """增量更新 LLM 配置并持久化。None 字段保持不变。"""
        if enabled is not None:
            self.llm.enabled = enabled
        if provider is not None:
            self.llm.provider = provider
        if api_key is not None:
            self.llm.api_key = api_key
        if api_base is not None:
            self.llm.api_base = api_base
        if model is not None:
            self.llm.model = model
        if temperature is not None:
            self.llm.temperature = temperature
        if max_tokens is not None:
            self.llm.max_tokens = max_tokens
        self.save()


def write_default_config_if_missing() -> bool:
    """若配置文件不存在，写入默认模板。返回是否写入。"""
    path = config_file_path()
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_DEFAULT_CONFIG_TPL, encoding="utf-8")
    return True


_DEFAULT_CONFIG_TPL = """\
# Lihua 狸花猫 配置文件
# 文档：https://github.com/lihua/lihua

[llm]
# 是否启用 LLM（不启用则使用纯规则模式）
enabled = false

# 提供商：deepseek | openai | anthropic | ollama | openai-compat
provider = "deepseek"

# API Key（也可用环境变量 DEEPSEEK_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY）
api_key = ""

# 自定义 API 端点（OpenAI 兼容服务用）
# api_base = "http://localhost:11434/v1"

# 模型名
model = "deepseek-chat"

# 复杂任务 fallback 模型
# fallback_model = "claude-3-5-sonnet-latest"

# 请求超时（秒）
timeout = 30.0

# 温度（0=确定，1=随机）
temperature = 0.3

# 最大 token
max_tokens = 1024

[memory]
# 是否启用记忆系统（记录 episode + 注入上下文）
enabled = true

# 情景记忆最大保留条数
max_episodes = 1000

# 知识库最大保留模式数
max_knowledge_patterns = 500

# 是否在 system prompt 注入记忆上下文
inject_context = true

# v0.8.16: 记忆分层加载（参考 OpenClaw L0-L4 设计）
# L2 热：最近 hot_days 天的 episodes，每次注入 context
hot_days = 3
# L3 温：warm_days 天内的 episodes，memory_recall 检索范围
warm_days = 7
# L4 冷：archive_days 天前的 episodes，归档到 archive/（P1-2 实现）
archive_days = 30

[general]
# 灰名单任务是否需要人类语言确认
always_confirm_grey = true

# 白名单任务是否自动执行（false=也走确认）
auto_execute_whitelist = true

# 是否记录审计日志
audit_log = true

# 界面语言
language = "zh"
"""
