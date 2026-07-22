# Lihua 狸花猫 - 产品需求文档（PRD）

**版本**：v0.1
**日期**：2026-07-19
**状态**：设计阶段

## 1. 产品愿景

**让普通用户也能省心用 Linux。**

Linux 桌面体验碎片化的根源：用户必须懂命令行才能完成基本操作（装软件、配置输入法、调字体、连 WiFi）。Lihua 用 AI 把这些琐事自动化，用户只需用自然语言描述需求，Lihua 理解、拆解、安全执行、反馈结果。

**Slogan**：想得多，做得少，事半功倍。

## 2. 目标用户画像

### 主用户：Linux 新手小白
- **画像**：从 Windows/Mac 转过来，因为开发 / 学习 / 工作必须用 Linux
- **痛点**：不会命令行，每次搜命令很累，配置文件看不懂，怕搞坏系统
- **场景**：装软件、换输入法、调字体、清理缓存、连蓝牙耳机
- **典型语录**："我就想装个 QQ，为什么要 apt install 这种东西？"

### 次用户：有经验的开发者
- **画像**：熟悉 Linux，但不想记生僻参数
- **痛点**：man 太长记不住，不同发行版命令差异烦
- **场景**：快速操作、查日志、批量处理
- **典型语录**："tar 解压参数我每次都要查"

### 非目标用户
- 服务器运维（用 Ansible / Terraform）
- 专业 DevOps（用 Kubernetes）
- 喜欢折腾的极客（他们享受命令行）

## 3. 用户故事

### 故事 1：装软件
> 作为 Linux 新手，我想用自然语言说"装个 QQ"，Lihua 自动帮我装好，我不用知道 flatpak 还是 apt。

### 故事 2：换输入法
> 作为从 Windows 转过来的用户，我想说"把输入法换成 fcitx5"，Lihua 自动完成切换 + 配置 + 自启，我不用懂 systemd。

### 故事 3：调系统设置
> 作为普通用户，我想说"字体太小了调大点"，Lihua 自动调整 GNOME 字体大小，我不用找设置面板。

### 故事 4：故障排查
> 作为新手，遇到问题时我想说"为什么我连不上 WiFi"，Lihua 自动检查网络状态、给出诊断和修复建议。

### 故事 5：多步任务
> 作为开发者，我想说"配置 Python 开发环境"，Lihua 自动装 pyenv、配置 venv、安装常用包。

## 4. 功能需求

### MVP（v0.1）

#### F1: 自然语言交互
- F1.1: 接收自然语言输入（文本，未来支持语音）
- F1.2: 调用 LLM 理解意图，输出结构化任务
- F1.3: 支持多轮对话（上下文记忆）

#### F2: 任务执行
- F2.1: 单步任务执行（"装 QQ"）
- F2.2: 多步任务编排（"配置 Python 环境" → 装 pyenv + 装 venv + 装包）
- F2.3: 失败自动重试 + 修复建议

#### F3: 安全引擎
- F3.1: 黑名单硬 ban（rm -rf /, dd, mkfs 等危险命令）
- F3.2: 白名单自动执行（apt install, gsettings set 等）
- F3.3: 灰名单人类语言确认（"我需要删除思源黑体字体包，确认吗？"）
- F3.4: **不向用户展示原始命令**

#### F4: 内置 Skill 库（20 个）

| Skill | 描述 |
|-------|------|
| install-app | 装软件（apt / flatpak / snap 自动选择） |
| uninstall-app | 卸载软件 |
| switch-im | 切换输入法（IBus ↔ Fcitx5） |
| install-font | 安装字体 |
| switch-font | 切换默认字体 |
| clean-cache | 清理系统缓存 |
| adjust-brightness | 调亮度 |
| adjust-volume | 调音量 |
| connect-wifi | 连 WiFi |
| connect-bluetooth | 连蓝牙 |
| screenshot | 截图 |
| screen-record | 录屏 |
| update-system | 系统更新 |
| manage-startup | 管理开机启动项 |
| set-wallpaper | 设置壁纸 |
| switch-theme | 切换主题（亮 / 暗） |
| configure-python-env | 配置 Python 环境 |
| configure-node-env | 配置 Node 环境 |
| diagnose-network | 网络诊断 |
| diagnose-disk | 磁盘诊断 |

#### F5: LLM 路由
- F5.1: 默认 DeepSeek（中文好 + 便宜 + 国内快）
- F5.2: 复杂任务 fallback Claude（质量优先）
- F5.3: 离线 fallback Ollama（Qwen2.5-Coder 7B）
- F5.4: 用户可配置 API key 和模型偏好

