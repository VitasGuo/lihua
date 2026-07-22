# Lihua 狸花猫

> 想得多，做得少，事半功倍。

AI 系统管家，让普通用户也能省心用 Linux。

## 项目简介

Lihua 是一个 AI-native 的 Linux 桌面助手。用户用自然语言描述需求（"装个 QQ"、"把输入法换成 fcitx5"、"没声音了"、"磁盘满了"），Lihua 自动理解意图、解析参数、安全执行、反馈结果。用户不需要打开终端、不需要记命令、不需要懂 Linux。

灵感来源：Linux 桌面体验碎片化是公认痛点——输入法、字体、包管理、systemd 各有各的生态，普通用户根本搞不定。Lihua 用 AI 把这些琐事自动化，把"终端"这个普通用户的噩梦藏到后台。

## 当前状态

**版本**：v0.8.23-alpha（pyproject `0.8.23a0`，Agent 聚焦本职：system prompt 精简 + 串台修复 + 死代码清理；84 个内置 Skill + 5 个万能工具）

已实现：
- ✅ **v0.8.23 Agent 聚焦本职** ⭐ 最新改动
  - 针对用户反馈"不同会话之间 agent 串台，LLM 抓不住用户真实需求"，查看对话历史发现 LLM 过度调工具（26 个仍失败）、过度澄清、system prompt 过载（~268 行含 ~100 行元能力描述让 LLM 分心）
  - **删除 agent.py 死代码 `_SYSTEM_PROMPT`（272 行）**：v0.8.13 已被 `prompt_builder.build_system_prompt()` 替代但旧代码一直留着，删除后 agent.py 3787→3515 行
  - **精简 system prompt（~268→128 行模板）**：A-E 核心工具保留，F-L 元能力描述（~100 行）合并为一个短小节"仅当用户明确要求时使用，不要主动发起"；usage_order 11→6 条，tool_examples 26→8 行，key_rules 15→8 条——让 LLM 聚焦"解决 Linux 问题"而非"自进化/记忆/自监控"
  - **优化前端 history 构建**（App.tsx）：缩短 20→10 条 + 过滤 UI 边框字符（用户粘贴旧 UI 导致串台）+ 过滤过长 assistant 消息（>800 字诊断报告干扰注意力）
  - 全代码审查：safety/memory/config/skill_runner 无冗余无 bug，logging_config 全局状态在 GIL 下安全
  - 模拟测试通过：工具选择正确（装QQ→install_app / 电脑慢→诊断类 skill）+ 多轮对话不串台 + 前端过滤 7/7
- ✅ **v0.8.22 CLI 命令补全**
  - 针对用户反馈"`lihua --help` 很多命令没放进去"，核对发现 6 个功能模块（记忆/自进化/技能自生成/Prompt/插件/自监控分析，46+ 端点）无对应 CLI 命令
  - **新建 `self_evolve.py`**：把 server.py 内联的自进化逻辑抽成独立模块，server.py 和 cli.py 共用；server.py 4 个 self 端点重构为瘦客户端（约 300 行 → 30 行）
  - **cli.py 新增 6 子应用 35 子命令**：memory（9）/ self（4）/ skill-auto（6）/ plugin（7）/ prompt（2 只读）/ analytics（6），全部直接调底层模块不走 HTTP
  - **`__main__.py` `_KNOWN_SUBCOMMANDS` 同步**（T011 教训：不同步会导致 `lihua memory` 被误预处理成 `lihua run memory`）
  - 用 `lihua self version-bump` 自举升级 6 处版本号，6 个新命令实测通过
- ✅ **v0.8.21 ModelSheet 4 个 bug 修复**
  - **Bug 1+2 Key 和自定义配置不持久化**：新增 `apiKeysByPreset` 按 provider 存储 key，切换时保存/恢复；切到 custom 不覆盖 URL/模型
  - **Bug 3 GLM 免费模型过时**：glm-4-flash-250414 → glm-4.7-flash（`src/lihua/model_presets.py`）
  - **Bug 4 下拉选项选不上**：mousedown 事件在 Tauri WebView 下误关闭 Portal 下拉，加 `onMouseDown stopPropagation` + scroll 监听器从捕获改冒泡（详见 traps T079）
- ✅ **v0.8.20 记忆管理入口 + 思考链记录 + 上下文持久化 + 历史对话调取**
  - 针对用户提出的 4 个连续性问题：① 没有记忆/配置编辑入口 ② 没记录思考链 ③ 对话上下文丢失 ④ 不能调取历史对话
  - **记忆管理入口**：托盘加"记忆管理..."菜单 → MemorySheet（4 tab：统计/对话历史/知识库/踩坑 + 导出 JSON + 清空二次确认）
  - **思考链记录**：解析 LLM 返回的 `reasoning_content` → SSE `reasoning` 事件 → MessageBubble 默认展开展示（Brain 图标 + 浅色斜体）+ 写入 Episode（不回传 LLM）
  - **上下文持久化**：前端生成 session_id 存 localStorage → messages 按 session_id 分键持久化 → SSE 中断自动重试 1 次（显示"🔄 正在重连..."）
  - **历史对话调取**：HistorySheet 左右分栏只读查看（会话列表 + episode 详情含 reasoning + tool_calls 简要）
  - 6 处版本号升级，tsc + cargo check + 后端 4 接口验证通过
- ✅ **v0.8.5 新用户引导**
  - 针对用户提出的「让用户愿意安装使用」目标，优化新用户首次打开体验——LLM 未配置时不再显示正常欢迎语让用户点击后看到技术性错误
  - **问题**：v0.8.3-v0.8.4 完成 Agent 工具链后，新用户第一次打开应用如果没配置 LLM，点击快捷动作会看到"502 Bad Gateway"或"连接失败"等技术性错误，影响首次留存
  - **Phase 1 WelcomeScreen.tsx 加 LLM 未配置引导卡片**：
    - 扩展 props 加 `health?: Health | null` 和 `onOpenModelSettings?: () => void`
    - LLM 未配置时在快捷动作上方显示警告色引导卡片：AlertCircle 图标 + "需要先配置 AI 模型" + "Lihua 需要 AI 模型才能理解你的需求并执行任务" + "配置模型"按钮（点击打开 ModelSheet）
  - **Phase 2 App.tsx 的 send 函数前置拦截**：
    - WelcomeScreen 调用加 `health` 和 `onOpenModelSettings` props 传递
    - send 函数在文本检查之后加 `if (health && !health.llm_available)` 拦截——不调用后端，直接显示友好提示消息："还没配置 AI 模型哦～请先点击底部的"配置模型"按钮设置模型后再开始对话。"
    - useCallback deps 加 health（避免 stale closure）
  - **设计决策**：
    - 不直接禁用 InputBar —— 用户输入了东西再提示"未配置"比一开始就禁用更友好
    - 同时改 WelcomeScreen 和 send —— WelcomeScreen 引导首次打开，send 拦截覆盖中途取消配置场景（双保险）
    - send 拦截不直接弹 ModelSheet —— 强制弹窗会打断用户思路，显示提示让用户自己决定何时配置
- ✅ **v0.8.4 confirm 弹窗富文本展示**
  - 针对用户提出的「让用户愿意安装使用」目标，优化 confirm 弹窗——这是用户每次执行修改类操作都会看到的 UI
  - **问题**：v0.8.0-v0.8.3 的 ConfirmSheet 用纯文本展示 message，run_python 的 ```python 标记和 run_shell 的 "命令：" 前缀会原样显示，不美观也不易读
  - **Phase 1 server.py 加结构化字段**：新增 `_enrich_confirm_event()` 函数，从 confirm msg 解析出 tool_name / intent / code / command_text 字段，加到 needs_confirm SSE 事件里
    - run_python：检测 ```python 代码块标记 → 提取 intent（代码块前部分）+ code（代码块内容）
    - run_shell：检测 "\n命令：" 前缀 → 提取 intent + command_text
    - file_op：检测 "写入文件" / "编辑文件" / "路径：" 关键词 → 标记 tool_name
    - 默认：不加额外字段，前端按纯文本展示（兼容旧路径）
  - **Phase 2 ConfirmSheet.tsx 富文本展示**：
    - 扩展 props 加 toolName / intent / code / commandText
    - run_python 展示：意图卡片 + Python 代码块（Code 图标 + 深色背景 #1e1e2e + 等宽字体 + max-h-60 滚动）
    - run_shell 展示：意图卡片 + 命令块（Terminal 图标 + 深色背景 + 等宽字体 + max-h-40 滚动）
    - 文件操作 / 默认：保持纯文本 messages 展示（兼容旧行为）
    - 底部辅助说明根据工具类型调整（run_python 提示"代码能力很强"，run_shell 提示"会修改系统"）
  - **Phase 3 测试**：13 个 _enrich_confirm_event 单元测试（run_python 4 + run_shell 3 + file_op 3 + 默认 3）+ 全量 872 pytest 通过
  - **价值**：用户看到 confirm 弹窗时能清晰区分"意图说明"和"代码/命令"，更快决策；代码块用深色背景 + 等宽字体，符合开发者审美
