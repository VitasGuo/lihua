"""Skill 加载器与执行器测试。"""

from __future__ import annotations

import pytest

from lihua.skills import SkillRegistry, get_registry


@pytest.fixture
def registry() -> SkillRegistry:
    reg = SkillRegistry()
    reg.load()
    return reg


class TestSkillLoading:
    def test_loads_builtin_skills(self, registry: SkillRegistry) -> None:
        skills = registry.all()
        assert len(skills) >= 5, "至少应加载 5 个 MVP skill"
        names = {s.name for s in skills}
        assert "install_app" in names
        assert "uninstall_app" in names
        assert "switch_im" in names
        assert "install_font" in names
        assert "clean_cache" in names

    def test_skill_has_triggers(self, registry: SkillRegistry) -> None:
        s = registry.get("install_app")
        assert s is not None
        assert len(s.triggers) > 0

    def test_skill_has_aliases(self, registry: SkillRegistry) -> None:
        s = registry.get("install_app")
        assert s is not None
        assert "QQ" in s.aliases or "qq" in s.aliases

    def test_skill_has_steps(self, registry: SkillRegistry) -> None:
        s = registry.get("install_app")
        assert s is not None
        assert len(s.steps) > 0


class TestTriggerMatch:
    @pytest.mark.parametrize("text", [
        "装QQ",
        "装个微信",
        "安装 vscode",
        "装个火狐浏览器",
        "安装一个 firefox",
        "装一下 telegram",
    ])
    def test_install_app_matches(self, registry: SkillRegistry, text: str) -> None:
        matched = registry.match_by_text(text)
        assert matched, f"应匹配 install_app：{text}"
        assert matched[0].name == "install_app"

    @pytest.mark.parametrize("text", [
        "卸载 firefox",
        "卸载 QQ",
        "删掉 vscode",
        "移除微信",
    ])
    def test_uninstall_app_matches(self, registry: SkillRegistry, text: str) -> None:
        matched = registry.match_by_text(text)
        assert matched, f"应匹配 uninstall_app：{text}"
        assert matched[0].name == "uninstall_app"

    @pytest.mark.parametrize("text", [
        "把输入法换成 fcitx5",
        "切换到 ibus",
        "用 fcitx5",
    ])
    def test_switch_im_matches(self, registry: SkillRegistry, text: str) -> None:
        matched = registry.match_by_text(text)
        assert matched, f"应匹配 switch_im：{text}"
        assert matched[0].name == "switch_im"

    @pytest.mark.parametrize("text", [
        "清理缓存",
        "清一下垃圾",
        "清理系统",
        "释放空间",
    ])
    def test_clean_cache_matches(self, registry: SkillRegistry, text: str) -> None:
        matched = registry.match_by_text(text)
        assert matched, f"应匹配 clean_cache：{text}"
        assert matched[0].name == "clean_cache"


class TestParamExtraction:
    def test_extract_qq(self, registry: SkillRegistry) -> None:
        s = registry.get("install_app")
        assert s is not None
        params = s.extract_params("装QQ")
        assert params.get("target") == "QQ"

    def test_extract_wechat(self, registry: SkillRegistry) -> None:
        s = registry.get("install_app")
        assert s is not None
        params = s.extract_params("装个微信")
        assert params.get("target") == "微信"

    def test_extract_vscode(self, registry: SkillRegistry) -> None:
        s = registry.get("install_app")
        assert s is not None
        params = s.extract_params("安装 vscode")
        assert "vscode" in params.get("target", "").lower()


class TestAliasResolution:
    def test_qq_resolves_to_flatpak(self, registry: SkillRegistry) -> None:
        s = registry.get("install_app")
        assert s is not None
        candidates = s.resolve_alias("QQ")
        assert "com.qq.QQ" in candidates

    def test_case_insensitive(self, registry: SkillRegistry) -> None:
        s = registry.get("install_app")
        assert s is not None
        assert s.resolve_alias("qq") == s.resolve_alias("QQ")

    def test_no_match_returns_empty(self, registry: SkillRegistry) -> None:
        s = registry.get("install_app")
        assert s is not None
        assert s.resolve_alias("不存在的应用xyz") == []


class TestSkillRunnerHelpers:
    def test_render_template(self) -> None:
        from lihua.skill_runner import render_template
        ctx = {"target": "QQ", "package": "com.qq.QQ"}
        assert render_template("安装 {{target}}", ctx) == "安装 QQ"
        assert render_template("{{package}} ({{package_type}})", ctx) == "com.qq.QQ ({{package_type}})"

    def test_eval_condition_eq(self) -> None:
        from lihua.skill_runner import eval_condition
        ctx = {"package_type": "flatpak"}
        assert eval_condition("{{package_type}} == flatpak", ctx) is True
        assert eval_condition("{{package_type}} == apt", ctx) is False

    def test_eval_condition_in(self) -> None:
        from lihua.skill_runner import eval_condition
        ctx = {"scope": "all"}
        assert eval_condition("{{scope}} in [all, apt]", ctx) is True
        ctx = {"scope": "user"}
        assert eval_condition("{{scope}} in [all, apt]", ctx) is False

    def test_eval_condition_none(self) -> None:
        from lihua.skill_runner import eval_condition
        assert eval_condition(None, {}) is True
        assert eval_condition("", {}) is True

    def test_is_flatpak_id(self) -> None:
        from lihua.skill_runner import _is_flatpak_id
        assert _is_flatpak_id("com.qq.QQ")
        assert _is_flatpak_id("org.mozilla.firefox")
        assert _is_flatpak_id("io.dbeaver.dbeaver")
        assert not _is_flatpak_id("firefox")
        assert not _is_flatpak_id("python3")