#### F6: 桌面集成
- F6.1: 快捷键唤起浮窗（默认 Super+Space）
- F6.2: systemd user service 常驻
- F6.3: GNOME 原生通知
- F6.4: 开机自启

#### F7: GUI
- F7.1: 浮窗对话界面（类 Spotlight / Alfred）
- F7.2: 任务进度实时显示
- F7.3: 确认对话框（灰名单任务）
- F7.4: 历史记录

### v0.2+
- 语音输入
- Skill 市场（社区贡献）
- 用户习惯学习
- 跨设备同步
- 多发行版适配（Fedora / Arch）
- 多桌面适配（KDE / Cosmic）

## 5. 非功能需求

### 性能
- 浮窗唤起延迟 < 200ms
- LLM 响应首 token < 2s（云端）/ < 5s（本地）
- 任务执行实时反馈进度
- 内存占用 < 200MB（常驻）

### 安全
- 黑名单命令绝不执行
- sudo 操作必须灰名单确认
- 不存储用户敏感数据（API key 加密存储）
- Skill 沙箱执行（限制权限）

### 可靠性
- LLM 调用失败自动 fallback
- 任务执行失败自动重试 3 次
- 系统崩溃后状态可恢复

### 可用性
- 中文优先，英文其次
- 无需注册即可使用（本地 LLM 模式）
- 安装包 < 50MB

### 兼容性
- MVP: Ubuntu 24.04+ GNOME Wayland
- v0.2: Fedora 40+ / Arch
- v0.3: KDE Plasma 6 / Cosmic

## 6. 成功指标

### 量化指标
- GitHub Stars > 1000（6 个月内）
- 月活用户 > 5000（12 个月内）
- Skill 库 > 50 个（社区贡献）
- 用户满意度 NPS > 50

### 质性指标
- 新手用户能独立完成 80% 常见 Linux 操作
- 用户反馈"再也不怕用 Linux 了"

## 7. 竞品分析

| 产品 | 优势 | 不足 | 我们的差异化 |
|------|------|------|------------|
| Warp | UI 漂亮、AI 补全 | 闭源、需登录、国内慢、英文优先 | 开源、本地优先、中文原生 |
| Open Interpreter | 强大、能操作系统 | 太重、安全风险高、不适合日常 | 轻量、安全分层、面向新手 |
| GitHub Copilot CLI | 命令生成准 | 只生成不执行、需订阅、英文 | 自动执行、免费、中文 |
| macOS Spotlight + AI | 体验好 | 只在 macOS | Linux 原生 |
| GNOME 扩展 AI Chat | 轻量 | 功能浅、不是 agent | 完整 agent、安全执行 |

## 8. 商业模式

**开源 MIT 协议**，核心功能免费。

可能盈利点（未来）：
- 托管云端 LLM 服务（用户不用自己配 API key）
- 企业版（多设备管理、审计日志）
- Skill 市场分成

## 9. 路线图

| 版本 | 时间 | 里程碑 |
|------|------|--------|
| v0.1 | 4 周 | MVP：Python 核心 + 20 Skill + Tauri GUI |
| v0.2 | +2 周 | systemd 常驻 + 桌面集成完善 |
| v0.3 | +2 周 | 多发行版适配（Fedora / Arch） |
| v0.5 | +1 月 | Skill 市场 + 用户习惯学习 |
| v1.0 | +2 月 | 稳定版 + 文档完善 + 多桌面适配 |

## 10. 风险与挑战

| 风险 | 应对 |
|------|------|
| LLM 误判导致执行危险命令 | 多层安全 + 黑名单 + 人工确认 |
| 不同发行版差异大 | Skill 抽象层 + 发行版检测 |
| LLM 成本高 | 默认便宜模型 + 本地 fallback + 缓存 |
| 用户信任问题 | 透明展示"我要做什么" + 可撤销 |
| GNOME Wayland 集成限制 | 优先支持 GTK / GNOME，其他桌面渐进 |
| 普通用户不会配 API key | 提供本地 Ollama 一键安装 + 云端托管服务 |

## 11. 开发阶段拆分

### W1: Python 核心验证
- litellm 多模型路由
- 安全分层引擎
- 5 个 MVP Skill（install-app / uninstall-app / switch-im / install-font / clean-cache）
- CLI 验证 `ai "装QQ"` 跑通

### W2: Tauri GUI 骨架
- React + shadcn/ui 浮窗
- 快捷键唤起
- 对话界面
- 对接 Python sidecar

### W3: Skill 库扩充 + 多步任务
- 扩充到 20 个 Skill
- 任务编排器
- 多步任务执行

### W4: 桌面集成 + 打磨
- systemd user service
- GNOME 通知
- 设置面板
- 打包 .deb
