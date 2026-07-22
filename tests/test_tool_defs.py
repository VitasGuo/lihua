"""tool_defs.py 单元测试：Skill YAML → OpenAI function calling 工具定义。"""

from __future__ import annotations

import pytest

from lihua.skills import SkillDef, SkillParam, SkillRegistry, get_registry
from lihua.tool_defs import (
    build_run_shell_tool,
    build_skill_catalog_for_prompt,
    build_tool_defs,
    build_tool_index,
    skill_to_tool,
)


@pytest.fixture
def registry() -> SkillRegistry:
    reg = get_registry()
    reg.reload()
    return reg


class TestSkillToTool:
    """单个 Skill → tool 转换。"""

    def test_basic_structure(self) -> None:
        skill = SkillDef(
            name="install_app",
            description="安装应用程序",
            triggers=["装", "安装", "装个"],
            examples=["装QQ", "装个微信"],
            parameters=[
                SkillParam(name="target", type="string", required=True, description="应用名"),
                SkillParam(name="prefer", type="string", required=False, description="偏好"),
            ],
        )
        tool = skill_to_tool(skill)
        assert tool["type"] == "function"
        assert tool["function"]["name"] == "install_app"
        assert "安装应用程序" in tool["function"]["description"]
        assert "装" in tool["function"]["description"]
        assert "装QQ" in tool["function"]["description"]

    def test_parameters_schema(self) -> None:
        skill = SkillDef(
            name="install_app",
            description="安装",
            parameters=[
                SkillParam(name="target", type="string", required=True, description="应用名"),
            ],
        )
        tool = skill_to_tool(skill)
        params = tool["function"]["parameters"]
        assert params["type"] == "object"
        assert "target" in params["properties"]
        assert params["properties"]["target"]["type"] == "string"
        assert params["required"] == ["target"]

    def test_no_parameters(self) -> None:
        """无参数的 skill 也要给空 properties。"""
        skill = SkillDef(name="cleanup", description="清理", parameters=[])
        tool = skill_to_tool(skill)
        assert tool["function"]["parameters"]["properties"] == {}

    def test_default_value(self) -> None:
        skill = SkillDef(
            name="test",
            description="test",
            parameters=[
                SkillParam(name="level", type="integer", required=False, default=50),
            ],
        )
        tool = skill_to_tool(skill)
        assert tool["function"]["parameters"]["properties"]["level"]["default"] == 50

    def test_description_falls_back_to_name(self) -> None:
        """没有 description / triggers / examples 时，description 退化为 [类别] name。"""
        skill = SkillDef(name="bare_skill")
        tool = skill_to_tool(skill)
        assert tool["function"]["description"] == "[其他] bare_skill"

    def test_description_has_category_prefix(self) -> None:
        """v0.7.12：description 应含 [类别] 前缀。"""
        skill = SkillDef(
            name="test_skill",
            description="测试用",
            category="system",
        )
        tool = skill_to_tool(skill)
        assert tool["function"]["description"].startswith("[系统管理] "), (
            f"应含 [系统管理] 前缀，实际：{tool['function']['description']}"
        )