class TestNewSkills:
    """新增 Skill 的加载与触发测试。"""

    @pytest.mark.parametrize("skill_name", [
        "system_update", "system_info", "power_management", "service_manager",
        "disk_usage", "cleanup_residual", "user_password", "timezone", "locale",
        "startup_apps", "file_extract", "file_compress", "file_search",
        "file_permission", "file_association", "network_info", "firewall",
        "wifi_connect", "network_test", "proxy_setting", "hardware_info",
        "bluetooth", "printer", "screen_display", "audio_control", "screenshot",
        "night_light", "change_wallpaper", "change_theme", "desktop_icon",
        "install_deb", "install_appimage", "install_snap", "install_dev_tools",
        "cleanup_apt", "open_app", "close_app", "list_apps", "default_apps",
        "process_manager", "kill_process", "cpu_monitor", "memory_monitor",
        "battery",
    ])
    def test_skill_loaded(self, registry: SkillRegistry, skill_name: str) -> None:
        s = registry.get(skill_name)
        assert s is not None, f"Skill {skill_name} 未加载"
        assert len(s.triggers) > 0, f"Skill {skill_name} 没有 triggers"
        assert len(s.steps) > 0, f"Skill {skill_name} 没有 steps"

    @pytest.mark.parametrize("text,expected", [
        # 系统管理类
        ("更新系统", "system_update"),
        ("系统信息", "system_info"),
        ("关机", "power_management"),
        ("重启", "power_management"),
        ("服务状态", "service_manager"),
        ("看磁盘", "disk_usage"),
        ("清理残留", "cleanup_residual"),
        ("深度清理", "cleanup_residual"),
        ("改密码", "user_password"),
        ("设置时区", "timezone"),
        ("改语言", "locale"),
        ("启动项", "startup_apps"),
        # 文件操作类
        ("解压 xxx.tar.gz", "file_extract"),
        ("压缩 xxx", "file_compress"),
        ("找文件", "file_search"),
        ("改权限", "file_permission"),
        ("用什么打开 pdf", "file_association"),
        # 网络类
        ("网络信息", "network_info"),
        ("防火墙", "firewall"),
        ("连接 wifi", "wifi_connect"),
        ("测网", "network_test"),
        ("ping baidu.com", "network_test"),
        ("设置代理", "proxy_setting"),
        # 硬件外设类
        ("看硬件", "hardware_info"),
        ("蓝牙", "bluetooth"),
        ("打印机", "printer"),
        ("屏幕设置", "screen_display"),
        ("音量", "audio_control"),
        # 桌面环境类
        ("截图", "screenshot"),
        ("夜灯", "night_light"),
        ("换壁纸", "change_wallpaper"),
        ("换主题", "change_theme"),
        ("切深色", "change_theme"),
        ("桌面图标", "desktop_icon"),
        # 软件安装增强类
        ("装 deb /tmp/x.deb", "install_deb"),
        ("装 appimage x.AppImage", "install_appimage"),
        ("装 snap vlc", "install_snap"),
        ("装 python 环境", "install_dev_tools"),
        ("清理 apt 缓存", "cleanup_apt"),
        # 应用操作类
        ("打开 firefox", "open_app"),
        ("关闭 firefox", "close_app"),
        ("列出应用", "list_apps"),
        ("默认浏览器 firefox", "default_apps"),
        # 进程与性能类
        ("看进程", "process_manager"),
        ("杀进程 nginx", "kill_process"),
        ("cpu 使用率", "cpu_monitor"),
        ("看内存", "memory_monitor"),
        ("看电量", "battery"),
    ])
    def test_intent_match(self, registry: SkillRegistry, text: str, expected: str) -> None:
        matched = registry.match_by_text(text)
        assert matched, f"未匹配任何 Skill：{text}"
        assert matched[0].name == expected, (
            f"「{text}」应匹配 {expected}，实际匹配 {matched[0].name}"
        )


