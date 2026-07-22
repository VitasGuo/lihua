"""多媒体+开发环境类 Skill 测试。"""

from __future__ import annotations

import pytest

from lihua.skills import SkillRegistry


@pytest.fixture
def registry() -> SkillRegistry:
    reg = SkillRegistry()
    reg.load()
    return reg


class TestMediaDevSkills:
    @pytest.mark.parametrize("skill_name", [
        "video_convert",
        "screen_record",
        "pdf_merge_split",
        "git_config",
        "docker_run",
        "python_venv",
        "ssh_key",
    ])
    def test_skill_loaded(self, registry: SkillRegistry, skill_name: str) -> None:
        s = registry.get(skill_name)
        assert s is not None, f"Skill {skill_name} 应加载"
        assert len(s.triggers) > 0, f"Skill {skill_name} 没有 triggers"
        assert len(s.steps) > 0, f"Skill {skill_name} 没有 steps"

    @pytest.mark.parametrize("text,expected", [
        ("转mp4 video.avi", "video_convert"),
        ("视频转换 video.mkv 转webm", "video_convert"),
        ("录屏", "screen_record"),
        ("开始录屏", "screen_record"),
        ("合并pdf", "pdf_merge_split"),
        ("拆分pdf report.pdf", "pdf_merge_split"),
        ("配置git", "git_config"),
        ("git配置用户名", "git_config"),
        ("运行docker nginx", "docker_run"),
        ("docker拉取 ubuntu", "docker_run"),
        ("创建venv myenv", "python_venv"),
        ("创建虚拟环境", "python_venv"),
        ("生成ssh密钥", "ssh_key"),
        ("查看ssh密钥", "ssh_key"),
    ])
    def test_intent_match(self, registry: SkillRegistry, text: str, expected: str) -> None:
        matched = registry.match_by_text(text)
        assert matched, f"应匹配：{text}"
        assert matched[0].name == expected, (
            f"{text} 应匹配 {expected}，实际 {matched[0].name}"
        )