- ✅ **v0.8.3 run_python 万能工具**
  - 针对用户提出的「让 lihua 真正做成好用的桌面助手」目标，引入 Python 代码执行工具，覆盖 shell 不擅长的场景（数据分析 / HTTP 请求 / 批量重命名 / 复杂逻辑等）
  - **Phase 1 tool_defs.py 加 run_python 工具定义**：`build_run_python_tool()` 直接 Python 构造，放在 tools 列表第 5 个（run_shell / read_file / write_file / edit_file / run_python）；parameters 含 code（必填）/ intent（必填，给用户看确认弹窗）/ timeout（默认 30，上限 300）
  - **Phase 2 agent.py 加 _execute_run_python 执行函数**：
    - 强制走 confirm（不走 safety.py，Python 代码能力太强必须用户确认）—— confirm 显示 intent + 代码预览（前 500 字符，超长截断）
    - 用 venv 的 python（`sys.executable`）通过 stdin 传代码（`[python, "-"]` + `input=code`），避免 shell 转义问题，能 import 已装库（requests / psutil / numpy 等）
    - 默认 cwd = 用户主目录（~），timeout clamp 1~300s
    - 完整 stdout（4000 字符截断）/ stderr（2000 字符截断）/ exit_code / duration / timed_out / code_length / python 路径回传 LLM
    - 手动写审计日志（`write_audit(AuditEntry(...))`，safety_level 统一标记 grey）
    - 速率限制：`MAX_RUN_PYTHON_CALLS = 10`（比 run_shell 更严，Python 能做更多事），run_agent 和 run_agent_streaming 都加计数器 + 拒绝逻辑
  - **Phase 3 system prompt 更新**：加「D. run_python」段落（触发场景：数据处理 / 系统管理 / 网络请求 / 复杂逻辑 / 文件操作高级）+ 工具选择示例表加 4 行 run_python 场景 + 更新使用顺序与关键规则
  - **Phase 4 测试**：11 个单元测试（TestExecuteRunPython：简单 print / import 标准库 / 异常 stderr / 空代码 / confirm 拒绝 / 无 confirm 回调 / dry_run / timeout clamp / 审计日志）+ 2 个速率限制测试 + 4 个工具定义测试 + 5 个端到端 SSE 测试（事件流 / 异常 / done 事件 / needs_confirm / timeout clamp）
  - **Phase 5 前端 ToolCallCard 加 run_python 展示**：加 Code 图标 + ToolItem.isRunPython 字段 + normalizeItems run_python 分支 + 标题行（intent 或代码首行，截断 60 字符）+ py 标签 + exit_code 标签 + 超时标签 + 展开内容（意图 + 代码块 + stdout + stderr）
  - **能力扩展**：从"shell 命令"扩展到"Python 代码"——批量 rename 用 Python 比 shell for 循环清晰；HTTP 请求用 requests 比 curl + jq 可控；数据分析用 Python 比 awk/sort 直观
  - **安全保证**：强制走 confirm（用户看到代码预览再决定）+ 速率限制 10 次 + timeout 上限 300s + 默认 cwd 在 ~
  - 全量 859 pytest 通过
- ✅ **v0.8.2 文件操作工具组（read_file / write_file / edit_file）**
  - 针对用户提出的「把 lihua 真正做成好用的桌面助手」目标，引入 SWE-agent 风格的 ACI（Agent-Computer Interface）文件操作工具
  - **Phase 1 tool_defs.py 加 3 个工具定义**：`build_read_file_tool()` / `build_write_file_tool()` / `build_edit_file_tool()`；`build_tool_defs` 在 run_shell 后插入 3 个文件工具，共 4 个内置工具
  - **Phase 2 agent.py 加执行函数**：
    - `_is_path_in_home(path)` 路径检查——write_file / edit_file 只允许在用户主目录内（防 LLM 改系统文件）
    - `_execute_file_op()` 调度器，分发到 read/write/edit
    - `_execute_read_file()`：自动带行号输出（`{i:>5}→{line}`）+ 二进制检测（`b"\x00" in raw`）+ 编码自动检测（utf-8 → gbk → latin-1）+ 长文件截断 200 行 + 提示用 start_line 续读
    - `_execute_write_file()`：覆盖模式 + 走灰名单 confirm（显示 intent + 路径 + 覆盖警告 + 内容预览前 200 字符）+ 自动 mkdir -p 父目录
    - `_execute_edit_file()`：old_string → new_string 精确替换（SWE-agent 风格）+ old_string 唯一性检查（0 次报错 / >1 次报错 / =1 次替换）+ 走灰名单 confirm（显示 old → new diff）
  - **Phase 3 system prompt 更新**：加「C. 文件操作工具」段落 + 更新使用顺序（先 skill → 文件工具 → run_shell）
  - **能力扩展**：从"run_shell + cat/sed 操作文件"扩展到"SWE-agent 风格 ACI 工具"——read_file 带行号便于 edit_file 定位；write_file 自动 mkdir；edit_file 精确替换避免 sed 正则错误
  - **安全保证**：write_file / edit_file 路径限制在 ~ 下（防 LLM 改 /etc /usr 等）；改系统文件请用 run_shell + pkexec；read_file 无路径限制（只读）
  - 33 个文件操作测试（_is_path_in_home 路径检查 4 + read_file 9 + write_file 7 + edit_file 8 + 结果格式化 5）+ 4 个工具定义测试
  - 全量 831 pytest 通过
- ✅ **v0.8.1 run_shell 安全增强**
  - 黑名单扩展 17 条 LLM 危险模式：find / -delete / find / -exec rm / mv to /dev/null / cp /dev/zero 到磁盘 / chmod 777 ~ 或 /etc/passwd / shutdown / reboot / poweroff（从灰名单升级）/ iptables -F / systemctl stop sshd/NetworkManager / 写 /boot / 写 /proc/sys/kernel/sysrq
  - 速率限制：`MAX_RUN_SHELL_CALLS = 15`，单次对话超过 15 次 run_shell 直接拒绝（防 LLM 无限循环）
  - cwd 控制：run_shell 默认在用户主目录执行（`~`），LLM 要操作系统目录必须显式 cd 或用绝对路径
  - 11 个安全测试 + 1 个速率限制测试
- ✅ **v0.8.0 run_shell 万能兜底工具**
  - 针对用户提出的「linux 本身终端能做的操作非常多，但是现在的 prompt 把 LLM 局限住了」问题，做架构审视 + 改造
  - **核心改造**：删除 system prompt 里「不要编造命令：只用提供的工具」的限制，新增 `run_shell` 万能工具让 LLM 能执行任意 shell 命令
  - **Phase 1 tool_defs.py 加 run_shell 工具定义**：`build_run_shell_tool()` 直接 Python 构造（不依赖 YAML），放在 tools 列表第一个；parameters 含 command（必填）/ intent（必填，给用户看确认弹窗）/ timeout（默认 60，上限 600）
  - **Phase 2 agent.py 改造**：system prompt 加「工具使用策略」（优先用预定义 skill，没有合适的才用 run_shell）+ `_execute_run_shell()` 走 safety.py 分类（黑名单拒绝/灰名单 confirm/白名单自动）+ `_format_tool_result_for_llm` 对 run_shell 特殊处理（完整 stdout/stderr/exit_code 回传 LLM）
  - **Phase 3 safety.py 补漏**：v0.7.13 替换 sudo→pkexec 时遗漏了灰名单——加 pkexec 规则；加 echo/printf/true/false 到白名单（run_shell 常用无害命令）
  - **架构对比**：参考 Open Interpreter / SWE-agent——它们让 LLM 直接生成命令；Lihua 的"预定义 skill + run_shell 兜底"混合模式更适合新手（高频任务有 skill 稳定可靠，长尾任务有 run_shell 万能兜底，安全引擎做防线）
  - **能力扩展**：从"83 个预定义 skill 覆盖的场景"扩展到"任意 Linux 任务"（配置 nginx / 批量改文件 / 查端口占用 / 写脚本 / clone 仓库 等）
  - 9 个 run_shell 测试 + 4 个 tool_defs 新测试 + 全量 761 pytest 通过
