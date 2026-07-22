"""把 Skill YAML 转成 OpenAI function calling 格式的工具定义。

LLM Agent 用这些工具定义来决定调用哪个 Skill。
工具定义包含：name / description / parameters（JSON Schema）。

设计原则：
1. 每个 Skill → 一个 tool
2. tool name = skill name（如 install_app / troubleshoot_no_sound）
3. tool description = skill description + when_to_use（triggers + examples）
4. tool parameters = skill parameters 转 JSON Schema
5. 不暴露 Skill 内部的 steps / aliases / safety（这些是执行细节，LLM 不需要知道）
"""

from __future__ import annotations

from typing import Any

from lihua.skills import SkillDef, SkillRegistry


# Skill 分类定义（v0.7.12 引入）
# 用于 catalog 分组展示 + skill_to_tool 的 description 前缀
# key = YAML 里的 category 值，value = 给 LLM 看的中文类别名
SKILL_CATEGORIES: dict[str, str] = {
    "system": "系统管理",
    "file": "文件操作",
    "file_adv": "文件管理高级",
    "network": "网络",
    "network_sys": "网络系统高级",
    "hardware": "硬件外设",
    "desktop": "桌面环境",
    "desktop_hw": "桌面硬件扩展",
    "mirror": "软件源镜像",
    "install": "软件安装增强",
    "app": "应用操作",
    "process": "进程性能",
    "media_dev": "多媒体开发环境",
    "troubleshoot": "新手救急诊断",
    "mvp": "MVP 基础",
    "other": "其他",
}


def _param_to_schema(p) -> dict[str, Any]:  # noqa: ANN001
    """把 SkillParam 转成 JSON Schema 属性。"""
    schema: dict[str, Any] = {
        "type": p.type if p.type in ("string", "number", "integer", "boolean", "array") else "string",
        "description": p.description or f"参数 {p.name}",
    }
    if p.default is not None:
        schema["default"] = p.default
    return schema


def skill_to_tool(skill: SkillDef) -> dict[str, Any]:
    """把一个 Skill 转成 OpenAI function calling 格式的工具定义。

    返回格式：
        {
            "type": "function",
            "function": {
                "name": "install_app",
                "description": "[软件安装增强] 安装应用程序\\n触发场景：装/安装/装个...\\n示例：装QQ / 装个微信",
                "parameters": {
                    "type": "object",
                    "properties": {"target": {"type": "string", "description": "应用名"}},
                    "required": ["target"],
                },
            },
        }

    v0.7.12 改造：description 加 [类别] 前缀，让 LLM 在 tools 列表里也能看到类别。
    """
    # 类别前缀（v0.7.12）
    cat_name = SKILL_CATEGORIES.get(skill.category or "other", "其他")
    cat_prefix = f"[{cat_name}] "

    # 构造 description：[类别] + skill 描述 + 触发场景 + 示例
    desc_parts: list[str] = []
    if skill.description:
        desc_parts.append(f"{cat_prefix}{skill.description}")
    else:
        desc_parts.append(f"{cat_prefix}{skill.name}")
    if skill.triggers:
        triggers_str = " / ".join(skill.triggers[:8])
        desc_parts.append(f"触发场景：{triggers_str}")
    if skill.examples:
        examples_str = " | ".join(skill.examples[:5])
        desc_parts.append(f"示例：{examples_str}")
    # v0.8.17: 注入已验证规则（从 usage_log 提炼的"已验证稳定规则"）
    # 让 LLM 调 skill 时看到这些规则，参考 OpenClaw "实践即认识" 设计
    if skill.rules:
        rules_lines = []
        for r in skill.rules[:10]:  # 最多注入 10 条，防 description 过长
            cond = r.get("condition", "")
            act = r.get("action", "")
            reason = r.get("reason", "")
            conf = r.get("confidence", 0.5)
            if not cond and not act:
                continue
            rules_lines.append(f"  - [{conf:.0%}] {cond} → {act}（{reason}）")
        if rules_lines:
            desc_parts.append("已验证规则：\n" + "\n".join(rules_lines))
    description = "\n".join(desc_parts)

    # 构造 parameters JSON Schema
    properties: dict[str, Any] = {}
    required: list[str] = []
    for p in skill.parameters:
        properties[p.name] = _param_to_schema(p)
        if p.required:
            required.append(p.name)

    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if properties:
        parameters_schema["required"] = required
    else:
        # 无参数的 skill 也要给空 properties，避免 LLM 困惑
        parameters_schema["properties"] = {}

    return {
        "type": "function",
        "function": {
            "name": skill.name,
            "description": description,
            "parameters": parameters_schema,
        },
    }


