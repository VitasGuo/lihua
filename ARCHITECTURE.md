# Lihua 狸花猫 - 架构文档

**版本**：v0.1
**日期**：2026-07-19

## 1. 系统架构

```
┌──────────────────────────────────────────────────────────┐
│                    Tauri 2.0 主进程                       │
│  ┌────────────────────────────────────────────────────┐  │
│  │         React + TypeScript 前端（WebView）         │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐           │  │
│  │  │ 浮窗对话  │ │ 任务进度  │ │ 设置面板  │           │  │
│  │  └──────────┘ └──────────┘ └──────────┘           │  │
│  └────────────────────────────────────────────────────┘  │
│                       ↕ Tauri IPC                        │
│  ┌────────────────────────────────────────────────────┐  │
│  │              Tauri Rust 后端（轻量）                │  │
│  │  - 全局快捷键注册（Super+Space）                    │  │
│  │  - 系统托盘                                          │  │
│  │  - 通知发送                                          │  │
│  │  - Python sidecar 进程管理                          │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
                       ↕ HTTP/WebSocket
┌──────────────────────────────────────────────────────────┐
│              Python sidecar（FastAPI + uvicorn）          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐    │
│  │  意图理解  │ │  任务编排  │ │  安全引擎  │ │  执行器    │    │
│  │ (Intent) │ │(Planner) │ │ (Safety)  │ │(Executor)│    │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                 │
│  │ LLM 路由  │ │ Skill 库  │ │  持久化    │                 │
│  │(Router)  │ │ (Skills)  │ │(Storage) │                 │
│  └──────────┘ └──────────┘ └──────────┘                 │
└──────────────────────────────────────────────────────────┘
                       ↕ 系统调用
┌──────────────────────────────────────────────────────────┐
│  Linux 系统（subprocess / dbus / gsettings / apt/flatpak）│
└──────────────────────────────────────────────────────────┘
```

## 2. 模块设计

### 2.1 意图理解层（Intent Parser）

**职责**：自然语言 → 结构化任务

**输入**：用户文本（如"装个QQ"）+ 上下文（当前目录、历史、用户偏好）

**输出**：

```json
{
  "action": "install_app",
  "target": "QQ",
  "method": "auto",
  "confirm_required": false,
  "raw_text": "装个QQ"
}
```

**实现**：

* LLM 调用，system prompt 限定输出 JSON

* few-shot examples 提升准确率

* 失败重试 + fallback 模型

### 2.2 任务编排层（Planner）

**职责**：复杂任务拆解为步骤序列

**示例**："配置 Python 环境" →

```json
{
  "steps": [
    {"skill": "install_app", "args": {"target": "pyenv"}},
    {"skill": "configure_pyenv", "args": {}},
    {"skill": "create_venv", "args": {"version": "3.12"}},
    {"skill": "install_packages", "args": {"packages": ["requests", "flask"]}}
  ]
}
```

**实现**：

* LLM 调用，根据 Skill 库生成步骤

* 步骤间依赖管理（串行 / 并行）

* 失败回滚策略

### 2.3 安全引擎（Safety Engine）

**三层防线**：

```python
class SafetyEngine:
    BLACKLIST = [
        r"rm\s+-rf\s+/",          # rm -rf /
        r"dd\s+if=.*of=/dev/sd",   # dd 写磁盘
        r"mkfs\.",                 # 格式化
        r":\(\)\{\s*:\|:&\s*\};:", # fork bomb
        r"chmod\s+-R\s+777\s+/",   # 全局权限
        r">\s*/dev/sda",           # 写裸设备
        r"shutdown|reboot|halt",   # 关机重启（无确认）
        r"kill\s+-9\s+-1",         # 杀所有进程
        r"curl.*\|\s*bash",        # 远程脚本执行
    ]

    WHITELIST = [
        r"apt\s+install",          # 装软件
        r"flatpak\s+install",
        r"snap\s+install",
        r"gsettings\s+set",        # 改设置
        r"dconf\s+write",
        r"fcitx5-.*",              # 输入法
        r"gnome-tweaks",
        r"fc-cache",               # 字体缓存
        r"systemctl\s+--user",     # 用户服务
        r"ls\s+", r"cat\s+", r"grep\s+", r"find\s+",  # 只读
    ]

    GREYLIST = [
        r"sudo\s+",                # 需要权限
        r"apt\s+purge",            # 卸载
        r"apt\s+remove",
        r"flatpak\s+uninstall",
        r"rm\s+-rf\s+/etc",        # 改系统目录
        r"nmcli\s+connection",     # 改网络
    ]
```

**关键设计**：

* **黑名单**：正则匹配，绝不执行，直接拒绝

* **白名单**：自动执行，不问用户

* **灰名单**：用人类语言确认，**不展示原始命令**

  * 例：`apt purge fonts-noto-cjk` → "我需要删除思源黑体字体包，确认吗？"

### 2.4 执行器（Executor）

**职责**：执行具体命令

**支持的操作**：

* `subprocess.run()`：shell 命令

* `dbus` 调用：GNOME 设置、应用控制

* `gsettings` / `dconf`：配置