- ✅ **v0.7.15 修复谎报成功 + 版本不匹配检测**
  - 针对用户实测问题：Agent 说"Snap 版 Steam 已经成功卸载了"但 steam 还在（uninstall_app 谎报成功）+ install_app confirm 弹窗没显示（后端没重启）
  - **Phase 1 修复 uninstall_app 谎报成功**：verify 用 target 检查 snap/flatpak/dpkg/which 四种安装方式 + on_failure=stop（失败就停止，不执行 notify）
  - **Phase 2 修复 install_app 谎报成功**：verify 加 snap/dpkg 检查 + on_failure=stop + 修复 YAML 冒号陷阱
  - **Phase 3 前端检测后端版本不匹配**：App.tsx 用 getVersion() 对比 health.version，不匹配显示"⚠️ 后端服务版本不匹配，请重启应用"警告横幅
- ✅ **v0.7.14 Agent 行为优化**
  - 针对用户实测问题：AI 太激进（list_apps 找不到 steam 就说"未安装"，不听用户说"steam我安装了"）+ 重复调工具（list_apps 3 次、process_manager 3 次）+ 达上限机械放弃
  - **Phase 1 system prompt 重写**：加 5 条核心原则（用户是事实/不激进换软件/避免重复/诊断工作流/修复要确认）+ 达上限要总结
  - **Phase 2 agent.py 改造**：重复调用检测（第 2 次提醒/第 3 次拒绝）+ `_summarize_on_max_iterations`（达上限让 LLM 看历史总结，不再机械返回固定文案）+ 迭代 8→12
- ✅ **v0.7.13 交互式 confirm + sudo→pkexec**
  - 针对用户实测问题：Agent 调用 install_app 时灰名单操作 confirm_cb=None 导致「需要确认但未提供确认回调」错误
  - **Phase 1 后端交互式 confirm**：`server.py` 新增 `_make_interactive_confirm_cb` + `_ConfirmSession` + `POST /api/chat/confirm` 端点，confirm_cb 阻塞等待前端响应（60s 超时），子线程跑 run_agent_streaming + 主线程从 event_queue 取事件 yield
  - **Phase 2 前端 confirm UI**：`api.ts` 加 `needs_confirm` SSE 事件类型 + `confirmChat` 方法；`App.tsx` SSE switch 加 `case 'needs_confirm'` 弹 ConfirmSheet；`handleConfirm` 支持 Agent（confirmId）/规则（重发）双模式
  - **Phase 3 sudo → pkexec**：36 个 skill 文件 137 处 sudo 替换为 pkexec（1 处 `sudo -u gdm` → `pkexec --user gdm`），走 PolicyKit 系统密码框
  - **设计决策**：lihua 不应运行在管理员权限（root 进程漏洞是灾难），正确做法是普通用户 + 交互式 confirm + pkexec 按需提权
- ✅ **v0.7.12 Skill 库三层整合**
  - 针对用户提出的「新增没有问题，但是对于 agent 来说，是不是需要分类整合？」问题，做三层整合
  - **L1 分类字段**：`SkillDef` 新增 `category` 字段，82 个 YAML 加 category（16 类别：system/file/file_adv/network/network_sys/hardware/desktop/desktop_hw/mirror/install/app/process/media_dev/troubleshoot/mvp/other）
  - **L2 合并 troubleshoot-* 8→1**：删除 8 个独立文件，合并为 1 个 `troubleshoot.yaml`（29 steps，3 参数 issue/action/app，82 triggers，37 aliases，condition 用 `in` 操作符匹配中文 issue 值）
  - **L3 catalog 精简**：`build_skill_catalog_for_prompt` 按类别分组（紧凑格式 `== 类别名 == \n- skill: desc`，4176 字符），`skill_to_tool` description 加 `[类别]` 前缀
  - 整合前 90 个 skill + catalog 双重冗余约 24000 token；整合后 83 个 skill + catalog 按类别分组约 12000 token，节省约 50%
  - 80 个 troubleshoot 测试 + 18 个 tool_defs 测试 + 全量 748 pytest 通过
- ✅ **v0.7.11 beautify_ubuntu 能力扩展**
  - 让 Lihua 拥有重构 Ubuntu 系统风格和界面的能力（不是重构 Lihua 自身的 UI）
  - `beautify-ubuntu.yaml` v0.2 → v0.3，macOS 风格从 8 个 step 扩展到 24 个 step
  - 字体安装（5 step）：思源黑体/宋体（Adobe GitHub 全字重 OTF）+ JetBrains Mono + Fira Code + apply_fonts_to_gnome + fontconfig 极致渲染（rgba 次像素 + hintslight + lcdfilter + 默认字体映射）
  - 窗口按钮位置（1 step）：gsettings `button-layout 'close,minimize,maximize:appmenu'`（移到左上，macOS 风格）
  - 壁纸（2 step）：wget macOS Sonoma/Sequoia 风格壁纸 + gsettings 设置桌面/锁屏
  - GDM 登录界面（4 step）：gdm-settings 工具 + 时间戳备份 gresource + WhiteSur gdm.sh 重新编译 + 设置 GDM 壁纸
  - GRUB 美化（4 step）：WhiteSur-grub-theme + xrandr 自动检测分辨率 + GRUB_TIMEOUT=3 + update-grub
  - restore_default 增强：重置窗口按钮到右上 + 删除 fontconfig + fc-cache -f
  - trigger 策略：新增「登录界面」/「开机界面」/「grub美化」/「GRUB美化」；删除与 install_font 冲突的「装字体」/「思源黑体」等（单纯装字体走 install_font，整套美化走 beautify_ubuntu）
  - extract 去掉 `登录|开机|grub`（让「美化登录界面」/「GRUB美化」走 target=macos 全套流程，避免局部执行导致依赖缺失）
  - 93 个 beautify 测试 + 全量 687 pytest 通过
- ✅ **v0.7.10 AuditSheet 独立审计日志**
  - 后端：`executor.py` 审计日志改为 JSON 行格式 + `parse_audit_line()` 向后兼容旧文本格式
  - 后端：`GET /api/audit` 结构化返回 + 过滤搜索（success/safety/q 三维过滤）
  - 后端：`GET /api/audit/export` 下载完整日志文件 + `DELETE /api/audit` 备份后清空
  - 后端：`cli.py audit` 命令用 Rich 美化输出 + safety 颜色编码
  - 前端：`AuditSheet.tsx` 独立组件（Portal + 退出动画 + max-w-[760px]）
  - 前端：工具栏（成功状态 + safety 级别 + 搜索防抖）+ 列表（时间/✓✗/safety 标签/命令/元数据）+ 底部栏（导出/清空二次确认/路径）
  - 前端：StatusBar 加 Shield 图标按钮 + 托盘 `open-audit` 事件改为打开 AuditSheet
  - 27 个审计测试覆盖（657 pytest 全通过）
- ✅ **v0.7.9 流式输出 + Agent 多轮对话**
  - 后端：`run_agent_streaming` 生成器 yield 7 种事件（start/iteration/text/tool_call_start/tool_call_end/done/error）
  - 后端：`POST /api/chat/stream` SSE 端点 + `X-Accel-Buffering: no` 禁用缓冲
  - 后端：`ChatRequest` 新增 `history` 字段，`run_agent` 也支持多轮
  - 前端：`api.chatStream()` async generator + fetch ReadableStream + SSE 解析
  - 前端：App.tsx send 重写，`for await` 消费流，实时更新消息内容 + 工具调用列表
  - 前端：MessageBubble 流式 UI（思考中 / 正在执行 X... spinner）
  - 前端：ToolCallCard 加 streaming prop + running 状态（Loader2 旋转）
  - 6 个流式测试覆盖（630 pytest 全通过）