def build_run_shell_tool() -> dict[str, Any]:
    """v0.8.0 新增：万能兜底工具 run_shell。

    让 LLM 能执行任意 shell 命令，覆盖预定义 skill 没有覆盖的长尾任务。
    命令走 safety.py 分类：黑名单拒绝 / 灰名单弹确认 / 白名单自动执行。

    设计原则：
    1. 不依赖 YAML——直接 Python 构造，避免给 SkillRegistry 加特殊 skill
    2. parameters 必填 command + intent——intent 是 LLM 给用户看的中文说明
    3. timeout 有上限（600s），防止 LLM 调 sleep 10000 卡死
    4. description 写清楚"优先用预定义 skill"，避免 LLM 滥用
    """
    return {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": (
                "[万能兜底] 执行任意 shell 命令（bash 语法，支持管道/重定向/变量）\n"
                "触发场景：预定义 skill 覆盖不到的任务（配置 nginx / 批量改文件 / 查端口占用 / 写脚本等）\n"
                "示例：run_shell(command=\"lsof -i:8080\", intent=\"查看 8080 端口被哪个进程占用\")\n"
                "注意：\n"
                "- 优先用预定义 skill（install_app / troubleshoot / beautify_ubuntu 等），它们经过测试更稳定\n"
                "- 黑名单命令会被拒绝（rm -rf /、dd、mkfs、curl|sh 等）\n"
                "- 灰名单命令会弹确认（sudo/pkexec、apt purge、改 /etc 配置等）\n"
                "- 白名单命令自动执行（ls/cat/grep/find/ps/df 等只读命令）\n"
                "- 一次只执行一条命令，观察输出后再决定下一步"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 shell 命令（bash 语法，支持 | > < && 等元字符）",
                    },
                    "intent": {
                        "type": "string",
                        "description": "用中文一句话说明为什么要执行这条命令（给用户看确认弹窗用）",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时秒数（默认 300，最长 1800）",
                        "default": 300,
                    },
                },
                "required": ["command", "intent"],
            },
        },
    }


def build_read_file_tool() -> dict[str, Any]:
    """v0.8.2 新增：读文件工具。

    让 LLM 能读文件内容，避免用 run_shell + cat 的组合（更高效、更安全）。
    - 自动带行号（便于后续 edit_file 定位）
    - 长文件自动截断（防爆 token）
    - 支持指定行范围（读大文件的某一段）
    - 只读，不走 safety.py（白名单）
    """
    return {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "[文件操作] 读取文件内容（带行号）\n"
                "触发场景：查看配置文件 / 阅读脚本 / 检查日志 / 读代码\n"
                "示例：read_file(path=\"/etc/nginx/nginx.conf\")\n"
                "示例：read_file(path=\"~/project/main.py\", start_line=50, end_line=100)\n"
                "注意：\n"
                "- 自动带行号输出，便于后续 edit_file 定位\n"
                "- 长文件自动截断到 200 行（可用 start_line/end_line 读指定段落）\n"
                "- 二进制文件会返回提示而不是乱码\n"
                "- 路径支持 ~ 展开"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径（支持 ~ 展开）",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "起始行号（从 1 开始，默认 1）",
                        "default": 1,
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "结束行号（默认到文件尾，最多读 200 行）",
                    },
                },
                "required": ["path"],
            },
        },
    }


def build_write_file_tool() -> dict[str, Any]:
    """v0.8.2 新增：写文件工具。

    让 LLM 能写文件，避免用 run_shell + echo/cat << EOF 的复杂语法。
    - 覆盖模式（truncate + write）
    - 自动创建父目录
    - 走灰名单 confirm（写文件是不可逆操作）
    - 路径限制：只允许用户主目录及其子目录（防 LLM 改系统文件）
    """
    return {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "[文件操作] 写文件（覆盖模式）\n"
                "触发场景：创建脚本 / 写配置 / 生成代码 / 保存输出\n"
                "示例：write_file(path=\"~/bin/clean_cache.sh\", content=\"#!/bin/bash\\nrm -rf ~/.cache/*\")\n"
                "注意：\n"
                "- 覆盖模式：如果文件已存在会被覆盖，会弹确认\n"
                "- 自动创建父目录（mkdir -p）\n"
                "- 路径限制：只允许用户主目录及其子目录（~ 或 /home/user/...）\n"
                "- 写系统目录（/etc /usr 等）请用 run_shell + pkexec"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径（支持 ~ 展开，必须在用户主目录下）",
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的完整内容",
                    },
                    "intent": {
                        "type": "string",
                        "description": "用中文一句话说明为什么要写这个文件（给用户看确认弹窗用）",
                    },
                },
                "required": ["path", "content", "intent"],
            },
        },
    }


