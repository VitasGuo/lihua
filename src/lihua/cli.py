"""Lihua CLI 入口。

用法：
    lihua "装QQ"                 # 单次执行（等价 lihua run "装QQ"）
    lihua "卸载 firefox" -y      # 自动确认
    lihua ask "..."              # run 的便捷别名
    lihua chat                   # 交互模式
    lihua doctor                 # 健康检查
    lihua serve                  # 启动 HTTP 服务
    lihua gui [--build|--dev]    # 启动桌面浮窗（Tauri 应用）
    lihua install                # 安装 systemd user service（开机自启）
    lihua uninstall-service      # 卸载 systemd user service
    lihua history                # 历史记录
    lihua audit                  # 审计日志

    lihua skills list            # 列出所有 Skill
    lihua skills show <name>     # 查看 Skill 详情
    lihua skills reload          # 重新加载 Skill
    lihua skills path            # 显示用户 Skill 目录

    lihua config show            # 显示当前配置
    lihua config init            # 写默认配置
    lihua config set <k> <v>     # 设置配置项（如 llm.enabled true）
    lihua config path            # 显示配置文件路径

    lihua memory stats           # 记忆系统统计
    lihua memory sessions        # 会话列表
    lihua memory session <id>    # 查看某会话
    lihua memory knowledge       # 知识库模式
    lihua memory traps           # 踩坑记录
    lihua memory traps-search <kw>  # 搜索踩坑
    lihua memory export [-o FILE]   # 导出 JSON
    lihua memory clear           # 清空记忆
    lihua memory archive         # 归档旧记录

    lihua self status            # 编译/重启状态
    lihua self build             # 后台编译桌面端
    lihua self restart           # 重启后端服务
    lihua self version-bump [V]  # 升级 6 个版本号文件

    lihua skill-auto list        # 自生成技能列表
    lihua skill-auto stats       # 自生成统计
    lihua skill-auto patterns    # 重复工具链（可固化）
    lihua skill-auto reload      # 重新加载
    lihua skill-auto delete <n>  # 删除技能
    lihua skill-auto path        # 技能目录

    lihua plugin list            # 插件列表
    lihua plugin stats           # 插件统计
    lihua plugin info <name>     # 插件详情
    lihua plugin reload          # 重新加载
    lihua plugin enable <name>   # 启用（持久化）
    lihua plugin disable <name>  # 禁用（持久化）
    lihua plugin path            # 插件目录

    lihua prompt sections        # Prompt 模块列表（只读）
    lihua prompt stats           # Prompt 模块统计

    lihua analytics overview     # 总览统计
    lihua analytics report       # 完整文本报告
    lihua analytics tools        # 工具使用
    lihua analytics errors       # 错误分析
    lihua analytics skills       # Skill 使用
    lihua analytics suggestions  # 改进建议
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from lihua import __version__
from lihua.config import (
    Config,
    config_dir,
    config_file_path,
    data_dir,
    state_dir,
    skills_user_dir,
    write_default_config_if_missing,
)
from lihua.agent import AgentResponse, run_agent
from lihua.executor import command_exists
from lihua.intent import understand
from lihua.router import is_available
from lihua.skill_runner import RunResult, StepResult, run_skill
from lihua.skills import SkillRegistry, get_registry

app = typer.Typer(
    name="lihua",
    help="狸花猫 - AI 系统管家，让普通用户也能省心用 Linux",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _print_banner() -> None:
    console.print(
        Panel.fit(
            f"[bold green]狸花猫 Lihua[/bold green] [dim]v{__version__}[/dim]\n"
            "[dim]想得多，做得少，事半功倍。[/dim]",
            border_style="green",
        )
    )


def _load_config() -> Config:
    cfg = Config.load()
    cfg.ensure_dirs()
    return cfg


def _make_confirm_callback(auto_yes: bool):
    """构造灰名单确认回调。"""
    def confirm(message: str, command: str) -> bool:
        if auto_yes:
            console.print(f"[yellow]⚠ 自动确认：[/yellow]{message}")
            return True
        console.print(Panel(
            f"[yellow]需要确认[/yellow]\n\n{message}",
            title="灰名单任务",
            border_style="yellow",
        ))
        return Confirm.ask("[bold]确认执行？[/bold]", default=False)
    return confirm


def _make_progress_callback(verbose: bool):
    """构造进度回调。"""
    def on_progress(step_name: str, message: str) -> None:
        if verbose:
            console.print(f"  [dim]· {step_name}:[/dim] {message}")
        else:
            # 简短模式：只在重要节点打印
            if any(k in message for k in ("解析为", "已安装", "已完成", "失败", "跳过")):
                console.print(f"  [dim]·[/dim] {message}")
    return on_progress


def _print_run_result(result: RunResult, verbose: bool = False) -> None:
    """打印执行结果。"""
    if result.success:
        console.print(f"[bold green]✓ 完成[/bold green] {result.final_message}")
    else:
        console.print(f"[bold red]✗ 失败[/bold red] {result.final_message}")

    if verbose:
        table = Table(title="执行步骤", show_lines=False)
        table.add_column("步骤", style="cyan")
        table.add_column("状态")
        table.add_column("耗时", justify="right")
        table.add_column("输出/错误", overflow="fold")
        for sr in result.steps:
            if sr.skipped:
                status = "[dim]跳过[/dim]"
            elif sr.success:
                status = "[green]✓[/green]"
            else:
                status = "[red]✗[/red]"
            duration = f"{sr.duration:.2f}s" if sr.duration > 0 else "-"
            out = sr.error or sr.output or ""
            if len(out) > 200:
                out = out[:200] + "..."
            table.add_row(sr.step.name, status, duration, out)
        console.print(table)


def _append_history(text: str, success: bool, message: str) -> None:
    """追加历史记录（简单 JSONL）。"""
    import json
    import time
    from lihua.config import history_path
    try:
        path = history_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": time.time(),
                "input": text,
                "success": success,
                "message": message,
            }, ensure_ascii=False) + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# 默认命令：lihua "装QQ"
# ---------------------------------------------------------------------------

def _version_callback(value: bool) -> None:
    if value:
        console.print(f"lihua {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=False)
def main_callback(
    ctx: typer.Context,
    version: bool = typer.Option(
        None,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="显示版本号并退出。",
    ),
) -> None:
    """狸花猫 - AI 系统管家。"""
    pass


@app.command(name="run")
def run_cmd(
    message: str = typer.Argument(..., help="自然语言指令，如 \"装QQ\""),
    yes: bool = typer.Option(False, "-y", "--yes", help="自动确认灰名单任务"),
    dry_run: bool = typer.Option(False, "--dry-run", help="只解析不执行"),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="详细输出"),
    no_llm: bool = typer.Option(False, "--no-llm", help="本次不调用 LLM（强制走规则匹配）"),
    rule: bool = typer.Option(False, "--rule", help="强制走规则匹配模式（不走 LLM Agent）"),
) -> None:
    """执行一条自然语言指令。

    默认走 LLM Agent 模式（智能对话 + 工具调用）。
    无 LLM 或 --rule 时回退到规则匹配模式。
    """
    _print_banner()
    cfg = _load_config()
    if no_llm:
        cfg.llm.enabled = False

    registry = get_registry()
    registry.reload()

    # 判断走哪个模式：默认 Agent，--rule 或无 LLM 时走规则
    use_agent = cfg.llm.enabled and not rule

    if use_agent:
        console.print(f"[dim]Agent 模式理解中：[/dim]{message}")
        confirm_cb = _make_confirm_callback(yes)
        progress_cb = _make_progress_callback(verbose)
        agent_resp = run_agent(
            user_text=message,
            cfg=cfg,
            registry=registry,
            confirm=confirm_cb,
            on_progress=progress_cb,
            dry_run=dry_run,
        )

        # 打印工具调用过程
        for tc in agent_resp.tool_calls:
            status = "[green]✓[/green]" if tc.success else "[red]✗[/red]"
            console.print(f"  {status} [cyan]{tc.tool_name}[/cyan] {tc.arguments}")
            if tc.result_message:
                console.print(f"     [dim]{tc.result_message}[/dim]")

        # 打印最终回复
        if agent_resp.text:
            console.print(Panel(
                agent_resp.text,
                title="[bold green]狸花猫[/bold green]",
                border_style="green",
            ))
        elif agent_resp.error:
            console.print(f"[red]✗[/red] {agent_resp.error}")

        success = agent_resp.success and all(tc.success for tc in agent_resp.tool_calls)
        summary = agent_resp.text[:200] if agent_resp.text else (
            " | ".join(f"{tc.tool_name}:{'✓' if tc.success else '✗'}" for tc in agent_resp.tool_calls)
        )
        _append_history(message, success, summary)
        raise typer.Exit(0 if success else 1)

    # 规则匹配模式（离线兜底）
    console.print(f"[dim]规则模式理解中：[/dim]{message}")
    intent = understand(message, cfg, registry)

    if not intent.matched:
        console.print(f"[yellow]⚠[/yellow] {intent.explanation}")
        if cfg.llm.enabled:
            console.print("[dim]提示：可以尝试更具体的描述，或用 --no-llm 走规则模式调试[/dim]")
        raise typer.Exit(1)

    console.print(
        f"[green]✓ 意图识别[/green] "
        f"skill=[cyan]{intent.skill_name}[/cyan] "
        f"source=[dim]{intent.source}[/dim] "
        f"confidence=[dim]{intent.confidence:.2f}[/dim]"
    )
    if intent.params:
        params_str = " ".join(f"{k}={v!r}" for k, v in intent.params.items())
        console.print(f"[dim]参数：[/dim]{params_str}")
    if intent.explanation:
        console.print(f"[dim]说明：[/dim]{intent.explanation}")

    if dry_run:
        console.print("[yellow]--dry-run 模式，不执行[/yellow]")
        raise typer.Exit(0)

    # 执行
    confirm_cb = _make_confirm_callback(yes)
    progress_cb = _make_progress_callback(verbose)
    result = run_skill(intent, cfg, confirm=confirm_cb, on_progress=progress_cb)
    _print_run_result(result, verbose=verbose)
    _append_history(message, result.success, result.final_message)

    raise typer.Exit(0 if result.success else 1)


# ---------------------------------------------------------------------------
# chat 交互模式
# ---------------------------------------------------------------------------

@app.command()
def chat(
    yes: bool = typer.Option(False, "-y", "--yes", help="自动确认灰名单任务"),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="详细输出"),
    rule: bool = typer.Option(False, "--rule", help="强制走规则匹配模式（不走 LLM Agent）"),
) -> None:
    """交互式对话模式。

    默认走 LLM Agent 模式（智能对话 + 工具调用 + 多轮）。
    无 LLM 或 --rule 时回退到规则匹配模式。
    """
    _print_banner()
    cfg = _load_config()
    registry = get_registry()
    registry.reload()

    use_agent = cfg.llm.enabled and not rule

    console.print(
        f"[dim]模式: [/dim]"
        f"{'[green]LLM Agent[/green] ' + cfg.llm.model if use_agent else '[yellow]规则匹配[/yellow]'}"
    )
    console.print(f"[dim]Skill: [/dim]{len(registry.all())} 个内置")
    console.print("[dim]输入 exit / quit 退出，history 看历史，help 看帮助[/dim]\n")

    while True:
        try:
            user_input = Prompt.ask("[bold green]狸花猫[/bold green]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]再见[/dim]")
            break

        if not user_input:
            continue
        if user_input in ("exit", "quit", "q"):
            console.print("[dim]再见[/dim]")
            break
        if user_input in ("help", "?"):
            _print_chat_help(registry)
            continue
        if user_input == "skills":
            _list_skills(registry)
            continue
        if user_input == "history":
            _show_history()
            continue

        if use_agent:
            # Agent 模式：直接调 run_agent，拿到最终回复
            confirm_cb = _make_confirm_callback(yes)
            progress_cb = _make_progress_callback(verbose)
            agent_resp = run_agent(
                user_text=user_input,
                cfg=cfg,
                registry=registry,
                confirm=confirm_cb,
                on_progress=progress_cb,
            )

            for tc in agent_resp.tool_calls:
                status = "[green]✓[/green]" if tc.success else "[red]✗[/red]"
                console.print(f"  {status} [cyan]{tc.tool_name}[/cyan] {tc.arguments}")
                if tc.result_message:
                    console.print(f"     [dim]{tc.result_message}[/dim]")

            if agent_resp.text:
                console.print(Panel(
                    agent_resp.text,
                    title="[bold green]狸花猫[/bold green]",
                    border_style="green",
                ))
            elif agent_resp.error:
                console.print(f"[red]✗[/red] {agent_resp.error}")

            success = agent_resp.success and all(tc.success for tc in agent_resp.tool_calls)
            summary = agent_resp.text[:200] if agent_resp.text else (
                " | ".join(f"{tc.tool_name}:{'✓' if tc.success else '✗'}" for tc in agent_resp.tool_calls)
            )
            _append_history(user_input, success, summary)
        else:
            # 规则模式
            intent = understand(user_input, cfg, registry)
            if not intent.matched:
                console.print(f"[yellow]⚠[/yellow] {intent.explanation}")
                continue

            console.print(
                f"[green]✓[/green] skill=[cyan]{intent.skill_name}[/cyan] "
                f"([dim]{intent.source}, {intent.confidence:.2f}[/dim])"
            )

            confirm_cb = _make_confirm_callback(yes)
            progress_cb = _make_progress_callback(verbose)
            result = run_skill(intent, cfg, confirm=confirm_cb, on_progress=progress_cb)
            _print_run_result(result, verbose=verbose)
            _append_history(user_input, result.success, result.final_message)

        console.print()


def _print_chat_help(registry: SkillRegistry) -> None:
    console.print(Panel(
        "[bold]交互命令[/bold]\n"
        "  exit / quit    退出\n"
        "  help / ?       显示本帮助\n"
        "  skills         列出所有 Skill\n"
        "  history        查看历史\n\n"
        "[bold]示例[/bold]\n"
        "  装QQ\n"
        "  卸载 firefox\n"
        "  把输入法换成 fcitx5\n"
        "  装个思源黑体字体\n"
        "  清理缓存",
        title="帮助",
        border_style="cyan",
    ))


# ---------------------------------------------------------------------------
# skills 子命令
# ---------------------------------------------------------------------------

skills_app = typer.Typer(help="Skill 管理")
app.add_typer(skills_app, name="skills")


@skills_app.command("list")
def _list_skills_cmd() -> None:
    """列出所有 Skill。"""
    registry = get_registry()
    registry.reload()
    _list_skills(registry)


def _list_skills(registry: SkillRegistry) -> None:
    skills = registry.all()
    if not skills:
        console.print("[yellow]没有可用的 Skill[/yellow]")
        return
    table = Table(title=f"内置 Skill（{len(skills)} 个）")
    table.add_column("名称", style="cyan")
    table.add_column("描述")
    table.add_column("触发词", overflow="fold")
    table.add_column("来源")
    for s in skills:
        triggers = " / ".join(s.triggers[:5])
        if len(s.triggers) > 5:
            triggers += f" (+{len(s.triggers) - 5})"
        table.add_row(s.name, s.description, triggers, s.source)
    console.print(table)


@skills_app.command("show")
def _show_skill_cmd(name: str = typer.Argument(..., help="Skill 名称")) -> None:
    """查看某个 Skill 详情。"""
    registry = get_registry()
    registry.reload()
    s = registry.get(name)
    if not s:
        console.print(f"[red]未找到 Skill: {name}[/red]")
        raise typer.Exit(1)
    console.print(Panel(
        f"[bold cyan]{s.name}[/bold cyan] v{s.version}（{s.source}）\n"
        f"{s.description}\n\n"
        f"[dim]触发词:[/dim] {' / '.join(s.triggers)}\n"
        f"[dim]示例:[/dim] {' | '.join(s.examples)}\n"
        f"[dim]文件:[/dim] {s.file_path}",
        title="Skill 详情",
        border_style="cyan",
    ))
    if s.parameters:
        table = Table(title="参数")
        table.add_column("名称", style="cyan")
        table.add_column("必填")
        table.add_column("描述")
        table.add_column("默认")
        for p in s.parameters:
            table.add_row(p.name, "✓" if p.required else "", p.description, str(p.default or ""))
        console.print(table)
    if s.steps:
        table = Table(title=f"步骤（{len(s.steps)}）")
        table.add_column("#", style="dim")
        table.add_column("名称", style="cyan")
        table.add_column("类型")
        table.add_column("描述", overflow="fold")
        for i, step in enumerate(s.steps, 1):
            table.add_row(str(i), step.name, step.type, step.description)
        console.print(table)


@skills_app.command("reload")
def _reload_skills_cmd() -> None:
    """重新加载 Skill。"""
    registry = get_registry()
    registry.reload()
    console.print(f"[green]✓ 已加载 {len(registry.all())} 个 Skill[/green]")


@skills_app.command("path")
def _skills_path_cmd() -> None:
    """显示用户 Skill 目录。"""
    p = skills_user_dir()
    p.mkdir(parents=True, exist_ok=True)
    console.print(f"用户 Skill 目录：[cyan]{p}[/cyan]")
    console.print(f"[dim]把 .yaml 文件放这里即可被自动加载[/dim]")


# ---------------------------------------------------------------------------
# config 子命令
# ---------------------------------------------------------------------------

config_app = typer.Typer(help="配置管理")
app.add_typer(config_app, name="config")


@config_app.command("show")
def _config_show() -> None:
    """显示当前配置。"""
    cfg = _load_config()
    console.print(Panel(
        f"[bold]配置文件[/bold]: [cyan]{config_file_path()}[/cyan]\n"
        f"[bold]LLM 启用[/bold]: {'[green]是[/green]' if cfg.llm.enabled else '[yellow]否[/yellow]'}\n"
        f"[bold]LLM 提供商[/bold]: {cfg.llm.provider}\n"
        f"[bold]LLM 模型[/bold]: {cfg.llm.model}\n"
        f"[bold]API Base[/bold]: {cfg.llm.api_base or '-'}\n"
        f"[bold]API Key[/bold]: {'***' + cfg.llm.api_key[-4:] if cfg.llm.api_key else '(未设置)'}\n"
        f"[bold]灰名单确认[/bold]: {'是' if cfg.always_confirm_grey else '否'}\n"
        f"[bold]白名单自动执行[/bold]: {'是' if cfg.auto_execute_whitelist else '否'}\n"
        f"[bold]审计日志[/bold]: {'是' if cfg.audit_log else '否'}",
        title="当前配置",
        border_style="cyan",
    ))


@config_app.command("init")
def _config_init(
    force: bool = typer.Option(False, "--force", help="覆盖已存在的配置"),
) -> None:
    """写入默认配置文件。"""
    path = config_file_path()
    if path.exists() and not force:
        console.print(f"[yellow]配置已存在：{path}[/yellow]")
        console.print("[dim]用 --force 覆盖[/dim]")
        raise typer.Exit(1)
    if force:
        path.unlink(missing_ok=True)
    wrote = write_default_config_if_missing()
    if wrote:
        console.print(f"[green]✓ 已写入默认配置：{path}[/green]")
    else:
        console.print(f"[yellow]配置已存在：{path}[/yellow]")


@config_app.command("path")
def _config_path() -> None:
    """显示配置文件路径。"""
    console.print(f"配置文件：[cyan]{config_file_path()}[/cyan]")
    console.print(f"配置目录：[cyan]{config_dir()}[/cyan]")
    console.print(f"数据目录：[cyan]{data_dir()}[/cyan]")
    console.print(f"状态目录：[cyan]{state_dir()}[/cyan]")


@config_app.command("set")
def _config_set(
    key: str = typer.Argument(..., help="配置键，如 llm.enabled / llm.model"),
    value: str = typer.Argument(..., help="配置值"),
) -> None:
    """设置配置项（简单实现：直接改 toml 文本）。"""
    path = config_file_path()
    if not path.exists():
        write_default_config_if_missing()
    # 简单实现：读 toml → 改 dict → 写回
    import tomllib
    try:
        with path.open("rb") as f:
            raw = tomllib.load(f)
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]读取配置失败: {e}[/red]")
        raise typer.Exit(1)

    # 解析 key（如 llm.enabled）
    parts = key.split(".")
    d = raw
    for p in parts[:-1]:
        if p not in d or not isinstance(d[p], dict):
            d[p] = {}
        d = d[p]
    # 类型推断
    parsed_value: Any = value
    if value.lower() in ("true", "false"):
        parsed_value = value.lower() == "true"
    elif value.isdigit():
        parsed_value = int(value)
    elif _is_float(value):
        parsed_value = float(value)
    d[parts[-1]] = parsed_value

    # 写回 toml
    try:
        import tomli_w
        with path.open("wb") as f:
            tomli_w.dump(raw, f)
    except ImportError:
        # 没有 tomli_w，用文本方式写
        _write_toml_simple(raw, path)
    console.print(f"[green]✓ 已设置 {key} = {parsed_value!r}[/green]")


def _is_float(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def _write_toml_simple(data: dict, path: Path) -> None:
    """简易 toml 写入（不依赖 tomli_w）。"""
    lines = []
    for k, v in data.items():
        if isinstance(v, dict):
            lines.append(f"\n[{k}]")
            for sk, sv in v.items():
                lines.append(f"{sk} = {_toml_value(sv)}")
        else:
            lines.append(f"{k} = {_toml_value(v)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _toml_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return f'"{v}"'


# ---------------------------------------------------------------------------
# doctor 健康检查
# ---------------------------------------------------------------------------

@app.command()
def doctor() -> None:
    """健康检查。"""
    _print_banner()
    cfg = _load_config()

    table = Table(title="健康检查")
    table.add_column("项目")
    table.add_column("状态")
    table.add_column("详情", overflow="fold")

    # Python 版本
    import platform
    py_ver = platform.python_version()
    table.add_row("Python", f"[green]✓ {py_ver}[/green]", "")

    # 配置文件
    cfg_path = config_file_path()
    if cfg_path.exists():
        table.add_row("配置文件", f"[green]✓ 存在[/green]", str(cfg_path))
    else:
        table.add_row("配置文件", "[yellow]⚠ 不存在[/yellow]", "运行 `lihua config init` 创建")

    # LLM
    if is_available(cfg.llm):
        table.add_row("LLM", f"[green]✓ 可用[/green]", f"{cfg.llm.provider} / {cfg.llm.model}")
    elif cfg.llm.enabled:
        table.add_row("LLM", "[red]✗ 启用但不可用[/red]", "检查 api_key / api_base")
    else:
        table.add_row("LLM", "[yellow]⚠ 未启用[/yellow]", "纯规则模式可用，但理解能力受限")

    # Skill 数
    registry = get_registry()
    registry.reload()
    skills = registry.all()
    table.add_row("Skill", f"[green]✓ {len(skills)} 个[/green]", ", ".join(s.name for s in skills[:5]))

    # 系统工具
    for tool in ("apt", "flatpak", "snap", "gsettings", "fcitx5", "notify-send"):
        exists = command_exists(tool)
        if exists:
            table.add_row(f"工具 {tool}", "[green]✓[/green]", "")
        else:
            table.add_row(f"工具 {tool}", "[dim]- 未安装[/dim]", "")

    # 目录
    for name, p in [("配置", config_dir()), ("数据", data_dir()), ("状态", state_dir())]:
        p.mkdir(parents=True, exist_ok=True)
        table.add_row(f"目录 {name}", f"[green]✓ {p}[/green]", "")

    console.print(table)

    # 测试 LLM 调用
    if is_available(cfg.llm):
        console.print("\n[bold]测试 LLM 调用...[/bold]")
        from lihua.router import call_llm, LLMError
        try:
            resp = call_llm(cfg.llm, [
                {"role": "system", "content": "你是测试助手。"},
                {"role": "user", "content": "回复 ok"},
            ])
            console.print(f"[green]✓ LLM 响应[/green]: {resp.text[:100]}")
        except LLMError as e:
            console.print(f"[red]✗ LLM 调用失败[/red]: {e}")


# ---------------------------------------------------------------------------
# serve 启动 HTTP 服务
# ---------------------------------------------------------------------------

@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="监听地址"),
    port: int = typer.Option(7531, help="监听端口"),
) -> None:
    """启动 HTTP 服务（需要安装 server extras）。"""
    # v0.7.7: 初始化日志系统
    from lihua.logging_config import setup_logging
    cfg = _load_config()
    setup_logging(level=cfg.log_level, enable_stderr=True)

    try:
        from lihua.server import create_app
    except ImportError as e:
        console.print(f"[red]server 依赖未安装[/red]: {e}")
        console.print("[dim]运行: pip install 'lihua[server]'[/dim]")
        raise typer.Exit(1) from e
    import uvicorn
    from lihua.logging_config import get_logger
    log = get_logger(__name__)
    log.info(f"启动 Lihua HTTP 服务 http://{host}:{port}")
    console.print(f"[green]启动 Lihua HTTP 服务[/green] http://{host}:{port}")
    uvicorn.run(create_app(), host=host, port=port, log_level="info")


# ---------------------------------------------------------------------------
# gui 启动桌面浮窗（Tauri 桌面应用：系统托盘 + 浮动小球 + 主浮窗）
# ---------------------------------------------------------------------------

# 后端 API 默认端口（Tauri 主进程内嵌 uvicorn sidecar 用）
DEFAULT_GUI_BACKEND_PORT = 7531


def _find_desktop_dir() -> Path | None:
    """定位 desktop/ 目录：优先与源码同级，其次用户 data 目录下。"""
    # 1. 源码包同级目录（开发模式）
    try:
        from lihua import __file__ as pkg_file
        if pkg_file:
            dev = Path(pkg_file).resolve().parent.parent.parent / "desktop"
            if (dev / "package.json").exists():
                return dev
    except Exception:  # noqa: BLE001
        pass
    # 2. 当前工作目录
    cwd_desktop = Path.cwd() / "desktop"
    if (cwd_desktop / "package.json").exists():
        return cwd_desktop
    # 3. 用户数据目录下的 desktop（生产安装模式，预留）
    user_desktop = data_dir() / "desktop"
    if (user_desktop / "package.json").exists():
        return user_desktop
    return None


def _find_tauri_binary(desktop_dir: Path) -> Path | None:
    """查找已编译的 Tauri 二进制：优先 release，其次 debug。"""
    src_tauri = desktop_dir / "src-tauri"
    candidates = [
        src_tauri / "target" / "release" / "lihua-desktop",
        src_tauri / "target" / "debug" / "lihua-desktop",
    ]
    for c in candidates:
        if c.exists() and c.stat().st_size > 0:
            return c
    return None


def _check_binary_ready(desktop_dir: Path) -> tuple[bool, str]:
    """v0.8.24: 自检 Tauri 二进制是否就绪可启动。返回 (是否就绪, 原因说明)。

    三层检查（任何一层不通过都触发自动编译，让用户零编译零命令行）：
    1. 二进制是否存在
    2. 前后端版本号是否匹配（Python __version__ vs Rust APP_VERSION）
    3. 前端/Rust 源代码是否比二进制新（源码改过但没重新编译）

    版本号格式对齐：
      Python "0.8.23a0"    → 去掉字母数字后缀 → "0.8.23"
      Rust   "0.8.23-alpha" → 去掉 -alpha     → "0.8.23"
    """
    import re
    from lihua import __version__ as py_version

    # 1. 二进制不存在
    binary = _find_tauri_binary(desktop_dir)
    if not binary:
        return False, "Tauri 二进制不存在"

    # 2. 版本号匹配检查
    py_base = re.sub(r"[a-z]\d*$", "", py_version)  # "0.8.23a0" → "0.8.23"
    lib_rs = desktop_dir / "src-tauri" / "src" / "lib.rs"
    if lib_rs.exists():
        try:
            content = lib_rs.read_text(encoding="utf-8")
            match = re.search(r'APP_VERSION[^"]*"([^"]+)"', content)
            if match:
                rs_base = match.group(1).split("-")[0]  # "0.8.23-alpha" → "0.8.23"
                if rs_base != py_base:
                    return False, f"版本不匹配（Rust {rs_base} / Python {py_base}）"
        except OSError:
            pass  # 读不到 lib.rs 不阻塞，继续后续检查

    # 3. 源代码是否比二进制新
    binary_mtime = binary.stat().st_mtime
    # 前端源码：src/ 下的 .ts/.tsx/.css/.html
    fe_src = desktop_dir / "src"
    if fe_src.exists():
        for f in fe_src.rglob("*"):
            if f.is_file() and f.suffix in (".ts", ".tsx", ".css", ".html"):
                if f.stat().st_mtime > binary_mtime:
                    return False, "前端源代码已更新"
    # Rust 源码：src-tauri/src/ 下的 .rs
    rs_src = desktop_dir / "src-tauri" / "src"
    if rs_src.exists():
        for f in rs_src.rglob("*.rs"):
            if f.is_file() and f.stat().st_mtime > binary_mtime:
                return False, "Rust 源代码已更新"
    # Tauri 配置改动也需要重新编译
    for cfg_name in ("tauri.conf.json", "Cargo.toml"):
        cfg = desktop_dir / "src-tauri" / cfg_name
        if cfg.exists() and cfg.stat().st_mtime > binary_mtime:
            return False, f"{cfg_name} 配置已更新"

    return True, ""


def _build_tauri(desktop_dir: Path) -> int:
    """编译 Tauri 应用（release 模式，嵌入前端资源）。返回 exit code。

    必须用 `npx tauri build --no-bundle` 而不是 `cargo build --release`：
    - tauri build 会先跑 beforeBuildCommand (npm run build) 生成 dist/
    - 然后通过 build.rs 把 dist/ 嵌入到二进制资源中
    - --no-bundle 跳过 deb/appimage 打包（我们不需要）
    """
    import subprocess

    # 检查 node_modules
    if not (desktop_dir / "node_modules").exists():
        console.print("[yellow]前端依赖未安装，运行 npm install...[/yellow]")
        r = subprocess.run(
            ["npm", "install", "--registry=https://registry.npmmirror.com"],
            cwd=str(desktop_dir),
        )
        if r.returncode != 0:
            console.print("[red]npm install 失败[/red]")
            return r.returncode

    console.print("[green]编译 Tauri 应用[/green] (npx tauri build --no-bundle, 可能要几分钟)")
    r = subprocess.run(
        ["npx", "tauri", "build", "--no-bundle"],
        cwd=str(desktop_dir),
    )
    if r.returncode != 0:
        console.print("[red]Tauri 编译失败[/red]")
        return r.returncode

    binary = desktop_dir / "src-tauri" / "target" / "release" / "lihua-desktop"
    if binary.exists():
        size_mb = binary.stat().st_size / 1024 / 1024
        console.print(f"[bold green]✓ 编译成功[/bold green] {binary} ({size_mb:.1f} MB)")
    return 0


def _is_tauri_running() -> bool:
    """检查 lihua-desktop 进程是否在运行。"""
    import subprocess
    r = subprocess.run(
        ["pgrep", "-f", "lihua-desktop"],
        capture_output=True,
        text=True,
    )
    return r.returncode == 0 and bool(r.stdout.strip())


@app.command()
def gui(
    build: bool = typer.Option(False, "--build", help="先编译 Tauri 应用再启动"),
    dev: bool = typer.Option(False, "--dev", help="用 tauri dev 启动（开发模式，热重载）"),
    foreground: bool = typer.Option(False, "--foreground", help="前台运行（默认后台 detached）"),
) -> None:
    """启动桌面浮窗（Tauri 应用：系统托盘 + 浮动小球 + 主浮窗）。

    流程：
      1. 找到已编译的 Tauri 二进制（target/release/lihua-desktop）
      2. Tauri 主进程内嵌启动 Python uvicorn sidecar（端口 7531）
      3. 创建系统托盘 + 桌面浮动小球 + 主浮窗
      4. 注册全局快捷键 Super+Space 切换主窗口

    使用：
      lihua gui              # 后台启动已编译的桌面应用
      lihua gui --build      # 重新编译后启动
      lihua gui --dev        # 开发模式（vite + cargo run，热重载）
      lihua gui --foreground # 前台运行（看日志，Ctrl+C 退出）
    """
    _print_banner()

    desktop_dir = _find_desktop_dir()
    if not desktop_dir:
        console.print("[red]找不到 desktop/ 目录[/red]")
        console.print("[dim]请确认源码目录下有 desktop/package.json[/dim]")
        raise typer.Exit(1)

    # --dev 模式：直接调用 tauri dev
    if dev:
        import subprocess
        node_modules = desktop_dir / "node_modules"
        if not node_modules.exists():
            console.print("[yellow]前端依赖未安装，运行 npm install...[/yellow]")
            r = subprocess.run(
                ["npm", "install", "--registry=https://registry.npmmirror.com"],
                cwd=str(desktop_dir),
            )
            if r.returncode != 0:
                console.print("[red]npm install 失败[/red]")
                raise typer.Exit(1)
        console.print("[green]启动 Tauri dev 模式[/green]（热重载，Ctrl+C 退出）")
        cmd = ["npx", "tauri", "dev"]
        os.execvp(cmd[0], cmd)
        return

    # --build 模式：先编译
    if build:
        rc = _build_tauri(desktop_dir)
        if rc != 0:
            raise typer.Exit(rc)
    else:
        # v0.8.24: 启动前自检——二进制不存在/版本不匹配/源码过期时自动编译
        # 让用户零编译零命令行：lihua gui 永远能启动到最新版本
        ready, reason = _check_binary_ready(desktop_dir)
        if not ready:
            console.print(f"[yellow]自检：{reason}，自动编译中...[/yellow]")
            console.print("[dim]（首次或源码更新后约 1-3 分钟，只需一次）[/dim]")
            rc = _build_tauri(desktop_dir)
            if rc != 0:
                console.print("[red]自动编译失败。请手动运行: lihua gui --build[/red]")
                raise typer.Exit(1)
            console.print("[green]✓ 编译完成[/green]")

    # 查找二进制
    binary = _find_tauri_binary(desktop_dir)
    if not binary:
        console.print("[red]找不到 Tauri 二进制[/red]")
        console.print("[dim]请先运行: lihua gui --build[/dim]")
        raise typer.Exit(1)

    # 检查是否已在运行
    if _is_tauri_running():
        console.print("[yellow]狸花猫桌面应用已在运行[/yellow]")
        console.print("[dim]如需重启：pkill -f lihua-desktop && lihua gui[/dim]")
        raise typer.Exit(0)

    import subprocess

    size_mb = binary.stat().st_size / 1024 / 1024
    console.print(f"[dim]二进制：{binary} ({size_mb:.1f} MB)[/dim]")

    # 前台模式：直接 exec
    if foreground:
        console.print("[green]前台启动[/green]（Ctrl+C 退出）")
        os.execv(str(binary), [str(binary)])
        return

    # 后台模式：用 systemd-run --user 创建 transient unit，脱离 sandbox
    log_file = "/tmp/lihua-desktop.log"
    log_fh = open(log_file, "w", encoding="utf-8")  # noqa: SIM115

    # 尝试 systemd-run --user（最稳定，进程不会被 sandbox 终止）
    if shutil.which("systemd-run"):
        # 先清理可能残留的旧 transient unit（上次启动的 unit 未卸载会导致冲突）
        for clean_cmd in (
            ["systemctl", "--user", "stop", "lihua-desktop.service"],
            ["systemctl", "--user", "reset-failed", "lihua-desktop.service"],
        ):
            subprocess.run(clean_cmd, capture_output=True, timeout=5)
        cmd = [
            "systemd-run", "--user",
            "--unit=lihua-desktop",
            f"--working-directory={desktop_dir}",
            "--setenv=HOME=" + str(Path.home()),
            "--setenv=DISPLAY=" + os.environ.get("DISPLAY", ":0"),
            "--setenv=XDG_RUNTIME_DIR=" + os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"),
            "--setenv=WAYLAND_DISPLAY=" + os.environ.get("WAYLAND_DISPLAY", ""),
            "--setenv=XDG_SESSION_TYPE=" + os.environ.get("XDG_SESSION_TYPE", ""),
            "--setenv=LANG=" + os.environ.get("LANG", "C.UTF-8"),
            "--setenv=RUST_LOG=info",
            str(binary),
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                console.print(f"[bold green]✓ 桌面应用已后台启动[/bold green]")
                console.print(f"[dim]日志：journalctl --user -u lihua-desktop -f[/dim]")
                console.print(f"[dim]停止：systemctl --user stop lihua-desktop[/dim]")
                # 等一下让进程起来
                import time
                time.sleep(1.5)
                if _is_tauri_running():
                    console.print(f"[green]✓ 进程运行中[/green]")
                else:
                    console.print(f"[yellow]⚠ 进程未运行，查看日志：journalctl --user -u lihua-desktop[/yellow]")
                return
            else:
                console.print(f"[yellow]systemd-run 失败({r.returncode})，回退到 nohup[/yellow]")
                if r.stderr:
                    console.print(f"[dim]{r.stderr.strip()}[/dim]")
        except Exception as e:  # noqa: BLE001
            console.print(f"[yellow]systemd-run 异常：{e}，回退到 nohup[/yellow]")

    # 回退方案：nohup + setsid
    import signal as _sig
    devnull = subprocess.DEVNULL
    try:
        proc = subprocess.Popen(
            [str(binary)],
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            stdin=devnull,
            start_new_session=True,
            env={**os.environ, "RUST_LOG": "info"},
            cwd=str(desktop_dir),
        )
        # 父进程退出后不接收 SIGHUP
        try:
            _sig.signal(_sig.SIGHUP, _sig.SIG_IGN)
        except (AttributeError, ValueError):
            pass
        console.print(f"[bold green]✓ 桌面应用已后台启动[/bold green] (PID={proc.pid})")
        console.print(f"[dim]日志：{log_file}[/dim]")
        console.print(f"[dim]停止：pkill -f lihua-desktop[/dim]")
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]启动失败：{e}[/red]")
        raise typer.Exit(1) from e


# ---------------------------------------------------------------------------
# install 安装 systemd 服务
# ---------------------------------------------------------------------------

@app.command()
def install(
    user: bool = typer.Option(True, "--user/--system", help="安装到用户级 systemd"),
    enable: bool = typer.Option(True, "--enable/--no-enable", help="安装后自动启用"),
) -> None:
    """安装 systemd user service（开机自启）。"""
    _print_banner()

    # 找 venv 里的 lihua 入口
    import shutil
    lihua_bin = shutil.which("lihua")
    if not lihua_bin:
        console.print("[red]找不到 lihua 命令[/red]")
        console.print("[dim]请先 pip install -e . 安装[/dim]")
        raise typer.Exit(1)

    if user:
        svc_dir = Path.home() / ".config" / "systemd" / "user"
    else:
        svc_dir = Path("/etc/systemd/system")
    svc_dir.mkdir(parents=True, exist_ok=True)
    svc_path = svc_dir / "lihua.service"

    service_content = f"""[Unit]
