"""beautify_ubuntu Skill 测试。

覆盖：
- Skill 加载
- trigger 匹配（macOS / elementary / performance / restore 四种模式）
- 步骤结构（条件渲染正确）
- condition 表达式
- 参数提取
- trigger 冲突防护（"美化桌面" 4 字符 vs desktop_icon 的 "桌面" 2 字符）
- v0.7.5 新增：performance 模式（字体渲染 / 动画 / GPU 检测 / 性能优化）
"""

from __future__ import annotations

import pytest

from lihua.skills import SkillRegistry


@pytest.fixture
def registry() -> SkillRegistry:
    reg = SkillRegistry()
    reg.load()
    return reg


class TestBeautifyUbuntuSkill:
    """Skill 基础加载验证。"""

    def test_skill_loaded(self, registry: SkillRegistry) -> None:
        s = registry.get("beautify_ubuntu")
        assert s is not None, "beautify_ubuntu 应加载"
        assert len(s.triggers) > 0, "beautify_ubuntu 没有 triggers"
        assert len(s.steps) > 0, "beautify_ubuntu 没有 steps"
        assert s.description, "beautify_ubuntu 没有 description"

    def test_skill_has_four_targets(self, registry: SkillRegistry) -> None:
        """应支持 macos / elementary / performance / restore 四种模式。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        target_param = next((p for p in s.parameters if p.name == "target"), None)
        assert target_param is not None, "应有 target 参数"
        assert target_param.default == "macos", "默认 target 应为 macos"
        # extract 正则应覆盖 performance
        assert "performance" in target_param.extract, "extract 应含 performance"

    def test_parameters_extract(self, registry: SkillRegistry) -> None:
        """参数提取应正确识别 macos / elementary / performance / restore。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None

        cases = [
            ("美化ubuntu", "macos"),  # 默认值
            ("让ubuntu像macos", "macos"),
            ("装elementary风格", "elementary"),
            ("恢复默认主题", "恢复"),
            ("还原ubuntu默认", "还原"),
            ("优化系统性能", "优化"),
            ("开启GPU加速", "GPU"),  # 正则 IGNORECASE，返回原文大写
            ("字体太模糊了", "字体"),
            ("动画卡顿", "动画"),
        ]
        for text, expected_target in cases:
            params = s.extract_params(text)
            if expected_target == "macos" and "macos" not in text and "mac" not in text.lower():
                # 仅触发词、未显式提取 target → 使用 default
                assert params.get("target", "macos") == "macos", (
                    f"「{text}」target 应默认为 macos，实际 {params.get('target')}"
                )
            else:
                assert params.get("target") == expected_target, (
                    f"「{text}」应提取 target={expected_target}，实际 {params.get('target')}"
                )


class TestBeautifyUbuntuTriggerMatch:
    """trigger 匹配测试。"""

    @pytest.mark.parametrize("text", [
        # 美化类
        "美化ubuntu",
        "美化桌面",
        "美化系统",
        "macos风格",
        "mac风格",
        "mac os风格",
        "macOS风格",
        "elementary风格",
        "让ubuntu好看",
        "桌面太丑",
        "桌面丑",
        "ubuntu太丑",
        "主题美化",
        "提升精致度",
        # v0.7.5 性能优化类
        "优化ubuntu",
        "优化系统",
        "提升性能",
        "系统优化",
        "gpu加速",
        "GPU加速",
        "字体模糊",
        "字体渲染",
        "动画卡顿",
        "装修系统",
        "装修ubuntu",
    ])
    def test_trigger_match(self, registry: SkillRegistry, text: str) -> None:
        s = registry.get("beautify_ubuntu")
        assert s is not None
        assert s.match_trigger(text), f"「{text}」应匹配 beautify_ubuntu 的 trigger"

    @pytest.mark.parametrize("text,expected", [
        ("美化ubuntu", "beautify_ubuntu"),
        ("美化桌面", "beautify_ubuntu"),
        ("macos风格", "beautify_ubuntu"),
        ("装elementary风格", "beautify_ubuntu"),
        ("桌面太丑了", "beautify_ubuntu"),
        ("主题美化", "beautify_ubuntu"),
        ("提升桌面精致度", "beautify_ubuntu"),
        # v0.7.5 性能模式
        ("优化系统性能", "beautify_ubuntu"),
        ("开启GPU加速", "beautify_ubuntu"),
        ("字体太模糊了", "beautify_ubuntu"),
        ("动画卡顿", "beautify_ubuntu"),
        ("装修系统", "beautify_ubuntu"),
    ])
    def test_intent_match(self, registry: SkillRegistry, text: str, expected: str) -> None:
        matched = registry.match_by_text(text)
        assert matched, f"应匹配：{text}"
        assert matched[0].name == expected, (
            f"「{text}」应匹配 {expected}，实际匹配 {matched[0].name}"
        )