def build_edit_file_tool() -> dict[str, Any]:
    """v0.8.2 新增：编辑文件工具。

    让 LLM 能精确替换文件内容，避免用 sed -i 的复杂正则。
    - old_string → new_string 精确替换
    - old_string 必须在文件中唯一存在（避免误替换）
    - 走灰名单 confirm
    - 路径限制：只允许用户主目录及其子目录

    这是 SWE-agent 风格的 ACI（Agent-Computer Interface）工具，
    比 sed -i 更安全（不会因为正则错误破坏文件）。
    """
    return {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "[文件操作] 精确替换文件内容（SWE-agent 风格）\n"
                "触发场景：改配置项 / 修代码 bug / 替换文本\n"
                "示例：edit_file(path=\"~/app/config.yml\", old_string=\"port: 8080\", new_string=\"port: 9090\", intent=\"改端口\")\n"
                "注意：\n"
                "- old_string 必须在文件中唯一存在（否则报错，需要提供更多上下文）\n"
                "- 会弹确认，用户看到 old → new 的 diff\n"
                "- 路径限制：只允许用户主目录及其子目录\n"
                "- 改系统文件请用 run_shell + pkexec"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径（支持 ~ 展开，必须在用户主目录下）",
                    },
                    "old_string": {
                        "type": "string",
                        "description": "要替换的原文（必须在文件中唯一存在）",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "替换后的新文本",
                    },
                    "intent": {
                        "type": "string",
                        "description": "用中文一句话说明为什么要改（给用户看确认弹窗用）",
                    },
                },
                "required": ["path", "old_string", "new_string", "intent"],
            },
        },
    }


def build_run_python_tool() -> dict[str, Any]:
    """v0.8.3 新增：执行 Python 代码工具。

    让 LLM 能跑 Python 脚本，覆盖 shell 不擅长的场景：
    - 数据处理（JSON/CSV 解析、批量改文件名、正则复杂替换）
    - 系统管理（os.walk 找文件、shutil 批量操作、psutil 进程管理）
    - 网络请求（requests 库调用 API、爬虫）
    - 复杂逻辑（LLM 写不进 shell 一行的算法）

    设计原则：
    1. 走灰名单 confirm——用户看到代码预览（前 500 字符）+ intent
    2. 速率限制：MAX_RUN_PYTHON_CALLS = 10（比 run_shell 更严，因为 Python 能做更多事）
    3. timeout 默认 30s，上限 300s（Python 脚本通常比 shell 命令慢）
    4. 用 venv 的 python 跑（不是系统 python）——确保能 import 已装的库
    5. 工作目录 = 用户主目录（cwd = ~）
    6. 不做沙箱——信任 LLM + 用户 confirm（沙箱化是 v0.9 的事）
    """
    return {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": (
                "[万能兜底] 执行 Python 3 代码（覆盖 shell 不擅长的场景）\n"
                "触发场景：\n"
                "- 数据处理：JSON/CSV 解析、批量改文件名、正则复杂替换\n"
                "- 系统管理：os.walk 找文件、shutil 批量操作、psutil 进程管理\n"
                "- 网络请求：requests 库调用 API、爬虫\n"
                "- 复杂逻辑：算法、循环、条件判断、异常处理\n"
                "示例：run_python(code=\"import json\\nprint(json.dumps({'a':1}, indent=2))\", intent=\"格式化 JSON\")\n"
                "注意：\n"
                "- 走灰名单 confirm，用户看到代码预览再决定\n"
                "- 用 venv 的 python（能 import 已装的库如 requests / psutil）\n"
                "- 工作目录是用户主目录（~）\n"
                "- 默认超时 30 秒，最长 300 秒\n"
                "- 单次对话最多 10 次 run_python（防无限循环）\n"
                "- 不要用 run_python 替代简单 shell 命令（如 ls/cat/grep）——那些用 run_shell"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "要执行的 Python 3 代码（直接执行，不需要 main 函数）",
                    },
                    "intent": {
                        "type": "string",
                        "description": "用中文一句话说明为什么要跑这段代码（给用户看确认弹窗用）",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时秒数（默认 30，最长 300）",
                        "default": 30,
                    },
                },
                "required": ["code", "intent"],
            },
        },
    }


def build_read_log_tool() -> dict[str, Any]:
    """v0.8.7: read_log 工具——让 LLM 自我诊断问题。

    设计原则：
    1. 不走 confirm（只读操作，安全）
    2. 默认读自己的日志 ~/.local/share/lihua/lihua.log 最后 100 行
    3. 支持 level 过滤（ERROR/WARNING/INFO）
    4. 支持读其他日志（/var/log/syslog 等，但权限不足会失败）
    5. lines 上限 500（防 token 爆炸）
    """
    return {
        "type": "function",
        "function": {
            "name": "read_log",
            "description": (
                "[自我诊断] 读日志文件——Lihua 自己的日志或系统日志\n"
                "触发场景：\n"
                "- 自我诊断：用户反馈'点确认却提示取消' → read_log 看 confirm_cb 是否超时\n"
                "- 错误回溯：用户说'上次操作失败了' → read_log 看历史错误\n"
                "- 行为审计：检查 LLM 自己调过哪些工具、哪些失败、为什么\n"
                "- 系统问题：读 /var/log/syslog 看系统级错误\n"
                "示例：\n"
                "- read_log() → 读自己日志最后 100 行\n"
                "- read_log(level='ERROR', lines=50) → 只看自己的 ERROR 日志\n"
                "- read_log(log_file='/var/log/syslog', lines=200) → 读系统日志\n"
                "注意：\n"
                "- 不走 confirm（只读操作）\n"
                "- 系统日志可能需要 sudo，权限不足时改用 run_shell + sudo journalctl\n"
                "- 优先用 read_log 诊断问题，比 run_shell + tail/grep 更高效"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "lines": {
                        "type": "integer",
                        "description": "读最后 N 行（默认 100，最多 500）",
                        "default": 100,
                    },
                    "level": {
                        "type": "string",
                        "enum": ["ERROR", "WARNING", "INFO", "DEBUG"],
                        "description": "过滤日志级别（默认不过滤）",
                    },
                    "log_file": {
                        "type": "string",
                        "description": "日志文件路径（默认 ~/.local/share/lihua/lihua.log，可选 /var/log/syslog 等）",
                        "default": "~/.local/share/lihua/lihua.log",
                    },
                },
                "required": [],
            },
        },
    }