* `apt` / `flatpak` / `snap`：包管理

**特性**：

* 实时捕获 stdout / stderr

* 超时控制

* 进度反馈（通过 WebSocket 推送给前端）

* 失败自动重试 + LLM 修复建议

### 2.5 Skill 库

**Skill 结构**（YAML）：

```yaml
# skills/install-app.yaml
name: install_app
description: 安装应用程序
version: 0.1
author: lihua

parameters:
  - name: target
    type: string
    required: true
    description: 应用名称
  - name: method
    type: enum
    values: [auto, apt, flatpak, snap]
    default: auto

# Skill 内部步骤
steps:
  - name: resolve_package
    description: 查找应用对应的包名
    llm_prompt: |
      用户想安装 {{target}}，请返回最合适的包名和安装方法。
      优先级：flatpak > apt > snap
    output: {package_name, method}

  - name: install
    command: "{{method}} install {{package_name}}"
    safety: whitelist
    confirm_message: "我将安装 {{target}}（{{package_name}}）"

  - name: verify
    command: "which {{package_name}} || flatpak list | grep {{package_name}}"
    on_failure: "安装可能失败，请检查"

# 后置处理
post_hooks:
  - update_desktop_database
  - send_notification: "{{target}} 已安装"
```

**Skill 来源**：

* 内置（20 个，覆盖常见场景）

* 社区贡献（v0.5+ Skill 市场）

* 用户自定义（`~/.config/lihua/skills/`）

### 2.6 LLM 路由（Router）

**路由策略**：

```python
def select_model(task: Task) -> str:
    # 1. 离线检查
    if not network_available():
        return "ollama/qwen2.5-coder:7b"

    # 2. 复杂任务用 Claude
    if task.complexity == "high":  # 多步编排、调试
        return "claude-sonnet-4-5"

    # 3. 中文任务用 DeepSeek（便宜 + 中文好 + 国内快）
    if task.lang == "zh":
        return "deepseek-chat"

    # 4. 默认 DeepSeek
    return "deepseek-chat"
```

**成本控制**：

* 缓存重复查询

* 简单任务用小模型（DeepSeek-Coder 1.3B 本地）

* 用户可设月度预算上限

### 2.7 持久化

**存储**：

* `~/.config/lihua/config.toml`：用户配置

* `~/.local/share/lihua/history.json`：历史记录

* `~/.local/share/lihua/preferences.json`：学习到的用户偏好

* API key 加密存储（keyring）

## 3. 数据流

### 3.1 单步任务流（"装QQ"）

```
1. 用户输入 "装QQ"
   ↓
2. [GUI] 捕获输入 → Tauri IPC → Python sidecar
   ↓
3. [意图理解] LLM 调用 → {action: install_app, target: QQ}
   ↓
4. [任务编排] 查 Skill 库 → install-app skill
   ↓
5. [Skill 执行]
   5.1 resolve_package: LLM 查找 → com.tencent.qq (flatpak)
   5.2 [安全引擎] flatpak install → 白名单，自动执行
   5.3 [执行器] subprocess 调用 flatpak → 实时输出
   5.4 verify: 检查安装结果
   ↓
6. [反馈] "QQ 已安装好，在应用菜单里能找到" → GUI + 通知
```

### 3.2 多步任务流（"配置 Python 环境"）

```
1. 用户输入
   ↓
2. [意图理解] → {action: configure_env, lang: python}
   ↓
3. [任务编排] LLM 拆解 → 4 步骤序列
   ↓
4. 串行执行：
   4.1 install_app(pyenv)    [白名单自动]
   4.2 configure_pyenv()     [白名单自动]
   4.3 create_venv(3.12)     [白名单自动]
   4.4 install_packages()    [白名单自动]
   ↓
5. 每步进度实时推送 GUI
   ↓
6. 全部完成 → 总结反馈
```

### 3.3 灰名单确认流（"卸载 Firefox"）

```
1. 用户输入 "卸载 Firefox"
   ↓
2. [意图理解] → {action: uninstall, target: firefox}
   ↓
3. [安全引擎] apt purge firefox → 灰名单
   ↓
4. [GUI] 弹出确认框：
   "我需要卸载 Firefox 浏览器，确认吗？"
   [确认] [取消] [详情]
   ↓
5a. 用户确认 → 执行 → "Firefox 已卸载"
5b. 用户取消 → "已取消" → 等待新输入
```

## 4. 技术选型理由

### 为什么 Tauri 而非 Electron？

* **体积**：Tauri 5MB vs Electron 150MB+

* **内存**：Tauri 50MB vs Electron 200MB+

* **原生集成**：Tauri 用系统 WebView，原生体验

* **安全**：Tauri 默认禁用 Node.js 集成，更安全

### 为什么 Python sidecar 而非纯 Rust？

* **LLM 生态**：Python 的 litellm / openai / anthropic 库最成熟

* **系统操作**：Python 的 subprocess / dbus / gi 生态完善

* **开发速度**：MVP 阶段 Python 开发快 3-5 倍

* **Skill 编写门槛**：Python 对社区贡献者更友好

