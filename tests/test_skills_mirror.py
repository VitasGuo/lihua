"""软件源镜像类 Skill 测试。"""
from __future__ import annotations

import pytest

from lihua.skills import SkillRegistry


@pytest.fixture
def registry() -> SkillRegistry:
    reg = SkillRegistry()
    reg.load()
    return reg


class TestMirrorSkills:
    @pytest.mark.parametrize("skill_name", [
        "mirror_source",
        "apt_repository",
        "ppa_management",
        "flatpak_remote",
        "snap_channel",
    ])
    def test_skill_loaded(self, registry: SkillRegistry, skill_name: str) -> None:
        s = registry.get(skill_name)
        assert s is not None, f"Skill {skill_name} 应加载"
        assert len(s.triggers) > 0, f"Skill {skill_name} 没有 triggers"
        assert len(s.steps) > 0, f"Skill {skill_name} 没有 steps"

    @pytest.mark.parametrize("text,expected", [
        ("换清华源", "mirror_source"),
        ("切换镜像源", "mirror_source"),
        ("添加仓库 ppa:obsproject/obs-studio", "apt_repository"),
        ("添加 ppa:git-core/ppa", "ppa_management"),
        ("添加 flathub", "flatpak_remote"),
        ("切换 snap firefox 通道 beta", "snap_channel"),
    ])
    def test_intent_match(self, registry: SkillRegistry, text: str, expected: str) -> None:
        matched = registry.match_by_text(text)
        assert matched, f"应匹配：{text}"
        assert matched[0].name == expected, (
            f"「{text}」应匹配 {expected}，实际匹配 {matched[0].name}"
        )

    def test_extract_mirror(self, registry: SkillRegistry) -> None:
        s = registry.get("mirror_source")
        assert s is not None
        params = s.extract_params("换清华源")
        assert params.get("mirror") == "清华"

    @pytest.mark.parametrize("text,expected_mirror", [
        ("换清华源", "清华"),
        ("换中科大源", "中科大"),
        ("换阿里源", "阿里"),
        ("换华为云源", "华为"),
        ("换腾讯云源", "腾讯"),
        ("换默认源", "默认"),
    ])
    def test_extract_mirror_variants(
        self, registry: SkillRegistry, text: str, expected_mirror: str
    ) -> None:
        s = registry.get("mirror_source")
        assert s is not None
        params = s.extract_params(text)
        assert params.get("mirror") == expected_mirror, (
            f"「{text}」应提取 mirror={expected_mirror}，实际 {params.get('mirror')}"
        )

    def test_mirror_source_has_backup_step(self, registry: SkillRegistry) -> None:
        s = registry.get("mirror_source")
        assert s is not None
        step_names = [st.name for st in s.steps]
        assert "backup" in step_names, "mirror_source 应有 backup 步骤"
        assert "apt_update" in step_names, "mirror_source 应有 apt_update 步骤"

    def test_mirror_source_supports_new_ubuntu_format(
        self, registry: SkillRegistry
    ) -> None:
        """镜像源命令应兼容 Ubuntu 24.04 的 ubuntu.sources 新格式。"""
        s = registry.get("mirror_source")
        assert s is not None
        # 至少有一个 step 的 command 中包含 ubuntu.sources 检测
        has_new_format = any(
            "ubuntu.sources" in (st.command or "") for st in s.steps
        )
        assert has_new_format, "mirror_source 应兼容 ubuntu.sources 新格式"

    def test_apt_repository_actions(self, registry: SkillRegistry) -> None:
        s = registry.get("apt_repository")
        assert s is not None
        step_names = [st.name for st in s.steps]
        assert "list_repos" in step_names
        assert "add_repo" in step_names
        assert "remove_repo" in step_names

    def test_apt_repository_extract_repo(self, registry: SkillRegistry) -> None:
        s = registry.get("apt_repository")
        assert s is not None
        params = s.extract_params("添加仓库 ppa:obsproject/obs-studio")
        assert params.get("action") == "添加"
        assert params.get("repo") == "ppa:obsproject/obs-studio"

    def test_ppa_management_actions(self, registry: SkillRegistry) -> None:
        s = registry.get("ppa_management")
        assert s is not None
        step_names = [st.name for st in s.steps]
        assert "list_ppa" in step_names
        assert "add_ppa" in step_names
        assert "remove_ppa" in step_names

    def test_ppa_management_extract_ppa(self, registry: SkillRegistry) -> None:
        s = registry.get("ppa_management")
        assert s is not None
        params = s.extract_params("添加 ppa:git-core/ppa")
        assert params.get("action") == "添加"
        assert params.get("ppa") == "ppa:git-core/ppa"

    def test_flatpak_remote_actions(self, registry: SkillRegistry) -> None:
        s = registry.get("flatpak_remote")
        assert s is not None
        step_names = [st.name for st in s.steps]
        assert "list_remotes" in step_names
        assert "add_flathub" in step_names
        assert "remove_remote" in step_names

    def test_flatpak_remote_extract_remote(self, registry: SkillRegistry) -> None:
        s = registry.get("flatpak_remote")
        assert s is not None
        params = s.extract_params("添加 flathub")
        assert params.get("action") == "添加"
        assert params.get("remote") == "flathub"

    def test_snap_channel_actions(self, registry: SkillRegistry) -> None:
        s = registry.get("snap_channel")
        assert s is not None
        step_names = [st.name for st in s.steps]
        assert "show_channels" in step_names
        assert "switch_channel" in step_names

    def test_snap_channel_extract_channel(self, registry: SkillRegistry) -> None:
        s = registry.get("snap_channel")
        assert s is not None
        params = s.extract_params("切换 snap firefox 通道 beta")
        assert params.get("channel") == "beta"