def build_self_restart_tool() -> dict[str, Any]:
    """v0.8.9: self_restart 工具——让 LLM 能重启后端服务。

    让 LLM 改完 Python 代码后能重启后端让代码生效。
    走 confirm（会中断当前 SSE 流）。
    """
    return {
        "type": "function",
        "function": {
            "name": "self_restart",
            "description": (
                "[自进化] 重启后端服务（让 Python 代码改动生效）\n"
                "触发场景：\n"
                "- 改完 src/lihua/ 下的 Python 代码后，重启让代码生效\n"
                "- 修复 bug 后重启验证修复效果\n"
                "- 配置文件改完后重启加载新配置\n"
                "示例：self_restart(intent='改完 server.py 的 confirm 逻辑，重启生效')\n"
                "注意：\n"
                "- 走 confirm（会中断当前对话，用户必须确认）\n"
                "- 重启约 3 秒，期间后端不可用\n"
                "- 新后端启动后需要重新发起对话\n"
                "- 重启不影响桌面端 Tauri 进程，只重启 Python 后端"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "description": "用中文一句话说明为什么要重启（给用户看确认弹窗用）",
                    },
                },
                "required": ["intent"],
            },
        },
    }


def build_self_build_tool() -> dict[str, Any]:
    """v0.8.9: self_build 工具——让 LLM 能编译桌面端。

    让 LLM 改完 Rust 代码后能重新编译桌面端二进制。
    走 confirm（长时间任务，CPU 占用高）。
    编译在后台执行，用 self_status 查进度。
    """
    return {
        "type": "function",
        "function": {
            "name": "self_build",
            "description": (
                "[自进化] 后台编译桌面端 Tauri 二进制（让 Rust 代码改动生效）\n"
                "触发场景：\n"
                "- 改完 desktop/src-tauri/src/lib.rs 后编译让改动生效\n"
                "- 升级桌面端版本号后重新编译\n"
                "- 修复桌面端 bug 后编译验证\n"
                "示例：self_build(intent='改完 lib.rs 的端口清理逻辑，重新编译')\n"
                "注意：\n"
                "- 走 confirm（长时间任务，约 30-60 秒）\n"
                "- 编译在后台执行，不阻塞当前对话\n"
                "- 编译完成后用 self_status 查结果\n"
                "- 编译成功后需要重启桌面端（kill 旧进程 + 启动新二进制）才生效\n"
                "- 编译日志在 /tmp/lihua-build.log"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "description": "用中文一句话说明为什么要编译（给用户看确认弹窗用）",
                    },
                },
                "required": ["intent"],
            },
        },
    }


def build_self_status_tool() -> dict[str, Any]:
    """v0.8.9: self_status 工具——查询编译/重启状态。

    只读，不走 confirm。让 LLM 能轮询编译进度。
    """
    return {
        "type": "function",
        "function": {
            "name": "self_status",
            "description": (
                "[自进化] 查询编译/重启状态\n"
                "触发场景：\n"
                "- self_build 后轮询编译进度\n"
                "- self_restart 后验证新后端是否就绪\n"
                "- 检查当前后端 PID 和版本号\n"
                "示例：\n"
                "- self_status() → 查询编译/重启状态\n"
                "注意：\n"
                "- 不走 confirm（只读操作）\n"
                "- 编译完成后状态会变成 done + exit_code\n"
                "- 重启完成后状态会变成 done + new_pid"
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    }


def build_self_version_bump_tool() -> dict[str, Any]:
    """v0.8.9: self_version_bump 工具——一键升级 6 个版本号文件。

    让 LLM 改完代码后能一键升级版本号，避免手动改 6 个文件容易遗漏。
    走 confirm（修改项目文件，用户应该知道）。
    """
    return {
        "type": "function",
        "function": {
            "name": "self_version_bump",
            "description": (
                "[自进化] 一键升级 6 个版本号文件（Python + Rust 全格式）\n"
                "触发场景：\n"
                "- 改完代码准备发布新版本时\n"
                "- 修复 bug 后升级 patch 版本号\n"
                "- self_restart / self_build 前升级版本号便于回滚\n"
                "示例：\n"
                "- self_version_bump(intent='修复 T074 后升级版本号') → 自动 patch+1\n"
                "- self_version_bump(intent='发布 0.9.0', version='0.9.0a0') → 指定版本号\n"
                "注意：\n"
                "- 走 confirm（修改 6 个项目文件，用户必须确认）\n"
                "- 不传 version 参数则自动 patch+1（如 0.8.9a0 → 0.8.10a0）\n"
                "- 升级后 Python 版本号需 self_restart 生效\n"
                "- Rust 版本号需 self_build + 重启桌面端生效\n"
                "- 6 个文件：__init__.py / pyproject.toml / package.json / Cargo.toml / tauri.conf.json / lib.rs"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "description": "用中文一句话说明为什么升级版本号（给用户看确认弹窗用）",
                    },
                    "version": {
                        "type": "string",
                        "description": "（可选）指定新版本号，如 '0.9.0a0'。不传则自动 patch+1",
                    },
                },
                "required": ["intent"],
            },
        },
    }