Description=Lihua AI Assistant
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart={lihua_bin} serve --host 127.0.0.1 --port 7531
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
"""
    try:
        svc_path.write_text(service_content, encoding="utf-8")
    except PermissionError as e:
        console.print(f"[red]写入失败: {e}[/red]")
        raise typer.Exit(1) from e

    console.print(f"[green]✓ 已写入 service 文件[/green]: {svc_path}")

    if enable:
        import subprocess
        scope = "--user" if user else ""
        for cmd in (
            ["systemctl", scope, "daemon-reload"] if scope else ["systemctl", "daemon-reload"],
            ["systemctl", scope, "enable", "lihua.service"],
            ["systemctl", scope, "start", "lihua.service"],
        ):
            cmd = [c for c in cmd if c]
            console.print(f"[dim]$ {' '.join(cmd)}[/dim]")
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                console.print(f"[yellow]⚠ 命令返回 {r.returncode}: {r.stderr.strip()}[/yellow]")
        console.print(f"[green]✓ lihua.service 已启用并启动[/green]")
        console.print(f"[dim]状态: systemctl {'--user' if user else ''} status lihua.service[/dim]")
        console.print(f"[dim]停止: systemctl {'--user' if user else ''} stop lihua.service[/dim]")


@app.command()
def uninstall_service() -> None:
    """卸载 systemd user service。"""
    import subprocess
    scope = "--user"
    for cmd in (
        ["systemctl", scope, "stop", "lihua.service"],
        ["systemctl", scope, "disable", "lihua.service"],
    ):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 and "not loaded" not in r.stderr:
            console.print(f"[yellow]⚠ {cmd}: {r.stderr.strip()}[/yellow]")

    svc_path = Path.home() / ".config" / "systemd" / "user" / "lihua.service"
    if svc_path.exists():
        svc_path.unlink()
        console.print(f"[green]✓ 已删除 {svc_path}[/green]")
    subprocess.run(["systemctl", scope, "daemon-reload"], capture_output=True)
    console.print("[green]✓ 已卸载[/green]")


# ---------------------------------------------------------------------------
# history / audit
# ---------------------------------------------------------------------------

@app.command()
def history(
    n: int = typer.Option(20, "-n", help="显示条数"),
) -> None:
    """查看历史记录。"""
    _show_history(n)


def _show_history(n: int = 20) -> None:
    import json
    from lihua.config import history_path
    path = history_path()
    if not path.exists():
        console.print("[dim]暂无历史[/dim]")
        return
    try:
        lines = path.read_text(encoding="utf-8").strip().splitlines()
    except OSError:
        return
    from datetime import datetime
    table = Table(title=f"历史（最近 {n} 条）")
    table.add_column("时间", style="dim")
    table.add_column("状态")
    table.add_column("输入")
    table.add_column("结果", overflow="fold")
    for line in lines[-n:]:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = datetime.fromtimestamp(entry.get("ts", 0)).strftime("%m-%d %H:%M")
        status = "[green]✓[/green]" if entry.get("success") else "[red]✗[/red]"
        table.add_row(ts, status, entry.get("input", ""), entry.get("message", ""))
    console.print(table)


@app.command()
def audit(
    n: int = typer.Option(30, "-n", help="显示条数"),
) -> None:
    """查看审计日志（v0.7.10：结构化显示）。"""
    from lihua.config import audit_log_path
    from lihua.executor import parse_audit_line
    path = audit_log_path()
    if not path.exists():
        console.print("[dim]暂无审计日志[/dim]")
        return
    try:
        lines = path.read_text(encoding="utf-8").strip().splitlines()
    except OSError:
        return
    console.print(f"[bold]审计日志[/bold] [dim]({path})[/dim]")
    # 解析并美化输出
    for line in lines[-n:]:
        entry = parse_audit_line(line)
        if entry is None:
            continue
        if "raw" in entry:
            console.print(f"[dim]{entry['raw']}[/dim]")
            continue
        ts = entry.get("ts", "?")
        status = "✓" if entry.get("success") else "✗"
        safety = entry.get("safety_level", "?")
        duration = entry.get("duration", 0)
        cmd = entry.get("command", "")
        ui = entry.get("user_input") or ""
        exit_code = entry.get("exit_code", "?")
        safety_color = {"white": "green", "grey": "yellow", "black": "red"}.get(safety, "white")
        line_out = f"[dim]{ts}[/dim] {status} [{safety_color}]{safety}[/{safety_color}] {duration}s exit={exit_code}"
        if ui:
            line_out += f" [dim]用户输入:{ui}[/dim]"
        line_out += f"\n  [cyan]{cmd}[/cyan]"
        console.print(line_out)


# ---------------------------------------------------------------------------
# 直接对话命令 lihua "装QQ"（不走 run 子命令）
# ---------------------------------------------------------------------------

@app.command()
def ask(
    message: str = typer.Argument(..., help="自然语言指令"),
    yes: bool = typer.Option(False, "-y", "--yes"),
    verbose: bool = typer.Option(False, "-v", "--verbose"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """同 `lihua run`，便捷别名。"""
    run_cmd(message=message, yes=yes, verbose=verbose, dry_run=dry_run, no_llm=False)


# ===========================================================================
# v0.8.22: memory 记忆管理子命令
# 直接调 lihua.memory.MemoryStore，不走 HTTP（与 history/audit 风格一致）
# ===========================================================================

memory_app = typer.Typer(help="记忆管理")
app.add_typer(memory_app, name="memory")


def _fmt_ts(ts: float | None) -> str:
    """unix 时间戳 → 'MM-dd HH:MM' 字符串。"""
    if not ts:
        return "-"
    from datetime import datetime
    return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")


@memory_app.command("stats")
def _memory_stats() -> None:
    """记忆系统统计。"""
    from lihua.memory import get_memory_store
    store = get_memory_store()
    s = store.get_stats()
    traps = s.get("traps", {})
    layers = s.get("layers", {})
    console.print(Panel(
        f"[bold]总交互[/bold]: {s.get('total_interactions', 0)}    "
        f"[bold]Episodes[/bold]: {s.get('episodes_count', 0)}    "
        f"[bold]知识模式[/bold]: {s.get('knowledge_patterns', 0)}\n"
        f"[bold]成功率[/bold]: {s.get('success_rate', 0)}    "
        f"[bold]首次[/bold]: {_fmt_ts(s.get('first_session'))}    "
        f"[bold]最近[/bold]: {_fmt_ts(s.get('last_session'))}\n\n"
        f"[bold]分层[/bold]: L2热={layers.get('L2_hot', {}).get('episodes_count', 0)} "
        f"L3温={layers.get('L3_warm', {}).get('episodes_count', 0)} "
        f"L4冷可归档={layers.get('L4_cold', {}).get('archivable_count', 0)}\n"
        f"[bold]踩坑[/bold]: 总{traps.get('total', 0)} 未修{traps.get('open', 0)} "
        f"已修{traps.get('fixed', 0)} 绕过{traps.get('workaround', 0)}",
        title="记忆系统统计",
        border_style="cyan",
    ))
    top_tools = s.get("top_tools", {})
    if top_tools:
        console.print("[dim]常用工具：[/dim] " + "  ".join(f"{k}×{v}" for k, v in top_tools.items()))


@memory_app.command("sessions")
def _memory_sessions(
    n: int = typer.Option(20, "-n", help="显示条数"),
) -> None:
    """列出会话（按 session_id 聚合）。"""
    from lihua.memory import get_memory_store
    sessions = get_memory_store().list_sessions(limit=n)
    if not sessions:
        console.print("[dim]暂无会话记录[/dim]")
        return
    table = Table(title=f"会话（最近 {len(sessions)} 个）")
    table.add_column("session_id", style="cyan", overflow="fold")
    table.add_column("轮次", justify="right")
    table.add_column("首条")
    table.add_column("末条")
    table.add_column("首句", overflow="fold")
    for s in sessions:
        table.add_row(
            s["session_id"][:16] + "…",
            str(s["episode_count"]),
            _fmt_ts(s["first_ts"]),
            _fmt_ts(s["last_ts"]),
            s.get("first_user_input", ""),
        )
    console.print(table)


@memory_app.command("session")
def _memory_session(
    session_id: str = typer.Argument(..., help="会话 ID"),
) -> None:
    """查看某会话的所有 episode。"""
    from lihua.memory import get_memory_store
    eps = get_memory_store().get_session_episodes(session_id, limit=100)
    if not eps:
        console.print(f"[yellow]未找到会话：{session_id}[/yellow]")
        raise typer.Exit(1)
    for i, ep in enumerate(eps, 1):
        status = "[green]✓[/green]" if ep.success else "[red]✗[/red]"
        console.print(f"{status} [dim]{_fmt_ts(ep.timestamp)}[/dim] {ep.user_input[:60]}")
        for tc in ep.tool_calls:
            tc_status = "[green]✓[/green]" if tc.get("success") else "[red]✗[/red]"
            console.print(f"    {tc_status} [cyan]{tc.get('name', '?')}[/cyan]")


@memory_app.command("knowledge")
def _memory_knowledge() -> None:
    """查看知识库模式。"""
    from lihua.memory import get_memory_store
    patterns = get_memory_store()._load_knowledge()
    if not patterns:
        console.print("[dim]暂无知识模式[/dim]")
        return
    table = Table(title=f"知识库（{len(patterns)} 个模式）")
    table.add_column("关键词", style="cyan", overflow="fold")
    table.add_column("工具链", overflow="fold")
    table.add_column("次数", justify="right")
    table.add_column("成功率")
    for p in patterns:
        table.add_row(
            " ".join(p.keywords[:6]),
            " → ".join(p.tool_chain),
            str(p.total_count),
            f"{p.success_rate:.0%}",
        )
    console.print(table)


@memory_app.command("traps")
def _memory_traps(
    status: str = typer.Option(None, "--status", help="过滤状态：open/fixed/workaround"),
) -> None:
    """查看踩坑记录。"""
    from lihua.memory import get_memory_store
    traps = get_memory_store().get_traps(status=status)
    if not traps:
        console.print("[dim]暂无踩坑记录[/dim]")
        return
    for t in traps:
        color = {"open": "red", "fixed": "green", "workaround": "yellow"}.get(t.status, "white")
        console.print(Panel(
            f"[bold]现象[/bold]: {t.symptom}\n"
            f"[bold]根因[/bold]: {t.root_cause or '(未诊断)'}\n"
            f"[bold]解决[/bold]: {t.solution or '(未修复)'}\n"
            f"[dim]相关 skill: {', '.join(t.related_skills) or '-'}  "
            f"出现 {t.occurrence_count} 次  {_fmt_ts(t.timestamp)}[/dim]",
            title=f"T{t.id:03d} [{color}]{t.status}[/{color}]",
            border_style=color,
        ))


@memory_app.command("traps-search")
def _memory_traps_search(
    keyword: str = typer.Argument(..., help="搜索关键词"),
) -> None:
    """搜索踩坑记录。"""
    from lihua.memory import get_memory_store
    traps = get_memory_store().search_traps(keywords=[keyword], limit=20)
    if not traps:
        console.print(f"[dim]未找到匹配 '{keyword}' 的踩坑记录[/dim]")
        return
    console.print(f"[green]✓ 找到 {len(traps)} 条匹配[/green]")
    for t in traps:
        color = {"open": "red", "fixed": "green", "workaround": "yellow"}.get(t.status, "white")
        console.print(f"  T{t.id:03d} [{color}]{t.status}[/{color}] {t.symptom[:70]}")


@memory_app.command("export")
def _memory_export(
    output: str = typer.Option("", "-o", "--output", help="输出文件路径（默认打印到终端）"),
) -> None:
    """导出记忆数据为 JSON。"""
    import json
    from lihua.memory import get_memory_store
    store = get_memory_store()
    data = {
        "stats": store.get_stats(),
        "recent_episodes": [ep.to_dict() for ep in store.get_recent_episodes(limit=200)],
        "traps": [t.to_dict() for t in store.get_traps()],
        "preferences": store.get_preferences().to_dict(),
    }
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if output:
        Path(output).write_text(text, encoding="utf-8")
        console.print(f"[green]✓ 已导出到 {output}[/green] ({len(text)} 字节)")
    else:
        console.print(text)


@memory_app.command("clear")
def _memory_clear(
    yes: bool = typer.Option(False, "-y", "--yes", help="跳过确认"),
) -> None:
    """清空所有记忆（不可逆）。"""
    from lihua.memory import get_memory_store
    if not yes:
        if not Confirm.ask("[bold red]确认清空所有记忆？此操作不可逆[/bold red]", default=False):
            console.print("[dim]已取消[/dim]")
            raise typer.Exit(0)
    get_memory_store().clear_all()
    console.print("[green]✓ 所有记忆已清空[/green]")


@memory_app.command("archive")
def _memory_archive() -> None:
    """归档旧 episodes（月度归档）。"""
    from lihua.memory import get_memory_store
    info = get_memory_store().archive_old_episodes()
    console.print(Panel(
        f"[bold]可归档[/bold]: {info.get('archivable_count', 0)} 条\n"
        f"[bold]归档目录[/bold]: {info.get('archive_dir', '-')}\n"
        f"[bold]已实现[/bold]: {info.get('implemented', False)}",
        title="归档结果",
        border_style="cyan",
    ))


# ===========================================================================
# v0.8.22: self 自进化子命令（复用 lihua.self_evolve 模块）
# ===========================================================================

self_app = typer.Typer(help="自进化（重启/编译/版本号）")
app.add_typer(self_app, name="self")


@self_app.command("status")
def _self_status() -> None:
    """查看编译/重启状态。"""
    from lihua.self_evolve import read_self_status
    s = read_self_status()
    build = s.get("build") or {}
    restart = s.get("restart") or {}
    console.print(Panel(
        f"[bold]当前版本[/bold]: {s.get('current_version')}    "
        f"[bold]当前 PID[/bold]: {s.get('current_pid')}\n\n"
        f"[bold]编译[/bold]: {build.get('status', '-')}  "
        f"{build.get('message', '')}  "
        f"[dim]{_fmt_ts(build.get('finished_at') or build.get('started_at'))}[/dim]\n"
        f"[bold]重启[/bold]: {restart.get('status', '-')}  "
        f"old={restart.get('old_pid', '-')} new={restart.get('new_pid', '-')}  "
        f"[dim]{_fmt_ts(restart.get('finished_at') or restart.get('started_at'))}[/dim]",
        title="自进化状态",
        border_style="cyan",
    ))


@self_app.command("build")
def _self_build() -> None:
    """后台编译桌面端 Tauri 二进制（30-60s）。"""
    from lihua.self_evolve import trigger_build
    r = trigger_build()
    if r.get("ok"):
        console.print(f"[green]✓ {r.get('message')}[/green]")
        console.print(f"[dim]状态文件: {r.get('status_file')}[/dim]")
        console.print(f"[dim]编译日志: {r.get('build_log')}[/dim]")
        console.print(f"[dim]查进度: lihua self status[/dim]")
    else:
        console.print(f"[yellow]⚠ {r.get('error', '编译启动失败')}[/yellow]")


@self_app.command("restart")
def _self_restart(
    yes: bool = typer.Option(False, "-y", "--yes", help="跳过确认"),
) -> None:
    """重启后端服务（约 8 秒新后端就绪）。"""
    if not yes:
        if not Confirm.ask("[bold yellow]确认重启后端服务？[/bold yellow]", default=False):
            console.print("[dim]已取消[/dim]")
            raise typer.Exit(0)
    from lihua.self_evolve import trigger_restart
    r = trigger_restart()
    if r.get("ok"):
        console.print(f"[green]✓ {r.get('message')}[/green]")
        console.print(f"[dim]查进度: lihua self status[/dim]")
    else:
        console.print(f"[red]✗ {r.get('error', '重启失败')}[/red]")


@self_app.command("version-bump")
def _self_version_bump(
    version: str = typer.Argument("", help="新版本号（如 0.8.22a0），留空则自动 patch+1"),
) -> None:
    """升级 6 个版本号文件。"""
    from lihua.self_evolve import bump_version
    r = bump_version(version)
    if r.get("ok"):
        console.print(f"[green]✓ {r.get('message')}[/green]")
        for f in r.get("files_updated", []):
            console.print(f"  [dim]✓ {f}[/dim]")
    else:
        console.print(f"[yellow]⚠ {r.get('message', '版本号升级失败')}[/yellow]")
        for f in r.get("files_failed", []):
            console.print(f"  [red]✗ {f.get('file')}: {f.get('error')}[/red]")


# ===========================================================================
# v0.8.22: skill-auto 技能自生成子命令
# ===========================================================================

skill_auto_app = typer.Typer(help="技能自生成管理")
app.add_typer(skill_auto_app, name="skill-auto")


@skill_auto_app.command("list")
def _skill_auto_list() -> None:
    """列出自生成技能。"""
    from lihua.skill_generator import list_auto_skills
    skills = list_auto_skills()
    if not skills:
        console.print("[dim]暂无自生成技能[/dim]")
        return
    table = Table(title=f"自生成技能（{len(skills)} 个）")
    table.add_column("名称", style="cyan")
    table.add_column("版本")
    table.add_column("描述", overflow="fold")
    table.add_column("触发词", overflow="fold")
    for s in skills:
        table.add_row(s["name"], s["version"], s["description"], " / ".join(s["triggers"][:3]))
    console.print(table)


@skill_auto_app.command("stats")
def _skill_auto_stats() -> None:
    """技能自生成统计。"""
    from lihua.skill_generator import get_skill_stats
    s = get_skill_stats()
    console.print(Panel(
        f"[bold]自生成技能[/bold]: {s.get('auto_skills_count', 0)} 个\n"
        f"[bold]重复模式[/bold]: {s.get('repeated_patterns_count', 0)} 个（阈值 {s.get('threshold', '-')}）\n"
        f"[bold]目录[/bold]: {s.get('auto_skills_dir', '-')}",
        title="技能自生成统计",
        border_style="cyan",
    ))
    if s.get("auto_skills"):
        console.print(f"[dim]技能列表: {', '.join(s['auto_skills'])}[/dim]")


@skill_auto_app.command("patterns")
def _skill_auto_patterns() -> None:
    """检测重复工具链（可固化为技能）。"""
    from lihua.skill_generator import detect_repeated_patterns
    patterns = detect_repeated_patterns()
    if not patterns:
        console.print("[dim]暂无重复模式（未达固化阈值）[/dim]")
        return
    table = Table(title=f"重复工具链（{len(patterns)} 个）")
    table.add_column("工具链", style="cyan", overflow="fold")
    table.add_column("次数", justify="right")
    table.add_column("成功率")
    table.add_column("建议", overflow="fold")
    for p in patterns:
        table.add_row(
            " → ".join(p["tool_chain"]),
            str(p["total_count"]),
            f"{p['success_rate']:.0%}",
            p["suggestion"],
        )
    console.print(table)


@skill_auto_app.command("reload")
def _skill_auto_reload() -> None:
    """重新加载自生成技能。"""
    from lihua.skill_generator import reload_registry
    ok, msg, count = reload_registry()
    if ok:
        console.print(f"[green]✓ {msg}（{count} 个）[/green]")
    else:
        console.print(f"[red]✗ {msg}[/red]")


@skill_auto_app.command("delete")
def _skill_auto_delete(
    name: str = typer.Argument(..., help="技能名"),
) -> None:
    """删除一个自生成技能。"""
    from lihua.skill_generator import delete_auto_skill
    ok, msg = delete_auto_skill(name)
    if ok:
        console.print(f"[green]✓ {msg}[/green]")
    else:
        console.print(f"[red]✗ {msg}[/red]")
        raise typer.Exit(1)


@skill_auto_app.command("path")
def _skill_auto_path() -> None:
    """显示自生成技能目录。"""
    from lihua.skill_generator import auto_skills_dir
    p = auto_skills_dir()
    console.print(f"自生成技能目录：[cyan]{p}[/cyan]")


# ===========================================================================
# v0.8.22: plugin 插件管理子命令
# ===========================================================================

plugin_app = typer.Typer(help="插件管理")
app.add_typer(plugin_app, name="plugin")


@plugin_app.command("list")
def _plugin_list() -> None:
    """列出插件。"""
    from lihua.plugin_loader import get_loader
    plugins = get_loader().list_plugins()
    if not plugins:
        console.print("[dim]暂无插件[/dim]")
        return
    table = Table(title=f"插件（{len(plugins)} 个）")
    table.add_column("名称", style="cyan")
    table.add_column("状态")
    table.add_column("版本")
    table.add_column("描述", overflow="fold")
    for p in plugins:
        color = {"loaded": "green", "disabled": "yellow", "error": "red", "skipped": "dim"}.get(
            p.status, "white"
        )
        table.add_row(p.name, f"[{color}]{p.status}[/{color}]", p.meta.version, p.meta.description)
    console.print(table)


@plugin_app.command("stats")
def _plugin_stats() -> None:
    """插件统计。"""
    from lihua.plugin_loader import get_loader
    s = get_loader().stats()
    console.print(Panel(
        f"[bold]总数[/bold]: {s.get('total', 0)}    "
        f"[bold]已加载[/bold]: {s.get('loaded', 0)}    "
        f"[bold]禁用[/bold]: {s.get('disabled', 0)}    "
        f"[bold]出错[/bold]: {s.get('error', 0)}",
        title="插件统计",
        border_style="cyan",
    ))


@plugin_app.command("info")
def _plugin_info(
    name: str = typer.Argument(..., help="插件名"),
) -> None:
    """查看插件详情。"""
    from lihua.plugin_loader import get_loader
    p = get_loader().get_plugin(name)
    if not p:
        console.print(f"[red]未找到插件: {name}[/red]")
        raise typer.Exit(1)
    console.print(Panel(
        f"[bold cyan]{p.name}[/bold cyan] v{p.meta.version}（[bold]{p.status}[/bold]）\n"
        f"{p.meta.description}\n\n"
        f"[dim]作者: {p.meta.author or '-'}[/dim]\n"
        f"[dim]路径: {p.path}[/dim]\n"
        f"[dim]注册 sections: {', '.join(p.registered_sections) or '-'}[/dim]"
        + (f"\n[red]错误: {p.error}[/red]" if p.error else ""),
        title="插件详情",
        border_style="cyan",
    ))


@plugin_app.command("reload")
def _plugin_reload() -> None:
    """重新加载所有插件。"""
    from lihua.plugin_loader import get_loader
    result = get_loader().reload()
    console.print(f"[green]✓ 已重新加载 {len(result)} 个插件[/green]")


@plugin_app.command("enable")
def _plugin_enable(
    name: str = typer.Argument(..., help="插件名"),
) -> None:
    """启用插件（持久化到 plugins.toml）。"""
    from lihua.plugin_loader import get_loader
    ok, msg = get_loader().enable_plugin(name)
    (console.print(f"[green]✓ {msg}[/green]") if ok
     else console.print(f"[red]✗ {msg}[/red]"))


@plugin_app.command("disable")
def _plugin_disable(
    name: str = typer.Argument(..., help="插件名"),
) -> None:
    """禁用插件（持久化到 plugins.toml）。"""
    from lihua.plugin_loader import get_loader
    ok, msg = get_loader().disable_plugin(name)
    (console.print(f"[green]✓ {msg}[/green]") if ok
     else console.print(f"[red]✗ {msg}[/red]"))


@plugin_app.command("path")
def _plugin_path() -> None:
    """显示插件目录和配置文件路径。"""
    from lihua.plugin_loader import plugins_dir, plugins_config_path
    console.print(f"插件目录：[cyan]{plugins_dir()}[/cyan]")
    console.print(f"插件配置：[cyan]{plugins_config_path()}[/cyan]")


# ===========================================================================
# v0.8.22: prompt 模块查看子命令（只读——enable/disable 只改内存不持久化）
# ===========================================================================

prompt_app = typer.Typer(help="Prompt 模块查看（只读）")
app.add_typer(prompt_app, name="prompt")


@prompt_app.command("sections")
def _prompt_sections() -> None:
    """列出 Prompt 模块（按优先级排序）。"""
    from lihua.prompt_builder import get_builder
    sections = get_builder().list_sections()
    table = Table(title=f"Prompt 模块（{len(sections)} 个）")
    table.add_column("优先级", justify="right", style="dim")
    table.add_column("名称", style="cyan")
    table.add_column("状态")
    table.add_column("标签")
    table.add_column("描述", overflow="fold")
    for s in sections:
        status = "[green]启用[/green]" if s.enabled else "[dim]禁用[/dim]"
        table.add_row(str(s.priority), s.name, status, ", ".join(s.tags), s.description)
    console.print(table)


@prompt_app.command("stats")
def _prompt_stats() -> None:
    """Prompt 模块统计。"""
    from lihua.prompt_builder import get_builder
    s = get_builder().stats()
    console.print(Panel(
        f"[bold]总数[/bold]: {s.get('total', 0)}    "
        f"[bold]启用[/bold]: {s.get('enabled', 0)}    "
        f"[bold]禁用[/bold]: {s.get('disabled', 0)}",
        title="Prompt 模块统计",
        border_style="cyan",
    ))


# ===========================================================================
# v0.8.22: analytics 自监控分析子命令
# ===========================================================================

analytics_app = typer.Typer(help="自监控分析")
app.add_typer(analytics_app, name="analytics")


@analytics_app.command("overview")
def _analytics_overview() -> None:
    """总览统计。"""
    from lihua import analytics
    ov = analytics.get_overview()
    console.print(Panel(
        f"[bold]总交互[/bold]: {ov.get('total_interactions', 0)}    "
        f"[bold]工具调用[/bold]: {ov.get('total_tool_calls', 0)}\n"
        f"[bold]成功率[/bold]: {ov.get('success_rate', 0)}    "
        f"[bold]平均耗时[/bold]: {ov.get('avg_duration', 0)}s    "
        f"[bold]活跃天数[/bold]: {ov.get('active_days', 0)}\n"
        f"[bold]知识模式[/bold]: {ov.get('knowledge_patterns', 0)}    "
        f"[bold]Episodes[/bold]: {ov.get('memory_episodes', 0)}",
        title="总览",
        border_style="cyan",
    ))
    top_tools = ov.get("top_tools", {})
    if top_tools:
        console.print("[dim]常用工具：[/dim] " + "  ".join(f"{k}×{v}" for k, v in list(top_tools.items())[:8]))


@analytics_app.command("report")
def _analytics_report() -> None:
    """完整文本报告。"""
    from lihua import analytics
    console.print(analytics.generate_text_report())


@analytics_app.command("tools")
def _analytics_tools() -> None:
    """工具使用统计。"""
    from lihua import analytics
    ts = analytics.get_tool_stats()
    console.print(f"[bold]共 {ts.get('total_tools', 0)} 种工具，调用 {ts.get('total_calls', 0)} 次[/bold]")
    tools = ts.get("tools", [])
    if not tools:
        return
    table = Table(title="工具使用")
    table.add_column("工具", style="cyan")
    table.add_column("次数", justify="right")
    table.add_column("成功率")
    table.add_column("平均耗时", justify="right")
    for t in tools[:15]:
        table.add_row(
            t.get("name", "?"),
            str(t.get("count", 0)),
            f"{t.get('success_rate', 0):.0%}",
            f"{t.get('avg_duration', 0):.1f}s",
        )
    console.print(table)


@analytics_app.command("errors")
def _analytics_errors() -> None:
    """错误分析。"""
    from lihua import analytics
    ea = analytics.get_error_analysis()
    console.print(Panel(
        f"[bold]失败交互[/bold]: {ea.get('total_failed_episodes', 0)}    "
        f"[bold]失败率[/bold]: {ea.get('fail_rate', 0):.1%}\n"
        f"[bold]失败最多的工具[/bold]: {', '.join(list((ea.get('top_fail_tools') or {}).keys())[:5]) or '-'}",
        title="错误分析",
        border_style="red",
    ))
    cats = ea.get("error_categories") or {}
    if cats:
        console.print(f"[dim]错误分类: {cats}[/dim]")


@analytics_app.command("skills")
def _analytics_skills() -> None:
    """Skill 使用统计。"""
    from lihua import analytics
    su = analytics.get_skill_usage()
    console.print(Panel(
        str(su),
        title="Skill 使用统计",
        border_style="cyan",
    ))


@analytics_app.command("suggestions")
def _analytics_suggestions() -> None:
    """改进建议。"""
    from lihua import analytics
    suggestions = analytics.get_suggestions()
    if not suggestions:
        console.print("[green]✓ 暂无改进建议（各项指标良好）[/green]")
        return
    for s in suggestions:
        sev = s.get("severity", "info")
        color = {"warning": "yellow", "info": "cyan", "error": "red"}.get(sev, "white")
        console.print(Panel(
            f"[bold]{s.get('title', '')}[/bold]\n"
            f"{s.get('detail', '')}\n"
            f"[dim]建议: {s.get('suggestion', '')}[/dim]",
            title=f"[{color}]{sev}[/{color}] {s.get('type', '')}",
            border_style=color,
        ))


if __name__ == "__main__":
    app()