### 为什么 litellm 而非直接调 SDK？

* **多模型路由**：一个 API 切换所有 LLM

* **自动 fallback**：内置重试和模型切换

* **成本控制**：统一计费和用量追踪

### 为什么 React 而非 Vue / Svelte？

* **生态**：shadcn/ui、Radix UI 等高质量组件库最多

* **类型安全**：TypeScript 集成最好

* **社区**：遇到问题最容易找到答案

## 5. 安全模型详解

### 5.1 黑名单（硬 ban）

绝不执行，直接拒绝并解释：

* `rm -rf /` 及变种

* `dd if=* of=/dev/sd*`

* `mkfs.*`

* Fork bomb `:(){ :|:& };:`

* `chmod -R 777 /`

* `> /dev/sda` 等裸设备写入

* `shutdown` / `reboot` / `halt`（无确认）

* `kill -9 -1`（杀所有进程）

* `curl ... | bash`（远程脚本执行）

### 5.2 白名单（自动执行）

不问用户，直接执行：

* `apt install` / `flatpak install` / `snap install`

* `gsettings set` / `dconf write`

* `fcitx5-*` / `gnome-tweaks` / `fc-cache`

* `systemctl --user *`

* 只读命令：`ls` / `cat` / `grep` / `find` / `ps`

### 5.3 灰名单（人类语言确认）

**不展示命令**，用人类语言描述：

* `sudo *` → "我需要管理员权限来..."

* `apt purge *` → "我需要卸载 X"

* `apt remove *` → "我需要删除 X"

* 修改 `/etc/*` → "我需要修改系统配置..."

* 网络配置变更 → "我需要修改网络设置..."

### 5.4 审计日志

所有执行记录到 `~/.local/share/lihua/audit.log`：

* 时间戳

* 用户原始输入

* 解析的任务

* 执行的命令

* 结果（成功 / 失败）

* 用户确认记录（灰名单）

## 6. 扩展性设计

### 6.1 Skill 扩展

社区可贡献 Skill：

1. fork 仓库
2. 在 `skills/` 下新增 YAML
3. PR 合并后随版本发布

用户自定义 Skill：

* 放 `~/.config/lihua/skills/`

* 自动加载，优先级高于内置

### 6.2 LLM 扩展

支持任意 OpenAI 兼容 API：

* 本地 LLM（Ollama / LM Studio / vLLM）

* 云端 API（OpenAI / Claude / DeepSeek / 通义千问 / 智谱）

* 自定义 endpoint

### 6.3 桌面环境扩展

MVP 仅支持 GNOME。后续：

* KDE Plasma 6（通过 kdialog / kwriteconfig5）

* Cosmic Desktop（通过 cosmic 协议）

* 独立 X11 / Wayland 兼容层

### 6.4 发行版扩展

发行版检测 + 适配层：

```python
class DistroAdapter:
    def get_install_command(self, package: str) -> str:
        if self.distro == "ubuntu":
            return f"apt install {package}"
        elif self.distro == "fedora":
            return f"dnf install {package}"
        elif self.distro == "arch":
            return f"pacman -S {package}"
```

## 7. 性能预算

| 指标          | 目标                 | 测量方法         |
| ----------- | ------------------ | ------------ |
| 浮窗唤起延迟      | < 200ms            | 快捷键按下到窗口可见   |
| LLM 首 token | < 2s（云端）/ < 5s（本地） | API 调用到首响应   |
| 任务执行反馈延迟    | < 100ms            | 命令输出到 GUI 显示 |
| 常驻内存        | < 200MB            | systemd 进程内存 |
| 安装包大小       | < 50MB             | .deb 文件大小    |

## 8. 测试策略

* **单元测试**：安全引擎 / Skill 解析 / LLM 路由

* **集成测试**：端到端任务流（mock LLM）

* **E2E 测试**：真实 LLM 调用 + 真实系统操作（CI 隔离环境）

* **安全测试**：黑名单命令注入测试 / 权限提升测试

* **性能测试**：延迟 / 内存基准

## 9. 部署

### 安装方式

* **.deb 包**（Ubuntu / Debian）

* **.rpm 包**（Fedora）

* **AUR**（Arch）

* **Flatpak**（沙箱，但限制系统操作）

* **AppImage**（便携）

### systemd user service

```ini
[Unit]
Description=Lihua AI Assistant
After=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/lib/lihua/lihua-sidecar
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
```

## 10. 关键接口定义（草案）

### 10.1 Python sidecar HTTP API

```
POST /api/chat
  Body: {message: string, context?: object}
  Resp: {task: Task, response: string}

POST /api/task/confirm
  Body: {task_id: string, confirmed: boolean}
  Resp: {result: TaskResult}

GET /api/task/:id/status
  Resp: {status: string, progress: float, output: string}

WS /api/stream
  双向：实时推送任务进度
```

### 10.2 Tauri IPC

```typescript
// 前端调用 Rust
invoke('show_window')
invoke('hide_window')
invoke('register_shortcut', {key: 'Super+Space'})

// Rust 调用 Python sidecar
sidecar.call('chat', {message: '装QQ'})
```