def build_memory_recall_tool() -> dict[str, Any]:
    """v0.8.11: memory_recall 工具——让 LLM 主动检索历史经验。

    二次进化第一支柱：记忆系统的对外查询接口。
    LLM 在面对复杂/模糊问题时可主动调用，检索：
    1. 知识库中类似问题曾用过的工具链 + 成功率
    2. 历史情景记忆中相关案例（用户输入 + 工具调用 + 结果）

    只读操作，不走 confirm。返回格式化文本给 LLM 阅读后决策。
    """
    return {
        "type": "function",
        "function": {
            "name": "memory_recall",
            "description": (
                "[记忆] 检索过去的相关交互经验（跨会话长期记忆）\n"
                "触发场景：\n"
                "- 遇到似曾相识的问题时，查过去怎么解决的\n"
                "- 用户说'上次那个问题' / '之前那个方法' → 查历史案例\n"
                "- 复杂任务前先看有没有现成经验可复用\n"
                "- 想知道某类问题历史上成功率多少、用过哪些工具\n"
                "示例：\n"
                "- memory_recall(query='显卡驱动黑屏') → 查相关历史经验\n"
                "- memory_recall(query='端口占用') → 查过去如何排查端口问题\n"
                "注意：\n"
                "- 不走 confirm（只读操作）\n"
                "- 系统每次对话开始已自动注入相关记忆，本工具用于主动深挖\n"
                "- 返回内容含：历史经验（工具链+成功率）、相关案例（用户输入+工具+结果）\n"
                "- 没有相关经验时返回空，按常规流程处理即可"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "要检索的问题或关键词（自然语言即可，系统会自动提取关键词）",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最多返回几条案例（默认 5，最多 20）",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    }


def build_create_skill_tool() -> dict[str, Any]:
    """v0.8.12: create_skill 工具——让 LLM 主动生成新技能。

    二次进化第二支柱：技能自生成的对外接口。
    LLM 在看到某类任务反复出现、或某个工具链特别有效时，可调用本工具把
    工具链固化成 YAML 技能，下次直接用 skill 名调用，更稳定更高效。

    走 confirm（会写入 ~/.config/lihua/skills/auto_generated/ 文件）。
    生成后自动 reload SkillRegistry，新技能立即可用。
    """
    return {
        "type": "function",
        "function": {
            "name": "create_skill",
            "description": (
                "[自进化] 创建一个新技能（固化经验为 YAML）\n"
                "触发场景：\n"
                "- 某个工具链（如 run_shell + sed）反复用，值得固化\n"
                "- 用户说'以后这种事直接这么办' → 把流程做成技能\n"
                "- 看到记忆系统中某工具链出现 3+ 次且成功率 ≥ 80%\n"
                "- 解决了复杂任务，想把步骤保存下来供下次复用\n"
                "示例：\n"
                "- create_skill(name='clean_docker_cache', description='清理 Docker 缓存', "
                "triggers=['清理docker', 'docker空间'], steps=[...])\n"
                "- create_skill(name='check_gpu_status', description='查看 GPU 状态', "
                "triggers=['显卡状态', 'GPU状态'], steps=[...])\n"
                "约束：\n"
                "- 技能名必须小写字母开头，只含小写字母/数字/下划线\n"
                "- 不能与内置技能同名（会拒绝）\n"
                "- steps 中的 command 不能含危险命令（rm -rf /、mkfs、dd of=/dev/ 等）\n"
                "- 走 confirm：用户确认后才写入文件\n"
                "- 生成后自动 reload SkillRegistry，立即可用"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "技能名（小写字母开头，只含小写字母/数字/下划线，最多 64 字符）",
                    },
                    "description": {
                        "type": "string",
                        "description": "技能用途的一句话描述",
                    },
                    "triggers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "触发关键词列表（中文 2-6 字片段为佳，如 ['清理缓存', 'docker空间']）",
                    },
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "step 名（如 'install'）"},
                                "type": {
                                    "type": "string",
                                    "enum": ["command", "verify", "notify", "set_var"],
                                    "description": "step 类型（默认 command）",
                                },
                                "command": {"type": "string", "description": "命令模板（支持 {{var}} 插值）"},
                                "safety": {
                                    "type": "string",
                                    "enum": ["white", "grey", "black"],
                                    "description": "安全等级（默认 white）",
                                },
                                "description": {"type": "string", "description": "step 说明"},
                            },
                            "required": ["name", "command"],
                        },
                        "description": "技能的执行步骤列表",
                    },
                    "examples": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "（可选）示例用户输入列表",
                    },
                    "parameters_schema": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "（可选）参数定义列表（name/type/required/extract/default）",
                    },
                    "allow_overwrite": {
                        "type": "boolean",
                        "description": "（可选）如果技能已存在是否覆盖（默认 false；覆盖 auto 技能时自动备份 .bak）",
                        "default": False,
                    },
                },
                "required": ["name", "description", "triggers", "steps"],
            },
        },
    }