- ✅ **v0.7.8 LogSheet 日志查看 UI**
  - GUI 中实时查看日志：SSE 实时流 + 级别筛选（ALL/DEBUG/INFO/WARNING/ERROR/CRITICAL）+ 搜索 + 暂停/继续 + 运行时级别调整 + 清空
  - StatusBar 加 Terminal 图标按钮触发，Portal 渲染避免 overflow 裁剪
  - paused ref 优化：toggle 暂停不重建 EventSource 连接
  - 退出动画 + 自动滚动 + MAX_ENTRIES=500 防内存爆炸
- ✅ **v0.7.7 日志系统**
  - Python `logging` 结构化日志：JSON 格式写入文件（`~/.local/share/lihua/lihua.log`，10MB×5 轮转）+ 彩色人类可读格式输出到 stderr
  - 内存环形缓冲区（1000 条）+ SSE 实时推送（`/api/logs/stream`）
  - 4 个 API：`GET /api/logs` / `GET /api/logs/stream` / `POST /api/logs/level` / `GET /api/logs/file`
  - 关键路径日志：`agent.py`（Agent 启动/迭代/完成/工具调用）+ `skill_runner.py`（Skill 执行/完成）+ `intent.py`（规则匹配/LLM 增强/识别结果）
  - Config 新增 `log_level` 字段（默认 INFO，运行时可调整 + 持久化）
  - 前端 `api.ts` 封装 `api.logs()` / `api.setLogLevel()` / `api.logStreamUrl()`
  - 22 个测试覆盖（全量 624 pytest 通过）
- ✅ **macOS Sequoia 暗色 UI 全量重构** ⭐ v0.7 核心改动
  - 设计系统：System Green #30D158 + 9 阶灰阶 + rgba 三阶边框 + 8 点栅格 + 分层圆角（6/10/14/18/24px）
  - 三层毛玻璃：window-glass (blur 40px) / card-glass (blur 16px) / input-glass (blur 20px)
  - 字体：思源黑体（正文）+ 思源宋体（欢迎语）+ JetBrains Mono（等宽）
  - 12 个独立组件：LihuaLogo（emoji 版）/ IconButton / TitleBar / InputBar / WelcomeScreen / MessageBubble / MessageList / ToolCallCard / ConfirmSheet / Sidebar / StatusBar / ModelSheet / LogoSheet
  - 工具调用过程默认折叠（ToolCallCard），出错自动展开
  - macOS Sheet 风格灰名单确认弹窗（从顶部滑下 + ShieldCheck 图标）
  - lucide-react SVG 图标系统，取代所有 emoji
  - spring 物理动画 + 中文排版优化（text-wrap: pretty / hanging-punctuation / cjk-spacing）
- ✅ **v0.7.5 细节精修 + GPU 加速 + 底层优化** ⭐ 最新改动
  - 主窗口 vignette 跟圆角（去外层 p-3 + 新增 `.window-outer` overflow:hidden + border-radius + 4 层 inset shadow 精致渐变，修复 T048）
  - ModelSheet/LogoSheet 四角圆角 + 漂浮边距（`rounded-t-2xl` → `rounded-2xl` + overlay `p-3` + `shadow-popover`，修复 T049）
  - WebKitGTK GPU 加速（lib.rs 设 `WEBKIT_DISABLE_COMPOSITING_MODE=0` + `WEBKIT_DISABLE_DMABUF_RENDERER=0` + CSS `will-change` + `translateZ(0)` 强制合成层，修复 T050）
  - beautify_ubuntu 扩展 performance 模式（27 个 trigger + 6 个新步骤：GPU 检测 + 字体渲染 + GNOME 动画 + Mesa 工具 + 性能优化 + 自启动清理）
  - condition 表达式支持 `in` 操作符（`{{target}} in [performance, 性能, 优化, gpu, GPU, 字体, 动画]` 多关键词匹配）
- ✅ **v0.7.4 真机实测修复**
  - ModelSheet 自绘下拉菜单（修复 Tauri WebView 下原生 `<select>` 白底白字问题）
  - ModelSheet 退出动画（修复关闭时残影：closing 状态 + fade-out 150ms 延迟 unmount）
  - LihuaLogo 改用 🐱 emoji（彻底放弃自绘 SVG，v0.7.0-v0.7.3 失败 3 次）
  - 新增 LogoSheet（点击 Logo → 上传自定义图片 / 拖拽上传 / 重置默认 emoji，base64 存 localStorage）
  - App.tsx 监听托盘菜单 `open-settings` / `open-audit` 事件（v0.7.3 托盘菜单「设置」「审计日志」点击无效的修复）
  - 窗口 vignette 内阴影（缓解 Wayland 方形硬边：inset 0 0 24px + inset 0 0 80px 两层渐变）
- ✅ **v0.7.3 ModelSheet 极简化 + 默认 pro 旗舰 + 能力下限警告**
  - ModelSheet 完全重写为极简版：厂商 segmented control + 模型下拉 + API Key 输入 + 底部警告条 + 保存按钮
  - 去掉 v0.7.2 的 6 个预设卡片网格 + tier 分组 + 免费徽章 + 上下文长度 + 当前状态卡片 + 描述卡片（信息过载，被用户反馈「大阵仗」）
  - 默认推荐改为 pro 旗舰（挑剔的懒人不在乎花钱，要最好的体验）：
    - 智谱 → `glm-5.2`
    - DeepSeek → `deepseek-v4-pro`
    - Kimi → `kimi-k3`（2026-07 最新 2.8T 参数）
    - MiMo → `mimo-v2.5-pro`（1T MoE）
    - MiniMax → `MiniMax-M2.7`（2026-03 最新旗舰）
  - 新增能力下限警告：`MIN_RECOMMENDED_MODEL = "deepseek-v4-flash"`
  - ModelSheet 底部固定黄色警告条（AlertTriangle 图标）：不建议使用能力低于 DeepSeek V4 Flash 的模型
  - 新增 `beautify_ubuntu` Skill：Ubuntu 美化（macOS WhiteSur 主题 + Elementary 风格 + GNOME 扩展配置）
- ✅ **v0.7.2 ModelSheet 主窗口内 overlay + 最新模型清单 + tier 分级**
  - ModelSheet 改为 `absolute inset-0`（主窗口内浮层，不再跑出主界面）+ `animate-slide-up` 从底部滑上
  - 最新模型清单（2026-07 各家最新版）：GLM-5.2 / DeepSeek V4 / Kimi K2.6+K3 / MiMo V2.5 / MiniMax-M3
  - tier 分级：basic（基础 / 性价比 / 免费优先）+ pro（旗舰）
  - 主内容区无 sidebar 时居中（WelcomeScreen flex-1 + MessageList/InputBar max-w-[640px] mx-auto）
- ✅ **v0.7.1 视觉精修 + 模型切换 UI**
  - Sidebar 双向动画（width + opacity transition，主内容区配合收缩）
  - 按钮微动效（hover scale 1.05 + active scale 0.95 + translateY + shadow）
  - 6 个 LLM 预设：DeepSeek / Kimi / MiniMax / 智谱 GLM / MiMo 小米 / 自定义
  - 后端 4 个新 API：`/api/models/presets` / `/api/config/llm` (GET/POST) / `/api/config/llm/preset/{id}`
  - 状态栏可点击打开模型设置 + 呼吸光晕动画
- ✅ **Tauri 2.0 单窗口架构**：移除浮动小球，托盘菜单重设计
  - 主窗口 720×640（毛玻璃 + 阴影 + 圆角 24px）
  - 托盘菜单：状态行 + 显示/新对话 + 设置/历史/审计 + 关于/退出
  - Python sidecar：Tauri 主进程内嵌启动 uvicorn
- ✅ **LLM Agent 主导架构**（v0.6 引入）：LLM 通过 function calling 调用 Skill 工具，多轮对话 + max_iterations 安全阀
  - `agent.py`：Agent 主循环（系统 prompt + tool_calls + tool 消息回传）
  - `tool_defs.py`：Skill YAML → OpenAI function calling 工具定义自动转换
  - `router.py` 扩展：`call_llm_with_tools()` 支持 tools / tool_choice 参数
  - SenseNova deepseek-v4-flash 原生支持 function calling（已实测）