class TestBuildToolDefs:
    """整个 registry → tool 列表。"""

    def test_returns_all_skills_plus_builtin_tools(self, registry: SkillRegistry) -> None:
        """build_tool_defs 在 skill 列表前加 17 个内置工具（5 核心 + 12 元能力）。"""
        tools = build_tool_defs(registry)
        # 17 个内置工具 + 所有 skill
        assert len(tools) == len(registry.all()) + 17

    def test_builtin_tools_at_head(self, registry: SkillRegistry) -> None:
        """v0.8.3：run_shell / read_file / write_file / edit_file / run_python 放在 tools 列表前 5 个。"""
        tools = build_tool_defs(registry)
        names = [t["function"]["name"] for t in tools[:5]]
        assert names == ["run_shell", "read_file", "write_file", "edit_file", "run_python"]

    def test_skill_tools_sorted_after_builtin(self, registry: SkillRegistry) -> None:
        """v0.8.18：除 17 个内置工具外，其余 skill 仍按字母序排序。"""
        tools = build_tool_defs(registry)
        skill_names = [t["function"]["name"] for t in tools[17:]]
        assert skill_names == sorted(skill_names)

    def test_all_tools_well_formed(self, registry: SkillRegistry) -> None:
        tools = build_tool_defs(registry)
        for t in tools:
            assert t["type"] == "function"
            assert "name" in t["function"]
            assert "description" in t["function"]
            assert "parameters" in t["function"]
            assert t["function"]["parameters"]["type"] == "object"
            assert "properties" in t["function"]["parameters"]

    def test_install_app_tool_exists(self, registry: SkillRegistry) -> None:
        tools = build_tool_defs(registry)
        names = [t["function"]["name"] for t in tools]
        assert "install_app" in names

    def test_skills_all_converted(self, registry: SkillRegistry) -> None:
        """v0.7.12 合并 troubleshoot-* 8→1 后应有 83 个 skill，全部能转成 tool。"""
        tools = build_tool_defs(registry)
        # v0.8.18：减去 17 个内置工具（5 核心 + 12 元能力）
        builtin_names = {
            "run_shell", "read_file", "write_file", "edit_file", "run_python",
            "read_log", "self_restart", "self_build", "self_status", "self_version_bump",
            "memory_recall", "create_skill", "self_analyze", "skill_evolve",
            "memory_archive", "trap_search", "trap_update",
        }
        skill_tools = [t for t in tools if t["function"]["name"] not in builtin_names]
        assert len(skill_tools) >= 80, f"应至少 80 个 skill tool，实际 {len(skill_tools)}"


class TestRunShellTool:
    """v0.8.0 新增：run_shell 万能兜底工具定义。"""

    def test_run_shell_tool_structure(self) -> None:
        tool = build_run_shell_tool()
        assert tool["type"] == "function"
        assert tool["function"]["name"] == "run_shell"
        # description 要包含关键信息
        desc = tool["function"]["description"]
        assert "shell" in desc.lower() or "命令" in desc
        assert "黑名单" in desc or "拒绝" in desc
        assert "灰名单" in desc or "确认" in desc
        assert "白名单" in desc or "自动执行" in desc

    def test_run_shell_required_params(self) -> None:
        """command + intent 是必填。"""
        tool = build_run_shell_tool()
        params = tool["function"]["parameters"]
        assert "command" in params["properties"]
        assert "intent" in params["properties"]
        assert "timeout" in params["properties"]
        assert set(params["required"]) == {"command", "intent"}

    def test_run_shell_in_build_tool_defs(self, registry: SkillRegistry) -> None:
        """build_tool_defs 把 run_shell 加到列表头。"""
        tools = build_tool_defs(registry)
        run_shell_tools = [t for t in tools if t["function"]["name"] == "run_shell"]
        assert len(run_shell_tools) == 1, "run_shell 应该只出现一次"


class TestFileOpTools:
    """v0.8.2 新增：read_file / write_file / edit_file 工具定义。"""

    def test_read_file_tool_structure(self) -> None:
        from lihua.tool_defs import build_read_file_tool
        tool = build_read_file_tool()
        assert tool["function"]["name"] == "read_file"
        params = tool["function"]["parameters"]
        assert "path" in params["properties"]
        assert "start_line" in params["properties"]
        assert "end_line" in params["properties"]
        assert set(params["required"]) == {"path"}

    def test_write_file_tool_structure(self) -> None:
        from lihua.tool_defs import build_write_file_tool
        tool = build_write_file_tool()
        assert tool["function"]["name"] == "write_file"
        params = tool["function"]["parameters"]
        assert "path" in params["properties"]
        assert "content" in params["properties"]
        assert "intent" in params["properties"]
        assert set(params["required"]) == {"path", "content", "intent"}

    def test_edit_file_tool_structure(self) -> None:
        from lihua.tool_defs import build_edit_file_tool
        tool = build_edit_file_tool()
        assert tool["function"]["name"] == "edit_file"
        params = tool["function"]["parameters"]
        assert "path" in params["properties"]
        assert "old_string" in params["properties"]
        assert "new_string" in params["properties"]
        assert "intent" in params["properties"]
        assert set(params["required"]) == {"path", "old_string", "new_string", "intent"}

    def test_file_op_tools_in_build_tool_defs(self, registry: SkillRegistry) -> None:
        """build_tool_defs 包含 3 个文件操作工具。"""
        tools = build_tool_defs(registry)
        names = [t["function"]["name"] for t in tools]
        assert "read_file" in names
        assert "write_file" in names
        assert "edit_file" in names