def build_self_analyze_tool() -> dict[str, Any]:
    """v0.8.15: self_analyze 工具——让 LLM 自省，查看自己的运行数据。

    返回 Lihua 的"体检报告"：总览、工具使用统计、错误分析、改进建议。
    让 LLM 能发现自己的问题（如某工具失败率高、某类问题处理慢）并优化行为。
    """
    return {
        "type": "function",
        "function": {
            "name": "self_analyze",
            "description": (
                "[自进化] 查看 Lihua 自己的运行数据——成功率、工具使用统计、错误分析、改进建议。"
                "用于自省：发现自己哪些工具失败率高、哪类问题处理慢、知识库覆盖不足等。"
                "只读，不走 confirm。"
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    }


def build_skill_evolve_tool() -> dict[str, Any]:
    """v0.8.17: skill_evolve 工具——从 usage_log 提炼规则写入 skill YAML。

    参考 OpenClaw "实践即认识" 设计：
    - 用前读 → 按 skill 做 → 用中记（usage_log）→ 用后调（skill_evolve）
    - usage_log 反复验证的实践 → 提升为 rules（已验证稳定规则）
    - rules 被新 usage_log 证伪 → 降级或删除

    实现：读 skill 的 usage_log → 调 LLM 总结新 rules 列表 → 写入 skill YAML。
    走 confirm（修改 skill 文件，用户应该知道）。
    """
    return {
        "type": "function",
        "function": {
            "name": "skill_evolve",
            "description": (
                "[自进化] 从某个 skill 的使用记录（usage_log）提炼规则写入 rules 字段。\n"
                "触发场景：\n"
                "- 某 skill 用了 N 次后想总结经验（成功模式 / 失败模式 / 参数偏好）\n"
                "- 用户说'以后这种事直接这么办' → 把经验提炼成规则\n"
                "- self_analyze 显示某 skill 成功率低 → 调 skill_evolve 总结失败模式\n"
                "- 定期回顾：每周/每月对高频 skill 调一次 skill_evolve 让规则保持新鲜\n"
                "示例：\n"
                "- skill_evolve(skill_name='install_app') → 总结 install_app 的 usage_log 为规则\n"
                "- skill_evolve(skill_name='install_app', dry_run=true) → 只返回建议不写入文件\n"
                "工作流程：\n"
                "1. 读 skill 的 usage_log（最近 50 条）+ 现有 rules\n"
                "2. 调 LLM 总结：哪些参数模式高频成功 → 提升为规则；哪些反复失败 → 降级\n"
                "3. dry_run=false 时备份 .bak 后写入 skill YAML 的 rules 字段\n"
                "4. dry_run=true 时只返回建议规则列表（不写入）\n"
                "注意：\n"
                "- 走 confirm（修改 skill 文件，用户必须确认）\n"
                "- 只对 user / auto source 的 skill 生效（builtin 在安装目录无写权限）\n"
                "- rules 字段每条含：condition / action / reason / added_at / confidence\n"
                "- skill 的 rules 会自动注入到 tool description，下次调 skill 时 LLM 就能看到"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "要进化的 skill 名（如 'install_app'）",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "（可选）只返回建议不写入文件，默认 false（写入）",
                        "default": False,
                    },
                    "intent": {
                        "type": "string",
                        "description": "用中文一句话说明为什么要进化这个 skill（给用户看确认弹窗用）",
                    },
                },
                "required": ["skill_name", "intent"],
            },
        },
    }