class TestBeautifyUbuntuTriggerConflict:
    """trigger 冲突防护。

    beautify_ubuntu 有 "美化桌面"(4) / "桌面太丑"(4) / "桌面丑"(3) / "装修系统"(4) / "装修ubuntu"(5)
    desktop_icon 有 "桌面"(2) / "显示桌面"(4) / "隐藏桌面"(4)

    依赖"最长 trigger 优先"策略消歧。
    """

    def test_meihuazhuomian_prefers_beautify(self, registry: SkillRegistry) -> None:
        """「美化桌面」应优先匹配 beautify_ubuntu（4字符 > desktop_icon 的「桌面」2字符）。"""
        matched = registry.match_by_text("美化桌面")
        assert matched, "应匹配"
        assert matched[0].name == "beautify_ubuntu", (
            f"「美化桌面」应优先匹配 beautify_ubuntu，实际 {matched[0].name}"
        )

    def test_zhuomiantaichou_prefers_beautify(self, registry: SkillRegistry) -> None:
        """「桌面太丑」应优先匹配 beautify_ubuntu。"""
        matched = registry.match_by_text("桌面太丑了")
        assert matched, "应匹配"
        assert matched[0].name == "beautify_ubuntu", (
            f"「桌面太丑了」应优先匹配 beautify_ubuntu，实际 {matched[0].name}"
        )

    def test_xianshizhuomian_prefers_desktop_icon(self, registry: SkillRegistry) -> None:
        """「显示桌面」应优先匹配 desktop_icon（精确 trigger 命中）。"""
        matched = registry.match_by_text("显示桌面")
        assert matched, "应匹配"
        assert matched[0].name == "desktop_icon", (
            f"「显示桌面」应优先匹配 desktop_icon，实际 {matched[0].name}"
        )

    def test_bare_zhuomian_prefers_desktop_icon(self, registry: SkillRegistry) -> None:
        """裸「桌面」应匹配 desktop_icon（短 trigger 命中，beautify_ubuntu 无此 trigger）。"""
        matched = registry.match_by_text("桌面")
        assert matched, "应匹配"
        assert matched[0].name == "desktop_icon", (
            f"「桌面」应匹配 desktop_icon，实际 {matched[0].name}"
        )