- ✅ **双轨模式**：默认走 Agent（LLM 主导），无 LLM 或 `--rule` 时回退规则匹配（intent.py 保留作离线兜底）
- ✅ 自然语言 → Skill → 执行的完整闭环（CLI + 桌面应用）
- ✅ **83 个内置 Skill**（覆盖 Linux 新手常见坑，按 16 类组织，v0.7.12 catalog 按类别分组）：
  - 系统管理（10）：系统更新 / 系统信息 / 电源管理 / 服务管理 / 磁盘占用 / 清理残留 / 修改密码 / 时区 / 语言环境 / 启动项
  - 文件操作（5）：解压 / 压缩 / 搜索 / 权限 / 关联
  - 文件管理高级（7）：备份 / 加密 / 安全删除 / 挂载 / U 盘启动盘 / 转 PDF / 图片转换
  - 网络（5）：网络信息 / 防火墙 / WiFi 连接 / 网络测试 / 代理
  - 网络系统高级（7）：VPN / SSH 远程 / WiFi 热点 / Samba 共享 / 内核管理 / 定时任务 / 日志查看
  - 硬件外设（5）：硬件信息 / 蓝牙 / 打印机 / 屏幕 / 音频
  - 桌面环境（6）：截图 / 夜灯 / 壁纸 / 主题 / 桌面图标 / **美化 Ubuntu（v0.7.3 新增，v0.7.5 扩展 performance 模式，v0.7.11 扩展 macOS 极致风格：字体安装 + GDM 登录界面 + GRUB 美化 + 壁纸 + 窗口按钮位置）**
  - 桌面硬件扩展（6）：GNOME 扩展 / 剪贴板 / 显卡驱动 / 键盘布局 / 触摸板 / 病毒扫描
  - 软件源镜像（5）：镜像源 / apt 仓库 / PPA / Flatpak 仓库 / Snap 通道
  - 软件安装增强（5）：.deb / AppImage / Snap / 开发工具链 / apt 缓存清理
  - 应用操作（4）：打开 / 关闭 / 列出 / 默认应用
  - 进程性能（5）：进程管理 / 终止进程 / CPU 监控 / 内存监控 / 电池
  - 多媒体开发环境（7）：视频转换 / 录屏 / PDF 合并拆分 / Git 配置 / Docker / Python venv / SSH 密钥
  - 新手救急诊断（1，v0.7.12 合并 8→1）：没声音 / 没 WiFi / 没网 / 磁盘满 / 内存高 / CPU 高 / 应用崩溃 / 系统慢（用 issue 参数区分，condition 用 `in` 操作符匹配中文值）
  - MVP（5）：装应用 / 卸载应用 / 切输入法 / 装字体 / 清缓存
- ✅ 安全分层引擎：黑名单硬 ban / 白名单自动 / 灰名单人类语言确认（Agent 调用的 Skill 执行时仍走 safety.py，安全模型不变）
- ✅ LLM 路由：OpenAI 兼容端点（urllib 原生支持 function calling）+ DeepSeek / Anthropic / Ollama（litellm 可选）
- ✅ Skill 系统：YAML 定义，支持 triggers / parameters / aliases / steps / conditions / safety
- ✅ 审计日志 + 历史记录
- ✅ FastAPI HTTP 服务（桌面浮窗后端）+ systemd user service 模板
- ✅ 748 个 pytest 测试全通过（v0.7.12 新增 troubleshoot 合并版 + tool_defs catalog 分组测试；v0.7.13 修复 2 个 beautify 测试期望 sudo→pkexec）

未来（v0.8+）：
- 多发行版适配（Fedora / Arch：dnf / pacman）
- 多桌面适配（KDE / Cosmic）
- Skill 市场（社区贡献 YAML）
- 语音输入（whisper.cpp 本地 ASR）
- Tauri 透明窗口 + layer-shell 协议（解决 Wayland 浮球位置 / 透明问题）

## 快速开始

### 安装

```bash
# 1. 克隆仓库
git clone <repo-url> lihua
cd lihua

# 2. 创建 venv 并安装（避免 PEP 668）
python3 -m venv ~/.local/share/lihua/venv
~/.local/share/lihua/venv/bin/pip install -e '.[dev]'

# 3. 创建软链（让 lihua 命令全局可用）
mkdir -p ~/.local/bin
ln -sf ~/.local/share/lihua/venv/bin/lihua ~/.local/bin/lihua

# 4. 验证
lihua --version
lihua doctor
lihua skills list
```

### 配置 LLM（强烈推荐）

LLM 是 Agent 模式的前提——配了 LLM 后 Lihua 走 **Agent 主导架构**（LLM 用 function calling 调用 89 个 Skill 工具，能理解任意自然语言、多轮对话、主动追问）。无 LLM 时自动回退到规则匹配模式（识别 89 个 Skill 的常见说法，离线可用）。

**模型要求**：必须支持 OpenAI function calling 协议（tools / tool_calls / tool_call_id）。已实测可用：
- SenseNova `deepseek-v4-flash`（本机默认配置）
- DeepSeek `deepseek-chat`
- OpenAI `gpt-4o` / `gpt-4o-mini`
- 任意 OpenAI 兼容端点（需原生支持 function calling）

编辑 `~/.config/lihua/config.toml`：

```toml
[llm]
enabled = true
provider = "openai-compat"          # OpenAI 兼容端点都用这个
api_key = "sk-xxxxx"
api_base = "https://token.sensenova.cn/v1"   # 或 https://api.deepseek.com/v1
model = "deepseek-v4-flash"          # 或 deepseek-chat

[general]
always_confirm_grey = true           # 灰名单任务必须人工确认
auto_execute_whitelist = true        # 白名单自动执行
audit_log = true                     # 写审计日志
language = "zh"
```

也支持环境变量：`DEEPSEEK_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `LIHUA_LLM_BASE` / `LIHUA_LLM_MODEL`。

### 使用

```bash
# CLI 模式（默认走 LLM Agent，配了 LLM 时自动启用 function calling）
lihua "装QQ"                    # 装 QQ（flatpak 优先）
lihua "装个思源黑体"            # 装字体
lihua "切换到 fcitx5"           # 切输入法
lihua "清一下垃圾"              # 清缓存
lihua "没声音了"                # Agent 调用 troubleshoot_no_sound 工具
lihua "磁盘满了"                # Agent 调用 troubleshoot_disk_full 工具
lihua "电脑怎么这么卡啊"        # Agent 自由诊断：CPU/内存监控 + 主动追问
lihua "看下 CPU 使用情况"       # Agent 调用 cpu_monitor，给出中文解释
lihua "切换镜像源 清华"         # 切换 apt 镜像源
lihua "装显卡驱动"              # 安装 NVIDIA 驱动
lihua "制作U盘启动盘 ubuntu.iso /dev/sdb"  # 高风险，必弹确认
lihua "备份 /home/user/docs 到 /backup"    # rsync 增量同步
lihua "查看系统日志"            # journalctl
lihua "切深色模式"              # GNOME 主题
lihua "看电量"                  # 电池信息
lihua "截全屏"                  # 截图
lihua "美化ubuntu"              # macOS WhiteSur 风格美化
lihua "装elementary风格"        # Elementary OS 风格（Plank dock）
lihua "恢复默认主题"            # 恢复 Yaru 主题

lihua "装QQ" --dry-run          # 干跑：只识别意图，不执行
lihua "装QQ" --rule             # 强制走规则匹配（不走 LLM Agent）
lihua "装QQ" --no-llm           # 本次不调用 LLM（同 --rule 效果）
lihua "卸载 firefox" -y         # 自动确认灰名单（慎用）
lihua chat                      # 交互模式（默认 Agent，支持 --rule）
lihua skills list               # 列出所有 Skill（89 个）
lihua skills show install_app   # 查看某个 Skill 详情
lihua config show               # 查看配置
lihua doctor                    # 健康检查（含 LLM 调用测试）
lihua history                   # 历史记录
lihua audit                     # 审计日志
lihua serve                     # 启动 HTTP 服务（需装 server extras）
lihua install                   # 安装 systemd user service

# 桌面浮窗模式（Tauri 2.0）
lihua gui                       # 后台启动桌面应用（自动自检+编译，用户零命令行）
lihua gui --build               # 强制重新编译 Tauri 应用后启动
lihua gui --dev                 # 开发模式（热重载）
lihua gui --foreground          # 前台运行（看日志，Ctrl+C 退出）

