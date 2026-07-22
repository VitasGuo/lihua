"""v0.8.12 技能自生成——让 agent 从成功经验中创造新技能。

二次进化第二支柱。记忆系统让 agent 能"记住"经验，技能自生成让 agent 能把
高频经验"固化"成可复用的技能（YAML），形成"记忆 → 学习 → 生成技能 →
注册 → 使用 → 记忆"的正向循环。

核心能力：

1. **从工具链生成技能**：LLM 看到某个工具链（如 run_shell + sed）重复出现，
   可调 `create_skill` 工具把它固化成 YAML 技能，下次直接用 skill 名调用

2. **自动检测重复模式**：从记忆系统的知识库中找出现 3+ 次的工具链，
   提示 LLM 考虑生成技能

3. **技能验证**：生成后做语法检查 + 试运行，确保不破坏系统

4. **技能管理**：自动生成的技能存 ~/.config/lihua/skills/auto_generated/，
   可列出、删除、回滚

设计原则：
- 不自动生成（避免噪音）：只提供工具，由 LLM 主动决定何时生成
- 保守验证：生成的技能必须通过语法检查 + 不在黑名单
- 可回滚：每个技能文件保留版本历史（.bak 文件）
- 不覆盖内置技能：auto-generated 技能名不能与内置技能冲突
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from lihua.config import skills_user_dir
from lihua.logging_config import get_logger

log = get_logger(__name__)

# 自动生成技能的子目录
_AUTO_SKILLS_SUBDIR = "auto_generated"

# 保留版本历史时旧版本后缀
_BAK_SUFFIX = ".bak"

# 重复模式检测阈值（出现 N+ 次的工具链建议生成技能）
_REPEAT_THRESHOLD = 3


@dataclass
class GeneratedSkill:
    """一个待保存的生成技能。"""

    name: str
    description: str
    triggers: list[str] = field(default_factory=list)
    parameters: list[dict[str, Any]] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    category: str = "auto"
    version: str = "0.1"

    def to_yaml(self) -> str:
        """序列化为 YAML 文本。"""
        data: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": "lihua-auto",
            "category": self.category,
            "source": "auto",
            "triggers": self.triggers,
            "examples": self.examples,
            "parameters": self.parameters,
            "steps": self.steps,
            "confirm_required": False,
            # v0.8.16: 使用记录（边用边长，v0.8.17 skill_evolve 工具会提炼为规则）
            "usage_log": [],
            # v0.8.17: 已验证规则（初始为空，skill_evolve 工具从 usage_log 提炼后写入）
            "rules": [],
        }
        return yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)


def auto_skills_dir() -> Path:
    """自动生成技能的目录：~/.config/lihua/skills/auto_generated/"""
    d = skills_user_dir() / _AUTO_SKILLS_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


# 技能名合法字符（小写字母/数字/下划线，必须以字母开头）
_VALID_NAME = re.compile(r"^[a-z][a-z0-9_]*$")

# 危险命令黑名单（生成技能的 steps 里不能含这些）
_DANGEROUS_PATTERNS = [
    r"\brm\s+-rf\s+/",
    r"\bmkfs\b",
    r"\bdd\b.*of=/dev/",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bcurl\b.*\|\s*sh",
    r"\bwget\b.*\|\s*sh",
    r">\s*/dev/sd[a-z]",
]


def validate_skill_name(name: str) -> tuple[bool, str]:
    """验证技能名是否合法。

    返回 (是否合法, 原因)。
    """
    if not name:
        return False, "技能名不能为空"
    if not _VALID_NAME.match(name):
        return False, "技能名必须以小写字母开头，只含小写字母/数字/下划线"
    if len(name) > 64:
        return False, "技能名过长（最多 64 字符）"
    return True, ""


def validate_skill_steps(steps: list[dict[str, Any]]) -> tuple[bool, str]:
    """验证技能 steps 是否安全。

    返回 (是否安全, 原因)。
    """
    if not steps:
        return False, "steps 不能为空"
    for i, step in enumerate(steps):
        cmd = str(step.get("command", ""))
        for pat in _DANGEROUS_PATTERNS:
            if re.search(pat, cmd, re.IGNORECASE):
                return False, f"step[{i}] 含危险命令：匹配 {pat}"
    return True, ""


def check_name_conflict(name: str, exclude_builtin: bool = True) -> bool:
    """检查技能名是否与现有技能冲突。

    返回 True 表示有冲突（不能使用）。
    """
    from lihua.skills import get_registry
    reg = get_registry()
    reg.ensure_loaded()
    existing = reg.get(name)
    if existing is None:
        return False
    # 如果已存在的是 auto-generated 技能，允许覆盖（更新）
    if existing.source == "auto":
        return False
    # 内置或用户自定义技能，不允许覆盖
    return True


def save_skill(skill: GeneratedSkill, allow_overwrite: bool = False) -> tuple[bool, str, Path | None]:
    """保存生成技能到 ~/.config/lihua/skills/auto_generated/{name}.yaml。

    allow_overwrite 控制文件已存在时的行为：
    - False：文件已存在则拒绝（避免意外覆盖）
    - True：文件已存在则备份 .bak 后覆盖

    注意：allow_overwrite 只影响"覆盖已存在的 auto 技能文件"，
    不影响"覆盖内置技能"——后者永远被 check_name_conflict 拒绝。
    check_name_conflict 内部对 auto 技能做了豁免（返回 False 表示无冲突）。

    返回 (是否成功, 消息, 文件路径)。
    """
    # 验证
    ok, msg = validate_skill_name(skill.name)
    if not ok:
        return False, msg, None
    ok, msg = validate_skill_steps(skill.steps)
    if not ok:
        return False, msg, None
    # 总是检查冲突：内置/用户技能永远不能被 auto 覆盖
    # check_name_conflict 内部对 auto 技能豁免（允许覆盖 auto）
    if check_name_conflict(skill.name):
        return False, f"技能名 '{skill.name}' 与内置/用户技能冲突，不能覆盖", None

    # 保存
    file_path = auto_skills_dir() / f"{skill.name}.yaml"

    # 文件已存在时的处理
    if file_path.exists() and not allow_overwrite:
        return False, f"技能文件已存在：{file_path}（如要覆盖请设 allow_overwrite=true）", None

    # 备份旧版本（allow_overwrite=True 且文件已存在）
    if file_path.exists() and allow_overwrite:
        bak_path = file_path.with_suffix(_BAK_SUFFIX)
        try:
            bak_path.write_text(file_path.read_text(encoding="utf-8"), encoding="utf-8")
            log.info(f"旧版本已备份到 {bak_path}")
        except OSError as e:
            log.warning(f"备份失败（继续覆盖）：{e}")

    try:
        file_path.write_text(skill.to_yaml(), encoding="utf-8")
        log.info(f"技能已保存：{file_path}")
    except OSError as e:
        return False, f"写入文件失败：{e}", None

    return True, f"技能 {skill.name} 已保存到 {file_path}", file_path


def list_auto_skills() -> list[dict[str, Any]]:
    """列出所有自动生成的技能。"""
    d = auto_skills_dir()
    result: list[dict[str, Any]] = []
    for p in sorted(d.glob("*.yaml")):
        try:
            raw = yaml.safe_load(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                result.append({
                    "name": raw.get("name", p.stem),
                    "description": raw.get("description", ""),
                    "version": raw.get("version", "0.1"),
                    "triggers": list(raw.get("triggers", []) or []),
                    "file_path": str(p),
                    "size": p.stat().st_size,
                    "mtime": p.stat().st_mtime,
                })
        except (OSError, yaml.YAMLError) as e:
            log.warning(f"读取技能文件失败 {p}: {e}")
    return result


def delete_auto_skill(name: str) -> tuple[bool, str]:
    """删除一个自动生成的技能。"""
    file_path = auto_skills_dir() / f"{name}.yaml"
    if not file_path.exists():
        return False, f"技能 {name} 不存在"
    try:
        file_path.unlink()
        log.info(f"技能已删除：{file_path}")
        # 同时删除 .bak 文件
        bak_path = file_path.with_suffix(_BAK_SUFFIX)
        if bak_path.exists():
            bak_path.unlink()
        return True, f"技能 {name} 已删除"
    except OSError as e:
        return False, f"删除失败：{e}"


def reload_registry() -> tuple[bool, str, int]:
    """重新加载 SkillRegistry，让新技能生效。

    返回 (是否成功, 消息, 技能总数)。
    """
    from lihua.skills import get_registry
    reg = get_registry()
    reg.reload()
    count = len(reg.all())
    log.info(f"SkillRegistry 已重新加载，共 {count} 个技能")
    return True, f"已重新加载，共 {count} 个技能", count


def detect_repeated_patterns() -> list[dict[str, Any]]:
    """从记忆系统检测重复工具链，提示 LLM 考虑生成技能。

    返回出现次数 >= _REPEAT_THRESHOLD 的工具链列表，按出现次数降序。
    """
    try:
        from lihua.memory import get_memory_store
        store = get_memory_store()
        # 从知识库加载所有 pattern
        patterns = store._load_knowledge()
    except Exception as e:
        log.warning(f"检测重复模式失败：{e}")
        return []

    repeated = []
    for p in patterns:
        if p.total_count >= _REPEAT_THRESHOLD:
            repeated.append({
                "keywords": p.keywords,
                "tool_chain": p.tool_chain,
                "total_count": p.total_count,
                "success_rate": round(p.success_rate, 3),
                "suggestion": (
                    f"工具链 {' → '.join(p.tool_chain)} 出现 {p.total_count} 次"
                    f"（成功率 {p.success_rate:.0%}），可考虑固化成技能"
                ),
            })

    # 按出现次数降序
    repeated.sort(key=lambda x: x["total_count"], reverse=True)
    return repeated


def generate_skill_suggestion(
    tool_chain: list[str],
    keywords: list[str],
    success_count: int,
) -> GeneratedSkill:
    """根据工具链 + 关键词生成一个技能建议（LLM 可在此基础上细化）。

    这是骨架生成器——生成的技能只有基本的 steps 结构，LLM 需要补充
    具体的 command 模板和参数提取正则。
    """
    # 从工具链推导技能名：tool1_tool2_tool3 → tool_chain
    name_parts = []
    for tool in tool_chain[:3]:  # 最多取前 3 个工具名
        # 取工具名最后一段（如果有下划线）
        parts = tool.split("_")
        name_parts.append(parts[-1] if parts else tool)
    base_name = "_".join(name_parts) if name_parts else "auto_skill"

    # 从关键词推导触发词（取前 3 个中文关键词）
    triggers = [kw for kw in keywords if len(kw) >= 2][:3]

    # 生成 steps 骨架
    steps = []
    for i, tool in enumerate(tool_chain):
        steps.append({
            "name": f"step_{i+1}_{tool}",
            "type": "command",
            "description": f"调用 {tool}",
            "command": f"# TODO: LLM 补充具体命令模板",
            "safety": "white",
        })

    return GeneratedSkill(
        name=base_name,
        description=f"自动生成：{' → '.join(tool_chain)}",
        triggers=triggers,
        examples=[],
        parameters=[],
        steps=steps,
        category="auto",
        version="0.1",
    )


def get_skill_stats() -> dict[str, Any]:
    """获取技能自生成系统的统计信息。"""
    auto_skills = list_auto_skills()
    repeated = detect_repeated_patterns()
    return {
        "auto_skills_count": len(auto_skills),
        "auto_skills": [s["name"] for s in auto_skills],
        "repeated_patterns_count": len(repeated),
        "repeated_patterns": repeated[:5],  # 只返回前 5 个
        "threshold": _REPEAT_THRESHOLD,
        "auto_skills_dir": str(auto_skills_dir()),
    }