class TestBeautifyUbuntuStepStructure:
    """步骤结构验证。"""

    def test_has_macos_steps(self, registry: SkillRegistry) -> None:
        """macOS 风格应有 WhiteSur 主题安装 + 应用 + GNOME 扩展配置步骤。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        step_names = {st.name for st in s.steps}
        expected = {
            "install_deps",
            "install_whitesur_gtk",
            "install_whitesur_icons",
            "install_whitesur_cursor",
            "apply_whitesur_theme",
            "install_gnome_extensions",
            "config_dash_to_dock",
            "config_blur_my_shell",
        }
        missing = expected - step_names
        assert not missing, f"缺少 macOS 风格步骤：{missing}"

    def test_has_macos_font_steps(self, registry: SkillRegistry) -> None:
        """v0.7.11: macOS 风格应有字体安装 + 应用 + 渲染配置步骤。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        step_names = {st.name for st in s.steps}
        expected = {
            "install_source_han_fonts",
            "install_jetbrains_mono",
            "install_fira_code",
            "apply_fonts_to_gnome",
            "config_font_rendering_extreme",
        }
        missing = expected - step_names
        assert not missing, f"缺少字体安装步骤：{missing}"

    def test_has_macos_gdm_steps(self, registry: SkillRegistry) -> None:
        """v0.7.11: macOS 风格应有 GDM 登录界面美化步骤。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        step_names = {st.name for st in s.steps}
        expected = {
            "install_gdm_settings",
            "backup_gdm_resources",
            "apply_gdm_whitesur",
            "set_gdm_wallpaper",
        }
        missing = expected - step_names
        assert not missing, f"缺少 GDM 登录界面美化步骤：{missing}"

    def test_has_macos_grub_steps(self, registry: SkillRegistry) -> None:
        """v0.7.11: macOS 风格应有 GRUB 美化步骤。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        step_names = {st.name for st in s.steps}
        expected = {
            "install_whitesur_grub_theme",
            "config_grub_resolution",
            "config_grub_timeout",
            "update_grub_config",
        }
        missing = expected - step_names
        assert not missing, f"缺少 GRUB 美化步骤：{missing}"

    def test_has_macos_wallpaper_steps(self, registry: SkillRegistry) -> None:
        """v0.7.11: macOS 风格应有壁纸下载 + 应用步骤。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        step_names = {st.name for st in s.steps}
        expected = {"download_macos_wallpaper", "set_wallpaper"}
        missing = expected - step_names
        assert not missing, f"缺少壁纸步骤：{missing}"

    def test_has_macos_window_buttons_step(self, registry: SkillRegistry) -> None:
        """v0.7.11: macOS 风格应有窗口按钮位置配置步骤。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        step_names = {st.name for st in s.steps}
        assert "config_window_buttons_macos" in step_names, "缺少 config_window_buttons_macos 步骤"

    def test_has_elementary_steps(self, registry: SkillRegistry) -> None:
        """Elementary 风格应有 Plank + elementary 图标步骤。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        step_names = {st.name for st in s.steps}
        expected = {"install_plank", "install_elementary_icons", "apply_elementary_theme"}
        missing = expected - step_names
        assert not missing, f"缺少 Elementary 风格步骤：{missing}"

    def test_has_performance_steps(self, registry: SkillRegistry) -> None:
        """v0.7.5: performance 模式应有 GPU 检测 + 字体渲染 + 动画 + 性能优化步骤。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        step_names = {st.name for st in s.steps}
        expected = {
            "detect_gpu_info",
            "enable_font_smoothing",
            "enable_gnome_animations",
            "install_mesa_tools",
            "config_gnome_perf",
            "cleanup_unnecessary_startup",
        }
        missing = expected - step_names
        assert not missing, f"缺少 performance 模式步骤：{missing}"

    def test_has_restore_step(self, registry: SkillRegistry) -> None:
        """应有恢复默认主题步骤。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        step_names = {st.name for st in s.steps}
        assert "restore_default" in step_names, "缺少 restore_default 步骤"

    def test_has_final_hint_and_notify(self, registry: SkillRegistry) -> None:
        """应有最终提示和通知步骤（v0.7.5: 拆分为 beauty / perf 两套）。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        step_names = {st.name for st in s.steps}
        assert "final_hint" in step_names, "缺少 final_hint 步骤"
        assert "final_hint_perf" in step_names, "缺少 final_hint_perf 步骤"
        assert "notify_beauty" in step_names, "缺少 notify_beauty 步骤"
        assert "notify_perf" in step_names, "缺少 notify_perf 步骤"

    def test_grey_safety_for_modify_steps(self, registry: SkillRegistry) -> None:
        """修改系统的 command 步骤应标记 safety: grey（强制走灰名单确认）。

        v0.7.5 例外：detect_gpu_info 和 cleanup_unnecessary_startup 是只读操作，safety: white。
        """
        s = registry.get("beautify_ubuntu")
        assert s is not None
        readonly_steps = {"detect_gpu_info", "cleanup_unnecessary_startup"}
        for step in s.steps:
            if step.type == "command":
                if step.name in readonly_steps:
                    assert step.safety == "white", (
                        f"只读步骤 {step.name} 应为 white，实际 {step.safety}"
                    )
                else:
                    assert step.safety == "grey", (
                        f"修改步骤 {step.name} 应为 grey，实际 {step.safety}"
                    )

    def test_all_steps_have_confirm(self, registry: SkillRegistry) -> None:
        """所有 command 步骤应有 confirm 文案（不展示原始命令）。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        for step in s.steps:
            if step.type == "command":
                assert step.confirm, f"步骤 {step.name} 缺少 confirm 文案"


class TestBeautifyUbuntuConditions:
    """condition 表达式验证。"""

    def test_macos_steps_have_target_macos_condition(self, registry: SkillRegistry) -> None:
        """macOS 风格步骤的 condition 应含 {{target}} == macos。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        macos_steps = [
            "install_whitesur_gtk",
            "install_whitesur_icons",
            "install_whitesur_cursor",
            "apply_whitesur_theme",
            "install_gnome_extensions",
            "config_dash_to_dock",
            "config_blur_my_shell",
        ]
        steps_by_name = {st.name: st for st in s.steps}
        for name in macos_steps:
            step = steps_by_name.get(name)
            assert step is not None, f"缺少步骤 {name}"
            assert step.condition, f"步骤 {name} 缺少 condition"
            assert "{{target}} == macos" in step.condition, (
                f"步骤 {name} 的 condition 应含 {{target}} == macos，实际：{step.condition}"
            )

    def test_elementary_steps_have_target_elementary_condition(
        self, registry: SkillRegistry
    ) -> None:
        """Elementary 风格步骤的 condition 应含 {{target}} == elementary。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        elementary_steps = [
            "install_plank",
            "install_elementary_icons",
            "apply_elementary_theme",
        ]
        steps_by_name = {st.name: st for st in s.steps}
        for name in elementary_steps:
            step = steps_by_name.get(name)
            assert step is not None, f"缺少步骤 {name}"
            assert step.condition, f"步骤 {name} 缺少 condition"
            assert "{{target}} == elementary" in step.condition, (
                f"步骤 {name} 的 condition 应含 {{target}} == elementary，实际：{step.condition}"
            )

    def test_performance_steps_have_target_performance_condition(
        self, registry: SkillRegistry
    ) -> None:
        """v0.7.5: performance 模式步骤的 condition 应使用 in 操作符包含 performance。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        perf_steps = [
            "detect_gpu_info",
            "enable_font_smoothing",
            "enable_gnome_animations",
            "install_mesa_tools",
            "config_gnome_perf",
            "cleanup_unnecessary_startup",
            "final_hint_perf",
            "notify_perf",
        ]
        steps_by_name = {st.name: st for st in s.steps}
        for name in perf_steps:
            step = steps_by_name.get(name)
            assert step is not None, f"缺少步骤 {name}"
            assert step.condition, f"步骤 {name} 缺少 condition"
            # v0.7.5: 使用 in 操作符支持多关键词（performance / 性能 / 优化 / gpu / GPU / 字体 / 动画）
            assert "{{target}} in [" in step.condition, (
                f"步骤 {name} 的 condition 应使用 in 操作符，实际：{step.condition}"
            )
            assert "performance" in step.condition, (
                f"步骤 {name} 的 condition 应含 performance，实际：{step.condition}"
            )

    def test_restore_step_has_restore_condition(self, registry: SkillRegistry) -> None:
        """恢复默认步骤的 condition 应支持「恢复」「还原」「默认」三种说法。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        restore_step = next((st for st in s.steps if st.name == "restore_default"), None)
        assert restore_step is not None, "缺少 restore_default 步骤"
        assert restore_step.condition, "restore_default 缺少 condition"
        # condition 形如 "{{target}} == 恢复 || {{target}} == 还原 || {{target}} == 默认"
        for keyword in ["恢复", "还原", "默认"]:
            expected = "{{target}} == " + keyword
            assert expected in restore_step.condition, (
                f"restore_default 的 condition 应支持 {keyword}，实际：{restore_step.condition}"
            )

    def test_install_deps_condition_supports_both_styles(
        self, registry: SkillRegistry
    ) -> None:
        """install_deps 应同时支持 macos 和 elementary（用 || 连接）。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        deps_step = next((st for st in s.steps if st.name == "install_deps"), None)
        assert deps_step is not None, "缺少 install_deps 步骤"
        assert deps_step.condition, "install_deps 缺少 condition"
        assert "{{target}} == macos" in deps_step.condition
        assert "{{target}} == elementary" in deps_step.condition
        assert "||" in deps_step.condition, "install_deps 的 condition 应使用 || 连接两种风格"


