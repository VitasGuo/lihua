"""v0.8.15 自监控分析——让 Lihua 能审视自己的运行数据，发现问题、优化行为。

二次进化第五支柱。把分散在 audit_log / memory episodes / knowledge / preferences
里的数据汇总成可读的分析报告，让 LLM 和用户都能看到 Lihua 的"体检报告"。

## 设计目标

1. **总览**：总交互数、成功率、平均耗时、活跃天数
2. **工具使用统计**：每个工具的调用次数、成功率、平均耗时
3. **错误分析**：常见错误类型、失败工具排行
4. **用户问题分类**：诊断类/修复类/查询类占比
5. **技能使用频率**：哪些 skill 用得多、成功率
6. **改进建议**：基于数据的优化建议（如某工具失败率高 → 换别的）

## 数据源

- `audit_log`（executor.py）：每条命令执行记录
- `memory episodes`（memory.py）：每次完整交互的情景
- `memory knowledge`（memory.py）：知识库模式
- `memory preferences`（memory.py）：用户偏好统计

## 核心 API

- `get_overview()`：总览统计
- `get_tool_stats()`：工具使用统计
- `get_error_analysis()`：错误分析
- `get_skill_usage()`：技能使用频率
- `get_suggestions()`：改进建议
- `generate_report()`：完整分析报告（LLM self_analyze 工具用）
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any

from lihua.config import audit_log_path
from lihua.logging_config import get_logger

log = get_logger(__name__)


def _load_audit_entries(limit: int = 1000) -> list[dict[str, Any]]:
    """加载审计日志（JSON 行格式），返回 dict 列表。

    limit=1000 表示读最后 1000 条（避免大数据量爆内存）。
    """
    path = audit_log_path()
    if not path.exists():
        return []
    try:
        # 读最后 limit 行（避免读整个大文件）
        with path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        lines = lines[-limit:] if len(lines) > limit else lines
        result = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return result
    except OSError as e:
        log.warning(f"读取审计日志失败：{e}")
        return []


def _load_memory_episodes(limit: int = 500) -> list[dict[str, Any]]:
    """从记忆系统加载最近的 episodes。"""
    try:
        from lihua.memory import get_memory_store
        store = get_memory_store()
        episodes = store.get_recent_episodes(limit=limit)
        return [e.to_dict() for e in episodes]
    except Exception as e:
        log.warning(f"读取记忆 episodes 失败：{e}")
        return []


def _load_memory_stats() -> dict[str, Any]:
    """从记忆系统加载统计信息。"""
    try:
        from lihua.memory import get_memory_store
        store = get_memory_store()
        return store.get_stats()
    except Exception as e:
        log.warning(f"读取记忆统计失败：{e}")
        return {}


# ─── 工具名识别 ────────────────────────────────────────────

def _classify_command(command: str) -> str:
    """根据命令字符串识别工具类型（用于 audit_log 数据）。

    audit_log 只记录 shell 命令，没有工具名。
    这里通过命令前缀推断对应的工具/skill。
    """
    cmd = command.strip().lower()
    if not cmd:
        return "unknown"

    # 常见命令前缀分类
    prefixes = {
        "apt": "apt",
        "apt-get": "apt",
        "dpkg": "apt",
        "snap": "snap",
        "flatpak": "flatpak",
        "git": "git",
        "docker": "docker",
        "systemctl": "service",
        "journalctl": "log_view",
        "cat": "read_file",
        "ls": "list",
        "ps": "process",
        "top": "process",
        "htop": "process",
        "kill": "kill_process",
        "killall": "kill_process",
        "df": "disk",
        "du": "disk",
        "free": "memory",
        "uname": "system_info",
        "lscpu": "hardware_info",
        "lspci": "hardware_info",
        "lsusb": "hardware_info",
        "ip": "network",
        "ifconfig": "network",
        "ss": "network",
        "netstat": "network",
        "ping": "network",
        "curl": "http",
        "wget": "http",
        "nvidia-smi": "gpu",
        "gsettings": "gnome",
        "dconf": "gnome",
        "fcitx5": "input_method",
        "ibus": "input_method",
        "pkexec": "sudo",
        "sudo": "sudo",
        "tee": "write_file",
        "echo": "echo",
        "sed": "edit_file",
        "awk": "text_process",
        "grep": "search",
        "find": "search",
        "rm": "remove",
        "cp": "copy",
        "mv": "move",
        "mkdir": "mkdir",
        "chmod": "permission",
        "chown": "permission",
        "tar": "archive",
        "zip": "archive",
        "unzip": "archive",
        "ffmpeg": "media",
        "convert": "image",
    }
    for prefix, category in prefixes.items():
        if cmd.startswith(prefix + " ") or cmd == prefix:
            return category
    return "other"


def _classify_user_question(user_input: str) -> str:
    """根据用户输入分类问题类型。

    返回 "diagnose"（诊断类）/ "fix"（修复类）/ "query"（查询类）/ "config"（配置类）/ "other"。
    """
    text = user_input.lower()
    # 诊断类关键词（优先级最高）
    diagnose_kw = ["为什么", "怎么这么", "什么原因", "失败", "报错", "错误", "慢", "卡", "崩溃", "无法", "不能", "不工作", "没声音", "连不上"]
    for kw in diagnose_kw:
        if kw in text:
            return "diagnose"
    # 配置类关键词（在 fix 之前检查，避免"改成"被"改"匹配）
    config_kw = ["改成", "换成", "设置成", "修改为", "调整为"]
    for kw in config_kw:
        if kw in text:
            return "config"
    # 修复类关键词
    fix_kw = ["修复", "解决", "修一下", "装一下", "安装", "卸载", "删除", "清理", "重启", "启动", "配置", "设置", "修改", "改"]
    for kw in fix_kw:
        if kw in text:
            return "fix"
    # 查询类关键词
    query_kw = ["查看", "看看", "列出", "查询", "检查", "状态", "信息", "是什么", "有哪些", "怎么样"]
    for kw in query_kw:
        if kw in text:
            return "query"
    return "other"


# ─── 统计函数 ────────────────────────────────────────────

def get_overview() -> dict[str, Any]:
    """总览统计：总交互数、成功率、平均耗时、活跃天数等。"""
    memory_stats = _load_memory_stats()
    episodes = _load_memory_episodes(limit=500)

    # 从 episodes 计算统计
    total = len(episodes)
    success_count = sum(1 for e in episodes if e.get("success"))
    durations = [e.get("duration", 0) for e in episodes if e.get("duration")]
    avg_duration = sum(durations) / len(durations) if durations else 0

    # 活跃天数（按 timestamp 的日期去重）
    days = set()
    for e in episodes:
        ts = e.get("timestamp", 0)
        if ts:
            import datetime
            day = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            days.add(day)

    # 工具调用总数
    total_tool_calls = sum(len(e.get("tool_calls", [])) for e in episodes)

    return {
        "total_interactions": total,
        "total_tool_calls": total_tool_calls,
        "success_rate": round(success_count / max(1, total), 3),
        "avg_duration": round(avg_duration, 2),
        "active_days": len(days),
        "memory_episodes": memory_stats.get("episodes_count", 0),
        "knowledge_patterns": memory_stats.get("knowledge_patterns", 0),
        "first_session": memory_stats.get("first_session"),
        "last_session": memory_stats.get("last_session"),
        "top_tools": memory_stats.get("top_tools", {}),
        "top_keywords": memory_stats.get("top_keywords", {}),
    }


def get_tool_stats() -> dict[str, Any]:
    """工具使用统计：每个工具的调用次数、成功率、平均耗时。"""
    episodes = _load_memory_episodes(limit=500)

    # 按 tool_call 统计
    tool_data: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "count": 0, "success": 0, "fail": 0, "durations": [], "errors": []
    })

    for ep in episodes:
        for tc in ep.get("tool_calls", []):
            name = tc.get("name", "unknown")
            success = tc.get("success", True)
            duration = tc.get("duration", 0)
            error = tc.get("error", "")
            d = tool_data[name]
            d["count"] += 1
            if success:
                d["success"] += 1
            else:
                d["fail"] += 1
                if error:
                    d["errors"].append(error[:100])  # 截断
            if duration:
                d["durations"].append(duration)

    # 计算汇总
    result = []
    for name, d in sorted(tool_data.items(), key=lambda x: x[1]["count"], reverse=True):
        avg_dur = sum(d["durations"]) / len(d["durations"]) if d["durations"] else 0
        result.append({
            "name": name,
            "count": d["count"],
            "success": d["success"],
            "fail": d["fail"],
            "success_rate": round(d["success"] / max(1, d["count"]), 3),
            "avg_duration": round(avg_dur, 2),
            "common_errors": list(Counter(d["errors"]).most_common(3)),
        })

    return {
        "total_tools": len(result),
        "total_calls": sum(d["count"] for d in tool_data.values()),
        "tools": result,
    }


def get_error_analysis() -> dict[str, Any]:
    """错误分析：常见错误类型、失败工具排行。"""
    episodes = _load_memory_episodes(limit=500)

    # 失败的 episodes
    failed = [e for e in episodes if not e.get("success")]

    # 失败工具统计
    fail_tools: dict[str, int] = defaultdict(int)
    error_messages: list[str] = []
    for ep in failed:
        for tc in ep.get("tool_calls", []):
            if not tc.get("success", True):
                fail_tools[tc.get("name", "unknown")] += 1
                err = tc.get("error", "")
                if err:
                    error_messages.append(err[:100])

    # 错误分类（按关键词）
    error_categories: dict[str, int] = defaultdict(int)
    category_kw = {
        "timeout": ["timeout", "timed out", "超时"],
        "permission": ["permission", "denied", "权限", "forbidden"],
        "not_found": ["not found", "no such", "不存在", "找不到"],
        "network": ["network", "connection", "refused", "unreachable", "网络"],
        "syntax": ["syntax", "invalid", "malformed", "语法"],
        "dependency": ["module", "import", "no module", "依赖"],
        "disk": ["disk", "space", "full", "磁盘", "空间"],
        "memory": ["memory", "oom", "out of memory", "内存"],
    }
    for msg in error_messages:
        msg_lower = msg.lower()
        categorized = False
        for cat, kws in category_kw.items():
            if any(kw in msg_lower for kw in kws):
                error_categories[cat] += 1
                categorized = True
                break
        if not categorized:
            error_categories["other"] += 1

    return {
        "total_failed_episodes": len(failed),
        "fail_rate": round(len(failed) / max(1, len(episodes)), 3),
        "top_fail_tools": dict(sorted(fail_tools.items(), key=lambda x: x[1], reverse=True)[:10]),
        "error_categories": dict(sorted(error_categories.items(), key=lambda x: x[1], reverse=True)),
        "sample_errors": list(Counter(error_messages).most_common(5)),
    }


def get_question_categories() -> dict[str, Any]:
    """用户问题分类统计。"""
    episodes = _load_memory_episodes(limit=500)
    categories: dict[str, int] = defaultdict(int)
    for ep in episodes:
        ui = ep.get("user_input", "")
        if ui:
            categories[_classify_user_question(ui)] += 1

    total = sum(categories.values())
    return {
        "total_questions": total,
        "categories": dict(sorted(categories.items(), key=lambda x: x[1], reverse=True)),
        "percentages": {
            k: round(v / max(1, total), 3) for k, v in categories.items()
        },
    }


def get_skill_usage() -> dict[str, Any]:
    """技能（预定义 skill）使用频率。"""
    tool_stats = get_tool_stats()
    # 过滤出 skill（非内置工具）
    builtin_tools = {
        "run_shell", "read_file", "write_file", "edit_file", "run_python",
        "read_log", "self_restart", "self_build", "self_status",
        "self_version_bump", "memory_recall", "create_skill",
    }
    skills = [t for t in tool_stats["tools"] if t["name"] not in builtin_tools]
    return {
        "total_skills_used": len(skills),
        "total_skill_calls": sum(t["count"] for t in skills),
        "skills": skills,
    }


def get_command_stats() -> dict[str, Any]:
    """从 audit_log 统计命令使用情况（按命令分类）。"""
    entries = _load_audit_entries(limit=1000)
    if not entries:
        return {"total_commands": 0, "categories": {}, "top_commands": []}

    categories: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "count": 0, "success": 0, "fail": 0, "durations": []
    })
    command_counter: Counter = Counter()

    for entry in entries:
        cmd = entry.get("command", "")
        category = _classify_command(cmd)
        success = entry.get("success", False)
        duration = entry.get("duration", 0)
        d = categories[category]
        d["count"] += 1
        if success:
            d["success"] += 1
        else:
            d["fail"] += 1
        if duration:
            d["durations"].append(duration)
        # 命令前缀（前 30 字符）作为 key
        cmd_key = cmd[:30].strip()
        if cmd_key:
            command_counter[cmd_key] += 1

    result_categories = {}
    for cat, d in sorted(categories.items(), key=lambda x: x[1]["count"], reverse=True):
        avg_dur = sum(d["durations"]) / len(d["durations"]) if d["durations"] else 0
        result_categories[cat] = {
            "count": d["count"],
            "success": d["success"],
            "fail": d["fail"],
            "success_rate": round(d["success"] / max(1, d["count"]), 3),
            "avg_duration": round(avg_dur, 2),
        }

    return {
        "total_commands": len(entries),
        "categories": result_categories,
        "top_commands": dict(command_counter.most_common(10)),
    }


def get_suggestions() -> list[dict[str, str]]:
    """基于数据的改进建议。

    规则：
    - 某工具失败率 > 30% → 建议检查或换工具
    - 某类命令频繁失败 → 建议诊断
    - 诊断类问题占比高 → 建议加强诊断能力
    - 平均耗时过长 → 建议优化
    - 知识库模式少 → 建议多调 memory_recall
    """
    suggestions: list[dict[str, str]] = []

    # 工具失败率分析
    tool_stats = get_tool_stats()
    for tool in tool_stats["tools"]:
        if tool["count"] >= 3 and tool["success_rate"] < 0.7:
            suggestions.append({
                "type": "tool_fail_rate",
                "severity": "warning",
                "title": f"工具 '{tool['name']}' 失败率偏高",
                "detail": (
                    f"调用 {tool['count']} 次，成功率仅 {tool['success_rate'] * 100:.0f}%。"
                    f"常见错误：{tool['common_errors'][:2]}"
                ),
                "suggestion": "考虑换用其他工具，或检查参数是否正确",
            })

    # 问题类型分析
    categories = get_question_categories()
    diag_pct = categories["percentages"].get("diagnose", 0)
    if diag_pct > 0.4:
        suggestions.append({
            "type": "high_diagnose_ratio",
            "severity": "info",
            "title": "诊断类问题占比高",
            "detail": f"诊断类问题占 {diag_pct * 100:.0f}%，用户经常遇到需要排查的问题",
            "suggestion": "加强诊断类 skill 库，或优化 read_log / system_info 等工具",
        })

    # 知识库覆盖
    memory_stats = _load_memory_stats()
    patterns = memory_stats.get("knowledge_patterns", 0)
    episodes = memory_stats.get("episodes_count", 0)
    if episodes > 20 and patterns < 5:
        suggestions.append({
            "type": "low_knowledge",
            "severity": "info",
            "title": "知识库模式偏少",
            "detail": f"已记录 {episodes} 次交互，但只总结出 {patterns} 个知识模式",
            "suggestion": "可考虑主动调 memory_recall 深挖历史经验，或调 create_skill 固化高频流程",
        })

    # 平均耗时
    overview = get_overview()
    avg_dur = overview.get("avg_duration", 0)
    if avg_dur > 30:
        suggestions.append({
            "type": "slow_response",
            "severity": "warning",
            "title": "平均响应时间较长",
            "detail": f"平均每次交互耗时 {avg_dur:.1f}s",
            "suggestion": "检查是否有过多的 run_shell 调用，或考虑用 skill 替代多步命令",
        })

    # 命令失败模式
    cmd_stats = get_command_stats()
    for cat, d in cmd_stats.get("categories", {}).items():
        if d["count"] >= 5 and d["success_rate"] < 0.5:
            suggestions.append({
                "type": "cmd_category_fail",
                "severity": "warning",
                "title": f"'{cat}' 类命令失败率高",
                "detail": f"调用 {d['count']} 次，成功率 {d['success_rate'] * 100:.0f}%",
                "suggestion": "检查命令参数或前置条件（如依赖未装、权限不够等）",
            })

    return suggestions


def generate_report() -> dict[str, Any]:
    """生成完整分析报告（self_analyze 工具调用）。

    返回包含所有统计 + 建议的完整 dict。
    """
    return {
        "overview": get_overview(),
        "tool_stats": get_tool_stats(),
        "error_analysis": get_error_analysis(),
        "question_categories": get_question_categories(),
        "skill_usage": get_skill_usage(),
        "command_stats": get_command_stats(),
        "suggestions": get_suggestions(),
    }


def generate_text_report() -> str:
    """生成人类可读的文本报告（self_analyze 工具返回给 LLM 的内容）。"""
    report = generate_report()
    lines: list[str] = []

    # 总览
    ov = report["overview"]
    lines.append("# Lihua 自监控分析报告")
    lines.append("")
    lines.append("## 总览")
    lines.append(f"- 总交互数：{ov['total_interactions']}")
    lines.append(f"- 总工具调用数：{ov['total_tool_calls']}")
    lines.append(f"- 成功率：{ov['success_rate'] * 100:.1f}%")
    lines.append(f"- 平均耗时：{ov['avg_duration']:.1f}s")
    lines.append(f"- 活跃天数：{ov['active_days']}")
    lines.append(f"- 知识库模式数：{ov['knowledge_patterns']}")
    if ov.get("top_tools"):
        lines.append(f"- 最常用工具：{', '.join(list(ov['top_tools'].keys())[:5])}")

    # 工具统计
    ts = report["tool_stats"]
    lines.append("")
    lines.append("## 工具使用统计")
    lines.append(f"共使用 {ts['total_tools']} 种工具，调用 {ts['total_calls']} 次")
    if ts["tools"]:
        lines.append("")
        lines.append("| 工具 | 调用次数 | 成功率 | 平均耗时 |")
        lines.append("|------|---------|--------|---------|")
        for t in ts["tools"][:10]:
            lines.append(
                f"| {t['name']} | {t['count']} | "
                f"{t['success_rate'] * 100:.0f}% | {t['avg_duration']:.1f}s |"
            )

    # 错误分析
    ea = report["error_analysis"]
    lines.append("")
    lines.append("## 错误分析")
    lines.append(f"- 失败交互数：{ea['total_failed_episodes']}")
    lines.append(f"- 失败率：{ea['fail_rate'] * 100:.1f}%")
    if ea["top_fail_tools"]:
        lines.append(f"- 失败最多的工具：{', '.join(list(ea['top_fail_tools'].keys())[:5])}")
    if ea["error_categories"]:
        lines.append(f"- 错误分类：{ea['error_categories']}")

    # 问题分类
    qc = report["question_categories"]
    lines.append("")
    lines.append("## 用户问题分类")
    lines.append(f"- 总问题数：{qc['total_questions']}")
    for cat, pct in qc["percentages"].items():
        lines.append(f"  - {cat}: {pct * 100:.1f}%")

    # 建议
    sugs = report["suggestions"]
    lines.append("")
    lines.append("## 改进建议")
    if not sugs:
        lines.append("（暂无建议——所有指标都在正常范围内）")
    else:
        for i, s in enumerate(sugs, 1):
            lines.append(f"{i}. **{s['title']}** ({s['severity']})")
            lines.append(f"   - 详情：{s['detail']}")
            lines.append(f"   - 建议：{s['suggestion']}")

    return "\n".join(lines)