# v0.8.24: lihua gui 启动前自动自检（_check_binary_ready）
#   检测二进制是否存在 / 前后端版本号是否匹配 / 源代码是否比二进制新
#   不通过时自动 npx tauri build --no-bundle 编译修复（约 1-3 分钟，只需一次）
#   用户无需手动编译，永远不会遇到"前后端版本不匹配"警告
```

**Agent 模式 vs 规则模式的区别**：
- Agent 模式（默认）：LLM 理解任意自然语言，能多轮对话、主动追问、组合多个工具、给出中文解释。"电脑怎么这么卡啊"这种没有 trigger 关键词的模糊表达也能理解。
- 规则模式（`--rule` 或无 LLM 时）：基于 YAML triggers 正则匹配，离线可用，响应快，但只能识别预设说法。

桌面浮窗启动后：
- 屏幕上会出现 🐱 浮动小球（可拖动）
- 顶部状态栏出现 🐱 系统托盘图标
- 主浮窗（760×800 暗色卡片）显示在屏幕中央
- 点击小球或托盘图标可切换主浮窗
- 在输入框输入自然语言，回车执行（默认走 Agent）

## 核心价值

- **傻瓜式交互**：自然语言 → 任务 → 执行 → 反馈，用户看不到命令
- **安全透明**：三层安全防线，普通用户不会误操作
  - 黑名单硬 ban（`rm -rf /`、`dd`、`mkfs`、`curl | bash`、`shred /dev/sd`、`sed -i /etc/passwd` 等绝不执行）
  - 白名单自动执行（`apt install`、`gsettings set`、`docker ps`、`fc-list` 等）
  - 灰名单人类语言确认（"我需要卸载 Firefox，确认吗？"——不展示原始命令）
- **中文原生**：中文 trigger / 中文确认消息 / 中文错误解释
- **省心常驻**：systemd user service 后台常驻，HTTP API 可对接任意前端
- **离线可用**：无 LLM 时走规则模式，配了 LLM 后体验更好
- **覆盖新手坑**：89 个 Skill 覆盖 Linux 新手能遇到的高频场景，从"没声音"到"制作 U 盘启动盘"

## 功能范围

### v0.6.0-alpha（当前版本）
- **LLM Agent 主导架构**：function calling + 多轮对话 + 规则兜底（双轨模式）
- 自然语言 → 任务 → 执行的完整闭环（CLI + Tauri 桌面浮窗）
- 89 个内置 Skill（按 9 类组织，覆盖 Linux 新手常见坑）
- 多 LLM provider 路由（DeepSeek / OpenAI / Anthropic / Ollama / 任意 OpenAI 兼容端点）
- FastAPI HTTP 服务 + systemd user service
- Tauri 2.0 桌面应用（系统托盘 + 浮动小球 + 主浮窗）
- 539 个 pytest 测试

### v0.7.0+
- 多发行版适配（Fedora / Arch）
- 多桌面适配（KDE / Cosmic）
- Skill 市场（社区贡献 YAML）
- 语音输入
- Tauri 透明窗口 + layer-shell 协议

## 目标用户

**主要用户**：从 Windows/macOS 转到 Linux 的新手，不熟悉命令行，但需要用 Linux（开发 / 学习 / 工作）。

**次要用户**：有经验的 Linux 用户，想省去记参数的麻烦。

**非目标用户**：纯服务器场景、专业 DevOps（他们用 Ansible / Terraform）、享受折腾的极客。

## 技术栈

| 层 | 技术 | 状态 | 理由 |
|----|------|------|------|
| CLI | Python 3.11+ + typer + rich | ✅ v0.6 | 交互友好、生态成熟 |
| Skill 引擎 | PyYAML | ✅ v0.6 | Skill 定义声明式、易扩展 |
| LLM Agent | OpenAI function calling 协议（urllib 原生） | ✅ v0.6 | 工具调用 + 多轮对话 + 规则兜底 |
| 工具定义转换 | tool_defs.py（Skill YAML → OpenAI tools schema） | ✅ v0.6 | 自动把 89 个 Skill 转成 LLM 可调用的工具 |
| LLM 路由 | urllib（OpenAI 兼容，原生 function calling）+ litellm（可选） | ✅ v0.6 | urllib 兜底避免重依赖 |
| HTTP 服务 | FastAPI + uvicorn | ✅ v0.6 | 桌面浮窗后端 API |
| 桌面集成 | systemd user service | ✅ v0.6 | 开机自启、常驻 |
| 桌面应用壳 | Tauri 2.0（Rust 主进程 + WebView） | ✅ v0.7 | 轻量、原生窗口、系统托盘 + 单窗口架构 |
| 前端 | React 18 + TypeScript + Tailwind CSS 3 | ✅ v0.7 | macOS Sequoia 暗色风 + 毛玻璃 + 组件化 |
| UI 图标 | lucide-react | ✅ v0.7 | SVG 图标系统，取代所有 emoji |
| 后端 sidecar | Tauri 主进程内嵌启动 uvicorn | ✅ v0.6 | 一键启动、统一日志 |

## 目录结构

```
lihua/
├── README.md                  # 项目入口（本文件）
├── PRD.md                     # 产品需求文档
├── ARCHITECTURE.md            # 架构文档
├── SESSION_CONTEXT.md         # 会话交接文档
├── process.md                 # 进度
├── traps.md                   # 踩坑记录（T001-T083）
├── pyproject.toml             # 构建配置 + 依赖 + scripts 入口
├── systemd/
│   └── lihua.service          # systemd user service 模板
├── src/
│   └── lihua/
│       ├── __init__.py        # 版本号
│       ├── __main__.py        # sys.argv 预处理（lihua "装QQ" → lihua run "装QQ"）
│       ├── cli.py             # typer CLI 入口（run/chat/doctor/serve/gui/skills/config + memory/self/skill-auto/plugin/prompt/analytics）
│       ├── self_evolve.py     # 自进化逻辑（build/restart/status/version_bump）⭐ v0.8.22 抽离
│       ├── config.py          # 配置加载（TOML）+ 路径管理
│       ├── safety.py          # 安全分层引擎（黑/白/灰 + 复合命令拆分 + 负向先行断言）
│       ├── executor.py        # subprocess 包装 + 审计日志
│       ├── skills.py          # Skill YAML 加载器 + 注册表 + 优先级排序
│       ├── skill_runner.py    # Skill 步骤执行器（模板渲染 + 条件判断 + default 过滤器）
│       ├── intent.py          # 规则意图理解（triggers + extract 正则 + LLM 增强，离线兜底）
│       ├── agent.py           # LLM Agent 主循环（function calling + 多轮对话 + max_iterations）⭐ v0.6 新增
│       ├── tool_defs.py       # Skill YAML → OpenAI function calling 工具定义自动转换 ⭐ v0.6 新增
│       ├── router.py          # LLM 路由（litellm + urllib 兜底，支持 tools/tool_calls）
│       ├── server.py          # FastAPI 服务（/api/chat 默认 Agent，/api/chat/rule 规则兜底）
│       └── data/
│           └── skills/        # 内置 Skill YAML（89 个，见下方分类）
├── desktop/                   # Tauri 桌面应用（v0.7 单窗口架构）
│   ├── package.json           # 前端依赖 + scripts（含 lucide-react）
│   ├── vite.config.ts         # Vite 单入口构建
│   ├── index.html             # 主窗口 HTML 入口
│   ├── tailwind.config.js     # ⭐ v0.7 设计系统（色板/间距/圆角/动画）
│   ├── src/
│   │   ├── App.tsx            # 主应用（240 行，组合 10 个子组件）
│   │   ├── api.ts             # API 封装 + 类型定义（含 ToolCall/Agent 模式）
│   │   ├── types.ts           # 类型 re-export（统一从 api.ts）
│   │   ├── index.css          # ⭐ v0.7 CSS 设计令牌 + 毛玻璃 + 动画系统
│   │   ├── main.tsx           # React 入口
│   │   └── components/        # ⭐ v0.7 组件层（10 个独立组件）
│   │       ├── LihuaLogo.tsx     # 狸花猫品牌 logo
│   │       ├── IconButton.tsx    # 通用图标按钮
│   │       ├── TitleBar.tsx      # 顶部标题栏 48px
│   │       ├── InputBar.tsx      # 输入区 + 发送按钮
│   │       ├── WelcomeScreen.tsx # 空状态欢迎屏
│   │       ├── MessageBubble.tsx # 消息气泡（用户/助手双轨）
│   │       ├── MessageList.tsx   # 对话流容器
│   │       ├── ToolCallCard.tsx  # 工具调用折叠卡片
│   │       ├── ConfirmSheet.tsx  # macOS Sheet 风格确认弹窗
│   │       ├── Sidebar.tsx       # 侧边栏（Skills / 历史，双向动画）
│   │       ├── StatusBar.tsx     # 底部状态栏（可点击打开 ModelSheet）
│   │       └── ModelSheet.tsx    # 模型切换面板（6 预设 + API Key 管理）
│   └── src-tauri/             # Rust 主进程
│       ├── Cargo.toml         # Rust 依赖（v0.7.0）
│       ├── tauri.conf.json    # Tauri 配置（单窗口 720×640）
│       ├── build.rs           # tauri_build::build()
│       ├── capabilities/
│       │   └── default.json   # 权限配置（仅 main 窗口）
│       ├── icons/             # 应用图标
│       └── src/
│           ├── main.rs        # 入口（调用 app_lib::run()）
│           └── lib.rs         # 主逻辑（托盘 + 快捷键 + 多窗口 + Python sidecar）
└── tests/
    ├── test_safety.py                 # 黑/白/灰名单 + 复合命令 + v0.5.0 新规则测试
    ├── test_skills.py                 # Skill 加载 + 触发词 + 参数提取 + 别名解析
    ├── test_intent.py                 # 规则意图识别测试
    ├── test_agent.py                  # LLM Agent 主循环测试（mock LLM，16 个用例）⭐ v0.6 新增
    ├── test_tool_defs.py              # Skill → function calling 工具定义转换测试（18 个用例）⭐ v0.6 新增
    ├── test_skills_troubleshoot.py    # 组 A 新手救急诊断类测试
    ├── test_skills_mirror.py          # 组 B 软件源镜像类测试
    ├── test_skills_file_adv.py        # 组 C 文件管理高级类测试
    ├── test_skills_media_dev.py       # 组 D 多媒体+开发环境类测试
    ├── test_skills_network_sys.py     # 组 E 网络+系统高级类测试
    └── test_skills_desktop_hw.py      # 组 F 桌面+硬件类测试