class TestBeautifyUbuntuCommands:
    """命令内容验证（确保关键命令存在 + 不直接展示给用户）。"""

    def test_whitesur_gtk_uses_git_clone(self, registry: SkillRegistry) -> None:
        """macOS GTK 主题应通过 git clone 安装 WhiteSur-gtk-theme。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        gtk_step = next((st for st in s.steps if st.name == "install_whitesur_gtk"), None)
        assert gtk_step is not None
        assert "git clone" in gtk_step.command
        assert "WhiteSur-gtk-theme" in gtk_step.command

    def test_apply_theme_uses_gsettings(self, registry: SkillRegistry) -> None:
        """应用主题应使用 gsettings set，不直接展示给用户。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        apply_step = next((st for st in s.steps if st.name == "apply_whitesur_theme"), None)
        assert apply_step is not None
        assert "gsettings set" in apply_step.command
        assert "WhiteSur-Dark" in apply_step.command
        # confirm 文案应是人类语言，不是原始命令
        assert "gsettings" not in apply_step.confirm, "confirm 不应展示原始命令"

    def test_restore_uses_yaru(self, registry: SkillRegistry) -> None:
        """恢复默认应使用 Yaru 主题。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        restore_step = next(
            (st for st in s.steps if st.name == "restore_default"), None
        )
        assert restore_step is not None
        assert "Yaru" in restore_step.command

    def test_plank_install_for_elementary(self, registry: SkillRegistry) -> None:
        """Elementary 风格应安装 Plank dock。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        plank_step = next((st for st in s.steps if st.name == "install_plank"), None)
        assert plank_step is not None
        assert "plank" in plank_step.command.lower()

    def test_performance_font_smoothing(self, registry: SkillRegistry) -> None:
        """v0.7.5: performance 模式应开启 rgba 次像素抗锯齿。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        font_step = next(
            (st for st in s.steps if st.name == "enable_font_smoothing"), None
        )
        assert font_step is not None
        assert "font-antialiasing" in font_step.command
        assert "rgba" in font_step.command
        assert "font-hinting" in font_step.command

    def test_performance_gpu_detect(self, registry: SkillRegistry) -> None:
        """v0.7.5: performance 模式应检测 GPU 硬件 + 驱动。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        gpu_step = next((st for st in s.steps if st.name == "detect_gpu_info"), None)
        assert gpu_step is not None
        assert "lspci" in gpu_step.command
        assert "XDG_SESSION_TYPE" in gpu_step.command

    def test_performance_animations(self, registry: SkillRegistry) -> None:
        """v0.7.5: performance 模式应开启 GNOME 动画。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        anim_step = next(
            (st for st in s.steps if st.name == "enable_gnome_animations"), None
        )
        assert anim_step is not None
        assert "enable-animations" in anim_step.command
        assert "true" in anim_step.command


class TestBeautifyUbuntuV0711Commands:
    """v0.7.11 新增 step 的命令内容验证。"""

    def test_source_han_fonts_downloads_from_adobe(self, registry: SkillRegistry) -> None:
        """思源黑体应从 Adobe GitHub release 下载 OTF 全字重。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        step = next((st for st in s.steps if st.name == "install_source_han_fonts"), None)
        assert step is not None
        assert "github.com/adobe-fonts" in step.command
        assert "source-han-sans" in step.command
        assert "source-han-serif" in step.command
        assert "fc-cache" in step.command, "应刷新字体缓存"

    def test_jetbrains_mono_downloads_from_jetbrains(self, registry: SkillRegistry) -> None:
        """JetBrains Mono 应从 JetBrains 官方下载。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        step = next((st for st in s.steps if st.name == "install_jetbrains_mono"), None)
        assert step is not None
        assert "download.jetbrains.com" in step.command
        assert "fc-cache" in step.command

    def test_apply_fonts_uses_source_han(self, registry: SkillRegistry) -> None:
        """应用字体应使用思源黑体作为界面字体。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        step = next((st for st in s.steps if st.name == "apply_fonts_to_gnome"), None)
        assert step is not None
        assert "Source Han Sans SC" in step.command
        assert "Source Han Serif SC" in step.command
        assert "JetBrains Mono" in step.command
        assert "gsettings set" in step.command

    def test_font_rendering_extreme_uses_fontconfig(self, registry: SkillRegistry) -> None:
        """极致字体渲染应生成 fontconfig 配置文件。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        step = next((st for st in s.steps if st.name == "config_font_rendering_extreme"), None)
        assert step is not None
        assert "fontconfig" in step.command
        assert "fonts.conf" in step.command
        assert "rgba" in step.command or "rgb" in step.command
        assert "hintslight" in step.command
        assert "lcdfilter" in step.command
        assert "Source Han Sans SC" in step.command  # 默认字体映射

    def test_window_buttons_macos_left_layout(self, registry: SkillRegistry) -> None:
        """窗口按钮应配置为 macOS 风格（左上 close,minimize,maximize）。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        step = next((st for st in s.steps if st.name == "config_window_buttons_macos"), None)
        assert step is not None
        assert "button-layout" in step.command
        assert "close,minimize,maximize" in step.command
        # close 应在左侧（macOS 风格）
        assert "close,minimize,maximize:appmenu" in step.command

    def test_download_wallpaper_uses_wget(self, registry: SkillRegistry) -> None:
        """壁纸下载应使用 wget 到 ~/Pictures/Wallpapers/。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        step = next((st for st in s.steps if st.name == "download_macos_wallpaper"), None)
        assert step is not None
        assert "wget" in step.command
        assert "~/Pictures/Wallpapers" in step.command or "$HOME/Pictures/Wallpapers" in step.command

    def test_set_wallpaper_uses_gsettings(self, registry: SkillRegistry) -> None:
        """壁纸应用应使用 gsettings set picture-uri。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        step = next((st for st in s.steps if st.name == "set_wallpaper"), None)
        assert step is not None
        assert "gsettings set" in step.command
        assert "picture-uri" in step.command
        # 桌面 + 锁屏都应设置
        assert "background" in step.command
        assert "screensaver" in step.command

    def test_gdm_backup_uses_timestamp(self, registry: SkillRegistry) -> None:
        """GDM 备份应使用时间戳避免覆盖。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        step = next((st for st in s.steps if st.name == "backup_gdm_resources"), None)
        assert step is not None
        assert "TIMESTAMP" in step.command or "date +" in step.command
        assert "gnome-shell-theme.gresource" in step.command
        assert "backups" in step.command

    def test_gdm_apply_uses_whitesur_gdm_sh(self, registry: SkillRegistry) -> None:
        """GDM 主题应用应使用 WhiteSur-gtk-theme 的 gdm.sh 脚本。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        step = next((st for st in s.steps if st.name == "apply_gdm_whitesur"), None)
        assert step is not None
        assert "gdm.sh" in step.command
        assert "WhiteSur-gtk-theme" in step.command
        # v0.7.13：sudo → pkexec
        assert "pkexec" in step.command

    def test_grub_theme_uses_whitesur(self, registry: SkillRegistry) -> None:
        """GRUB 主题应安装 WhiteSur-grub-theme。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        step = next((st for st in s.steps if st.name == "install_whitesur_grub_theme"), None)
        assert step is not None
        assert "WhiteSur-grub-theme" in step.command
        assert "git clone" in step.command
        assert "install.sh" in step.command

    def test_grub_resolution_auto_detects(self, registry: SkillRegistry) -> None:
        """GRUB 分辨率应自动检测屏幕分辨率。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        step = next((st for st in s.steps if st.name == "config_grub_resolution"), None)
        assert step is not None
        assert "xrandr" in step.command
        assert "GRUB_GFXMODE" in step.command
        assert "GRUB_GFXPAYLOAD_LINUX" in step.command

    def test_grub_timeout_sets_3_seconds(self, registry: SkillRegistry) -> None:
        """GRUB 超时应配置为 3 秒。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        step = next((st for st in s.steps if st.name == "config_grub_timeout"), None)
        assert step is not None
        assert "GRUB_TIMEOUT=3" in step.command

    def test_update_grub_runs_update_grub(self, registry: SkillRegistry) -> None:
        """update_grub_config 应运行 pkexec update-grub（v0.7.13: sudo→pkexec）。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        step = next((st for st in s.steps if st.name == "update_grub_config"), None)
        assert step is not None
        assert "update-grub" in step.command
        # v0.7.13：sudo → pkexec
        assert "pkexec" in step.command

    def test_restore_default_resets_window_buttons(self, registry: SkillRegistry) -> None:
        """v0.7.11: 恢复默认应重置窗口按钮位置到右上。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        step = next((st for st in s.steps if st.name == "restore_default"), None)
        assert step is not None
        # Ubuntu 默认：appmenu:minimize,maximize,close（右上）
        assert "appmenu:minimize,maximize,close" in step.command
        # 应删除自定义 fontconfig
        assert "fonts.conf" in step.command
        assert "fc-cache" in step.command


class TestBeautifyUbuntuV0711Conditions:
    """v0.7.11 新增 step 的 condition 验证。"""

    def test_new_macos_steps_have_target_macos_condition(
        self, registry: SkillRegistry
    ) -> None:
        """v0.7.11 新增的 macos step 的 condition 应含 {{target}} == macos。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        new_macos_steps = [
            "install_source_han_fonts",
            "install_jetbrains_mono",
            "install_fira_code",
            "apply_fonts_to_gnome",
            "config_font_rendering_extreme",
            "config_window_buttons_macos",
            "download_macos_wallpaper",
            "set_wallpaper",
            "install_gdm_settings",
            "backup_gdm_resources",
            "apply_gdm_whitesur",
            "set_gdm_wallpaper",
            "install_whitesur_grub_theme",
            "config_grub_resolution",
            "config_grub_timeout",
            "update_grub_config",
        ]
        steps_by_name = {st.name: st for st in s.steps}
        for name in new_macos_steps:
            step = steps_by_name.get(name)
            assert step is not None, f"缺少步骤 {name}"
            assert step.condition, f"步骤 {name} 缺少 condition"
            assert "{{target}} == macos" in step.condition, (
                f"步骤 {name} 的 condition 应含 {{target}} == macos，实际：{step.condition}"
            )

    def test_new_steps_are_grey_safety(self, registry: SkillRegistry) -> None:
        """v0.7.11 新增的修改系统 step 应标记 safety: grey。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        new_modify_steps = [
            "install_source_han_fonts",
            "install_jetbrains_mono",
            "install_fira_code",
            "apply_fonts_to_gnome",
            "config_font_rendering_extreme",
            "config_window_buttons_macos",
            "download_macos_wallpaper",
            "set_wallpaper",
            "install_gdm_settings",
            "backup_gdm_resources",  # 虽然是备份，但是 sudo 操作，标 grey
            "apply_gdm_whitesur",
            "set_gdm_wallpaper",
            "install_whitesur_grub_theme",
            "config_grub_resolution",
            "config_grub_timeout",
            "update_grub_config",
        ]
        steps_by_name = {st.name: st for st in s.steps}
        for name in new_modify_steps:
            step = steps_by_name.get(name)
            assert step is not None, f"缺少步骤 {name}"
            assert step.safety == "grey", (
                f"修改步骤 {name} 应为 grey，实际 {step.safety}"
            )

    def test_new_steps_have_confirm_message(self, registry: SkillRegistry) -> None:
        """v0.7.11 新增的 command step 应有 confirm 文案（人类语言，非原始命令）。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        new_steps = [
            "install_source_han_fonts",
            "install_jetbrains_mono",
            "install_fira_code",
            "apply_fonts_to_gnome",
            "config_font_rendering_extreme",
            "config_window_buttons_macos",
            "download_macos_wallpaper",
            "set_wallpaper",
            "install_gdm_settings",
            "backup_gdm_resources",
            "apply_gdm_whitesur",
            "set_gdm_wallpaper",
            "install_whitesur_grub_theme",
            "config_grub_resolution",
            "config_grub_timeout",
            "update_grub_config",
        ]
        steps_by_name = {st.name: st for st in s.steps}
        for name in new_steps:
            step = steps_by_name.get(name)
            assert step is not None, f"缺少步骤 {name}"
            assert step.confirm, f"步骤 {name} 缺少 confirm 文案"
            # confirm 不应展示原始命令
            assert "gsettings" not in step.confirm, (
                f"步骤 {name} 的 confirm 不应展示 gsettings 原始命令"
            )
            assert "sudo" not in step.confirm, (
                f"步骤 {name} 的 confirm 不应展示 sudo 原始命令"
            )