def build_memory_archive_tool() -> dict[str, Any]:
    """v0.8.17: memory_archive 工具——让 LLM 能触发记忆归档。

    参考 OpenClaw "每月末压缩上月日志到 memory/archive/YYYY-MM.md" 设计。
    把 N 天前的 episodes 按月分组移到 archive/ 目录，主 episodes.jsonl 只保留近期数据。
    不走 confirm（数据归档不丢失，只是移到 archive/ 目录）。
    """
    return {
        "type": "function",
        "function": {
            "name": "memory_archive",
            "description": (
                "[记忆] 触发记忆归档——把 N 天前的 episodes 按月分组移到 archive/ 目录。\n"
                "触发场景：\n"
                "- 用户说'清理旧记忆' / '归档上月的记忆' → 调 memory_archive\n"
                "- self_analyze 显示 episodes 太多影响性能 → 调 memory_archive 归档旧数据\n"
                "- 定期维护：每月初调一次归档上月数据\n"
                "- 主 episodes.jsonl 太大（> 10MB）→ 调 memory_archive 减负\n"
                "示例：\n"
                "- memory_archive() → 用默认 archive_days（30 天）归档\n"
                "- memory_archive(days=60) → 归档 60 天前的数据\n"
                "工作流程：\n"
                "1. 读主 episodes.jsonl，按 timestamp 分为可归档（< cutoff）和保留（>= cutoff）\n"
                "2. 可归档的按月份分组（YYYY-MM），追加写入 archive/episodes_YYYY-MM.jsonl\n"
                "3. 重写主 episodes.jsonl，只保留近期数据（原子替换）\n"
                "注意：\n"
                "- 不走 confirm（归档不丢数据，只是移到 archive/ 目录）\n"
                "- 归档后的 episodes 不再被 memory_recall 检索（L4 冷数据）\n"
                "- 归档是原子的：先写归档文件，再原子替换主文件\n"
                "- 写归档失败的数据会保留在主文件（不丢数据）"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "（可选）归档 N 天前的数据，默认用 config.memory.archive_days（30 天）",
                    },
                },
                "required": [],
            },
        },
    }


def build_trap_search_tool() -> dict[str, Any]:
    """v0.8.18: trap_search 工具——搜索踩坑记录。

    参考 trae 工作流的 traps.md：失败案例结构化记录（现象→根因→解决方案）。
    LLM 遇到似曾相识的问题时调 trap_search 看有没有踩过同样的坑。
    不走 confirm（只读）。
    """
    return {
        "type": "function",
        "function": {
            "name": "trap_search",
            "description": (
                "[记忆] 搜索踩坑记录（traps）——看之前是否踩过同样的坑。\n"
                "触发场景：\n"
                "- 遇到似曾相识的问题 → 先 trap_search 看有没有踩过同样的坑\n"
                "- 用户说'上次那个坑' → trap_search 找历史踩坑记录\n"
                "- 执行某操作前想确认有没有已知坑 → trap_search\n"
                "- self_analyze 显示某 skill 失败率高 → trap_search 看失败根因\n"
                "示例：\n"
                "- trap_search(query='install_app 失败') → 搜 install_app 相关的坑\n"
                "- trap_search(query='chrome flatpak', status='open') → 只搜未修复的坑\n"
                "- trap_search(query='', status='open') → 列出所有未修复的坑\n"
                "返回：匹配的 traps 列表（id / symptom / root_cause / solution / status / occurrence_count）\n"
                "注意：\n"
                "- 不走 confirm（只读）\n"
                "- status='open' 只搜未修复的坑（默认全部）\n"
                "- 匹配 symptom / root_cause / solution / related_keywords 字段\n"
                "- open 状态的 trap 排序优先（更紧急）"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词（空字符串列出所有 trap）",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["open", "fixed", "workaround", ""],
                        "description": "（可选）按状态过滤：open（未修复）/ fixed（已修复）/ workaround（绕过）。空字符串=全部",
                        "default": "",
                    },
                },
                "required": ["query"],
            },
        },
    }


def build_trap_update_tool() -> dict[str, Any]:
    """v0.8.18: trap_update 工具——更新踩坑记录（填根因/标记修复）。

    LLM 诊断出根因 + 解决方案后调 trap_update 填充，下次同类问题就能避免。
    走 confirm（修改记忆数据，用户应该知道）。
    """
    return {
        "type": "function",
        "function": {
            "name": "trap_update",
            "description": (
                "[记忆] 更新踩坑记录——填根因 / 标记修复 / 累加出现次数。\n"
                "触发场景：\n"
                "- 诊断出某 trap 的根因 → trap_update 填 root_cause + solution\n"
                "- 修复了某 trap 对应的问题 → trap_update 标记 status=fixed\n"
                "- 发现 trap 的根因描述不准确 → trap_update 更新 root_cause\n"
                "示例：\n"
                "- trap_update(trap_id=3, root_cause='flatpak 权限问题', solution='flatpak override --user --filesystem=home') → 填根因\n"
                "- trap_update(trap_id=3, status='fixed') → 标记已修复\n"
                "- trap_update(trap_id=3, status='fixed', fix_verified=true) → 标记已修复且验证过\n"
                "工作流程：\n"
                "1. LLM 诊断失败原因（看错误日志 / 分析 step 失败原因）\n"
                "2. 调 trap_update 填 root_cause（根因）+ solution（解决方案）\n"
                "3. 验证修复后调 trap_update 标记 status=fixed + fix_verified=true\n"
                "注意：\n"
                "- 走 confirm（修改记忆数据，用户确认）\n"
                "- trap_id 必填（从 trap_search 结果获取）\n"
                "- root_cause / solution 可选（只更新提供的字段）\n"
                "- status 可选：open / fixed / workaround\n"
                "- fix_verified=true 表示修复已经验证（下次同类问题成功解决后标记）"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "trap_id": {
                        "type": "integer",
                        "description": "要更新的 trap id（从 trap_search 结果获取）",
                    },
                    "root_cause": {
                        "type": "string",
                        "description": "（可选）根因分析（源码行号 / 配置项 / 环境问题）",
                    },
                    "solution": {
                        "type": "string",
                        "description": "（可选）解决方案（改哪个文件哪个值 / 用什么参数）",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["open", "fixed", "workaround"],
                        "description": "（可选）状态：open（未修复）/ fixed（已修复）/ workaround（绕过）",
                    },
                    "fix_verified": {
                        "type": "boolean",
                        "description": "（可选）修复是否已验证（下次同类问题成功解决后标记 true）",
                    },
                    "intent": {
                        "type": "string",
                        "description": "用中文一句话说明为什么更新这个 trap（给用户看确认弹窗用）",
                    },
                },
                "required": ["trap_id", "intent"],
            },
        },
    }