```

### 内置 Skill 分类（89 个）

位于 `src/lihua/data/skills/`，按功能分组：

| 分组 | 数量 | 代表 Skill |
|------|------|------------|
| 系统管理 | 10 | system_update / system_info / power_management / service_manager / disk_usage / cleanup_residual / user_password / timezone / locale / startup_apps |
| 文件操作 | 5 | file_extract / file_compress / file_search / file_permission / file_association |
| 文件管理高级 | 7 | file_backup / file_encrypt / file_shred / disk_mount / usb_bootable / file_convert_pdf / image_convert |
| 网络 | 5 | network_info / firewall / wifi_connect / network_test / proxy_setting |
| 网络系统高级 | 7 | vpn_connect / ssh_connect / hotspot_create / share_folder / kernel_management / cron_job / log_view |
| 硬件外设 | 5 | hardware_info / bluetooth / printer / screen_display / audio_control |
| 桌面环境 | 6 | screenshot / night_light / change_wallpaper / change_theme / desktop_icon / beautify_ubuntu |
| 桌面硬件扩展 | 6 | gnome_extension / clipboard_history / gpu_driver / keyboard_layout / touchpad_config / virus_scan |
| 软件源镜像 | 5 | mirror_source / apt_repository / ppa_management / flatpak_remote / snap_channel |
| 软件安装增强 | 5 | install_deb / install_appimage / install_snap / install_dev_tools / cleanup_apt |
| 应用操作 | 4 | open_app / close_app / list_apps / default_apps |
| 进程性能 | 5 | process_manager / kill_process / cpu_monitor / memory_monitor / battery |
| 多媒体开发环境 | 7 | video_convert / screen_record / pdf_merge_split / git_config / docker_run / python_venv / ssh_key |
| 新手救急诊断 | 8 | troubleshoot_no_sound / troubleshoot_no_wifi / troubleshoot_no_internet / troubleshoot_disk_full / troubleshoot_memory_high / troubleshoot_cpu_high / troubleshoot_app_crash / troubleshoot_slow_system |
| MVP | 5 | install_app / uninstall_app / switch_im / install_font / clean_cache |
| **合计** | **90** | |

## 模块划分

1. **CLI（cli.py）**：typer 入口，提供 `run` / `chat` / `skills` / `config` / `doctor` / `serve` / `gui` / `install` 等子命令（v0.8.22 新增 6 个子应用：`memory` / `self` / `skill-auto` / `plugin` / `prompt` / `analytics`，共 35 个子命令，直接调底层模块不走 HTTP）。`run` / `chat` 默认走 Agent 模式，`--rule` 强制规则模式
2. **LLM Agent（agent.py）** ⭐ v0.6 新增：Agent 主循环
   - 构造系统 prompt（含 89 个 Skill 的紧凑索引）+ 工具定义
   - 发送给 LLM，LLM 返回 `tool_calls` → 执行每个工具 → 结果回传 LLM
   - 多轮对话直到 LLM 不再调用工具或达到 `max_iterations`（默认 8）
   - 工具执行时仍走 `skill_runner` + `safety.py`，安全模型不变
3. **工具定义转换（tool_defs.py）** ⭐ v0.6 新增：把 89 个 Skill YAML 自动转成 OpenAI function calling 格式
   - `skill_to_tool()`：单个 Skill → 工具定义（description 含触发场景 + 示例）
   - `build_tool_defs()`：整个 registry → tool 列表
   - `build_skill_catalog_for_prompt()`：紧凑索引给系统 prompt 用
4. **规则意图理解（intent.py）**：离线兜底。triggers + extract 正则 + LLM 增强（别名表查不到时调 LLM 解析包名）
5. **Skill 库（skills.py）**：YAML 加载器 + 注册表。内置 89 个 + 用户自定义（`~/.config/lihua/skills/`）。优先级排序：alias 命中 > trigger 长度
6. **Skill 执行器（skill_runner.py）**：按步骤序列执行，支持条件分支、模板插值（含 `{{var|default:value}}`）、进度回调
7. **安全引擎（safety.py）**：命令分类（黑/白/灰）+ 复合命令拆分 + 整体黑名单检测 + 负向先行断言区分查询 / 修改命令。Agent 调用的工具执行时也走这里
8. **执行器（executor.py）**：subprocess 包装，实时输出 + 超时 + 审计日志
9. **HTTP 服务（server.py）**：FastAPI 后端，`/api/chat` 默认走 Agent，`/api/chat/rule` 走规则兜底。还提供 `/api/health` / `/api/skills` / `/api/parse` / `/api/history` / `/api/audit` 等接口
10. **桌面应用（desktop/）**：Tauri 2.0 桌面应用
    - **Rust 主进程（src-tauri/src/lib.rs）**：系统托盘 + 菜单 + 全局快捷键 + 多窗口管理 + Python sidecar 启动 + Tauri 命令
    - **主浮窗（src/App.tsx）**：760×800 暗色卡片，标题栏 + 输入框 + 对话流 + 进度卡片 + 灰名单确认弹窗 + 侧边栏（Skills+历史）
    - **Sheet 浮层组件群**：ModelSheet（模型配置）/ LogoSheet（自定义 logo）/ LogSheet（日志）/ AuditSheet（审计日志）/ MemorySheet（记忆管理 4 tab：统计/对话历史/知识库/踩坑 + 导出/清空）/ HistorySheet（只读历史会话查看，左右分栏）⭐ v0.8.20 新增后两者
    - **浮动小球（src/Bubble.tsx）**：96×96 圆角方块，可拖动 + 单击唤起主浮窗
11. **LLM 路由（router.py）**：多 provider 支持，urllib 原生 function calling（litellm 可选）。`call_llm_with_tools()` 支持 tools / tool_choice 参数
12. **配置（config.py）**：TOML 配置 + 环境变量覆盖 + 路径管理

## 核心数据流

### Agent 模式（默认，配了 LLM 时）

```
用户输入 "电脑怎么这么卡啊"
    ↓
[桌面浮窗 / CLI] → agent.run_agent()
    ↓
[构造系统 prompt] agent.py
  ├─ 角色：Linux 桌面智能助手
  ├─ 工作流程：分析 → 调用工具 → 中文解释
  └─ 可用工具：89 个 Skill 的紧凑索引（tool_defs.build_skill_catalog_for_prompt）
    ↓
[构造工具定义] tool_defs.build_tool_defs()
  └─ 89 个 Skill → OpenAI function calling 格式（name + description + parameters schema）
    ↓