class TestBeautifyUbuntuV0711TriggerMatch:
    """v0.7.11 新增 trigger 匹配测试。"""

    @pytest.mark.parametrize("text", [
        "美化登录界面",
        "美化开机界面",
        "grub美化",
        "GRUB美化",
    ])
    def test_new_trigger_match(self, registry: SkillRegistry, text: str) -> None:
        """v0.7.11 新增的 trigger 应匹配 beautify_ubuntu。"""
        s = registry.get("beautify_ubuntu")
        assert s is not None
        assert s.match_trigger(text), f"「{text}」应匹配 beautify_ubuntu 的 trigger"

    @pytest.mark.parametrize("text", [
        "美化登录界面",
        "美化开机界面",
        "grub美化",
        "GRUB美化",
    ])
    def test_new_trigger_extract_target_macos(
        self, registry: SkillRegistry, text: str
    ) -> None:
        """v0.7.11: 登录界面/开机界面/grub 美化都走 macos 全套流程（不拆分 target）。

        设计理由：GDM 主题依赖 WhiteSur GTK 主题，GRUB 主题独立但属于 macOS 风格整体。
        让「美化登录界面」/「GRUB美化」走 target=macos，执行全套 macOS 美化，
        避免局部执行导致依赖缺失。
        """
        s = registry.get("beautify_ubuntu")
        assert s is not None
        params = s.extract_params(text)
        assert params.get("target") == "macos", (
            f"「{text}」应提取 target=macos（走全套 macOS 流程），实际 {params.get('target')}"
        )
