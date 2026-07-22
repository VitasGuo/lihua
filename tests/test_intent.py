"""意图理解测试。"""

from __future__ import annotations

import pytest

from lihua.config import Config, LLMConfig
from lihua.intent import understand
from lihua.skills import SkillRegistry


@pytest.fixture
def cfg_no_llm() -> Config:
    return Config(llm=LLMConfig(enabled=False))


@pytest.fixture
def registry() -> SkillRegistry:
    reg = SkillRegistry()
    reg.load()
    return reg


class TestRuleIntent:
    """规则模式（不启用 LLM）。"""

    def test_install_qq(self, cfg_no_llm: Config, registry: SkillRegistry) -> None:
        intent = understand("装QQ", cfg_no_llm, registry)
        assert intent.matched
        assert intent.skill_name == "install_app"
        assert intent.params.get("target") == "QQ"
        assert intent.source == "rule"

    def test_install_wechat(self, cfg_no_llm: Config, registry: SkillRegistry) -> None:
        intent = understand("装个微信", cfg_no_llm, registry)
        assert intent.matched
        assert intent.skill_name == "install_app"
        assert intent.params.get("target") == "微信"

    def test_uninstall_firefox(self, cfg_no_llm: Config, registry: SkillRegistry) -> None:
        intent = understand("卸载 firefox", cfg_no_llm, registry)
        assert intent.matched
        assert intent.skill_name == "uninstall_app"

    def test_switch_im(self, cfg_no_llm: Config, registry: SkillRegistry) -> None:
        intent = understand("把输入法换成 fcitx5", cfg_no_llm, registry)
        assert intent.matched
        assert intent.skill_name == "switch_im"
        assert "fcitx5" in intent.params.get("target", "").lower()

    def test_install_font(self, cfg_no_llm: Config, registry: SkillRegistry) -> None:
        intent = understand("装个思源黑体", cfg_no_llm, registry)
        assert intent.matched
        assert intent.skill_name == "install_font"
        assert "思源" in intent.params.get("target", "")

    def test_clean_cache(self, cfg_no_llm: Config, registry: SkillRegistry) -> None:
        intent = understand("清理缓存", cfg_no_llm, registry)
        assert intent.matched
        assert intent.skill_name == "clean_cache"

    def test_unknown_returns_unmatched(self, cfg_no_llm: Config, registry: SkillRegistry) -> None:
        intent = understand("今天天气怎么样", cfg_no_llm, registry)
        assert not intent.matched
        assert intent.source == "none"

    def test_empty_input(self, cfg_no_llm: Config, registry: SkillRegistry) -> None:
        intent = understand("", cfg_no_llm, registry)
        assert not intent.matched


class TestParamEdgeCases:
    def test_chinese_app_name(self, cfg_no_llm: Config, registry: SkillRegistry) -> None:
        intent = understand("装个火狐浏览器", cfg_no_llm, registry)
        assert intent.matched
        assert intent.skill_name == "install_app"
        assert "火狐" in intent.params.get("target", "")

    def test_english_app_name(self, cfg_no_llm: Config, registry: SkillRegistry) -> None:
        intent = understand("安装 vscode", cfg_no_llm, registry)
        assert intent.matched
        assert intent.skill_name == "install_app"
        assert "vscode" in intent.params.get("target", "").lower()

    def test_multi_word_app_name(self, cfg_no_llm: Config, registry: SkillRegistry) -> None:
        intent = understand("装 visual studio code", cfg_no_llm, registry)
        assert intent.matched
        assert intent.skill_name == "install_app"
