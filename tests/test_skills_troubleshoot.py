"""新手救急诊断 Skill 测试（v0.7.12 合并版）。

v0.7.12 把 8 个 troubleshoot_* skill 合并为 1 个 troubleshoot skill：
- 参数 issue 指定问题类型（sound/wifi/internet/disk/memory/cpu/crash/slow）
- 参数 action 指定诊断或修复
- 参数 app 仅 crash 场景用

覆盖：
- Skill 加载（1 个合并版 troubleshoot）
- trigger 匹配（8 类问题场景）
- 参数提取（issue / action / app）
- 步骤结构（双重 condition：issue + action）
- 与 monitor/usage 类 skill 的优先级冲突
"""
from __future__ import annotations

import pytest

from lihua.skills import SkillRegistry


@pytest.fixture
def registry() -> SkillRegistry:
    reg = SkillRegistry()
    reg.load()
    return reg


class TestTroubleshootSkillLoaded:
    """合并版 troubleshoot skill 加载验证。"""

    def test_skill_loaded(self, registry: SkillRegistry) -> None:
        s = registry.get("troubleshoot")
        assert s is not None, "troubleshoot skill 未加载"
        assert len(s.triggers) > 0, "troubleshoot 没有 triggers"
        assert len(s.steps) > 0, "troubleshoot 没有 steps"
        assert s.category == "troubleshoot", f"category 应为 troubleshoot，实际 {s.category}"

    def test_has_three_parameters(self, registry: SkillRegistry) -> None:
        """应有 issue / action / app 三个参数。"""
        s = registry.get("troubleshoot")
        assert s is not None
        param_names = {p.name for p in s.parameters}
        assert param_names == {"issue", "action", "app"}, (
            f"参数应为 issue/action/app，实际 {param_names}"
        )

    def test_issue_default_is_sound(self, registry: SkillRegistry) -> None:
        """issue 默认值应为「没声音」。"""
        s = registry.get("troubleshoot")
        assert s is not None
        issue_param = next((p for p in s.parameters if p.name == "issue"), None)
        assert issue_param is not None
        assert issue_param.default == "没声音"

    def test_action_default_is_diagnose(self, registry: SkillRegistry) -> None:
        """action 默认值应为 诊断。"""
        s = registry.get("troubleshoot")
        assert s is not None
        action_param = next((p for p in s.parameters if p.name == "action"), None)
        assert action_param is not None
        assert action_param.default == "诊断"

    def test_has_eight_issue_steps(self, registry: SkillRegistry) -> None:
        """应有 8 个 issue 的诊断/修复步骤（sound/wifi/internet/disk/memory/cpu/crash/slow）。"""
        s = registry.get("troubleshoot")
        assert s is not None
        step_names = {st.name for st in s.steps}
        # 每个 issue 至少有诊断步骤
        expected_prefixes = ["sound_", "wifi_", "internet_", "disk_", "memory_", "cpu_", "crash_", "slow_"]
        for prefix in expected_prefixes:
            matching = [n for n in step_names if n.startswith(prefix)]
            assert matching, f"缺少 {prefix}* 步骤"

    def test_has_notify_step(self, registry: SkillRegistry) -> None:
        """应有 notify 步骤。"""
        s = registry.get("troubleshoot")
        assert s is not None
        step_names = {st.name for st in s.steps}
        assert "notify" in step_names, "缺少 notify 步骤"

    def test_all_steps_have_condition(self, registry: SkillRegistry) -> None:
        """除 notify 外，所有 command 步骤都应有 condition（含 issue + action 双重条件）。"""
        s = registry.get("troubleshoot")
        assert s is not None
        for step in s.steps:
            if step.type == "command":
                assert step.condition, f"步骤 {step.name} 缺少 condition"
                assert "{{issue}}" in step.condition, (
                    f"步骤 {step.name} 的 condition 应含 {{issue}}，实际：{step.condition}"
                )
                assert "{{action}}" in step.condition, (
                    f"步骤 {step.name} 的 condition 应含 {{action}}，实际：{step.condition}"
                )


