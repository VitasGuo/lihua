"""意图理解：规则优先 + LLM 增强。

策略：
1. 先用规则匹配 Skill（triggers + extract）
2. 规则匹配 + LLM 可用 → 用 LLM 解析别名表里没有的包名/目标
3. 规则未匹配 + LLM 可用 → 让 LLM 选 skill + 生成参数
4. 规则未匹配 + LLM 不可用 → 返回 None，让上层走"我不懂"分支
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from lihua.config import Config
from lihua.logging_config import get_logger
from lihua.router import LLMError, call_llm
from lihua.skills import SkillDef, SkillRegistry

log = get_logger(__name__)


@dataclass
class Intent:
    """意图识别结果。"""

    skill_name: str
    params: dict[str, str] = field(default_factory=dict)
    raw_text: str = ""
    source: str = "rule"  # rule | llm | hybrid
    confidence: float = 1.0
    explanation: str = ""
    skill: SkillDef | None = None

    @property
    def matched(self) -> bool:
        return bool(self.skill_name)


def _build_skill_catalog(registry: SkillRegistry) -> str:
    """构造给 LLM 看的 skill 列表。"""
    lines = []
    for s in registry.all():
        triggers = " / ".join(s.triggers[:5]) if s.triggers else ""
        examples = " | ".join(s.examples[:3]) if s.examples else ""
        params = ", ".join(p.name for p in s.parameters) if s.parameters else "无"
        lines.append(
            f"- {s.name}: {s.description}\n"
            f"  触发词: {triggers}\n"
            f"  示例: {examples}\n"
            f"  参数: {params}"
        )
    return "\n".join(lines)


_LLM_SYSTEM_PROMPT = """你是 Lihua 狸花猫，一个 Linux 桌面助手。任务：根据用户的中文输入，选择最合适的内置 Skill 并提取参数。

输出严格的 JSON（不要 markdown 代码块，不要解释）：
{
  "skill": "skill_name",
  "params": {"参数名": "值"},
  "explanation": "给用户看的中文简短解释（一句话）",
  "confidence": 0.0-1.0
}

如果没有任何 skill 匹配，返回：
{"skill": "", "params": {}, "explanation": "这个请求我暂时还不会处理", "confidence": 0.0}

可用 Skill 列表：
"""

_LLM_PARAM_PROMPT = """用户想用「{skill_name}」技能处理：{user_text}

已知参数（从规则提取）：{rule_params}
候选包名（从别名表）：{candidates}

请用 JSON 返回最合适的参数（只返回 JSON，不要其他文字）：
{{
  "target": "用户想要的应用/字体/输入法名",
  "package": "推荐的包名（apt 包名或 flatpak 应用 ID）",
  "package_type": "flatpak | apt | snap",
  "explanation": "一句话中文解释"
}}