def build_tool_defs(registry: SkillRegistry) -> list[dict[str, Any]]:
    """把整个 SkillRegistry 转成工具定义列表。

    v0.8.0 改造：run_shell 万能工具放在列表第一个，让 LLM 知道有这个兜底选项。
    v0.8.2 改造：read_file / write_file / edit_file 三个文件操作工具放在 run_shell 后面。
    v0.8.3 改造：run_python 万能工具放在 edit_file 后面。
    v0.8.11 改造：memory_recall 记忆检索工具放在自进化工具组后。
    v0.8.12 改造：create_skill 技能自生成工具放在 memory_recall 后。
    其余 skill 按字母序排序（便于 LLM 阅读）。
    """
    skills = sorted(registry.all(), key=lambda s: s.name)
    tools = [skill_to_tool(s) for s in skills]
    # v0.8.7: 内置万能工具组——run_shell / read_file / write_file / edit_file / run_python / read_log
    tools.insert(0, build_run_shell_tool())
    tools.insert(1, build_read_file_tool())
    tools.insert(2, build_write_file_tool())
    tools.insert(3, build_edit_file_tool())
    tools.insert(4, build_run_python_tool())
    tools.insert(5, build_read_log_tool())
    # v0.8.9: 自进化工具组——self_restart / self_build / self_status / self_version_bump
    tools.insert(6, build_self_restart_tool())
    tools.insert(7, build_self_build_tool())
    tools.insert(8, build_self_status_tool())
    tools.insert(9, build_self_version_bump_tool())
    # v0.8.11: 记忆系统——memory_recall
    tools.insert(10, build_memory_recall_tool())
    # v0.8.12: 技能自生成——create_skill
    tools.insert(11, build_create_skill_tool())
    # v0.8.15: 自监控分析——self_analyze
    tools.insert(12, build_self_analyze_tool())
    # v0.8.17: Skill 规则提升——skill_evolve
    tools.insert(13, build_skill_evolve_tool())
    # v0.8.17: 记忆归档——memory_archive
    tools.insert(14, build_memory_archive_tool())
    # v0.8.18: 踩坑记录——trap_search + trap_update
    tools.insert(15, build_trap_search_tool())
    tools.insert(16, build_trap_update_tool())
    return tools


def build_tool_index(registry: SkillRegistry) -> dict[str, SkillDef]:
    """构造工具名 → SkillDef 的映射，便于 Agent 执行时查找。"""
    return {s.name: s for s in registry.all()}


def build_skill_catalog_for_prompt(registry: SkillRegistry, max_skills: int = 0) -> str:
    """构造给 LLM 系统 prompt 用的 skill 索引（按类别分组的紧凑格式）。

    格式：
        == 系统管理 ==
        - apt_update: 更新 apt 软件源索引
        - apt_upgrade: 升级所有已安装的软件包

        == 文件操作 ==
        - file_search: 搜索文件

    v0.7.12 改造：
    - 按 category 分组，让 LLM 按类别快速定位工具
    - 只保留 skill name + 简短 description（triggers/params 在 tools 列表里已有，避免冗余）
    - max_skills=0 表示全部，>0 表示只给前 N 个 skill（按类别顺序截断）
    """
    skills = sorted(registry.all(), key=lambda s: s.name)
    if max_skills > 0:
        skills = skills[:max_skills]

    # 按 category 分组
    by_category: dict[str, list[SkillDef]] = {}
    for s in skills:
        cat = s.category or "other"
        by_category.setdefault(cat, []).append(s)

    # 按 SKILL_CATEGORIES 的定义顺序输出（未知类别放最后）
    known_cats = list(SKILL_CATEGORIES.keys())
    sorted_cats = sorted(
        by_category.keys(),
        key=lambda c: known_cats.index(c) if c in known_cats else len(known_cats),
    )

    blocks: list[str] = []
    for cat in sorted_cats:
        cat_name = SKILL_CATEGORIES.get(cat, cat)
        lines = [f"== {cat_name} =="]
        for s in by_category[cat]:
            line = f"- {s.name}"
            if s.description:
                line += f": {s.description}"
            lines.append(line)
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)