class TestRunPythonTool:
    """v0.8.3 新增：run_python 工具定义。"""

    def test_run_python_tool_structure(self) -> None:
        from lihua.tool_defs import build_run_python_tool
        tool = build_run_python_tool()
        assert tool["type"] == "function"
        assert tool["function"]["name"] == "run_python"
        # description 要包含关键信息
        desc = tool["function"]["description"]
        assert "python" in desc.lower() or "Python" in desc
        assert "confirm" in desc.lower() or "确认" in desc

    def test_run_python_required_params(self) -> None:
        """code + intent 是必填，timeout 可选。"""
        from lihua.tool_defs import build_run_python_tool
        tool = build_run_python_tool()
        params = tool["function"]["parameters"]
        assert "code" in params["properties"]
        assert "intent" in params["properties"]
        assert "timeout" in params["properties"]
        assert set(params["required"]) == {"code", "intent"}

    def test_run_python_in_build_tool_defs(self, registry: SkillRegistry) -> None:
        """build_tool_defs 包含 run_python。"""
        from lihua.tool_defs import build_run_python_tool
        tools = build_tool_defs(registry)
        run_python_tools = [t for t in tools if t["function"]["name"] == "run_python"]
        assert len(run_python_tools) == 1, "run_python 应该只出现一次"

    def test_run_python_is_first_5_tools(self, registry: SkillRegistry) -> None:
        """run_shell / read_file / write_file / edit_file / run_python 应在前 5 个。"""
        tools = build_tool_defs(registry)
        names = [t["function"]["name"] for t in tools[:5]]
        assert "run_python" in names
        assert "run_shell" in names
        assert "read_file" in names
        assert "write_file" in names
        assert "edit_file" in names


class TestBuildToolIndex:
    """tool name → SkillDef 映射。"""

    def test_index_contains_all_skills(self, registry: SkillRegistry) -> None:
        idx = build_tool_index(registry)
        for s in registry.all():
            assert s.name in idx
            assert idx[s.name] is s

    def test_get_specific_skill(self, registry: SkillRegistry) -> None:
        idx = build_tool_index(registry)
        assert "install_app" in idx
        assert idx["install_app"].name == "install_app"


class TestBuildSkillCatalogForPrompt:
    """系统 prompt 用的 skill 索引。"""

    def test_returns_non_empty_string(self, registry: SkillRegistry) -> None:
        catalog = build_skill_catalog_for_prompt(registry)
        assert isinstance(catalog, str)
        assert len(catalog) > 0

    def test_contains_skill_names(self, registry: SkillRegistry) -> None:
        catalog = build_skill_catalog_for_prompt(registry)
        assert "install_app" in catalog

    def test_max_skills_limit(self, registry: SkillRegistry) -> None:
        """max_skills > 0 时只给前 N 个 skill（不含 `==` 类别标题行）。"""
        catalog = build_skill_catalog_for_prompt(registry, max_skills=5)
        skill_lines = [
            l for l in catalog.splitlines()
            if l.strip() and not l.startswith("== ")
        ]
        assert len(skill_lines) <= 5

    def test_format_contains_description(self, registry: SkillRegistry) -> None:
        """v0.7.12：catalog 行格式为 `- skill_name: description`。"""
        catalog = build_skill_catalog_for_prompt(registry)
        # 精确匹配 `- install_app:` 行（避免误匹配 install_appimage）
        install_line = [l for l in catalog.splitlines() if l.startswith("- install_app:")]
        assert install_line, "install_app 应该在 catalog 里"
        # 应含 description（triggers/params 已移到 tools 列表，避免冗余）
        assert "安装应用程序" in install_line[0], (
            f"应含 description，实际：{install_line[0]}"
        )

    def test_catalog_grouped_by_category(self, registry: SkillRegistry) -> None:
        """v0.7.12：catalog 应按类别分组，含 `== 类别名 ==` 标题行。"""
        catalog = build_skill_catalog_for_prompt(registry)
        assert "== " in catalog, "catalog 应含类别标题行（== 类别名 ==）"
        # 至少有 5 个不同的类别
        category_lines = [l for l in catalog.splitlines() if l.startswith("== ")]
        assert len(category_lines) >= 5, (
            f"应至少 5 个类别，实际 {len(category_lines)} 个"
        )
