"""网络+系统高级类 Skill 测试。"""
from __future__ import annotations

import pytest

from lihua.skills import SkillRegistry


@pytest.fixture
def registry() -> SkillRegistry:
    reg = SkillRegistry()
    reg.load()
    return reg


class TestNetworkSysSkills:
    @pytest.mark.parametrize("skill_name", [
        "vpn_connect",
        "ssh_connect",
        "hotspot_create",
        "share_folder",
        "kernel_management",
        "cron_job",
        "log_view",
    ])
    def test_skill_loaded(self, registry: SkillRegistry, skill_name: str) -> None:
        s = registry.get(skill_name)
        assert s is not None, f"Skill {skill_name} 应加载"
        assert len(s.triggers) > 0, f"Skill {skill_name} 没有 triggers"
        assert len(s.steps) > 0, f"Skill {skill_name} 没有 steps"

    @pytest.mark.parametrize("text,expected", [
        ("连vpn config.conf", "vpn_connect"),
        ("查看vpn", "vpn_connect"),
        ("ssh连接 user@host", "ssh_connect"),
        ("创建热点 MyHotspot", "hotspot_create"),
        ("开热点", "hotspot_create"),
        ("共享文件夹 /home/share", "share_folder"),
        ("查看内核", "kernel_management"),
        ("内核版本", "kernel_management"),
        ("查看定时任务", "cron_job"),
        ("添加定时任务", "cron_job"),
        ("查看日志", "log_view"),
        ("系统日志", "log_view"),
    ])
    def test_intent_match(self, registry: SkillRegistry, text: str, expected: str) -> None:
        matched = registry.match_by_text(text)
        assert matched, f"应匹配：{text}"
        assert matched[0].name == expected, (
            f"{text} 应匹配 {expected}，实际 {matched[0].name}"
        )