class TestNoTriggerConflicts:
    """确保新 Skill 的 trigger 不与既有 Skill 冲突。"""

    def test_flathub_not_bare_trigger(self, registry: SkillRegistry) -> None:
        """flatpak_remote 不应使用裸 "flathub" 作为 trigger，避免与 install_app 冲突。"""
        s = registry.get("flatpak_remote")
        assert s is not None
        for t in s.triggers:
            assert t.strip().lower() != "flathub", (
                "flatpak_remote 不应使用裸 'flathub' 作为 trigger（用 '添加flathub' 复合形式）"
            )

    def test_add_source_not_in_apt_repository(self, registry: SkillRegistry) -> None:
        """apt_repository 不应使用裸 '添加源' 作为 trigger，避免与 mirror_source 冲突。"""
        s = registry.get("apt_repository")
        assert s is not None
        for t in s.triggers:
            assert t.strip() != "添加源", (
                "apt_repository 不应使用 '添加源' 作为 trigger（用 '添加仓库'）"
            )

    def test_mirror_source_does_not_match_add_repo(
        self, registry: SkillRegistry
    ) -> None:
        """「添加仓库」类输入应优先匹配 apt_repository，不应被 mirror_source 抢走。"""
        matched = registry.match_by_text("添加仓库 ppa:obsproject/obs-studio")
        assert matched
        names = [s.name for s in matched]
        assert "apt_repository" in names
        assert matched[0].name == "apt_repository"

    def test_add_ppa_does_not_match_apt_repository(
        self, registry: SkillRegistry
    ) -> None:
        """「添加 ppa:xxx」应优先匹配 ppa_management，不应被 apt_repository 抢走。"""
        matched = registry.match_by_text("添加 ppa:git-core/ppa")
        assert matched
        assert matched[0].name == "ppa_management"

    def test_switch_snap_does_not_match_install_snap(
        self, registry: SkillRegistry
    ) -> None:
        """「切换 snap ... 通道」应匹配 snap_channel，不应被 install_snap 抢走。"""
        matched = registry.match_by_text("切换 snap firefox 通道 beta")
        assert matched
        assert matched[0].name == "snap_channel"
        names = [s.name for s in matched]
        assert "install_snap" not in names, "install_snap 不应匹配 '切换 snap' 类输入"
