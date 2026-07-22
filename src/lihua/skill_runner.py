"""Skill 执行器：按步骤序列执行 Skill。

支持的 step 类型：
- resolve_package: 用 aliases + LLM 解析包名 → ctx.package, ctx.package_type
- command: 执行 shell 命令（模板插值）
- verify: 执行验证命令，失败标 verify_failed（不抛错）
- notify: 发送桌面通知
- set_var: 设置上下文变量

condition 语法：
- "{{var}} == value"
- "{{var}} != value"
- "{{var}} in [a, b, c]"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from lihua.config import Config
from lihua.executor import ExecOptions, ExecResult, execute_safely
from lihua.intent import Intent
from lihua.logging_config import get_logger
from lihua.router import LLMError, call_llm
from lihua.skills import SkillDef, SkillStep
from lihua.safety import classify

log = get_logger(__name__)

# 确认回调：(message, command) -> decision
# v0.8.6：返回值从 bool 改成 str，区分"用户取消"和"超时"
#   "confirmed"：用户点击确认
#   "denied"：用户点击取消
#   "timeout"：超时未响应
ConfirmCallback = Callable[[str, str], str]
# 进度回调：(step_name, message) -> None
ProgressCallback = Callable[[str, str], None]


@dataclass
class StepResult:
    step: SkillStep
    skipped: bool = False
    success: bool = False
    output: str = ""
    error: str = ""
    duration: float = 0.0
    needs_confirm: bool = False
    confirm_message: str = ""
    confirm_decision: str = ""  # confirmed | denied | auto
    exec_result: ExecResult | None = None


@dataclass
class RunResult:
    skill: SkillDef
    steps: list[StepResult] = field(default_factory=list)
    success: bool = False
    final_message: str = ""
    ctx: dict[str, str] = field(default_factory=dict)
    cancelled: bool = False

    def step_by_name(self, name: str) -> StepResult | None:
        for r in self.steps:
            if r.step.name == name:
                return r
        return None


# ---------------------------------------------------------------------------
# 模板插值
# ---------------------------------------------------------------------------

# 支持 {{var}} 和 {{var|default:value}} 两种语法
# default 过滤器：变量未定义或为空字符串时使用默认值
_TEMPLATE_RE = re.compile(r"\{\{\s*(\w+)(?:\s*\|\s*default\s*:\s*([^}]*?))?\s*\}\}")


def render_template(template: str, ctx: dict[str, str]) -> str:
    """{{var}} 插值。支持 {{var|default:value}} 默认值。

    - {{var}}：未定义时保留原占位符
    - {{var|default:value}}：未定义或为空字符串时使用 value
    """
    def replace(m: re.Match) -> str:
        key = m.group(1)
        default = m.group(2)
        if key in ctx and ctx[key] != "":
            return str(ctx[key])
        if default is not None:
            return default
        return m.group(0)
    return _TEMPLATE_RE.sub(replace, template)


# ---------------------------------------------------------------------------
# condition 求值
# ---------------------------------------------------------------------------

# 单个原子条件：{{var}} == value / {{var}} != value / {{var}} in [a, b, c]
# rhs 用 (.*) 允许空字符串（如 "{{var}} != " 判断非空）
_ATOM_CONDITION_RE = re.compile(
    r"^\{\{\s*(\w+)\s*\}\}\s*(==|!=|in)\s*(.*)$"
)


def _eval_atom(condition: str, ctx: dict[str, str]) -> bool:
    """求值单个原子条件。无法解析的视为 True。"""
    m = _ATOM_CONDITION_RE.match(condition.strip())
    if not m:
        return True
    var_name, op, rhs = m.groups()
    lhs = ctx.get(var_name, "")
    rhs = rhs.strip()
    if op == "==":
        return lhs == rhs
    if op == "!=":
        return lhs != rhs
    if op == "in":
        # rhs 形如 "[a, b, c]"
        rhs_clean = rhs.strip("[] ")
        candidates = [c.strip().strip("'\"") for c in rhs_clean.split(",") if c.strip()]
        return lhs in candidates
    return True


def eval_condition(condition: str | None, ctx: dict[str, str]) -> bool:
    """求值 condition 表达式。None 视为 True。

    支持复合条件（&& 和 ||）：
    - {{var}} == value && {{var2}} != value2
    - {{var}} == a || {{var}} == b

    优先级：&& 高于 ||（与大多数语言一致）
    """
    if not condition:
        return True
    expr = condition.strip()
    # 拆分 || （低优先级）
    or_parts = re.split(r"\s*\|\|\s*", expr)
    for or_part in or_parts:
        # 拆分 && （高优先级）
        and_parts = re.split(r"\s*&&\s*", or_part)
        if all(_eval_atom(p, ctx) for p in and_parts):
            return True
    return False


# ---------------------------------------------------------------------------
# resolve_package 步骤
# ---------------------------------------------------------------------------

_FLATPAK_ID_PREFIXES = ("com.", "org.", "io.", "cn.", "net.", "re.")


def _is_flatpak_id(name: str) -> bool:
    return name.startswith(_FLATPAK_ID_PREFIXES) and "." in name[4:]


def _resolve_package(
    skill: SkillDef, target: str, prefer: list[str], cfg: Config
) -> tuple[str, str] | None:
    """返回 (package_name, package_type)。失败返回 None。

    优先级：
    1. 别名表完全匹配
    2. LLM 解析（如果启用）
    3. 直接当 apt 包名
    """
    candidates = skill.resolve_alias(target)
    if candidates:
        # 按 prefer 顺序选第一个匹配的候选
        for pref in prefer:
            for c in candidates:
                if pref == "flatpak" and _is_flatpak_id(c):
                    return c, "flatpak"
                if pref == "apt" and not _is_flatpak_id(c):
                    return c, "apt"
                if pref == "snap":
                    return c, "snap"
        # 没有匹配 prefer 的，用第一个
        c = candidates[0]
        return c, ("flatpak" if _is_flatpak_id(c) else "apt")

    # LLM 兜底
    if cfg.llm.enabled:
        try:
            resp = call_llm(cfg.llm, [
                {"role": "system", "content": "你是 Linux 包名解析助手，只返回 JSON。"},
                {"role": "user", "content": (
                    f"用户想安装：{target}\n"
                    "请用 JSON 返回最合适的包名：\n"
                    '{"package": "包名", "package_type": "flatpak|apt|snap", "explanation": "中文一句话"}\n'
                    "规则：flatpak 应用 ID 以 com./org./io. 开头；apt 包名小写含 -。"
                )},
            ])
            import json
            text = resp.text.strip()
            # 找 JSON
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                data = json.loads(text[start:end+1])
                pkg = str(data.get("package", "")).strip()
                ptype = str(data.get("package_type", "apt")).strip().lower()
                if pkg:
                    if ptype not in ("flatpak", "apt", "snap"):
                        ptype = "flatpak" if _is_flatpak_id(pkg) else "apt"
                    return pkg, ptype
        except (LLMError, ValueError, KeyError):
            pass

    # 兜底：直接当 apt 包名（小写化、空格转 -）
    fallback = target.lower().replace(" ", "-")
    return fallback, "apt"


# ---------------------------------------------------------------------------
# 主执行循环
# ---------------------------------------------------------------------------

def run_skill(
    intent: Intent,
    cfg: Config,
    confirm: ConfirmCallback | None = None,
    on_progress: ProgressCallback | None = None,
    user_input: str | None = None,
) -> RunResult:
    """执行一个 Skill。

    confirm: 灰名单确认回调。None 视为自动拒绝（保守策略）。
    on_progress: 进度回调。
    user_input: v0.8.16 用户原始输入（用于 usage_log 记录）。
                None 时用 intent.raw_text（agent 内部调用描述）。
    """
    import time as _time
    t0 = _time.perf_counter()
    skill = intent.skill
    if skill is None:
        log.warning(f"Skill 未找到：{intent.skill_name}")
        return RunResult(
            skill=SkillDef(name=intent.skill_name),
            success=False,
            final_message="未找到匹配的 Skill",
        )

    log.info(
        f"执行 Skill「{skill.name}」",
        extra={"params": intent.params, "steps": len(skill.steps)},
    )

    ctx: dict[str, str] = dict(intent.params)
    ctx["__user_input__"] = intent.raw_text
    ctx["__skill_name__"] = skill.name

    result = RunResult(skill=skill, ctx=ctx)

    for step in skill.steps:
        # 评估 condition
        if not eval_condition(step.condition, ctx):
            sr = StepResult(step=step, skipped=True, success=True)
            result.steps.append(sr)
            if on_progress:
                on_progress(step.name, f"跳过：条件不满足")
            continue

        sr = _execute_step(step, skill, ctx, cfg, intent.raw_text, confirm, on_progress)
        result.steps.append(sr)

        # set_var 永远继续
        if step.type == "set_var":
            continue

        # verify 失败不阻断（on_failure=continue 是默认）
        if step.type == "verify":
            if not sr.success and step.on_failure == "stop":
                result.success = False
                result.final_message = f"验证失败：{step.description or step.name}"
                break
            continue

        # notify 失败不阻断
        if step.type == "notify":
            continue

        # command / resolve_package 失败处理
        if not sr.success:
            if step.on_failure == "stop":
                result.success = False
                result.final_message = sr.error or f"步骤「{step.name}」失败"
                break
            # continue：继续下一步

    else:
        # 所有步骤执行完（没 break）
        result.success = True
        if not result.final_message:
            result.final_message = f"「{skill.description}」已完成"

    elapsed = _time.perf_counter() - t0
    log.info(
        f"Skill「{skill.name}」{'完成' if result.success else '失败'}（{elapsed:.2f}s）",
        extra={"steps_run": len(result.steps), "final": result.final_message[:200]},
    )

    # v0.8.16: 追加 usage_log（参考 OpenClaw "实践即认识" 设计）
    # 只对 user / auto source 的 skill 追加（builtin 在安装目录，可能没写权限）
    if skill.file_path is not None and skill.source in ("user", "auto"):
        try:
            from lihua.skills import append_usage_log
            # v0.8.16: 优先用 user_input（用户原始输入），fallback 到 intent.raw_text
            log_input = user_input if user_input else intent.raw_text
            append_usage_log(skill.file_path, {
                "timestamp": _time.time(),
                "success": result.success,
                "user_input": log_input,
                "notes": result.final_message or ("成功" if result.success else "失败"),
                "params": dict(intent.params),
            })
        except Exception as e:
            log.warning(f"追加 usage_log 失败（不影响执行）：{e}")

    # v0.8.18: 失败时自动追加 trap（踩坑记录）
    # 参考 trae 工作流：遇到坑→追加 trap。失败案例结构化记录：现象→根因（待填）→解决方案（待填）
    # LLM 诊断出根因后可调 trap_update 工具填充 root_cause/solution
    if not result.success:
        try:
            from lihua.memory import get_memory_store
            store = get_memory_store()
            # 构造 symptom：失败 skill + 失败的 step + 错误信息
            failed_steps = [sr for sr in result.steps if not sr.success and not sr.skipped]
            if failed_steps:
                step_info = f"step「{failed_steps[-1].step.name}」"
                err_msg = failed_steps[-1].error or result.final_message
            else:
                step_info = "未知 step"
                err_msg = result.final_message or "执行失败"
            log_input = user_input if user_input else intent.raw_text
            symptom = f"skill「{skill.name}」{step_info} 失败：{err_msg[:200]}"
            # 提取关键词（用于检索 + 匹配同类 trap）
            from lihua.memory import _extract_keywords
            keywords = _extract_keywords(log_input)[:6]
            # 检查是否已有同类 open trap（按 symptom 前 80 字符匹配）
            existing = store.get_traps(status="open")
            matched_existing = None
            symptom_prefix = symptom[:80]
            for t in existing:
                if t.symptom.startswith(symptom_prefix):
                    matched_existing = t
                    break
            if matched_existing is not None:
                # 累加出现次数
                store.update_trap(matched_existing.id, {
                    "occurrence_count": matched_existing.occurrence_count + 1,
                })
                log.info(f"trap T{matched_existing.id:03d} 出现次数 +1（同类失败累加）")
            else:
                # 新增 trap
                store.add_trap(
                    symptom=symptom,
                    related_skills=[skill.name],
                    related_keywords=keywords,
                )
        except Exception as e:
            log.warning(f"追加 trap 失败（不影响执行）：{e}")

    return result


def _execute_step(
    step: SkillStep,
    skill: SkillDef,
    ctx: dict[str, str],
    cfg: Config,
    user_input: str,
    confirm: ConfirmCallback | None,
    on_progress: ProgressCallback | None,
) -> StepResult:
    """执行单个步骤。"""
    sr = StepResult(step=step)

    if on_progress:
        msg = step.description or step.name
        on_progress(step.name, msg)

    try:
        if step.type == "set_var":
            for k, v in step.vars.items():
                ctx[k] = render_template(v, ctx)
            sr.success = True
            return sr

        if step.type == "resolve_package":
            target = ctx.get("target", "")
            if not target:
                sr.success = False
                sr.error = "缺少 target 参数"
                return sr
            resolved = _resolve_package(skill, target, step.prefer, cfg)
            if resolved:
                pkg, ptype = resolved
                ctx["package"] = pkg
                ctx["package_type"] = ptype
                sr.success = True
                sr.output = f"{pkg} ({ptype})"
                if on_progress:
                    on_progress(step.name, f"解析为：{pkg}（{ptype}）")
            else:
                sr.success = False
                sr.error = f"无法解析「{target}」对应的包名"
            return sr

        if step.type == "notify":
            cmd = render_template(step.command, ctx)
            # notify-send 不需要确认
            opts = ExecOptions(shell=True, timeout=10.0, audit=False)
            r = execute_safely(cmd, opts, user_input=user_input)
            sr.exec_result = r
            sr.success = True  # 通知失败不影响主流程
            sr.output = r.stdout
            return sr

        if step.type in ("command", "verify"):
            cmd = render_template(step.command, ctx)
            if not cmd:
                sr.success = False
                sr.error = "命令模板为空"
                return sr

            # 安全分类
            decision = classify(cmd)
            if decision.level == "black":
                sr.success = False
                sr.error = f"安全引擎拒绝：{decision.reason}"
                sr.confirm_decision = "denied"
                return sr

            # 确定最终安全级别：
            # YAML 中 step.safety 是 skill 作者的标注（white/grey/black）。
            # 取 YAML 标注和 classify 结果中更严格的一方，
            # 这样即使 classify 把 `flatpak install` 识别为 white，
            # 只要 YAML 标了 grey，仍然走灰名单确认流程。
            yaml_safety = (step.safety or "").strip().lower()
            if yaml_safety == "grey":
                effective_level = "grey"
            elif yaml_safety == "black":
                # YAML 显式标 black，但 classify 未拦截：仍拒绝
                sr.success = False
                sr.error = f"Skill 标注为黑名单：{step.confirm or '禁止执行'}"
                sr.confirm_decision = "denied"
                return sr
            else:
                effective_level = decision.level

            # 灰名单确认
            if effective_level == "grey":
                msg = step.confirm or decision.human_message or decision.reason or "需要确认"
                msg = render_template(msg, ctx)
                sr.confirm_message = msg
                sr.needs_confirm = True

                if cfg.always_confirm_grey:
                    if confirm is None:
                        # 无确认回调 = 拒绝（保守）
                        sr.success = False
                        sr.error = "需要确认但未提供确认回调"
                        sr.confirm_decision = "denied"
                        return sr
                    confirm_decision = confirm(msg, cmd)
                    if confirm_decision != "confirmed":
                        sr.success = False
                        # v0.8.6：区分"用户取消"和"超时"
                        sr.error = "确认超时（10 分钟内未响应）" if confirm_decision == "timeout" else "用户取消"
                        sr.confirm_decision = confirm_decision  # "denied" 或 "timeout"
                        return sr
                    sr.confirm_decision = "confirmed"
                else:
                    sr.confirm_decision = "auto"

            # 执行
            # v0.8.6：扩大长命令检测关键字（原只检测 "install"）
            # install/update/upgrade/dist-upgrade/download/clone/build/make 都是潜在长命令
            if step.timeout:
                timeout = step.timeout
            elif any(kw in cmd for kw in ("install", "update", "upgrade", "dist-upgrade", "download", "clone", "build", "make")):
                timeout = 600.0  # 10 分钟
            else:
                timeout = 120.0  # 2 分钟（原 60s 对部分命令略短）
            opts = ExecOptions(
                shell=True,
                timeout=timeout,
                audit=True,
                on_progress=lambda name, line: (
                    on_progress(step.name, line) if on_progress else None
                ),
            )
            r = execute_safely(cmd, opts, user_input=user_input)
            sr.exec_result = r
            sr.success = r.success
            sr.output = r.stdout
            sr.error = r.stderr if not r.success else ""
            sr.duration = r.duration
            return sr

        # 未知 step 类型
        sr.success = False
        sr.error = f"未知的 step 类型：{step.type}"
        return sr

    except Exception as e:  # noqa: BLE001
        sr.success = False
        sr.error = f"步骤执行异常：{e}"
        return sr