规则：
- flatpak 应用 ID 通常以 com. / org. / io. / cn. / net. 开头
- apt 包名通常是小写，含 - 分隔
- 优先 flatpak（沙箱、版本新），其次 apt（系统级、稳定）
- 如果不确定包名，留空让上层处理
"""


def _parse_llm_json(text: str) -> dict[str, Any]:
    """从 LLM 输出中提取 JSON（容忍前后空白和代码块）。"""
    text = text.strip()
    # 去掉 markdown 代码块
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    # 找到第一个 { 和最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}


def understand(text: str, cfg: Config, registry: SkillRegistry) -> Intent:
    """理解用户意图。"""
    text = (text or "").strip()
    if not text:
        return Intent(skill_name="", raw_text="", explanation="空输入")

    log.debug(f"意图理解：「{text[:80]}」")

    # 第一步：规则匹配
    matched_skills = registry.match_by_text(text)
    if matched_skills:
        # 取最佳匹配
        skill = matched_skills[0]
        params = skill.extract_params(text)
        intent = Intent(
            skill_name=skill.name,
            params=params,
            raw_text=text,
            source="rule",
            confidence=0.8,
            skill=skill,
            explanation=f"已识别为「{skill.description}」",
        )
        log.info(
            f"规则匹配：skill={skill.name}, params={params}",
            extra={"source": "rule", "confidence": 0.8},
        )

        # 如果有 target 参数但别名表查不到，且 LLM 可用 → LLM 增强
        if cfg.llm.enabled and "target" in params:
            candidates = skill.resolve_alias(params["target"])
            if not candidates:
                log.debug(f"别名表未命中「{params['target']}」，调 LLM 增强")
                enhanced = _enhance_with_llm(text, skill, params, cfg)
                if enhanced:
                    intent.params.update(enhanced.get("params", {}))
                    if enhanced.get("explanation"):
                        intent.explanation = enhanced["explanation"]
                    intent.source = "hybrid"
                    intent.confidence = 0.9
                    log.info(f"LLM 增强：params={intent.params}", extra={"source": "hybrid"})
        return intent

    # 第二步：规则未匹配，尝试 LLM
    if not cfg.llm.enabled:
        log.info(f"规则未匹配且 LLM 未启用：「{text[:50]}」")
        return Intent(
            skill_name="",
            raw_text=text,
            source="none",
            confidence=0.0,
            explanation="未启用 LLM，无法理解这个请求",
        )

    log.debug("规则未匹配，调 LLM 识别意图")
    llm_intent = _understand_with_llm(text, cfg, registry)
    if llm_intent and llm_intent.matched:
        log.info(
            f"LLM 识别：skill={llm_intent.skill_name}, params={llm_intent.params}",
            extra={"source": "llm", "confidence": llm_intent.confidence},
        )
        return llm_intent

    log.info(f"意图理解失败（LLM 也未识别）：「{text[:50]}」")
    return Intent(
        skill_name="",
        raw_text=text,
        source="llm",
        confidence=0.0,
        explanation=llm_intent.explanation if llm_intent else "LLM 未能识别意图",
    )


def _enhance_with_llm(
    text: str, skill: SkillDef, params: dict[str, str], cfg: Config
) -> dict[str, Any] | None:
    """用 LLM 增强参数解析（找不到别名时调用）。"""
    if not cfg.llm.enabled:
        return None
    prompt = _LLM_PARAM_PROMPT.format(
        skill_name=skill.name,
        user_text=text,
        rule_params=json.dumps(params, ensure_ascii=False),
        candidates="（无）",
    )
    try:
        resp = call_llm(cfg.llm, [
            {"role": "system", "content": "你是 Linux 包名解析助手，只返回 JSON。"},
            {"role": "user", "content": prompt},
        ])
    except LLMError:
        return None

    data = _parse_llm_json(resp.text)
    if not data:
        return None
    return {
        "params": {k: str(v) for k, v in data.items() if k in {"target", "package", "package_type"}},
        "explanation": str(data.get("explanation", "")),
    }


def _understand_with_llm(
    text: str, cfg: Config, registry: SkillRegistry
) -> Intent | None:
    """让 LLM 选 skill + 生成参数。"""
    catalog = _build_skill_catalog(registry)
    messages = [
        {"role": "system", "content": _LLM_SYSTEM_PROMPT + catalog},
        {"role": "user", "content": f"用户输入：{text}"},
    ]
    try:
        resp = call_llm(cfg.llm, messages)
    except LLMError:
        return None

    data = _parse_llm_json(resp.text)
    if not data:
        return Intent(
            skill_name="",
            raw_text=text,
            source="llm",
            confidence=0.0,
            explanation="LLM 返回格式异常",
        )

    skill_name = str(data.get("skill", "")).strip()
    if not skill_name:
        return Intent(
            skill_name="",
            raw_text=text,
            source="llm",
            confidence=0.0,
            explanation=str(data.get("explanation", "这个请求我暂时还不会处理")),
        )

    skill = registry.get(skill_name)
    if not skill:
        return Intent(
            skill_name="",
            raw_text=text,
            source="llm",
            confidence=0.0,
            explanation=f"LLM 选择了不存在的 skill：{skill_name}",
        )

    params = {k: str(v) for k, v in (data.get("params", {}) or {}).items()}
    return Intent(
        skill_name=skill_name,
        params=params,
        raw_text=text,
        source="llm",
        confidence=float(data.get("confidence", 0.7)),
        skill=skill,
        explanation=str(data.get("explanation", "")),
    )