class TestTroubleshootTriggerMatch:
    """trigger 匹配测试（8 类问题场景）。"""

    @pytest.mark.parametrize("text", [
        # 没声音
        "没声音了",
        "听不到声音",
        "喇叭不响",
        # 连不上 WiFi
        "连不上wifi",
        "WiFi连不上",
        "无线网连不上",
        # 没网
        "没网",
        "上不了网",
        "网络不通",
        # 磁盘满
        "磁盘满了",
        "硬盘满",
        "空间不足",
        # 内存高
        "内存占用高",
        "内存满了",
        "内存泄漏",
        # CPU 高
        "cpu占用高",
        "cpu满了",
        "cpu过热",
        # 应用崩溃
        "应用崩溃 firefox",
        "程序闪退",
        "软件打不开",
        # 系统慢
        "系统慢",
        "电脑卡",
        "卡顿",
    ])
    def test_trigger_match(self, registry: SkillRegistry, text: str) -> None:
        s = registry.get("troubleshoot")
        assert s is not None
        assert s.match_trigger(text), f"「{text}」应匹配 troubleshoot 的 trigger"

    @pytest.mark.parametrize("text", [
        "没声音了",
        "连不上wifi",
        "没网",
        "磁盘满了",
        "内存占用高",
        "cpu占用高",
        "应用崩溃 firefox",
        "系统慢",
    ])
    def test_intent_match(self, registry: SkillRegistry, text: str) -> None:
        """所有 8 类场景都应匹配 troubleshoot。"""
        matched = registry.match_by_text(text)
        assert matched, f"未匹配任何 Skill：{text}"
        assert matched[0].name == "troubleshoot", (
            f"「{text}」应匹配 troubleshoot，实际匹配 {matched[0].name}"
        )


class TestTroubleshootExtractParams:
    """参数提取测试。"""

    @pytest.mark.parametrize("text,expected_issue", [
        # issue 提取的是正则匹配到的中文词（无捕获组 → group(0)）
        ("没声音了", "没声音"),
        ("喇叭不响", "喇叭"),
        ("音频问题", "音频"),
        ("连不上wifi", "wifi"),
        ("WiFi用不了", "WiFi"),
        ("无线网卡坏了", "无线网"),
        ("没网", "没网"),
        ("上不了网", "上不了网"),
        ("网络不通", "网络不通"),
        ("磁盘满", "磁盘满"),
        ("硬盘满", "硬盘满"),
        ("空间不足", "空间不足"),
        ("内存高", "内存高"),
        ("内存占用高", "内存占用"),
        ("内存泄漏", "内存泄漏"),
        ("cpu高", "cpu高"),
        ("cpu占用高", "cpu占用"),
        ("cpu过热", "cpu过热"),
        ("应用崩溃", "崩溃"),
        ("程序闪退", "闪退"),
        ("软件崩溃", "崩溃"),
        ("系统慢", "系统慢"),
        ("电脑卡", "电脑卡"),
        ("卡顿", "卡顿"),
    ])
    def test_extract_issue(
        self, registry: SkillRegistry, text: str, expected_issue: str
    ) -> None:
        """应从用户输入提取正确的 issue。"""
        s = registry.get("troubleshoot")
        assert s is not None
        params = s.extract_params(text)
        assert params.get("issue") == expected_issue, (
            f"「{text}」应提取 issue={expected_issue}，实际 {params.get('issue')}"
        )

    @pytest.mark.parametrize("text,expected_action", [
        ("没声音了", "诊断"),
        ("修复没声音", "修复"),
        ("诊断wifi", "诊断"),
        ("检查磁盘", "检查"),
        ("看下内存", "看"),
        ("修复cpu高", "修复"),
    ])
    def test_extract_action(
        self, registry: SkillRegistry, text: str, expected_action: str
    ) -> None:
        """应从用户输入提取 action（修复/诊断/检查/看）。"""
        s = registry.get("troubleshoot")
        assert s is not None
        params = s.extract_params(text)
        assert params.get("action") == expected_action, (
            f"「{text}」应提取 action={expected_action}，实际 {params.get('action')}"
        )

    def test_extract_app_from_crash(self, registry: SkillRegistry) -> None:
        """「应用崩溃 firefox」应提取 app=firefox。"""
        s = registry.get("troubleshoot")
        assert s is not None
        params = s.extract_params("应用崩溃 firefox")
        assert params.get("app") == "firefox", (
            f"应提取 app=firefox，实际 {params.get('app')}"
        )

    def test_extract_app_after_keyword(self, registry: SkillRegistry) -> None:
        """「应用 firefox 崩溃」同样应提取 app=firefox。"""
        s = registry.get("troubleshoot")
        assert s is not None
        params = s.extract_params("应用 firefox 崩溃")
        assert params.get("app") == "firefox"

    def test_app_default_firefox(self, registry: SkillRegistry) -> None:
        """非 crash 场景 app 默认 firefox。"""
        s = registry.get("troubleshoot")
        assert s is not None
        params = s.extract_params("没声音了")
        assert params.get("app") == "firefox"