[第 1 轮 LLM 调用] router.call_llm_with_tools()
  └─ LLM 返回 tool_calls: [{name: "cpu_monitor", args: {}}]
    ↓
[执行工具] agent._execute_tool()
  ├─ 构造 Intent 对象（skill_name=cpu_monitor, params={}）
  ├─ run_skill(intent, cfg, ...) → skill_runner.py 执行
  │   └─ [安全引擎] safety.py 分类命令（top/htop 走白名单自动执行）
  └─ 返回 ToolCallRecord(success=True, result_message="CPU 使用率 45%...")
    ↓
[工具结果回传 LLM] messages.append({"role": "tool", "tool_call_id": "...", "content": "CPU 45%..."})
    ↓
[第 2 轮 LLM 调用] LLM 看到工具结果
  ├─ 可能再调用 memory_monitor 工具 → 重复上述流程
  └─ 或返回最终 text: "你的 CPU 占用 45%，内存 6.2G/16G，看起来是浏览器开太多了。
                可以试试关掉一些不用的标签页，或者用 `lihua \"清理内存\"` 释放一下。"
    ↓
[反馈] 浮窗消息气泡 + 工具调用过程（折叠显示）+ 桌面通知
```

#### v0.8.20 新增流转路径

**session_id 贯穿**（解决连续对话上下文丢失）：

前端生成 session_id（`s_{timestamp}_{random}`）→ 存 localStorage（`lihua:current-session`）+ messages 分键持久化（`lihua:messages:{sessionId}`）→ 随 chat/chatStream 请求传给后端 → `agent.run_agent(session_id=...)` → `_record_episode(session_id=...)` → episode 按 session_id 聚合 → `GET /api/memory/sessions` → HistorySheet 按会话查看

**reasoning_content 流转**（思考链记录，不回传 LLM）：

LLM 返回 `reasoning_content` 字段 → `router.py` 解析到 `LLMResponse.reasoning_content` → `agent.py` yield `{type: "reasoning", content: ...}` 事件 + 写入 `Episode.reasoning`（不加入 messages，OpenAI 协议不支持 assistant 消息带此字段）→ SSE 推送前端 → MessageBubble 思考链展示区（Brain 图标 + 默认展开 + 浅色斜体）

### 规则模式（无 LLM 或 `--rule` 时，离线兜底）

```
用户输入 "装个QQ"
    ↓
[意图理解] intent.py
  ├─ 规则匹配：triggers "装" / "装个" 命中 install_app
  ├─ 参数提取：正则捕获 target="QQ"
  └─ 别名查询：QQ → [com.qq.QQ, linuxqq]
    ↓
[Skill 执行] skill_runner.py
  ├─ resolve_package: 选 flatpak（com.qq.QQ）
  ├─ install_via_flatpak: flatpak install -y --noninteractive com.qq.QQ
  │   └─ [安全引擎] 灰名单（YAML safety: grey）→ 弹确认框
  │   └─ 用户确认后 [执行器] subprocess 实时输出
  ├─ verify: flatpak list | grep com.qq.QQ
  └─ notify: notify-send "QQ 已安装完成"
    ↓
[反馈] 浮窗消息气泡 + 步骤列表 + 桌面通知
```

## 关键设计决策

1. **LLM Agent 主导 + 规则兜底（双轨模式）** ⭐ v0.6 核心架构变更：
   - **Agent 模式（默认）**：LLM 通过 function calling 调用 89 个 Skill 工具，能理解任意自然语言、多轮对话、主动追问、组合多个工具。用户说"电脑怎么这么卡啊"这种没有 trigger 关键词的模糊表达也能理解。
   - **规则模式（`--rule` 或无 LLM 时）**：基于 YAML triggers 正则匹配，离线可用，响应快，但只能识别预设说法。
   - **为什么这样设计**：用户不是只拿来处理 Linux bug，更用来解决实际问题。LLM 主导才能称为"智能助手"，规则作文档（triggers / examples / aliases / safety）让 LLM 知道何时调用哪个工具、如何安全执行。
2. **Agent 不绕过安全引擎**：Agent 调用的每个工具都走 `skill_runner.py` + `safety.py`，黑名单硬 ban / 灰名单人类语言确认 / 白名单自动执行的规则不变。LLM 不能直接执行 shell 命令，只能调用预定义的 Skill 工具。
3. **OpenAI function calling 协议**：原生支持 tools / tool_calls / tool_call_id / role:tool 消息。SenseNova deepseek-v4-flash、DeepSeek、OpenAI gpt-4o 等主流模型已实测可用。
4. **max_iterations 安全阀**：Agent 主循环最多 8 轮，防止 LLM 无限调用工具。达到上限时返回当前已执行的工具结果 + 提示"已达最大轮次"。
5. **安全分层**：黑名单硬 ban（绝不执行）+ 白名单自动（流畅）+ 灰名单确认（用人类语言问，不展示命令）。普通用户看不懂 `apt purge`，只展示"删除思源黑体字体包"。
6. **复合命令整体黑名单检测**：`curl ... | bash` 这种含 pipe 的危险复合模式必须在拆分前整体匹配，否则拆分后子命令会丢失上下文（见 traps T006）。
7. **Skill YAML 声明式**：triggers / parameters / aliases / steps / conditions / safety 全在 YAML 里，无需写 Python 代码就能加新 Skill。`tool_defs.py` 自动把 YAML 转成 LLM 可调用的工具定义。用户自定义 Skill 放 `~/.config/lihua/skills/` 自动加载。
8. **YAML safety 字段优先于 classify()**：Skill 作者在 YAML 中标注 `safety: grey` 的步骤，无论 classify() 怎么判断，都按 grey 处理（取更严格一方）。避免 `flatpak install` 被 `_WHITELIST` 误判为 white 而不弹确认（见 traps T014）。Agent 模式下这条同样适用。
9. **urllib 原生 function calling**：避免强制依赖 litellm。OpenAI 兼容端点用 urllib 直接 POST，原生支持 tools / tool_calls（见 traps T030-T032）。litellm 仅作为非 OpenAI 兼容 provider 的可选回退。
10. **venv + 软链安装**：避开 PEP 668 externally-managed-environment（见 traps T002），同时让 `lihua` 命令全局可用。
11. **Skill 优先级：alias 命中 > trigger 长度**：当多个 Skill 同时匹配时，能从文本提取出参数且命中别名表的 Skill 优先（如"装个思源黑体"同时匹配 install_app 和 install_font，但只有 install_font 的别名表里有"思源黑体"，所以选 install_font）。Agent 模式下此优先级仅用于规则兜底，LLM 自行决策。
12. **Tauri 桌面应用 + Python sidecar**：Tauri Rust 主进程通过 `std::process::Command` 启动 uvicorn 后端，前端 React 通过 HTTP API 通信。Rust 负责原生窗口/托盘/快捷键，Python 负责业务逻辑，互不干扰。
13. **systemd-run --user 后台启动**：避免 sandbox 终端关闭时 SIGHUP 子进程组导致应用消失（见 traps T019 之前的 nohup 问题）。
14. **负向先行断言区分查询 / 修改命令**：v0.5.0 引入。同一命令的查询子命令（如 `rsync --version` / `ssh-keygen -l` / `prime-select --query`）应自动执行，而修改子命令（如 `rsync -av /src/ /dst/` / `ssh-keygen -t ed25519`）走灰名单确认。用 `(?!...)` 在灰名单正则中排除查询子命令（见 traps T026）。
15. **trigger 长度优先 + alias 命中优先消歧**：v0.5.0 新增 40 个 Skill 后 trigger 冲突频繁（如 "磁盘满了" vs "磁盘"、"卸载磁盘" vs "卸载 firefox"）。依赖"命中最长 trigger 优先"和"alias 命中优先"两个策略自动消歧，无需在 Skill YAML 中显式声明冲突关系。

## 项目状态

详见 [process.md](./process.md)。当前阶段：**v0.8.23-alpha Agent 聚焦本职**。

架构设计详见 [ARCHITECTURE.md](./ARCHITECTURE.md)。

产品需求详见 [PRD.md](./PRD.md)。

踩坑记录详见 [traps.md](./traps.md)（T001-T083）。

## 贡献

详见 [ARCHITECTURE.md](./ARCHITECTURE.md) 的 Skill 编写指南（待补充）。

## License

MIT
