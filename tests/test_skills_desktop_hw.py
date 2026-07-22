"""桌面+硬件类 Skill 测试。"""

from __future__ import annotations

import pytest

from lihua.skills import SkillRegistry


@pytest.fixture
def registry() -> SkillRegistry:
    reg = SkillRegistry()
    reg.load()
    return reg


class TestDesktopHwSkills:
    @pytest.mark.parametrize("skill_name", [
        "gnome_extension",
        "clipboard_history",
        "gpu_driver",
        "keyboard_layout",
        "touchpad_config",
        "virus_scan",
    ])
    def test_skill_loaded(self, registry: SkillRegistry, skill_name: str) -> None:
        s = registry.get(skill_name)
        assert s is not None, f"Skill {skill_name} 应加载"
        assert len(s.triggers) > 0, f"Skill {skill_name} 没有 triggers"
        assert len(s.steps) > 0, f"Skill {skill_name} 没有 steps"

    @pytest.mark.parametrize("text,expected", [
        ("查看gnome扩展", "gnome_extension"),
        ("启用扩展 dash-to-dock", "gnome_extension"),
        ("查看剪贴板", "clipboard_history"),
        ("清空剪贴板", "clipboard_history"),
        ("查看显卡", "gpu_driver"),
        ("安装nvidia驱动", "gpu_driver"),
        ("切换键盘布局 us", "keyboard_layout"),
        ("查看键盘布局", "keyboard_layout"),
        ("关闭触摸板", "touchpad_config"),
        ("启用触摸板点击", "touchpad_config"),
        ("扫描病毒", "virus_scan"),
        ("扫描文件 /home", "virus_scan"),
    ])
    def test_intent_match(self, registry: SkillRegistry, text: str, expected: str) -> None:
        matched = registry.match_by_text(text)
        assert matched, f"应匹配：{text}"
        assert matched[0].name == expected, (
            f"「{text}」应匹配 {expected}，实际匹配 {matched[0].name}"
        )