class TestTriggerWordBoundary:
    """英文 trigger 单词边界匹配测试。"""

    def test_du_not_in_baidu(self, registry: SkillRegistry) -> None:
        """disk_usage 的 trigger 'du' 不应误匹配 'baidu'。"""
        matched = registry.match_by_text("ping baidu.com")
        assert matched, "应匹配 network_test"
        assert matched[0].name == "network_test"
        # disk_usage 不应匹配
        names = [s.name for s in matched]
        assert "disk_usage" not in names, "du 不应误匹配 baidu"

    def test_df_not_in_pdf(self, registry: SkillRegistry) -> None:
        """disk_usage 的 trigger 'df' 不应误匹配 'pdf'。"""
        matched = registry.match_by_text("打开 pdf 文件")
        names = [s.name for s in matched]
        assert "disk_usage" not in names, "df 不应误匹配 pdf"

    def test_ping_word_boundary(self, registry: SkillRegistry) -> None:
        """network_test 的 trigger 'ping' 应匹配独立单词。"""
        s = registry.get("network_test")
        assert s is not None
        assert s.match_trigger("ping baidu.com") is True
        assert s.match_trigger("pinging the server") is False  # pinging 中的 ping 不应匹配


class TestRenderTemplateDefault:
    """render_template 的 default 过滤器测试。"""

    def test_default_used_when_empty(self) -> None:
        from lihua.skill_runner import render_template
        ctx = {"target": ""}
        assert render_template("ping {{target|default:baidu.com}}", ctx) == "ping baidu.com"

    def test_default_used_when_missing(self) -> None:
        from lihua.skill_runner import render_template
        ctx = {}
        assert render_template("ping {{target|default:baidu.com}}", ctx) == "ping baidu.com"

    def test_default_not_used_when_set(self) -> None:
        from lihua.skill_runner import render_template
        ctx = {"target": "google.com"}
        assert render_template("ping {{target|default:baidu.com}}", ctx) == "ping google.com"

    def test_no_default_keeps_placeholder(self) -> None:
        from lihua.skill_runner import render_template
        ctx = {}
        # 没有 default 时，未定义变量保留原占位符
        assert "{{target}}" in render_template("{{target}}", ctx)


class TestEvalConditionCompound:
    """eval_condition 复合条件（&& / ||）测试。"""

    def test_and_both_true(self) -> None:
        from lihua.skill_runner import eval_condition
        ctx = {"ssid": "MyHome", "password": "pass123"}
        assert eval_condition("{{ssid}} !=  && {{password}} != ", ctx) is True

    def test_and_one_false(self) -> None:
        from lihua.skill_runner import eval_condition
        ctx = {"ssid": "MyHome", "password": ""}
        assert eval_condition("{{ssid}} !=  && {{password}} != ", ctx) is False

    def test_and_both_false(self) -> None:
        from lihua.skill_runner import eval_condition
        ctx = {"ssid": "", "password": ""}
        assert eval_condition("{{ssid}} !=  && {{password}} != ", ctx) is False

    def test_or_one_true(self) -> None:
        from lihua.skill_runner import eval_condition
        ctx = {"mode": "ping"}
        assert eval_condition("{{mode}} == ping || {{mode}} == traceroute", ctx) is True

    def test_or_both_false(self) -> None:
        from lihua.skill_runner import eval_condition
        ctx = {"mode": "dns"}
        assert eval_condition("{{mode}} == ping || {{mode}} == traceroute", ctx) is False

    def test_mixed_and_or(self) -> None:
        from lihua.skill_runner import eval_condition
        # (a == 1 && b == 2) || (c == 3)
        ctx = {"a": "1", "b": "2", "c": "0"}
        assert eval_condition("{{a}} == 1 && {{b}} == 2 || {{c}} == 3", ctx) is True
        ctx = {"a": "0", "b": "2", "c": "3"}
        assert eval_condition("{{a}} == 1 && {{b}} == 2 || {{c}} == 3", ctx) is True
        ctx = {"a": "0", "b": "2", "c": "0"}
        assert eval_condition("{{a}} == 1 && {{b}} == 2 || {{c}} == 3", ctx) is False

    def test_three_or(self) -> None:
        from lihua.skill_runner import eval_condition
        ctx = {"mode": "速"}
        assert eval_condition(
            "{{mode}} ==  || {{mode}} == ping || {{mode}} == 速 || {{mode}} == 延迟",
            ctx,
        ) is True


class TestSkillPriority:
    """Skill 匹配优先级测试。"""

    def test_install_deb_over_install_app(self, registry: SkillRegistry) -> None:
        """装 deb 应优先匹配 install_deb 而不是 install_app。"""
        matched = registry.match_by_text("装 deb /tmp/x.deb")
        assert matched[0].name == "install_deb"

    def test_cleanup_apt_over_residual(self, registry: SkillRegistry) -> None:
        """清理 apt 缓存应优先匹配 cleanup_apt。"""
        matched = registry.match_by_text("清理 apt 缓存")
        assert matched[0].name == "cleanup_apt"

    def test_default_apps_over_file_assoc(self, registry: SkillRegistry) -> None:
        """默认浏览器应优先匹配 default_apps。"""
        matched = registry.match_by_text("默认浏览器 firefox")
        assert matched[0].name == "default_apps"
