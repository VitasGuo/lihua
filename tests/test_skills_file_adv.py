"""文件管理高级类 Skill 测试。"""
from __future__ import annotations

import pytest

from lihua.skills import SkillRegistry


@pytest.fixture
def registry() -> SkillRegistry:
    reg = SkillRegistry()
    reg.load()
    return reg


class TestFileAdvSkills:
    @pytest.mark.parametrize("skill_name", [
        "file_backup",
        "file_encrypt",
        "file_shred",
        "disk_mount",
        "usb_bootable",
        "file_convert_pdf",
        "image_convert",
    ])
    def test_skill_loaded(self, registry: SkillRegistry, skill_name: str) -> None:
        s = registry.get(skill_name)
        assert s is not None, f"Skill {skill_name} 应加载"

    @pytest.mark.parametrize("text,expected", [
        ("备份文件 /home/user/docs 到 /mnt/backup", "file_backup"),
        ("加密文件 secret.txt", "file_encrypt"),
        ("安全删除 secret.txt", "file_shred"),
        ("挂载磁盘 /dev/sdb1", "disk_mount"),
        ("制作启动盘 ubuntu.iso 到 /dev/sdb", "usb_bootable"),
        ("doc转pdf report.docx", "file_convert_pdf"),
        ("转png image.jpg", "image_convert"),
    ])
    def test_intent_match(self, registry: SkillRegistry, text: str, expected: str) -> None:
        matched = registry.match_by_text(text)
        assert matched, f"应匹配：{text}"
        assert matched[0].name == expected, f"{text} 应匹配 {expected}，实际 {matched[0].name}"