class TestTroubleshootPriorityConflict:
    """与 monitor/usage 类 skill 的优先级冲突测试。"""

    def test_disk_full_wins_over_disk_usage(self, registry: SkillRegistry) -> None:
        """「磁盘满了」同时命中 disk_usage 与 troubleshoot，
        troubleshoot 靠 alias_hit=1 取胜（无 alias 时靠 trigger 长度）。"""
        matched = registry.match_by_text("磁盘满了")
        names = [s.name for s in matched]
        assert "troubleshoot" in names
        assert "disk_usage" in names
        assert matched[0].name == "troubleshoot", (
            f"「磁盘满了」应优先匹配 troubleshoot，实际 {matched[0].name}"
        )

    def test_cpu_high_wins_over_cpu_monitor(self, registry: SkillRegistry) -> None:
        """「cpu占用高」同时命中 cpu_monitor 与 troubleshoot，
        troubleshoot 靠 alias_hit=1 或 trigger 长度取胜。"""
        matched = registry.match_by_text("cpu占用高")
        names = [s.name for s in matched]
        assert "troubleshoot" in names
        assert "cpu_monitor" in names
        assert matched[0].name == "troubleshoot", (
            f"「cpu占用高」应优先匹配 troubleshoot，实际 {matched[0].name}"
        )

    def test_memory_high_wins_over_memory_monitor(
        self, registry: SkillRegistry
    ) -> None:
        """「内存占用高」同时命中 memory_monitor 与 troubleshoot。"""
        matched = registry.match_by_text("内存占用高")
        names = [s.name for s in matched]
        assert "troubleshoot" in names
        assert "memory_monitor" in names
        assert matched[0].name == "troubleshoot", (
            f"「内存占用高」应优先匹配 troubleshoot，实际 {matched[0].name}"
        )


class TestTroubleshootStepConditions:
    """步骤 condition 验证。"""

    def test_diagnose_steps_have_non_fix_condition(self, registry: SkillRegistry) -> None:
        """诊断步骤的 condition 应含 {{action}} != 修复。"""
        s = registry.get("troubleshoot")
        assert s is not None
        diagnose_steps = [
            st for st in s.steps
            if st.type == "command" and "{{action}} != 修复" in (st.condition or "")
        ]
        assert len(diagnose_steps) >= 8, (
            f"诊断步骤应至少 8 个（每 issue 至少 1 个），实际 {len(diagnose_steps)}"
        )

    def test_fix_steps_have_fix_condition(self, registry: SkillRegistry) -> None:
        """修复步骤的 condition 应含 {{action}} == 修复。"""
        s = registry.get("troubleshoot")
        assert s is not None
        fix_steps = [
            st for st in s.steps
            if st.type == "command" and "{{action}} == 修复" in (st.condition or "")
        ]
        # sound/wifi/internet/disk/memory/crash 有修复步骤（cpu/slow 无修复，只诊断）
        assert len(fix_steps) >= 6, (
            f"修复步骤应至少 6 个，实际 {len(fix_steps)}"
        )

    def test_grey_safety_for_fix_steps(self, registry: SkillRegistry) -> None:
        """修复步骤（修改系统）应标记 safety: grey。

        例外：slow_fix_hint 只 echo 建议、不修改系统，safety=white 合理。
        """
        s = registry.get("troubleshoot")
        assert s is not None
        for step in s.steps:
            if step.type == "command" and "{{action}} == 修复" in (step.condition or ""):
                if step.name == "slow_fix_hint":
                    continue
                assert step.safety == "grey", (
                    f"修复步骤 {step.name} 应为 grey，实际 {step.safety}"
                )

    def test_white_safety_for_diagnose_steps(self, registry: SkillRegistry) -> None:
        """诊断步骤（只读查询）应标记 safety: white。"""
        s = registry.get("troubleshoot")
        assert s is not None
        for step in s.steps:
            if step.type == "command" and "{{action}} != 修复" in (step.condition or ""):
                assert step.safety == "white", (
                    f"诊断步骤 {step.name} 应为 white，实际 {step.safety}"
                )

    def test_fix_steps_have_confirm(self, registry: SkillRegistry) -> None:
        """修复步骤应有 confirm 文案。

        例外：slow_fix_hint 只 echo 建议、不修改系统，无需 confirm。
        """
        s = registry.get("troubleshoot")
        assert s is not None
        for step in s.steps:
            if step.type == "command" and "{{action}} == 修复" in (step.condition or ""):
                if step.name == "slow_fix_hint":
                    continue
                assert step.confirm, f"修复步骤 {step.name} 缺少 confirm 文案"
