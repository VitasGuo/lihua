"""Skill 库：YAML 定义的任务模板。

Skill 结构：
    name: install_app
    description: 安装应用程序
    triggers: [装, 安装]      # 规则识别关键词
    parameters:
      - name: target
        required: true
        extract: "正则"       # 从用户输入提取参数
    aliases:                   # 中文应用名 → 候选包名
      QQ: [com.tencent.qq, linuxqq]
    steps:
      - name: resolve
        type: resolve_package
        prefer: [flatpak, apt, snap]
      - name: install
        type: command
        command: "flatpak install -y flathub {{package}}"
        safety: white
        confirm: "安装 {{target}}"
      - name: verify
        type: verify
        command: "which {{package}}"

Step 类型：
    resolve_package  解析包名（用 aliases 或 LLM）
    command          执行 shell 命令
    verify           验证命令存在/成功
    notify           发送桌面通知
    set_var          设置上下文变量
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from lihua.config import skills_user_dir

# 内置 skill 数据目录（与包一起安装）
_BUILTIN_SKILLS_DIR = Path(__file__).parent / "data" / "skills"


@dataclass
class SkillParam:
    name: str
    type: str = "string"
    required: bool = False
    description: str = ""
    extract: str | None = None
    default: Any = None


@dataclass
class SkillStep:
    name: str
    type: str = "command"  # command | resolve_package | verify | notify | set_var
    description: str = ""
    command: str = ""
    safety: str = "white"  # white | grey | black
    confirm: str | None = None
    prefer: list[str] = field(default_factory=list)
    on_failure: str = "stop"  # stop | continue | retry
    retry_max: int = 0
    condition: str | None = None  # 简单条件 "{{var}} == value"
    vars: dict[str, str] = field(default_factory=dict)  # set_var 用
    timeout: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillDef:
    name: str
    description: str = ""
    version: str = "0.1"
    author: str = "lihua"
    category: str = "other"  # system/file/network/...（见 SKILL_CATEGORIES）
    triggers: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    parameters: list[SkillParam] = field(default_factory=list)
    aliases: dict[str, list[str]] = field(default_factory=dict)
    steps: list[SkillStep] = field(default_factory=list)
    confirm_required: bool = False
    raw: dict[str, Any] = field(default_factory=dict)
    source: str = "builtin"  # builtin | user
    file_path: Path | None = None
    # v0.8.16: Skill 使用记录（参考 OpenClaw "实践即认识" 设计）
    # 每条记录：{"timestamp": float, "success": bool, "user_input": str, "notes": str, "params": dict}
    # 边用边长：反复验证的记录 → v0.8.17 提升为规则；被证伪的 → 降级
    usage_log: list[dict[str, Any]] = field(default_factory=list)
    # v0.8.17: Skill 规则（从 usage_log 提炼的"已验证稳定规则"）
    # 每条规则：{"condition": str, "action": str, "reason": str, "added_at": float, "confidence": float}
    # - 提升逻辑：usage_log 反复验证 → skill_evolve 工具调 LLM 总结 → 写入 rules
    # - 降级逻辑：规则被新 usage_log 证伪 → skill_evolve 工具调 LLM 降级或删除
    # - 注入：tool_defs 把 rules 附加到 tool description，让 LLM 调 skill 时看到
    rules: list[dict[str, Any]] = field(default_factory=list)

    def match_trigger(self, text: str) -> bool:
        """是否匹配任何触发关键词。

        匹配策略：
        1. 大小写不敏感
        2. 中文触发词：子串匹配（"装QQ" 能匹配 "装"）
        3. 中文触发词：去空白匹配（"用fcitx5" 能匹配 "用 fcitx5"）
        4. 纯英文触发词：单词边界匹配（避免 "du" 误匹配 "baidu"）
        """
        text_lower = text.lower()
        text_nospace = re.sub(r"\s+", "", text_lower)
        for t in self.triggers:
            t_lower = t.lower()
            # 判断是否纯 ASCII（英文 trigger）
            is_ascii = all(ord(c) < 128 for c in t_lower)
            if is_ascii and re.search(r'[a-zA-Z]', t_lower):
                # 纯英文 trigger：单词边界匹配
                if re.search(r'\b' + re.escape(t_lower) + r'\b', text_lower):
                    return True
                continue
            # 中文 trigger：子串匹配
            if t_lower in text_lower:
                return True
            # 退化：去空格后匹配（中英文混合场景）
            t_nospace = re.sub(r"\s+", "", t_lower)
            if t_nospace and t_nospace in text_nospace:
                return True
        return False

    def extract_params(self, text: str) -> dict[str, str]:
        """用 parameters 里的 extract 正则从用户输入中提取参数。"""
        params: dict[str, str] = {}
        for p in self.parameters:
            if p.extract:
                m = re.search(p.extract, text, re.IGNORECASE)
                if m:
                    if m.groups():
                        params[p.name] = m.group(1).strip()
                    else:
                        params[p.name] = m.group(0).strip()
            if p.name not in params and p.default is not None:
                params[p.name] = str(p.default)
        return params

    def resolve_alias(self, target: str) -> list[str]:
        """根据中文/别名查候选包名。"""
        if not target:
            return []
        # 完全匹配
        if target in self.aliases:
            return list(self.aliases[target])
        # 大小写不敏感匹配
        for k, v in self.aliases.items():
            if k.lower() == target.lower():
                return list(v)
        # 包含匹配（"QQ 音乐" → "QQ"）
        for k, v in self.aliases.items():
            if k.lower() in target.lower() and len(k) >= 2:
                return list(v)
        return []


def _parse_step(raw: dict[str, Any]) -> SkillStep:
    return SkillStep(
        name=str(raw.get("name", "")),
        type=str(raw.get("type", "command")),
        description=str(raw.get("description", "")),
        command=str(raw.get("command", "")),
        safety=str(raw.get("safety", "white")),
        confirm=raw.get("confirm"),
        prefer=list(raw.get("prefer", []) or []),
        on_failure=str(raw.get("on_failure", "stop")),
        retry_max=int(raw.get("retry_max", 0)),
        condition=raw.get("condition"),
        vars=dict(raw.get("vars", {}) or {}),
        timeout=raw.get("timeout"),
        raw=raw,
    )


def _parse_skill(raw: dict[str, Any], source: str, file_path: Path | None) -> SkillDef:
    params_raw = raw.get("parameters", []) or []
    params = [
        SkillParam(
            name=str(p.get("name", "")),
            type=str(p.get("type", "string")),
            required=bool(p.get("required", False)),
            description=str(p.get("description", "")),
            extract=p.get("extract"),
            default=p.get("default"),
        )
        for p in params_raw
    ]
    steps_raw = raw.get("steps", []) or []
    steps = [_parse_step(s) for s in steps_raw]
    aliases_raw = raw.get("aliases", {}) or {}
    aliases = {str(k): list(v) if isinstance(v, list) else [str(v)]
               for k, v in aliases_raw.items()}
    return SkillDef(
        name=str(raw.get("name", "")),
        description=str(raw.get("description", "")),
        version=str(raw.get("version", "0.1")),
        author=str(raw.get("author", "lihua")),
        category=str(raw.get("category", "other")),
        triggers=list(raw.get("triggers", []) or []),
        examples=list(raw.get("examples", []) or []),
        parameters=params,
        aliases=aliases,
        steps=steps,
        confirm_required=bool(raw.get("confirm_required", False)),
        raw=raw,
        # v0.8.12: 允许 YAML 内 source 字段覆盖（auto-generated 技能标注 source: auto）
        source=str(raw.get("source", source)),
        file_path=file_path,
        # v0.8.16: 加载 usage_log（向后兼容：旧 YAML 没有此字段时为空列表）
        usage_log=list(raw.get("usage_log", []) or []),
        # v0.8.17: 加载 rules（从 usage_log 提炼的"已验证稳定规则"）
        rules=list(raw.get("rules", []) or []),
    )


def load_skill_file(path: Path, source: str = "user") -> SkillDef | None:
    """从 YAML 文件加载一个 Skill。失败返回 None。"""
    try:
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        if not isinstance(raw, dict):
            return None
        return _parse_skill(raw, source, path)
    except (OSError, yaml.YAMLError) as e:
        import sys
        print(f"[lihua] Skill 加载失败 {path}: {e}", file=sys.stderr)
        return None


# v0.8.16: Skill 使用记录——追加 usage_log 到 YAML 文件
_USAGE_LOG_MAX = 50  # 每个 skill 最多保留 50 条使用记录


def append_usage_log(
    file_path: Path,
    entry: dict[str, Any],
    max_log: int = _USAGE_LOG_MAX,
) -> bool:
    """v0.8.16: 追加一条使用记录到 skill YAML 文件。

    参考 OpenClaw "实践即认识" 设计：每次用 skill 后记录"意外/发现"，
    边用边长。v0.8.17 的 skill_evolve 工具会把这些记录提炼为规则。

    entry 字段：
    - timestamp: float（必填）
    - success: bool（必填）
    - user_input: str（截断到 200 字符防爆 YAML）
    - notes: str（成功=完成消息，失败=错误信息）
    - params: dict（参数快照，每个值截断到 100 字符）

    策略：
    1. 读取原 YAML（保留所有字段）
    2. 追加 entry 到 usage_log 列表
    3. 裁剪到 max_log 条（保留最近的）
    4. 写回文件（allow_unicode + sort_keys=False 保留可读性）

    返回是否成功写入。失败时不影响 skill 执行（仅 log warning）。
    """
    try:
        with file_path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        if not isinstance(raw, dict):
            return False
        usage_log = list(raw.get("usage_log", []) or [])
        # 截断 entry 中的长字段防 YAML 膨胀
        clean_entry = {
            "timestamp": float(entry.get("timestamp", 0.0)),
            "success": bool(entry.get("success", False)),
            "user_input": str(entry.get("user_input", ""))[:200],
            "notes": str(entry.get("notes", ""))[:200],
            "params": {str(k): str(v)[:100] for k, v in (entry.get("params") or {}).items()},
        }
        usage_log.append(clean_entry)
        # 裁剪：保留最近 max_log 条
        if len(usage_log) > max_log:
            usage_log = usage_log[-max_log:]
        raw["usage_log"] = usage_log
        # 写回（sort_keys=False 保留原始字段顺序，allow_unicode 保留中文）
        with file_path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(
                raw, f,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            )
        return True
    except (OSError, yaml.YAMLError) as e:
        import sys
        print(f"[lihua] 追加 usage_log 失败 {file_path}: {e}", file=sys.stderr)
        return False


# v0.8.17: Skill 规则提升——从 usage_log 提炼规则写入 YAML 的 rules 字段
_RULES_MAX = 20  # 每个 skill 最多保留 20 条规则（防止无限增长）


def update_skill_rules(
    file_path: Path,
    rules: list[dict[str, Any]],
    max_rules: int = _RULES_MAX,
) -> tuple[bool, str]:
    """v0.8.17: 更新 skill YAML 的 rules 字段（先备份 .bak 再写入）。

    参考 OpenClaw "实践即认识" 设计：
    - usage_log 反复验证的实践 → 提升为 rules（已验证稳定规则）
    - rules 被新 usage_log 证伪 → 降级或删除（由 LLM 决定）
    - skill_evolve 工具调 LLM 总结新 rules 列表后调此函数写入

    rules 字段结构：
        - condition: str（触发条件，自然语言描述，如 "target == 'chrome'"）
        - action: str（建议动作，如 "prefer_flatpak" / "avoid_param_combination"）
        - reason: str（规则来源，如 "usage_log 10 次成功率 100%"）
        - added_at: float（添加时间戳）
        - confidence: float（置信度 0.0-1.0）

    策略：
    1. 读取原 YAML（保留所有字段，包括 usage_log）
    2. 备份旧版本到 .bak（保留上一次的 rules 便于回滚）
    3. 写入新 rules（裁剪到 max_rules 条）
    4. 返回 (是否成功, 消息)

    返回 (是否成功, 消息)。
    """
    try:
        with file_path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        if not isinstance(raw, dict):
            return False, f"YAML 格式错误：{file_path}"
        # 备份旧版本
        bak_path = file_path.with_suffix(".yaml.bak")
        try:
            bak_path.write_text(file_path.read_text(encoding="utf-8"), encoding="utf-8")
        except OSError as e:
            # 备份失败不阻断（仅 log）
            import sys
            print(f"[lihua] 备份 rules 失败 {file_path}: {e}", file=sys.stderr)
        # 清洗 + 裁剪
        clean_rules: list[dict[str, Any]] = []
        for r in rules[:max_rules]:
            if not isinstance(r, dict):
                continue
            clean_rules.append({
                "condition": str(r.get("condition", ""))[:200],
                "action": str(r.get("action", ""))[:100],
                "reason": str(r.get("reason", ""))[:300],
                "added_at": float(r.get("added_at", 0.0)),
                "confidence": max(0.0, min(1.0, float(r.get("confidence", 0.5)))),
            })
        raw["rules"] = clean_rules
        with file_path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(
                raw, f,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            )
        return True, f"已更新 {len(clean_rules)} 条规则到 {file_path.name}"
    except (OSError, yaml.YAMLError) as e:
        return False, f"更新 rules 失败：{e}"


class SkillRegistry:
    """Skill 注册表。内置 + 用户自定义。"""

    def __init__(self) -> None:
        self._skills: dict[str, SkillDef] = {}
        self._loaded = False

    def load(self) -> None:
        """加载所有 Skill（内置 + 用户自定义 + 自动生成）。

        加载顺序（后者覆盖前者）：
        1. 内置 skill（_BUILTIN_SKILLS_DIR）
        2. 用户自定义 skill（skills_user_dir() 根目录）
        3. 自动生成 skill（skills_user_dir() / "auto_generated" 子目录）

        v0.8.12 新增第 3 阶段：从 ~/.config/lihua/skills/auto_generated/
        加载 LLM 通过 create_skill 工具自动生成的技能。
        """
        self._skills.clear()
        # 内置
        if _BUILTIN_SKILLS_DIR.exists():
            for p in sorted(_BUILTIN_SKILLS_DIR.glob("*.yaml")):
                sk = load_skill_file(p, "builtin")
                if sk and sk.name:
                    self._skills[sk.name] = sk
            for p in sorted(_BUILTIN_SKILLS_DIR.glob("*.yml")):
                sk = load_skill_file(p, "builtin")
                if sk and sk.name:
                    self._skills[sk.name] = sk
        # 用户自定义（覆盖内置）
        user_dir = skills_user_dir()
        if user_dir.exists():
            for p in sorted(user_dir.glob("*.yaml")):
                sk = load_skill_file(p, "user")
                if sk and sk.name:
                    self._skills[sk.name] = sk
            for p in sorted(user_dir.glob("*.yml")):
                sk = load_skill_file(p, "user")
                if sk and sk.name:
                    self._skills[sk.name] = sk
        # v0.8.12: 自动生成技能（覆盖用户自定义和内置）
        # _parse_skill 中 source 字段会覆盖这里的 "auto" 传入值，
        # 但保留 "auto" 传入作为兜底（YAML 没有 source 字段时）
        auto_dir = user_dir / "auto_generated"
        if auto_dir.exists():
            for p in sorted(auto_dir.glob("*.yaml")):
                sk = load_skill_file(p, "auto")
                if sk and sk.name:
                    self._skills[sk.name] = sk
            for p in sorted(auto_dir.glob("*.yml")):
                sk = load_skill_file(p, "auto")
                if sk and sk.name:
                    self._skills[sk.name] = sk
        self._loaded = True

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def all(self) -> list[SkillDef]:
        self.ensure_loaded()
        return list(self._skills.values())

    def get(self, name: str) -> SkillDef | None:
        self.ensure_loaded()
        return self._skills.get(name)

    def reload(self) -> None:
        self._loaded = False
        self.load()

    def match_by_text(self, text: str) -> list[SkillDef]:
        """根据用户文本返回所有匹配的 Skill（按匹配优先级排序）。

        优先级策略（从高到低）：
        1. 能从文本提取参数且参数命中别名表的 skill（精确度最高）
        2. 命中的 trigger 中最长者（更具体的 trigger 优先）
        3. 原始加载顺序
        """
        self.ensure_loaded()
        matched = [s for s in self._skills.values() if s.match_trigger(text)]

        def priority(s: SkillDef) -> tuple[int, int]:
            # 是否能从文本提取参数并命中别名表
            alias_hit = 0
            try:
                params = s.extract_params(text)
            except Exception:
                params = {}
            for v in params.values():
                if v and s.resolve_alias(v):
                    alias_hit = 1
                    break
            # 命中的 trigger 中最长者（更具体的优先）
            text_lower = text.lower()
            text_nospace = re.sub(r"\s+", "", text_lower)
            max_hit_len = 0
            for t in s.triggers:
                t_lower = t.lower()
                is_ascii = all(ord(c) < 128 for c in t_lower)
                hit = False
                if is_ascii and re.search(r'[a-zA-Z]', t_lower):
                    if re.search(r'\b' + re.escape(t_lower) + r'\b', text_lower):
                        hit = True
                else:
                    if t_lower in text_lower:
                        hit = True
                    else:
                        t_nospace = re.sub(r"\s+", "", t_lower)
                        if t_nospace and t_nospace in text_nospace:
                            hit = True
                if hit and len(t) > max_hit_len:
                    max_hit_len = len(t)
            return (alias_hit, max_hit_len)

        matched.sort(key=priority, reverse=True)
        return matched


# 全局单例
_registry: SkillRegistry | None = None


def get_registry() -> SkillRegistry:
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
    return _registry
