# Lihua 狸花猫 - 进度

## 项目目标

让普通用户也能省心用 Linux：自然语言 → 任务 → 自动执行 → 反馈，不用命令行。

**当前版本**：v0.8.30-alpha（pyproject `0.8.30`，Wayland fcitx5 修复 + Linux 桌面诊断知识注入 + fix_ime skill）
**阶段**：v0.7.0 UI 重构 + v0.7.1 增强 + v0.7.2 修复 + v0.7.3 极简模型设置 + v0.7.4 真机实测修复 + v0.7.5 细节精修 + GPU 加速 + 底层优化 + v0.7.6 下拉菜单 Portal 修复 + v0.7.7 日志系统 + v0.7.8 LogSheet 日志查看 UI + v0.7.9 流式输出 + Agent 多轮对话 + v0.7.10 AuditSheet 独立审计日志 + v0.7.11 beautify_ubuntu 能力扩展 + v0.7.12 Skill 库三层整合 + v0.7.13 交互式 confirm + sudo→pkexec + v0.7.14 Agent 行为优化 + v0.7.15 修复谎报成功 + 版本不匹配检测 + v0.8.0 run_shell 万能兜底工具 + v0.8.1 run_shell 安全增强 + v0.8.2 文件操作工具组 + v0.8.3 run_python 万能工具 + v0.8.4 confirm 弹窗富文本展示 + v0.8.5 新用户引导 + v0.8.6 confirm 超时修复 + v0.8.7 LLM 自我诊断能力增强 + v0.8.8 confirm 流程致命 bug 修复 + v0.8.9 自进化能力（self_restart / self_build / self_status）+ v0.8.10 自进化完善（self_version_bump + 前端 SSE 恢复）+ v0.8.11 二次进化第一支柱（记忆系统）+ v0.8.12 二次进化第二支柱（技能自生成）+ v0.8.13 二次进化第三支柱（模块化 Prompt 系统）+ v0.8.14 二次进化第四支柱（插件架构）+ v0.8.15 二次进化第五支柱（自监控分析）+ v0.8.16 记忆分层 + Skill 使用记录（参考 OpenClaw）+ v0.8.17 Skill 规则提升 + 月度归档（参考 OpenClaw）+ v0.8.18 踩坑记录机制（参考 trae 工作流）+ v0.8.19 UI 改进（窗口控制按钮 + 最大化铺满 + 底栏防误触）+ v0.8.20 记忆管理入口 + 思考链记录 + 上下文持久化 + 历史对话调取 + v0.8.21 ModelSheet 4 个 bug 修复 + v0.8.22 CLI 命令补全 + v0.8.23 Agent 聚焦本职 + v0.8.24 gui 启动自检+自动编译 + v0.8.25 ModelSheet 选模型退出 bug 修复 + 模型清单全面更新 + v0.8.26 ModelSheet 事件处理 DOM 级重构 + v0.8.27 滚动性能优化 + v0.8.28 滚动合成层提升 + v0.8.29 ConfirmSheet 布局修复 + confirm 超时自动关闭 + v0.8.30 Wayland fcitx5 候选框飘移+闪烁修复 + Linux 桌面诊断知识注入 + fix_ime skill

## 版本历史

### v0.8.30-alpha (2026-07-23) — Wayland fcitx5 修复 + 桌面诊断知识注入 + fix_ime skill（T086）

**问题背景**：用户反馈"输入法候选框有时候到处飘"+"按一个字母候选框闪两次"。用户说"lihua 一直修复不了，找到的原因好像也不对"。随后提出更深层需求："lihua 能具备你这种解决这一类问题的能力吗？"

**三层改造**：

1. **直接修复**（T086，`lib.rs` L350-361）：Wayland 会话下清除 `GTK_IM_MODULE`，让 WebKitGTK 使用 Wayland text-input-v3 协议
   - 根因：`GTK_IM_MODULE=fcitx` 强制 GTK3/4 用 X11 im module，Wayland 下坐标转换不正确→候选框飘移+闪烁
   - 参考：https://fcitx-im.org/wiki/Using_Fcitx_5_on_Wayland

2. **知识注入**（`prompt_builder.py` L320-386 + L409-415）：
   - 新增 `linux_troubleshooting` PromptSection（priority=15，在 principles 之后、tool_strategy 之前）
   - 包含诊断方法论（收集环境→对照已知问题→定位根因→最小化修复）
   - 包含已知问题知识库：输入法（Wayland GTK_IM_MODULE）、WebKitGTK（滚动卡顿、GPU 黑屏）、Wayland vs X11 差异速查表
   - 让 lihua 面对桌面环境问题时能系统化诊断，不盲目猜测

3. **fix_ime skill**（`src/lihua/data/skills/fix-ime.yaml`，85th skill）：
   - 8 个步骤：环境收集→诊断→修复 fcitx5/ibus→Kimpanel 后备→fcitx5-diagnose→通知
   - 23 个触发词（候选框飘/闪/不跟随等）
   - 自动检测 Wayland + GTK_IM_MODULE 并修复

**验证**：
- prompt_builder 验证通过（linux_troubleshooting section 在 tool_strategy 之前，prompt 总长 8089 字符）
- SkillRegistry 成功加载 fix_ime（84→85 skills）
- 全量测试 879 passed 无回归
- v0.8.30 启动正常，health API 确认 skills_count=85

### v0.8.29-alpha (2026-07-22) — ConfirmSheet 布局修复 + confirm 超时自动关闭（T085）

**问题背景**：用户反馈"确认执行的框特别长，看不到按钮没办法点"和"confirm 在 600s 等待后才出来"。根因链：ConfirmSheet 无 max-height → 按钮被推出可视区域 → 用户无法确认 → 600s 超时 → agent 继续运行 → 再次需要 confirm → 弹新框。且超时后前端 ConfirmSheet 不自动关闭（"幽灵弹窗"）。

**核心改造**（T085，3 处改动）：

1. **ConfirmSheet 布局修复**（`ConfirmSheet.tsx`）：sheet 容器加 `maxHeight: calc(100vh - 8rem)` + `flex flex-col`，内容区加 `overflow-y-auto flex-1`，顶部栏和按钮区加 `shrink-0`——按钮始终固定底部可见
2. **后端 confirm 超时推送事件**（`server.py` L170）：超时后推 `confirm_timeout` 事件到 SSE 流
3. **前端处理 confirm_timeout**（`App.tsx` L383-388 + `api.ts` L120）：收到事件后 `setConfirmPending(null)` 自动关闭旧 ConfirmSheet

**验证**：TypeScript 编译通过，v0.8.29 构建成功，`lihua gui` 启动正常

### v0.8.28-alpha (2026-07-22) — 滚动合成层提升（T084 续）

**问题背景**：v0.8.27 的 blur 降级不够，滚动仍卡。根因是滚动容器没有合成层提升——WebKitGTK 下 `overflow-y: auto` 每帧走 CPU 重绘。

**核心改造**：
1. 滚动容器加 `translateZ(0)` + `will-change: scroll-position`（`MessageList.tsx`）
2. 恢复 `.window-glass` + `.window-outer` 的 `translateZ(0)`（v0.8.27 错误移除导致窗口渲染退化为 CPU）
3. MessageBubble 加 `React.memo`（避免滚动时不必要重渲染）

### v0.8.27-alpha (2026-07-22) — 滚动性能优化（T084）

**问题背景**：用户反馈"对话的时候滚轮上下滑动，界面好卡。尤其是界面全屏最大化的时候"。根因是多层 backdrop-filter blur 在 Linux WebKitGTK 下性能极差（可能软件渲染），全屏时面积翻倍导致卡顿加剧。

**核心改造**（T084，`index.css` + `MessageBubble.tsx` + `MessageList.tsx`）：

1. **窗口 blur 降级**：`.window-glass` 的 `blur(40px) saturate(180%)` → `blur(20px)`
2. **消息卡片去 backdrop-filter**：`.card-glass` 从 `blur(16px) saturate(150%)` → 纯色 `rgba(60, 60, 67, 0.72)`，GPU 开销降低 ~90%
3. **输入框 blur 降级**：`.input-glass` 的 `blur(20px) saturate(150%)` → `blur(12px)`
4. **清理 will-change 滥用**：移除 `.window-outer`、`.window-glass`、`.card-glass`、`.input-glass` 的 will-change + translateZ（常驻合成层浪费 GPU 内存）
5. **消息 content-visibility: auto**（`MessageBubble.tsx`）：屏幕外消息跳过渲染，搭配 `contain-intrinsic-size: 120px` 避免滚动条跳动。流式消息不加
6. **scrollIntoView smooth → auto**（`MessageList.tsx`）：避免平滑滚动与手动滚动冲突

**验证**：
- TypeScript 编译通过，CSS 从 27.82KB → 27.47KB（减少 will-change/backdrop-filter 代码）
- v0.8.27 构建成功，`lihua gui` 启动正常，health API 确认 v0.8.27
- 待用户真机验证：滚动流畅度改善，全屏时不再卡顿

**版本号升级**：5 处 v0.8.26 → v0.8.27

### v0.8.26-alpha (2026-07-22) — ModelSheet 事件处理 DOM 级重构（T083）

**问题背景**：v0.8.25 的 T082 修复用 `stopPropagation` 阻止 Portal click 冒泡到遮罩，但浏览器测试证明该修复在标准浏览器中冗余。如果用户报告的 bug 发生在 Tauri WebKitGTK，说明 `stopPropagation`（React 合成事件级）在 Tauri WebView 中对 Portal 内容的处理可能不可靠。需要不依赖合成事件冒泡的更健壮方案。

**核心改造**（`desktop/src/components/ModelSheet.tsx`，T083）：

1. **遮罩层改用 `e.target === e.currentTarget`**（L284-286）
   - 旧：`onClick={handleClose}` + sheet 容器 `onClick={e => e.stopPropagation()}`——依赖合成事件冒泡到 sheet 容器被拦截
   - 新：`onClick={e => { if (e.target === e.currentTarget) handleClose() }}`——只在点击遮罩本身时关闭，DOM 级检查，不依赖冒泡
   - 移除 sheet 容器上已冗余的 `stopPropagation`

2. **Portal 容器加 `data-dropdown-list` 属性**（L492）
   - 供 window mousedown 监听器用原生 `closest()` 识别，不依赖 React ref

3. **window mousedown 监听器加 `closest()` fallback**（L143-144）
   - 旧：仅 `ref.contains(target)` 判断点击是否在下拉内（Portal ref 偶发未挂载时失效）
   - 新：加 `target.closest('[data-dropdown-list]')` 兜底，原生 DOM API 更可靠

4. Portal 容器的 `onMouseDown`/`onClick` stopPropagation 作为 defense-in-depth 保留

**验证**：
- TypeScript 编译通过（`tsc -b` 无错误），v0.8.26 构建成功（前端 1602 模块 + Rust 19.66s）
- `lihua gui` 启动正常（v0.8.26，进程运行中）
- 逻辑分析：点击下拉选项时 `e.target`（按钮）≠ `e.currentTarget`（遮罩），handleClose 不会触发——无论合成事件是否冒泡
- 待用户 Tauri 真机验证：选模型不再退出界面

**版本号升级**：5 处 v0.8.25 → v0.8.26（`__init__.py` / `lib.rs` / `tauri.conf.json` / `Cargo.toml` / `pyproject.toml`）

### v0.8.25-alpha (2026-07-22) — ModelSheet 选模型退出 bug 修复 + 模型清单全面更新

**问题背景**：用户报告两个问题：① "模型配置界面，点智谱，选择GLM 4.7,模型配置界面退出。用户没法换成功啊" ② "你没有到网上各家去看最新模型清单吧？很多基础模型都不是最新的！"

**核心改造**：

1. **修复 ModelSheet 选模型后界面退出 bug**（T082）
   - 根因：React Portal 事件冒泡——模型下拉列表用 `createPortal` 渲染到 `document.body`，Portal 内的 click 事件沿 **React 树**（不是 DOM 树）冒泡到 ModelSheet 根 div 的 `onClick={handleClose}`，导致选模型时整个界面退出
   - T079（v0.7.6）已修了 `onMouseDown` 的 `stopPropagation`，但 `onClick` 漏了
   - 修复：Portal 容器 div 加 `onClick={e => e.stopPropagation()}`（`ModelSheet.tsx` L495）
   - 同一个 Portal 下拉的两次踩坑：T079 修 mousedown，T082 补 click

2. **模型清单全面更新**（`model_presets.py`，上网查证 5 家厂商 2026-07 最新模型）
   - **智谱**：去掉过时的 glm-4.5-flash / glm-4.5-air；加入 glm-4.7（标准版 200K）/ glm-4-plus（经典旗舰 128K）；GLM-4.7-Flash 上下文 128K → 200K；GLM-5.2 上下文 128K → 200K
   - **Kimi**：修正 kimi-k2.6 描述（"开源旗舰" → "开源高效版"，K3 才是最新旗舰）
   - **MiniMax**：去掉旧模型 abab6.5s-chat；加入 MiniMax-M3（2026-06 发布，1M 上下文，多模态 coding）；MiniMax-M2.7 降为 basic（上一代旗舰）；recommended 从 M2.7 改为 M3
   - **DeepSeek** / **MiMo**：确认无需修改（已是最新）

**验证**：
- 后端 API `/api/models/presets` 返回正确：智谱 4 模型 / DeepSeek 2 / Kimi 2 / MiMo 2 / MiniMax 2，全部 recommended 指向最新旗舰
- 版本号 0.8.25 五处同步（Python / Rust code / tauri.conf.json / Cargo.toml / pyproject.toml）
- `lihua gui` 启动自检通过（二进制版本匹配 0.8.25），无需重新编译
- **全量测试 879 passed** 无回归
- **浏览器测试**（React 18 UMD + createPortal 复现）：标准浏览器中 T082 修复是冗余的——sheet 容器 div（L282）的 `onClick stopPropagation` 已在 React 合成事件路径中拦截 click，选模型不会触发 handleClose。用户报告的 bug 可能是 T079（v0.8.21 已修复）的残留或 Tauri WebKitGTK 特有差异。T082 作为额外防护层保留
- 待用户真机验证：选模型不再退出界面

### v0.8.24-alpha (2026-07-22) — gui 启动自检 + 自动编译：用户零编译零命令行

**问题背景**：用户强烈反馈"用户是不懂命令行的！能安装这个软件已经是最大的能力了，我们不能让用户每次还得自己编译吧？这个前后端的问题能不能解决？我经常遇到前后端不匹配的提示。软件就不能自己确认好编译好吗？这个软件也太傻了吧。"——根因是 Tauri 前端资源嵌入机制（T080）：`cargo build --release` 不触发 `beforeBuildCommand`，不会更新 codegen-assets，必须用 `npx tauri build --no-bundle`；而普通用户根本不会编译，版本号升级后二进制仍是旧的，前端 getVersion()（二进制内嵌 APP_VERSION）与后端 health.version（Python `__version__`）不一致，触发"版本不匹配"警告横幅。

**核心改造**：

1. **新增 `_check_binary_ready(desktop_dir)` 自检函数**（`cli.py` L809-864）
   - 三层检查，任何一层不通过都触发自动编译：
     - ① 二进制是否存在（`target/release/lihua-desktop`）
     - ② 前后端版本号是否匹配：Python `__version__`（如 `0.8.24`）去字母数字后缀 vs Rust `APP_VERSION`（如 `0.8.24-alpha`）去 `-alpha` 后缀
     - ③ 源代码是否比二进制新：前端 `src/*.ts(x)/css/html` + Rust `src-tauri/src/*.rs` + `tauri.conf.json`/`Cargo.toml` 的 mtime 对比
   - 设计意图：覆盖"版本号升级后没重新编译"、"改了前端代码没重新编译"、"改了 Rust 代码没重新编译"三种常见不匹配场景

2. **gui 命令集成自检**（`cli.py` L961-977）
   - 非 `--build` 模式下，启动前先调 `_check_binary_ready()`
   - 不通过时自动调 `_build_tauri()`（`npx tauri build --no-bundle`）编译
   - 编译失败才提示"请手动运行 lihua gui --build"
   - 用户只需 `lihua gui`，软件自己保证二进制永远是最新匹配的

**验证**：
- 版本号升级 0.8.23 → 0.8.24 后运行 `lihua gui`：
  - 自检正确检测到"Rust 源代码已更新"（lib.rs 被 version-bump 改过，mtime 比旧二进制新）
  - 自动触发 `npx tauri build --no-bundle`：npm run build（vite 1602 模块）+ cargo build（20.40s）成功
  - 输出"✓ 编译成功 (15.7 MB)" → "✓ 编译完成" → 启动
- 编译后再次自检返回 `ready=True`（不重复编译）
- 新增 7 个单元测试（`tests/test_gui_selfcheck.py`）覆盖 4 种场景：二进制不存在/版本不匹配/前端源码过期/Rust 源码过期/配置过期/alpha 后缀对齐/全部就绪，全部通过
- **全量测试 879 passed**（872 + 7 新增）

**版本号升级**：6 处 v0.8.23 → v0.8.24（`lihua self version-bump 0.8.24`）

### v0.8.23-alpha (2026-07-22) — Agent 聚焦本职：system prompt 精简 + 串台修复 + 死代码清理

**问题背景**：用户反馈"不同会话之间 agent 可能会串台，LLM 很难抓住用户真实需求"。查看对话历史发现：① LLM 过度调工具（steam dota2 诊断调了 26 个工具仍失败）② 过度澄清（用户说 self_build，LLM 反问"为什么要编译"而不直接做）③ 用户粘贴旧 UI 输出导致上下文混乱 ④ system prompt 过载（~268 行，含 ~100 行元能力描述让 LLM 分心于"自进化/记忆/自监控"而非"解决 Linux 问题"）。用户明确要求"不要为了 agent 更智能把本职工作忘记了"。

**核心改造**：

1. **删除 agent.py 死代码 `_SYSTEM_PROMPT`（L36-304，272 行）**
   - 该字符串在 v0.8.13 已被 `prompt_builder.build_system_prompt()` 替代，但旧代码一直留着
   - 删除后 agent.py 从 3787 行 → 3515 行

2. **精简 `prompt_builder.py` system prompt（~268 行 → 128 行模板，含 catalog 实际 242 行）**
   - A-E 核心工具（skill/run_shell/文件工具/run_python/read_log）保留，这是解决 Linux 问题的本职
   - F-L 元能力描述（~100 行）合并为一个短小节"## F. 元能力工具组（仅当用户明确要求时使用，不要主动发起）"，~8 行
   - usage_order 从 11 条 → 6 条（去掉元能力相关 5 条）
   - tool_examples 表从 26 行 → 8 行（去掉元能力示例 12 行）
   - key_rules 从 15 条 → 8 条（去掉元能力规则 7 条）
   - 让 LLM 聚焦"解决 Linux 问题"而非"自进化/记忆/自监控"

3. **优化前端 history 构建（`desktop/src/App.tsx` L235-242）**
   - 缩短到 10 条（旧 20 条，减少旧话题干扰）
   - 过滤包含 UI 边框字符（`╭╰╮╯│┃━┅`）的消息（用户粘贴旧 UI 输出导致串台）
   - 过滤过长的 assistant 消息（>800 字的诊断报告进 history 会干扰 LLM 注意力）

4. **全代码审查**（自己验证，Explore agent 结果不可信——编造了不存在的函数名）
   - safety.py / memory.py / config.py / skill_runner.py：无冗余、无硬编码路径、无重复定义
   - logging_config.py 全局状态（`_RING_BUFFER` / `_SSE_SUBSCRIBERS`）：在 GIL 下安全，`list()` 拷贝遍历避免竞态
   - agent.py `_execute_self_*` 通过 HTTP 调后端 `/api/self/*`：设计选择（让 agent 无论在哪都能调），非冗余

**验证**：
- 后端启动正常（v0.8.23a0，84 skills，LLM 可用）
- "装个QQ" dry_run 测试：LLM 正确选 install_app 相关工具 + 给出安装指南
- "为什么电脑这么慢" dry_run 测试：LLM 选诊断类工具（system_info / hardware_info / run_shell），符合 system prompt 诊断工作流
- 多轮对话测试（"我想装个聊天软件" → "那帮我装一下"）：LLM 正确理解上下文追问装哪个，不串台、不过度调工具
- 前端 history 过滤正则 7/7 测试通过（正常消息保留 / UI 边框过滤 / 过长 assistant 过滤 / user 消息不限长）
- system prompt 内容验证 14 项全部通过（A-E 保留 / F 精简 / G-L 删除 / usage_order 精简）
- **全量测试 872 passed**（修复 3 个过时测试：test_agent.py MAX_RUN_SHELL_CALLS 15→30 + confirm bool→str 16 处；test_tool_defs.py 5→17 内置工具 3 处）
- tsc + cargo check + Python import 全部通过
- **真机验证 `lihua gui`**：发现并修复 3 个启动问题——
  ① systemd-run 残留 unit 冲突（"Unit lihua-desktop.service was already loaded"）：启动前先 `systemctl --user stop/reset-failed` 清理旧 transient unit
  ② Rust 二进制版本过旧（v0.8.21-alpha）：重新 `cargo build --release`，版本号同步到 v0.8.23-alpha
  ③ 日志提示误导（systemd-run 模式下 /tmp/lihua-desktop.log 为空）：改为提示 `journalctl --user -u lihua-desktop -f`
  修复后 `lihua gui` 干净启动：无警告、无快捷键冲突、版本号一致
- **修复 "Could not connect to localhost: Connection refused"**（用户反馈"经常报错，必须解决"）：
  根因：后端启动需要 2-3 秒（Python uvicorn 导入），前端 WebView 加载后立即 fetch → 连接拒绝；运行中后端短暂中断（self_restart / 崩溃）也会触发
  ① `api.ts request<T>()` 加自动重试：网络错误（TypeError）时重试 2 次（300ms + 600ms），HTTP 错误码不重试
  ② `api.ts chatStream` 的 fetch 加重试：连接拒绝时重试 2 次（500ms + 1000ms）
  ③ `App.tsx` 启动时轮询 health（500ms 间隔，最多 15 秒），替代原来一次性 fetch
  ④ `App.tsx send()` 中 `health === null` 时友好提示"后端正在启动中"，不直接调 chatStream

**版本号升级**：6 处 v0.8.22 → v0.8.23

### v0.8.22-alpha (2026-07-22) — CLI 命令补全

**问题背景**：用户反馈"终端里面 `lihua --help` 是不是很多命令没放进去"。核对发现 `lihua --help` 只列 12 个顶层命令，后端 server.py 有 46+ 个 API 端点，涉及 6 个功能模块（记忆/自进化/技能自生成/Prompt/插件/自监控分析）完全没有对应 CLI 命令。

**核心改造**：

1. **新建 `src/lihua/self_evolve.py`（361 行）**：把 server.py 内联的自进化逻辑（build/restart/status/version_bump，约 300 行）抽成独立模块，server.py 和 cli.py 共用，避免代码重复。

2. **重构 `server.py` 4 个 self 端点**：`/api/self/restart`、`/build`、`/status`、`/version_bump` 改为调用 self_evolve.py 的函数，端点变瘦客户端（30 行），逻辑完全不变。server.py 从约 1910 行减到 1607 行。

3. **`cli.py` 新增 6 个子应用（35 个子命令）**，全部直接调底层模块（不走 HTTP，与 history/audit/config 风格一致）：
   - `memory`（9 命令）：stats/sessions/session/knowledge/traps/traps-search/export/clear/archive
   - `self`（4 命令）：status/build/restart/version-bump
   - `skill-auto`（6 命令）：list/stats/patterns/reload/delete/path
   - `plugin`（7 命令）：list/stats/info/reload/enable/disable/path（enable/disable 持久化到 plugins.toml）
   - `prompt`（2 命令，只读）：sections/stats（enable/disable 不持久化，不提供）
   - `analytics`（6 命令）：overview/report/tools/errors/skills/suggestions

4. **`__main__.py` `_KNOWN_SUBCOMMANDS` 同步**：加 memory/self/skill-auto/plugin/prompt/analytics（T011 教训：不同步会导致 `lihua memory` 被预处理成 `lihua run memory`）。

5. **`cli.py` docstring 补全**：从 12 行扩展到 65 行，覆盖全部命令用法示例。

**版本号升级**：用 `lihua self version-bump` 自举完成，6 处 v0.8.21 → v0.8.22

**验证**：`lihua --help` 显示 18 个命令；6 个新命令实测通过（memory stats / self status / prompt sections / plugin list / analytics overview / skill-auto list）；import 检查通过

**Plan 文件**：`.trae/documents/v0.8.22-cli-commands.md`

### v0.8.21-alpha (2026-07-22) — ModelSheet 4 个 bug 修复

**问题背景**：用户报告模型配置界面有 4 个 bug：① 每个 provider 的 API Key 不能持久化 ② 自定义 provider 不能单独持久化 ③ GLM 免费模型没更新（glm-4-flash-250414 → glm-4.7-flash）④ 除了 GLM-5.2 其他模型选不上（一点击下拉选项就退出）。

**修复内容**：

1. **Bug 1+2：Key 和自定义配置不持久化**（`desktop/src/components/ModelSheet.tsx`）
   - 根因：只有一个全局 apiKey state，切换 provider 时不保存/恢复；切到 custom 时用当前后端 config 覆盖了自定义输入
   - 修复：新增 `apiKeysByPreset` state（`Record<string, string>`）按 presetId 存储 key；handleSelectPreset 切换时保存当前 key + 恢复目标 key；切到 custom 时不覆盖 customApiBase/customModel

2. **Bug 3：GLM 免费模型过时**（`src/lihua/model_presets.py`）
   - 根因：glm-4-flash-250414 已过时
   - 修复：更新为 glm-4.7-flash（is_free=True），更新日期 2026-07-22

3. **Bug 4：下拉选项选不上**（`desktop/src/components/ModelSheet.tsx`）
   - 根因：window 的 mousedown 监听器在 click 之前触发，Tauri WebView 下 Portal 的 ref contains() 可能返回 false 导致下拉被误关闭；scroll 监听器用捕获模式导致内部滚动误关闭
   - 修复：下拉列表项加 `onMouseDown={e => e.stopPropagation()}` 阻止 mousedown 冒泡；scroll 监听器从捕获（true）改冒泡（false）
   - 详见 traps.md T079

**版本号升级**：6 处 v0.8.20 → v0.8.21

**验证**：tsc 通过 + cargo check 通过 + 后端 /api/models/presets 确认 glm-4.7-flash

**Plan 文件**：`.trae/documents/v0.8.21-modelsheet-bugfix.md`

### v0.8.20-alpha (2026-07-21) — 记忆管理入口 + 思考链记录 + 上下文持久化 + 历史对话调取

**问题背景**：用户提出 4 个连续性问题：① 没有合适的记忆/配置编辑入口，需在托盘增加记忆系统的初始化/查看/编辑功能；② Lihua 虽然是工具调用但没有很好记录思考链；③ 连续对话时上下文丢失，尤其 LLM 输出被打断时；④ 不能调取历史对话。经 AskUserQuestion 确认 3 个决策：4 个需求一次性全做 / 思考链默认展开 / 历史对话在 Sheet 里只读查看。

**核心改造**（6 阶段，跨会话续接完成）：

1. **阶段 A：session_id 贯穿 + messages 持久化 + SSE 重试**（上下文丢失修复）
   - 后端：ChatRequest 加 session_id 字段 → run_agent/run_agent_streaming 函数签名加 session_id → _record_episode / _record_episode_streaming 传 session_id → episode 按 session_id 聚合
   - 前端：App.tsx 生成 session_id（`s_{timestamp}_{random}`）存 localStorage → messages 按 session_id 分键持久化（`lihua:messages:{sessionId}`）→ 启动时恢复 → 新会话生成新 session_id → SSE 中断自动重试 1 次（显示"🔄 正在重连..."，非 LLM 错误才重试）

2. **阶段 B：思考链记录**（reasoning_content 解析 + 事件 + UI）
   - 后端：router.py LLMResponse 加 reasoning_content 字段 + _call_openai_compat_with_tools / _call_litellm 解析 → agent.py yield `reasoning` 事件 + 写入 Episode（不回传给 LLM，OpenAI 协议不支持）
   - 前端：AgentStreamEvent 加 reasoning 类型 → Message 加 reasoning 字段 → SSE switch 处理 reasoning case → MessageBubble 思考链展示区（Brain 图标 + 默认展开 + 浅色斜体）

3. **阶段 C：历史对话调取**（按 session_id 聚合 + Sheet 只读查看）
   - 后端：memory.py 新增 list_sessions / get_session_episodes 方法 → server.py 新增 4 个接口（/api/memory/sessions、/sessions/{id}、/knowledge、/export）
   - 前端：api.ts 加 4 个新 API 方法 + 5 个类型定义 → 新建 HistorySheet.tsx（左右分栏只读查看：会话列表 + episode 详情含 reasoning + tool_calls 简要）→ Sidebar 历史 tab 加"查看完整对话历史"按钮

4. **阶段 D：记忆管理入口**（托盘菜单 + MemorySheet）
   - Rust：lib.rs 托盘加"记忆管理..."菜单项 + emit open-memory 事件
   - 前端：App.tsx 监听 open-memory → 新建 MemorySheet.tsx（4 tab：统计/对话历史/知识库/踩坑 + 导出 JSON + 清空二次确认）

5. **阶段 E：版本号升级**：6 处版本号 v0.8.19 → v0.8.20

6. **阶段 F：文档更新**：process.md / traps.md / README.md

**新增文件**：
- `desktop/src/components/HistorySheet.tsx`：只读历史会话查看（左右分栏 + reasoning 折叠 + tool_calls 简要）
- `desktop/src/components/MemorySheet.tsx`：4 tab 记忆管理（统计/对话历史/知识库/踩坑 + 导出/清空）

**修改文件**：
- 后端：`src/lihua/server.py`（ChatRequest 加 session_id + 3 处调用传值 + 4 个新接口 + import time）/ `src/lihua/agent.py`（函数签名加 session_id + reasoning + 5 处调用传值 + yield reasoning 事件）/ `src/lihua/router.py`（LLMResponse 加 reasoning_content + 2 处解析）/ `src/lihua/memory.py`（Episode 加 reasoning + list_sessions / get_session_episodes）
- 前端：`desktop/src/api.ts`（chat/chatStream 加 sessionId + 5 个新 API 方法 + 6 个类型定义）/ `desktop/src/types.ts`（Message 加 reasoning）/ `desktop/src/App.tsx`（session_id 管理 + messages 持久化 + SSE 重试 + reasoning 事件 + 监听 open-memory + 渲染 MemorySheet/HistorySheet + 清理死代码 finalToolCalls/finalSuccess/finalError）/ `desktop/src/components/MessageBubble.tsx`（思考链展示区）/ `desktop/src/components/Sidebar.tsx`（历史 tab 加按钮 + onOpenHistorySheet prop）
- Rust：`desktop/src-tauri/src/lib.rs`（托盘 memory_item + open-memory 事件 + APP_VERSION）
- 版本号 6 文件升级 v0.8.19 → v0.8.20

**验证**：
- 前端类型检查：`npx tsc --noEmit` 通过（无错误）
- Rust 编译：`cargo check` 通过（1.47s）
- 后端启动：venv python 启动正常，version 返回 0.8.20a0
- 4 个新接口验证：
  - `GET /api/memory/sessions` → `{"ok":true,"sessions":[]}`（旧数据无 session_id，新会话后会有）
  - `GET /api/memory/knowledge` → 返回 7 个 pattern
  - `GET /api/memory/export` → 返回 14 episode + 7 pattern + 83.9% 成功率
  - `GET /api/memory/sessions/{id}` → 正确返回 episode 列表
- 功能验证清单（需用户在桌面环境确认）：
  - 发送消息后 MessageBubble 上方显示思考链（如 LLM 返回 reasoning_content）
  - 关闭桌面端再打开，messages 从 localStorage 恢复
  - 点击 TitleBar"新会话"按钮，生成新 session_id + messages 清空
  - 托盘"记忆管理"菜单项点击后弹出 MemorySheet
  - MemorySheet 4 个 tab 切换正常 + 导出 JSON + 清空二次确认
  - Sidebar 历史 tab"查看完整对话历史"按钮打开 HistorySheet
  - HistorySheet 左侧选中会话，右侧显示 episode 列表（含 reasoning 折叠）
  - 模拟 SSE 中断，前端显示"🔄 正在重连..."并重试 1 次

**关键决策**：
1. 4 个需求一次性全做（互相耦合：session_id 是 reasoning 记录和历史对话调取的共同基础）
2. 思考链默认展开（MessageBubble 不设折叠按钮，保持简洁）
3. 历史对话在 Sheet 里只读查看（低频需求，只读避免误改记忆）
4. session_id 前端生成（`s_{timestamp}_{random}` 格式，存 localStorage）
5. SSE 重试上限 1 次（避免无限重试，非 LLM 错误才重试）
6. localStorage 按 session_id 分键（避免单键超 5MB 配额，超限时只保留最近 20 条）
7. reasoning_content 不回传给 LLM（OpenAI 协议不支持 assistant 消息带此字段）
8. MemorySheet 不编辑单个 pattern/preference（只支持查看 + 清空重置）

**Plan 文件**：
- 完整需求分析 + 后端实施：`.trae/documents/v0.8.20-memory-thinking-context-history.md`
- 前端续接实施：`.trae/documents/v0.8.20-frontend-resume.md`

### v0.8.19-alpha (2026-07-21) — UI 改进（窗口控制按钮 + 最大化铺满 + 底栏防误触）

**问题背景**：用户反馈 UI 界面不足以支持 Lihua 的丰富功能，提出 4 个问题：① 需要增加按钮功能（如新会话）；② 底栏太纤细容易误触窗口拉扯；③ 没有最大化/还原按钮；④ 双击最大化后界面也很小。经 AskUserQuestion 确认 3 个关键决策：移除窗口最大尺寸限制（铺满屏幕）/ TitleBar 右侧加按钮组 / 增大 StatusBar 高度 + 底部安全区。

**核心改造**：
1. **移除窗口最大尺寸限制**（tauri.conf.json）：
   - 删除 `maxWidth: 900, maxHeight: 900` 两个字段
   - 保留 `minWidth: 480, minHeight: 480` 最小尺寸
   - 最大化时窗口可铺满屏幕，双击标题栏触发 Tauri 默认最大化

2. **新增 Tauri 窗口控制命令**（lib.rs）：
   - `cmd_minimize`：调 `win.minimize()`
   - `cmd_toggle_maximize`：手动判断 `is_maximized()` + 切换 `maximize()` / `unmaximize()`（Tauri 2.x 没有 toggle_maximize 方法，见 T078）
   - 注册到 `invoke_handler`

3. **TitleBar 改造按钮组**（TitleBar.tsx）：
   - 右侧按钮从 `侧栏切换 + 关闭` 扩展为 `新会话 + 侧栏切换 + 最小化 + 最大化/还原 + 关闭`（5 个）
   - 新会话：SquarePen 图标，title="新会话"
   - 最小化：Minus 图标，title="最小化"
   - 最大化/还原：Maximize2 / Minimize2 根据 isMaximized 切换
   - 关闭：X 图标，hoverDanger 变体（等同原 onHide，隐藏到托盘）
   - Props 新增：onNewChat / onMinimize / onToggleMaximize / isMaximized

4. **App.tsx 接入新回调 + isMaximized 监听**：
   - 新增 `isMaximized` state
   - 动态 import `@tauri-apps/api/window`，用 `getCurrentWindow().onResized()` 监听窗口大小变化，更新 isMaximized
   - 新增 3 个回调：`minimizeWindow` (invoke cmd_minimize) / `toggleMaximize` (invoke cmd_toggle_maximize) / `handleNewChat` (清空 messages + input)
   - TitleBar 调用扩展传入新 props

5. **StatusBar 增大高度 + 底部安全区**（StatusBar.tsx）：
   - 高度从 `h-7`（28px）改为 `h-9`（36px）
   - 加 `pb-1.5`（6px bottom padding）让按钮向上内缩，远离窗口底部 resize handle
   - 防止点击 StatusBar 右侧按钮（审计/日志）误触窗口拉扯

6. **版本号升级**：6 处版本号 v0.8.18 → v0.8.19

**新增文件**：无

**修改文件**：
- `desktop/src-tauri/tauri.conf.json`：删除 maxWidth/maxHeight + 版本号
- `desktop/src-tauri/src/lib.rs`：新增 cmd_minimize + cmd_toggle_maximize 命令 + 注册到 invoke_handler + APP_VERSION
- `desktop/src/components/TitleBar.tsx`：改造按钮组（2 按钮 → 5 按钮）+ Props 扩展
- `desktop/src/App.tsx`：isMaximized state + onResized 监听 + 3 个新回调 + TitleBar 调用扩展
- `desktop/src/components/StatusBar.tsx`：h-7 → h-9 + pb-1.5
- 版本号 6 文件升级 v0.8.18 → v0.8.19

**验证**：
- 前端构建：`npm run build` 通过（tsc 类型检查 + vite 打包，1600 modules transformed）
- Rust 编译：`cargo check` 通过（首次报 T078 toggle_maximize 不存在，修复后通过）
- 功能验证清单（需用户在桌面环境跑 `npm run tauri dev` 确认）：
  - TitleBar 5 个按钮显示正确
  - 新会话清空对话
  - 最小化/最大化/还原按钮工作
  - 双击标题栏最大化铺满屏幕（不再受 900×900 限制）
  - StatusBar 按钮不再误触窗口 resize

**已知问题**：
- skipTaskbar=true 时最小化行为需测试（窗口可能不在任务栏显示，只能通过托盘或 Ctrl+Alt+L 恢复）
- 详见 plan 文件 `.trae/documents/ui-improvement-v0.8.19.md` 的 Verification Steps

**踩坑**：T078（Tauri 2.0 WebviewWindow 没有 toggle_maximize 方法）

---

### v0.8.18-alpha (2026-07-21) — 踩坑记录机制（参考 trae 工作流）

**问题背景**：用户在 trae 里定了"每个项目维护 README.md + process.md + traps.md"的工作流，其中 traps.md 的三段式（现象→根因→解决方案）很适合融入 Lihua 的记忆系统。经 AskUserQuestion 确认，用户选择"B. 把 traps 机制融入 Lihua 自己的记忆系统"（而非让 Lihua 帮用户做项目时遵守这套工作流）。与 v0.8.16 usage_log + v0.8.17 rules 形成互补：usage_log 记每次使用 / rules 记提炼规则 / traps 记失败根因。

**核心改造**：
1. **Trap 数据结构**（memory.py）：
   - 新增 `Trap` dataclass：id / timestamp / symptom（现象）/ root_cause（根因）/ solution（解决方案）/ status（open/fixed/workaround）/ related_skills / related_keywords / fixed_at / fix_verified / occurrence_count
   - 存储：`~/.local/share/lihua/memory/traps.jsonl`（与 episodes.jsonl 同级），最多 200 条
   - `MemoryStore` 加 `add_trap` / `get_traps` / `get_trap` / `update_trap` / `search_traps` / `_load_traps_locked` / `_save_traps_locked` 方法
   - `add_trap`：自动分配递增 id，超过上限时删最旧的 open trap（fixed 优先保留作历史教训）
   - `search_traps`：按关键词匹配 symptom/root_cause/solution/related_keywords，open 优先排序
   - `update_trap`：支持填 root_cause/solution/改 status/标记 fix_verified/累加 occurrence_count

2. **自动记录**（skill_runner.py）：
   - `run_skill` 失败时自动追加 trap（status=open，root_cause/solution 留空待 LLM 诊断）
   - symptom = `skill「{name}」step「{step}」失败：{error}`
   - related_keywords 从用户输入提取（用于检索 + 匹配同类 trap）
   - 同类失败累加 occurrence_count（按 symptom 前 80 字符匹配，不重复创建）

3. **LLM 工具**（tool_defs.py + agent.py）：
   - `trap_search`（只读不走 confirm）：搜坑，必填 query + 可选 status
   - `trap_update`（走 confirm）：填根因/标记修复，必填 trap_id + intent，可选 root_cause/solution/status/fix_verified
   - `_execute_trap_search` / `_execute_trap_update` 实现
   - `_SYSTEM_PROMPT` 加 L 节（traps 工具组说明）

4. **Prompt 注入**（memory.py）：
   - `get_context_for_prompt` 注入相关的 open traps（最多 3 条，按关键词匹配）
   - 格式：`⚠️ 已知踩坑（open traps，遇到要小心）` + `T001 [skill]: symptom（出现 N 次）`
   - 让 LLM 知道"这些坑还没填"，遇到类似问题时小心

5. **HTTP 接口**（server.py）：
   - `GET /api/memory/traps`：列出所有 traps（可按 status 过滤）
   - `GET /api/memory/traps/search?q=...&status=...&limit=...`：搜索 traps
   - `POST /api/memory/traps`：手动添加 trap
   - `PATCH /api/memory/traps/{id}`：更新 trap（填根因/标记修复）

6. **统计**（memory.py）：
   - `get_stats` 加 traps 字段（total / open / fixed / workaround）
   - `clear_all` 清空 traps.jsonl

**新增文件**：无

**修改文件**：
- `src/lihua/memory.py`：Trap dataclass + _TRAPS_FILE 常量 + _MAX_TRAPS 常量 + MemoryStore 加 traps 方法 + get_context_for_prompt 注入 open traps + get_stats 加 traps 统计 + clear_all 清空 traps
- `src/lihua/skill_runner.py`：run_skill 失败时自动追加 trap + 同类失败累加 occurrence_count
- `src/lihua/tool_defs.py`：新增 build_trap_search_tool + build_trap_update_tool + build_tool_defs 注册（位置 15/16）
- `src/lihua/agent.py`：新增 _execute_trap_search + _execute_trap_update 函数 + _execute_tool 调度 + _SYSTEM_PROMPT L 节 + 可用工具列表
- `src/lihua/server.py`：新增 4 个 /api/memory/traps* 接口 + 修复 Body 导入 bug（T077）
- `src/lihua/prompt_builder.py`：L 节 + 可用工具列表 + 工具示例表 + 关键规则 + 使用顺序
- 版本号 6 文件升级 v0.8.17 → v0.8.18

**验证**：
- 语法检查 8 个文件全通过
- 后端启动 + /api/health 返回 v0.8.18a0
- 4 个 /api/memory/traps* HTTP 接口验证全通过（GET 列表 / POST 添加 / GET 搜索 / PATCH 更新）
- skill 失败自动追加 trap 验证：触发 test_trap_fail skill 失败 → traps.jsonl 自动追加 T001（symptom/related_skills/related_keywords 正确）
- 同类失败累加 occurrence_count 验证：再触发 2 次 → occurrence_count=3，trap 总数=1（不重复创建）
- LLM Agent 模式调用 trap_search 工具端到端验证通过：LLM 正确识别意图 + 选择工具 + 传参 + 中文解释结果（T001 / 出现 3 次 / 状态未修复 / 根因待填）
- /api/memory/stats 返回 traps 字段（total/open/fixed/workaround）

**已知问题**：无

**踩坑机制完整闭环**：
1. skill 失败 → 自动创建 trap（status=open，root_cause/solution 留空）
2. LLM 诊断 → trap_update 填 root_cause + solution
3. 验证修复 → trap_update 标记 status=fixed + fix_verified=true
4. 同类失败累加 occurrence_count（不重复创建）
5. 每次对话开始时相关 open traps 自动注入到"记忆上下文"区

### v0.8.17-alpha (2026-07-21) — Skill 规则提升 + 月度归档（参考 OpenClaw）

**问题背景**：延续 v0.8.16 的 OpenClaw 参考融入，完成两个 P1 设计：P1-1 Skill 规则提升机制（让 skill 边用边长，从 usage_log 提炼规则写入 rules 字段）+ P1-2 月度归档（让旧 episodes 按月分组移到 archive/ 目录，不阻塞 L2/L3 检索）。这是 OpenClaw "实践即认识" 设计的完整闭环：用前读 → 按 skill 做 → 用中记（usage_log）→ 用后调（skill_evolve）。

**核心改造**：
1. **P1-1 Skill 规则提升机制**（skill_evolve 工具）：
   - `SkillDef` 加 `rules: list[dict]` 字段（每条含 condition / action / reason / added_at / confidence）
   - `_parse_skill` 解析 YAML 的 `rules` 字段（向后兼容：旧 YAML 无此字段时为空列表）
   - 新增 `update_skill_rules(file_path, rules, max_rules=20)` 函数：备份 .yaml.bak + 清洗 + 裁剪 + 写入 rules（每条 condition≤200 / action≤100 / reason≤300 / confidence 0-1）
   - `skill_to_tool` 把 `skill.rules` 注入 tool description（让 LLM 调 skill 时看到"已验证规则"），格式 `[置信度] 条件 → 动作（原因）`，最多 10 条防 description 过长
   - 新增 `skill_evolve` 工具（agent 调用）：读 skill 的 usage_log → 调 LLM 总结新 rules 列表（提升/降级/保留/删除原则）→ 走 confirm → 写入 skill YAML → reload registry
   - LLM prompt 含 skill 信息 + 使用统计 + 最近 20 条 usage_log + 现有 rules + 规则提炼原则
   - LLM 输出 JSON 格式的新 rules 列表 + summary 总结
   - dry_run 模式只返回建议不写入
   - `skill_generator.GeneratedSkill.to_yaml()` 加 `rules: []` 初始字段

2. **P1-2 月度归档**（memory_archive 工具 + /api/memory/archive 接口）：
   - `MemoryStore.archive_old_episodes(days)` 完整实现（v0.8.16 是骨架）：
     - 读主 episodes.jsonl，按 timestamp 分为可归档（< cutoff）和保留（>= cutoff）
     - 可归档的按月份分组（YYYY-MM），追加写入 `archive/episodes_YYYY-MM.jsonl`
     - 重写主 episodes.jsonl 只保留近期数据（原子替换：先写 .tmp 再 replace）
     - 写归档失败的数据保留在主文件（不丢数据）
   - 新增 `POST /api/memory/archive` HTTP 接口（body: `{"days": 30}`，默认用 config.memory.archive_days）
   - 新增 `memory_archive` 工具（agent 调用，不走 confirm）：让 LLM 能在对话中触发归档
   - 归档后 episodes 不再被 memory_recall 检索（L4 冷数据）

**新增文件**：无

**修改文件**：
- `src/lihua/skills.py`：`SkillDef` 加 `rules` 字段 + `_parse_skill` 解析 + 新增 `update_skill_rules()` 函数
- `src/lihua/skill_generator.py`：`GeneratedSkill.to_yaml()` 加 `rules: []` 初始字段
- `src/lihua/tool_defs.py`：
  - `skill_to_tool` 注入 `skill.rules` 到 tool description
  - 新增 `build_skill_evolve_tool()` 函数
  - 新增 `build_memory_archive_tool()` 函数
  - `build_tool_defs` 注册 `skill_evolve`（位置 13）+ `memory_archive`（位置 14）
- `src/lihua/agent.py`：
  - 新增 `_execute_skill_evolve()` 函数（读 usage_log → 调 LLM → 走 confirm → 写 rules → reload）
  - 新增 `_execute_memory_archive()` 函数（调 archive_old_episodes + 返回统计）
  - `_execute_tool` 加 skill_evolve + memory_archive 调度
  - `_SYSTEM_PROMPT` 加 J 节（skill_evolve）+ K 节（memory_archive）
  - 可用工具列表加 skill_evolve + memory_archive
- `src/lihua/memory.py`：`archive_old_episodes` 从骨架升级为完整实现（按月分组 + 原子替换 + 错误兜底）
- `src/lihua/server.py`：新增 `POST /api/memory/archive` HTTP 接口
- `src/lihua/prompt_builder.py`：J 节 + K 节 + 工具示例表 + 关键规则 + 使用顺序 + 可用工具列表
- 版本号 6 文件升级 v0.8.16 → v0.8.17

**验证**：
- 语法检查 8 个文件全通过（agent / skills / skill_runner / skill_generator / tool_defs / prompt_builder / memory / server）
- 后端重启 + /api/health 返回 v0.8.17a0
- /api/memory/archive HTTP 接口验证：默认 30 天归档（无数据可归档）+ days=1 + days=30 + 手动构造 60 天前 episode 归档成功（写入 episodes_2026-05.jsonl，主文件 remaining_count=7，归档文件内容完整）
- LLM Agent 模式调用 memory_archive 工具端到端验证通过：LLM 正确识别意图 + 正确选择工具 + 正确传参 days=60 + 工具执行成功（LLM 最终回复因 429 速率限制失败，与工具无关）
- skill_evolve 工具静态验证：tool_defs 注册 + agent.py 调度 + LLM prompt 注入正确（动态测试需要构造带 usage_log 的 skill + 走 confirm 流程，复杂度高，留作真实使用场景验证）

**已知问题**：无

**OpenClaw 设计融入总结**（v0.8.16 + v0.8.17 完成）：
- ✅ P0-1 记忆分层加载（L0-L4）：v0.8.16 完成
- ✅ P0-2 Skill 使用记录（usage_log）：v0.8.16 完成
- ✅ P1-1 Skill 规则提升机制（skill_evolve）：v0.8.17 完成
- ✅ P1-2 月度归档机制：v0.8.17 完成
- 形成完整闭环：用前读（rules 注入 tool description）→ 按 skill 做 → 用中记（usage_log）→ 用后调（skill_evolve 提炼 rules）+ 旧记忆自动归档（memory_archive）

### v0.8.16-alpha (2026-07-21) — 记忆分层加载 + Skill 使用记录（参考 OpenClaw）

**问题背景**：二次进化 5 大支柱完成后，参考用户提供的 OpenClaw AGENTS.md（记忆系统 + 自学习机制），把其中两个 P0 设计融入狸花猫：L0-L4 记忆分层（让旧经验自动淡出）+ Skill 使用记录（"实践即认识"，每次用 skill 都写 usage_log，为 v0.8.17 skill_evolve 规则提升打基础）。

**核心改造**：
1. **P0-1 记忆分层加载**（L0-L4）：
   - L0 核心：system prompt（不变）
   - L1 长期：knowledge + preferences（不变）
   - L2 热：最近 `hot_days`（默认 3 天）episodes，`get_context_for_prompt` 只注入 L2
   - L3 温：`warm_days`（默认 7 天）内 episodes，`query_episodes` 只扫 L3
   - L4 冷：超过 `archive_days`（默认 30 天）的 episodes 归档不加载（v0.8.17 实现归档逻辑）
   - 新增 `MemoryStore.get_hot_episodes()` / `get_warm_episodes()` / `archive_old_episodes()` 方法
   - `MemoryConfig` 加 `hot_days / warm_days / archive_days` 三个配置项（可在 config.toml 调）
   - `get_memory_store()` 全局单例从 Config 读取分层参数
   - `/api/memory/stats` 返回 `layers` 字段（L2_hot / L3_warm / L4_cold 统计）

2. **P0-2 Skill 使用记录**（usage_log）：
   - `SkillDef` 加 `usage_log: list[dict]` 字段（默认空）
   - `_parse_skill` 解析 YAML 的 `usage_log`
   - 新增 `append_usage_log(file_path, entry, max_log=50)` 函数：追加一条记录到 skill YAML，自动裁剪到 50 条，长字段截断（user_input/notes 限 200 字符，params 值限 100 字符）防爆 YAML
   - `run_skill` 加 `user_input` 参数，执行后追加 usage_log（只对 user/auto source 的 skill 追加，builtin 在安装目录无写权限）
   - `skill_generator.GeneratedSkill.to_yaml()` 加 `usage_log: []` 初始字段
   - **修复 usage_log user_input 记录错误**：`agent.py` `_execute_tool` 加 `user_text` 参数 + 两个调用方传 `user_text=user_text`，让 usage_log 记录用户原始输入（而非 `[agent] test_usage_log({})` 内部描述）

**新增文件**：无

**修改文件**：
- `src/lihua/memory.py`：分层常量 + `MemoryStore.__init__` 加分层参数 + `_load_episodes_in_days` / `get_hot_episodes` / `get_warm_episodes` / `archive_old_episodes` 方法 + `query_episodes` 加 `days` 参数 + `get_context_for_prompt` 改用 L2 + `get_stats` 加 `layers` 字段 + `get_memory_store` 读 Config
- `src/lihua/config.py`：`MemoryConfig` 加 `hot_days / warm_days / archive_days` + `_from_dict` / `to_toml` / `_DEFAULT_CONFIG_TPL` 同步
- `src/lihua/skills.py`：`SkillDef` 加 `usage_log` 字段 + `_parse_skill` 解析 + 新增 `append_usage_log()` 函数
- `src/lihua/skill_runner.py`：`run_skill` 加 `user_input` 参数 + 末尾追加 usage_log
- `src/lihua/skill_generator.py`：`GeneratedSkill.to_yaml()` 加 `usage_log: []`
- `src/lihua/agent.py`：`_execute_tool` 加 `user_text` 参数 + `run_skill` 调用传 `user_input` + 两个 `_execute_tool` 调用方传 `user_text=user_text`
- 版本号 6 文件升级 v0.8.15 → v0.8.16

**验证**：
- 语法检查 6 个文件全通过
- 后端重启 + /api/health 返回 v0.8.16a0
- /api/memory/stats 返回 layers 字段（L2_hot / L3_warm / L4_cold）
- 测试 skill 规则模式 + Agent 模式各调一次 → usage_log 记录的用户原始输入正确（"测试使用记录" / "请帮我测试使用记录"，非 `[agent] test_usage_log({})`）
- LLM 对话正常

**已知问题**：无

**下一步**：v0.8.17 实现 P1-1 Skill 规则提升机制（skill_evolve 工具，从 usage_log 提炼规则）+ P1-2 月度归档机制（L4 冷数据压缩到 archive/）

### v0.8.15-alpha (2026-07-21) — 二次进化第五支柱：自监控分析

**问题背景**：延续二次进化 goal，5 大支柱中第 1（记忆系统）、第 2（技能自生成）、第 3（模块化 Prompt 系统）、第 4（插件架构）已完成。本版本实现第 5 支柱——自监控分析，让 LLM 能自省查看自己的运行数据：成功率、工具使用统计、错误分析、改进建议，从"凭感觉回复"进化到"基于数据回答"。这是 5 大支柱的最后一个，完成后二次进化 goal 全部完成。

**核心改造**：新增 `analytics.py` 模块 + `agent.py` 集成 `self_analyze` 工具 + `tool_defs.py` 注册工具定义 + `prompt_builder.py` 加 I 节 + `server.py` 新增 8 个 `/api/analytics/*` HTTP 接口，让 Lihua：
1. **可自省**：LLM 通过 self_analyze 工具查看自己的运行数据（成功率、工具统计、错误分析、建议）
2. **可量化**：从"我表现得还行"进化到"成功率 100%、平均耗时 3.3s、活跃 1 天"
3. **可优化**：基于数据给出改进建议（如某工具失败率 > 30%、诊断类占比高、知识库模式少等）
4. **可审计**：8 个 HTTP 接口让用户/前端也能查看 LLM 的运行数据
5. **闭环自进化**：5 大支柱形成完整闭环（记忆→技能生成→Prompt 模块化→插件扩展→自监控→反馈到记忆）

**新增文件**：
- `src/lihua/analytics.py`（约 400 行）：自监控分析核心
  - **数据源**：
    - `_load_audit_entries(limit=1000)`：从 audit_log 读 JSON 行（最后 1000 条）
    - `_load_memory_episodes(limit=500)`：从 memory.py MemoryStore 读最近 episodes
    - `_load_memory_stats()`：从 memory.py MemoryStore.get_stats() 读统计
  - **分类器**：
    - `_classify_command(command)`：按命令前缀分类（apt/snap/docker/git/...）
    - `_classify_user_question(user_input)`：按关键词分类（diagnose > config > fix > query > other）
  - **8 个分析函数**：
    - `get_overview()`：总览（总交互数/工具调用数/成功率/平均耗时/活跃天数/记忆数/Top 工具/Top 关键词）
    - `get_tool_stats()`：工具使用统计（每个工具的 count/success/fail/success_rate/avg_duration/common_errors）
    - `get_error_analysis()`：错误分析（失败交互数/失败率/失败工具 Top/错误分类/样本错误）
    - `get_question_categories()`：用户问题分类（总问题数/各类别数/百分比）
    - `get_skill_usage()`：技能使用频率（过滤内置工具）
    - `get_command_stats()`：命令使用统计（按分类汇总，来自 audit_log）
    - `get_suggestions()`：改进建议列表（规则：工具失败率>30%、诊断类占比高、知识库模式少、平均耗时长、命令类失败率高）
    - `generate_report()` / `generate_text_report()`：完整 dict 报告 / Markdown 文本报告

**修改文件**：
- `src/lihua/agent.py`：
  - `_execute_tool` 加 self_analyze 调度（只读不走 confirm）
  - 新增 `_execute_self_analyze(arguments, on_progress, dry_run)` 函数：调 analytics 生成文本报告 + dict 详情，返回 ToolCallRecord
  - `_SYSTEM_PROMPT` 新增 I 节（self_analyze 工具说明）
  - 可用工具列表加 `self_analyze`
- `src/lihua/tool_defs.py`：
  - 新增 `build_self_analyze_tool()` 函数（无参数，描述含"自进化""自省""只读不走 confirm"）
  - `build_tool_defs` 注册 `self_analyze`（位置 12，总 96 个工具）
- `src/lihua/prompt_builder.py`：
  - `_TOOL_STRATEGY_CONTENT` 新增 I 节（self_analyze 工具说明，含触发场景/返回内容/不走 confirm/基于数据的改进）
  - `_TOOL_CATALOG_CONTENT` 加 self_analyze
- `src/lihua/server.py`：新增 8 个 `/api/analytics/*` 接口
  - `GET /api/analytics/overview`：总览统计
  - `GET /api/analytics/tools`：工具使用统计
  - `GET /api/analytics/errors`：错误分析
  - `GET /api/analytics/questions`：用户问题分类
  - `GET /api/analytics/skills`：技能使用频率
  - `GET /api/analytics/commands`：命令使用统计（来自 audit_log 1000 条）
  - `GET /api/analytics/suggestions`：改进建议
  - `GET /api/analytics/report`：完整分析报告（dict + text）

**版本号升级**（6 个文件）：
- `src/lihua/__init__.py`：`0.8.14a0` → `0.8.15a0`
- `pyproject.toml`：`0.8.14a0` → `0.8.15a0`
- `desktop/package.json`：`0.8.14a0` → `0.8.15a0`
- `desktop/src-tauri/Cargo.toml`：`0.8.14` → `0.8.15`
- `desktop/src-tauri/tauri.conf.json`：`0.8.14` → `0.8.15`
- `desktop/src-tauri/src/lib.rs`：`0.8.14-alpha` → `0.8.15-alpha`

**验证记录**：
1. ✓ 语法检查（analytics/agent/tool_defs/server/prompt_builder/plugin_loader/memory/skill_generator 全部通过）
2. ✓ analytics 单元测试 11 项全部通过（命令分类/问题分类/总览/工具统计/错误分析/问题分类/技能使用/命令统计/建议/报告/文本报告）
3. ✓ 后端重启 v0.8.14a0 → v0.8.15a0
4. ✓ HTTP 端到端验证 8 个 /api/analytics/* 接口全部通过：
   - GET /api/analytics/overview → total_interactions=2, success_rate=1.0, avg_duration=3.34, top_keywords={"你好":2,"你是谁":2}
   - GET /api/analytics/tools → total_tools=0, total_calls=0
   - GET /api/analytics/errors → total_failed_episodes=0, fail_rate=0.0
   - GET /api/analytics/questions → total_questions=2, categories={"other":2}
   - GET /api/analytics/skills → total_skills_used=0
   - GET /api/analytics/commands → total_commands=1000, 18 个分类（echo/list/read_file/search/http/...），含 audit_log 真实数据
   - GET /api/analytics/suggestions → [] （所有指标正常，暂无建议）
   - GET /api/analytics/report → 完整 dict 报告（含所有统计）
5. ✓ LLM 端到端验证：POST /api/chat 发"你最近表现怎么样？请直接调用 self_analyze 工具..." → LLM 成功调用 self_analyze 工具，基于报告给出数据化回答：
   - "总交互次数：2 次（刚起步~）/ 工具调用：0 次 / 成功率：100% 🎉 / 平均响应耗时：3.3 秒 / 失败率：0.0% / 活跃天数：第 1 天"
   - 工具调用记录里 result_message 是完整 Markdown 报告，result_details 是完整 dict（含 command_stats 18 个分类）

**修复 bug**：
- 首次 LLM 端到端验证报错 `ToolCallRecord.__init__() got an unexpected keyword argument 'duration'`——_execute_self_analyze 误传了 duration 参数，但 ToolCallRecord 没有 duration 字段
- 修复：移除 duration 参数 + 移除 t0 参数（self_analyze 不需要计时）+ 移除调用方的 `import time as _t`

**五大支柱进度**：
1. ✅ 记忆系统（v0.8.11）：memory.py + memory_recall 工具 + 上下文自动注入 + episode 自动记录
2. ✅ 技能自生成（v0.8.12）：skill_generator.py + create_skill 工具 + auto_generated/ 目录 + 5 个 /api/skill/* 接口
3. ✅ 模块化 Prompt 系统（v0.8.13）：prompt_builder.py + 10 个内置 section + 7 个 /api/prompt/* 接口
4. ✅ 插件架构（v0.8.14）：plugin_loader.py + PluginAPI + 6 个 /api/plugin/* 接口 + 示例插件
5. ✅ 自监控分析（v0.8.15）：analytics.py + self_analyze 工具 + 8 个 /api/analytics/* 接口

**二次进化 goal 完成**：5 大支柱全部实现，Lihua 拥有了可扩展、可延伸、可塑造的自进化 agent 架构。

**已知问题**：无

---

### v0.8.14-alpha (2026-07-21) — 二次进化第四支柱：插件架构

**问题背景**：延续二次进化 goal，5 大支柱中第 1（记忆系统）、第 2（技能自生成）、第 3（模块化 Prompt 系统）已完成。本版本实现第 4 支柱——插件架构，让第三方能扩展 Lihua 而不需要改源码。插件是 Python 模块，放在 `~/.config/lihua/plugins/` 目录下，通过 `setup(api)` 函数注册 PromptSection / 钩子，第 3 支柱的 PromptBuilder 为此提供了 `register_section()` 入口。

**核心改造**：新增 `plugin_loader.py` 模块 + `server.py` 启动时自动加载插件 + 6 个 `/api/plugin/*` HTTP 接口 + 1 个示例插件，让 Lihua：
1. **可扩展**：插件通过 `api.register_section(PromptSection(...))` 注入 prompt 内容，无需改源码
2. **可塑造**：用户可在 `plugins.toml` 启用/禁用单个插件（白名单 + 黑名单）
3. **可延伸**：新增能力只需放一个 .py 文件到 `~/.config/lihua/plugins/`
4. **错误隔离**：单个插件失败不影响其他插件和主流程（try/except 包裹 import 和 setup）
5. **可调试**：通过 `/api/plugin/*` 接口查看插件状态、热重载、单点 enable/disable

**新增文件**：
- `src/lihua/plugin_loader.py`（616 行）：插件架构核心
  - `PluginMeta` dataclass：name / version / description / author（从 `__plugin_meta__` 读取）
  - `PluginInfo` dataclass：name / path / status / error / meta / registered_sections / module
  - `PluginAPI` 类：插件 setup() 时收到的对象，提供：
    - `api.builder`：PromptBuilder 实例
    - `api.config`：Config 实例
    - `api.log`：插件专属 logger（`lihua.plugin.{name}`）
    - `api.data_dir`：插件专属数据目录（`~/.local/share/lihua/plugin_data/{name}/`，自动创建）
    - `api.register_section(section)`：注册 PromptSection（自动加 "plugin" tag）
    - `api.unregister_section(name)`：移除 section
  - `PluginLoader` 类：
    - `load_all(config)`：扫描目录 + 读配置 + 逐个 import + setup()
    - `unload_all()`：逆序调 teardown() + 移除 section + 清空状态
    - `reload()`：unload + load
    - `list_plugins()` / `get_plugin(name)`
    - `enable_plugin(name)` / `disable_plugin(name)`：单点启用/禁用 + 更新配置文件
    - `_discover_plugins()`：扫描 .py 文件和含 __init__.py 的子目录
    - `_import_plugin(name, path)`：importlib 动态 import
    - `_load_one(...)`：加载单个插件（黑名单/白名单检查 → import → 读 meta → 调 setup）
    - `_set_plugin_state(name, enable)`：更新 plugins.toml
    - `stats()`：返回 total/loaded/disabled/error/skipped/plugins 列表
  - `get_loader()` / `reset_loader()`：全局单例
- `~/.config/lihua/plugins/example_plugin.py`：示例插件（Docker 专家提示）
  - 注册 `docker_expert` section（priority=55，在 tool_examples 和 key_rules 之间）
  - 完整 `__plugin_meta__` + `setup(api)` + `teardown(api)` 演示

**修改文件**：
- `src/lihua/server.py`：
  - `create_app` 开头加 `loader.load_all(cfg)` 自动加载插件（错误隔离，不影响主流程）
  - 新增 6 个 `/api/plugin/*` 接口：
    - `GET /api/plugin/stats`：插件加载器统计（total/loaded/disabled/error/skipped/plugins）
    - `GET /api/plugin/list`：列出所有已发现插件
    - `GET /api/plugin/{name}/info`：单个插件详情
    - `POST /api/plugin/reload`：重新加载所有插件
    - `POST /api/plugin/{name}/enable`：启用单个插件
    - `POST /api/plugin/{name}/disable`：禁用单个插件

**配置文件**：
- `~/.config/lihua/plugins.toml`（自动生成）：
  - `enabled = []`：白名单（空表示加载所有非黑名单插件）
  - `disabled = []`：黑名单（优先级高于 enabled）

**版本号升级**（6 个文件）：
- `src/lihua/__init__.py`：`0.8.13a0` → `0.8.14a0`
- `pyproject.toml`：`0.8.13a0` → `0.8.14a0`
- `desktop/package.json`：`0.8.13a0` → `0.8.14a0`
- `desktop/src-tauri/Cargo.toml`：`0.8.13` → `0.8.14`
- `desktop/src-tauri/tauri.conf.json`：`0.8.13` → `0.8.14`
- `desktop/src-tauri/src/lib.rs`：`0.8.13-alpha` → `0.8.14-alpha`

**验证记录**：
1. ✓ 语法检查（plugin_loader.py / server.py 全部通过）
2. ✓ PluginLoader 单元测试 12 项全部通过：
   - 加载所有插件（5 个候选：2 成功 + 3 失败）
   - 插件注册的 section 在 builder 中
   - build 时输出插件内容
   - 插件 section 顺序正确（priority=25 在 tool_strategy(20) 和 memory_context(30) 之间）
   - 卸载所有插件后 section 被移除
   - reload 后插件重新加载
   - disable_plugin：状态变 disabled + section 移除 + 配置文件更新
   - enable_plugin：状态变 loaded + section 恢复 + 配置文件恢复
   - 黑名单（disabled 列表）：插件被屏蔽
   - 白名单（enabled 非空）：未在列表的插件被跳过
   - PluginAPI data_dir 自动创建
   - 错误隔离：3 个坏插件（import 错误 / setup 错误 / 无 setup）不影响好插件
3. ✓ 后端重启 v0.8.13a0 → v0.8.14a0
4. ✓ /api/health 验证：version=0.8.14a0，skills_count=83，LLM available
5. ✓ example_plugin 自动加载（启动时 load_all 调用）
6. ✓ HTTP 端到端验证 6 个 /api/plugin/* 接口全部通过：
   - GET /api/plugin/stats → total=1, loaded=1（example_plugin）
   - GET /api/plugin/list → 列出 example_plugin v1.0.0
   - GET /api/plugin/example_plugin/info → 完整插件信息
   - POST /api/plugin/example_plugin/disable → "插件 'example_plugin' 已禁用"
   - 验证 stats：total=1, loaded=0, disabled=1
   - 验证 prompt/stats：total=10（docker_expert section 被移除）
   - POST /api/plugin/example_plugin/enable → "插件 'example_plugin' 已启用"
   - 验证 stats：total=1, loaded=1, disabled=0
   - POST /api/plugin/reload → "插件重载完成：1 成功，0 失败"
7. ✓ /api/prompt/stats 验证插件 section 注入：total=11（原 10 + docker_expert），priority=55 在 tool_examples(50) 和 key_rules(60) 之间，tags 含 "plugin"
8. ✓ LLM 端到端对话验证：POST /api/chat 发"你好，你是谁" → LLM 回复符合"狸花猫"角色定位，插件加载不影响 LLM 正常工作

**五大支柱进度**：
1. ✅ 记忆系统（v0.8.11）：memory.py + memory_recall 工具 + 上下文自动注入 + episode 自动记录
2. ✅ 技能自生成（v0.8.12）：skill_generator.py + create_skill 工具 + auto_generated/ 目录 + 5 个 /api/skill/* 接口
3. ✅ 模块化 Prompt 系统（v0.8.13）：prompt_builder.py + 10 个内置 section + 7 个 /api/prompt/* 接口
4. ✅ 插件架构（v0.8.14）：plugin_loader.py + PluginAPI + 6 个 /api/plugin/* 接口 + 示例插件
5. ⏳ 自监控分析（analytics.py + self_analyze 工具）

**已知问题**：无

---

### v0.8.13-alpha (2026-07-21) — 二次进化第三支柱：模块化 Prompt 系统

**问题背景**：延续二次进化 goal，5 大支柱中第 1（记忆系统）、第 2（技能自生成）已完成。本版本实现第 3 支柱——模块化 Prompt 系统，把原本硬编码在 agent.py 里的巨型 `_SYSTEM_PROMPT` 字符串（约 9000+ 字符）拆成多个独立的 section，每个 section 可单独编辑、启用/禁用、排序调整，并为第 4 支柱（插件架构）提供注册入口。

**核心改造**：新增 `prompt_builder.py` 模块 + `agent.py` 两个调用点迁移到 `build_system_prompt` + `server.py` 新增 7 个 `/api/prompt/*` HTTP 接口，让 system prompt：
1. **可扩展**：插件通过 `get_builder().register_section(PromptSection(...))` 注入新内容，无需改 `_SYSTEM_PROMPT`
2. **可塑造**：根据任务类型/用户偏好动态调整 section 顺序（priority）和内容
3. **可延伸**：新增功能时只需添加 section，不用改原有 prompt
4. **零侵入**：默认 PromptBuilder 构造的 prompt 和原 `_SYSTEM_PROMPT` 完全等价（向后兼容）
5. **可调试**：通过 `/api/prompt/stats` 查看所有 section 状态，`/api/prompt/sections` 查看详情

**新增文件**：
- `src/lihua/prompt_builder.py`（543 行）：模块化 Prompt 系统核心
  - `PromptSection` dataclass（name / content / priority / enabled / tags / description）+ `render(**kwargs)` 方法（try/except KeyError 容错，未知变量保留原样）
  - `PromptBuilder` 类：
    - `register_section(section)` / `unregister_section(name)` / `get_section(name)`
    - `enable(name)` / `disable(name)` / `enable_by_tag(tag)` / `disable_by_tag(tag)`
    - `list_sections()`（按 priority 排序）
    - `build(**kwargs)`（排序 → 跳过 disabled → render → `\n\n` 连接）
    - `stats()`（total/enabled/disabled/sections 列表）
  - 10 个内置 section 常量（priority 0-90）：
    - 0 `role` 角色定位（tag: core）
    - 10 `principles` 核心原则 5 条（tag: core）
    - 20 `tool_strategy` 工具使用策略 A-H 节（tag: tool）
    - 30 `memory_context` 记忆上下文（tag: memory）
    - 40 `usage_order` 使用顺序（tag: tool）
    - 50 `tool_examples` 工具选择示例（tag: tool）
    - 60 `key_rules` 关键规则
    - 70 `workflow` 工作流程
    - 80 `final_rules` 重要规则
    - 90 `tool_catalog` 可用工具列表（tag: tool）
  - `get_default_builder()`：注册所有内置 section
  - `get_builder()`：全局单例（插件通过此函数注册 section）
  - `reset_builder()`：重置全局 builder
  - `build_system_prompt(skill_count, skill_catalog, memory_context, builder=None, **extra_vars)`：便捷构造函数

**修改文件**：
- `src/lihua/agent.py`：
  - `run_agent` 中 `_SYSTEM_PROMPT.format(...)` 替换为 `build_system_prompt(...)`（L1584-1591）
  - `run_agent_streaming` 中同样替换（L1889-1895）
  - 原 `_SYSTEM_PROMPT` 字符串保留（向后兼容，但不再被调用）
  - 修复 `_SYSTEM_PROMPT` 的 `{"name":"prune"}` KeyError bug（改为 `{{"name":"prune"}}` 双花括号转义）
- `src/lihua/server.py`：新增 7 个 `/api/prompt/*` 接口
  - `GET /api/prompt/stats`：PromptBuilder section 统计（total/enabled/disabled/sections）
  - `GET /api/prompt/sections`：列出所有 section（按 priority 排序，含 content_length）
  - `POST /api/prompt/section/{name}/enable`：启用一个 section
  - `POST /api/prompt/section/{name}/disable`：禁用一个 section
  - `POST /api/prompt/tag/{tag}/enable`：按标签批量启用
  - `POST /api/prompt/tag/{tag}/disable`：按标签批量禁用
  - `POST /api/prompt/reset`：重置 PromptBuilder（重新注册所有内置 section）

**版本号升级**（6 个文件）：
- `src/lihua/__init__.py`：`0.8.12a0` → `0.8.13a0`
- `pyproject.toml`：`0.8.12a0` → `0.8.13a0`
- `desktop/package.json`：`0.8.12a0` → `0.8.13a0`
- `desktop/src-tauri/Cargo.toml`：`0.8.12` → `0.8.13`
- `desktop/src-tauri/tauri.conf.json`：`0.8.12` → `0.8.13`
- `desktop/src-tauri/src/lib.rs`：`0.8.12-alpha` → `0.8.13-alpha`

**验证记录**：
1. ✓ 语法检查（prompt_builder.py / agent.py / server.py 全部通过）
2. ✓ build_system_prompt 输出与原 _SYSTEM_PROMPT 关键内容对比：13 个关键短语全部匹配（角色定位/核心原则/A-H 节/记忆上下文/使用顺序/工具示例/关键规则/工作流程/重要规则/可用工具/clean_docker_cache/skill_count）
3. ✓ PromptBuilder 单元测试 10 项全部通过：
   - 默认 10 个内置 section
   - enable/disable 单个 section
   - 按 tag 批量禁用（tag=tool 禁用 4 个 section）
   - 插件注册 section（priority=25 插在 tool_strategy 和 memory_context 之间）
   - unregister section
   - 全局 builder 单例
   - build_system_prompt 便捷函数
   - disable 后 build 不输出
   - 按 tag 禁用后 build 不输出
   - stats 结构正确
4. ✓ 后端重启 v0.8.12a0 → v0.8.13a0
5. ✓ /api/health 验证：version=0.8.13a0，skills_count=83，LLM available
6. ✓ HTTP 端到端验证 7 个 /api/prompt/* 接口全部通过：
   - GET /api/prompt/stats → 返回 10 个 section，全部 enabled
   - GET /api/prompt/sections → 列出 10 个 section（含 content_length）
   - POST /api/prompt/section/principles/disable → "section 'principles' 已禁用"
   - POST /api/prompt/tag/tool/disable → "标签 'tool' 的所有 section 已禁用"
   - 验证 stats：total=10, enabled=5, disabled=5（principles + 4 个 tool tag）
   - POST /api/prompt/reset → "PromptBuilder 已重置"
   - 验证 stats：total=10, enabled=10, disabled=0（全部恢复）
7. ✓ LLM 端到端对话验证：POST /api/chat 发"你好，你是谁" → LLM 回复符合"狸花猫"角色定位，build_system_prompt 在实际 LLM 调用中工作正常

**五大支柱进度**：
1. ✅ 记忆系统（v0.8.11）：memory.py + memory_recall 工具 + 上下文自动注入 + episode 自动记录
2. ✅ 技能自生成（v0.8.12）：skill_generator.py + create_skill 工具 + auto_generated/ 目录 + 5 个 /api/skill/* 接口
3. ✅ 模块化 Prompt 系统（v0.8.13）：prompt_builder.py + 10 个内置 section + 7 个 /api/prompt/* 接口
4. ⏳ 插件架构（plugin_loader.py）
5. ⏳ 自监控分析（analytics.py + self_analyze 工具）

**已知问题**：无

---

### v0.8.12-alpha (2026-07-21) — 二次进化第二支柱：技能自生成

**问题背景**：延续二次进化 goal，5 大支柱中第 1 支柱（记忆系统）已完成。本版本实现第 2 支柱——技能自生成，让 agent 能把高频经验固化成可复用的 YAML 技能，形成"记忆 → 学习 → 生成技能 → 注册 → 使用 → 记忆"的正向循环。

**核心改造**：新增 `skill_generator.py` 模块 + `create_skill` 工具 + `skills.py load()` 扫描 `auto_generated/` 子目录 + system prompt H 节 + 5 个 `/api/skill/*` HTTP 接口，让 agent：
1. **主动生成技能**：LLM 看到某个工具链反复出现或解决了复杂任务后，可调 `create_skill(name, description, triggers, steps, ...)` 把它固化成 YAML 技能
2. **自动注册生效**：生成后立即 reload SkillRegistry，下次用户提到 trigger 时就会匹配到新技能
3. **安全管理**：技能名规则校验（小写字母开头+下划线/数字）+ steps 危险命令黑名单检测（rm -rf /、mkfs、dd of=/dev/、shutdown、reboot、curl|sh 等）+ 不覆盖内置/用户技能（auto 技能可覆盖更新并备份 .bak）
4. **走 confirm 流程**：用户看到技能内容预览（YAML 全文）后决定是否创建
5. **重复模式检测**：从记忆系统知识库找出出现 3+ 次的工具链，提示 LLM 考虑生成技能

**新增文件**：
- `src/lihua/skill_generator.py`（330 行）：技能自生成核心模块
  - `GeneratedSkill` dataclass + `to_yaml()` 序列化
  - `validate_skill_name()` / `validate_skill_steps()`（危险命令黑名单检测）
  - `check_name_conflict()`（不覆盖内置/用户技能，允许覆盖 auto 技能）
  - `save_skill()`（保存到 `~/.config/lihua/skills/auto_generated/`，覆盖时备份 .bak）
  - `list_auto_skills()` / `delete_auto_skill()` / `reload_registry()`
  - `detect_repeated_patterns()`（从记忆知识库找出现 3+ 次的工具链）
  - `generate_skill_suggestion()`（骨架生成器）
  - `get_skill_stats()`（统计信息）

**修改文件**：
- `src/lihua/skills.py`：
  - `_parse_skill`：允许 YAML 内 `source` 字段覆盖（auto 技能标注 `source: auto`）
  - `SkillRegistry.load()`：新增第 3 阶段加载 `auto_generated/` 子目录（覆盖内置/用户技能）
- `src/lihua/tool_defs.py`：
  - 新增 `build_create_skill_tool()`（90 行工具定义）
  - `build_tool_defs` 注册 `create_skill`（位置 11）
- `src/lihua/agent.py`：
  - `_execute_tool` 加 `create_skill` 调度
  - 新增 `_execute_create_skill` 函数（175 行）：参数解析 → 验证 → check_name_conflict → confirm → save_skill → reload_registry
  - system prompt 新增 H 节（技能自生成说明）+ 工具选择示例表加 create_skill 行 + 可用工具列表加 create_skill
- `src/lihua/server.py`：新增 5 个 `/api/skill/*` 接口
  - `GET /api/skill/auto/stats`：技能自生成系统统计
  - `GET /api/skill/auto/list`：列出所有自动生成技能
  - `DELETE /api/skill/auto/{name}`：删除自动生成技能（自动 reload）
  - `POST /api/skill/auto/reload`：手动 reload SkillRegistry
  - `GET /api/skill/auto/patterns`：检测重复工具链模式

**版本号升级**（6 个文件一致升级 v0.8.11 → v0.8.12）：
- `src/lihua/__init__.py` — `0.8.12a0`
- `pyproject.toml` — `0.8.12a0`
- `desktop/package.json` — `0.8.12a0`
- `desktop/src-tauri/Cargo.toml` — `0.8.12`
- `desktop/src-tauri/tauri.conf.json` — `0.8.12`
- `desktop/src-tauri/src/lib.rs` — `0.8.12-alpha`

**验证记录**：
1. ✓ 5 个文件语法检查通过（skill_generator.py / skills.py / tool_defs.py / agent.py / server.py）
2. ✓ skill_generator 所有 API 导入成功
3. ✓ validate_skill_name 合法/非法名验证通过（小写开头、大写开头、数字开头、过长名）
4. ✓ validate_skill_steps 危险命令检测通过（rm -rf /、mkfs、dd of=/dev/、curl|sh、空 steps）
5. ✓ check_name_conflict 不覆盖内置技能（install_app 冲突）、允许 auto 技能
6. ✓ 完整闭环：save_skill → list_auto_skills → reload_registry → SkillRegistry 加载 → trigger 匹配 → 覆盖更新（.bak 备份）→ delete → reload 确认删除
7. ✓ 不 allow_overwrite 时拒绝覆盖已存在文件
8. ✓ 即使 allow_overwrite=True 也拒绝覆盖内置技能（关键 bug 修复：save_skill 总是调 check_name_conflict）
9. ✓ tool_defs build_tool_defs 注册 create_skill（共 95 个工具）
10. ✓ _execute_create_skill 函数已定义
11. ✓ dry-run 模式只展示不写入
12. ✓ 参数校验：空参数 / 大写名 / 危险命令 / 覆盖内置 全部被拒
13. ✓ confirm 回调：用户拒绝时不写入文件 + 返回失败；用户确认时写入文件 + reload + 返回成功
14. ✓ 后端重启 v0.8.11a0 → v0.8.12a0
15. ✓ HTTP 端到端验证 5 个 /api/skill/* 接口全部通过（stats / list / patterns / reload / DELETE）

**五大支柱进度**：
1. ✅ 记忆系统（v0.8.11）：memory.py + memory_recall 工具 + 上下文自动注入 + episode 自动记录
2. ✅ 技能自生成（v0.8.12）：skill_generator.py + create_skill 工具 + auto_generated/ 目录 + 5 个 /api/skill/* 接口
3. ⏳ 模块化 Prompt 系统（prompt_builder.py）
4. ⏳ 插件架构（plugin_loader.py）
5. ⏳ 自监控分析（analytics.py + self_analyze 工具）

**已知问题**：无

---

### v0.8.11-alpha (2026-07-21) — 二次进化第一支柱：记忆系统

**问题背景**：用户发起 goal"自进化的agent应该有一个可扩展，可延伸，可塑造的架构，这个架构需要精心的规划和填充适当的内容。你来完成lihua的二次进化吧"。要求为 Lihua 设计 5 大支柱：记忆系统 / 技能自生成 / 模块化 Prompt / 插件架构 / 自监控分析。本版本实现第一支柱——记忆系统，让 agent 拥有跨会话的长期记忆，能从过去交互中学习。

**核心改造**：新增 `memory.py` 模块 + `memory_recall` 工具 + system prompt 记忆上下文自动注入 + episode 自动记录 + `MemoryConfig` 配置 + 4 个 `/api/memory/*` HTTP 接口，让 agent：
1. **自动记录**每次交互（用户输入 + 工具调用链 + 成功/失败 + agent 回复）到 `~/.local/share/lihua/memory/episodes.jsonl`
2. **自动学习**：从情景记忆提炼"问题→工具链→成功率"知识库存入 `knowledge.json`
3. **自动注入**：每次对话开始时把相关历史经验注入到 system prompt 的"记忆上下文"区
4. **主动检索**：LLM 可调 `memory_recall(query=...)` 工具深挖历史经验
5. **可观测可管理**：4 个 HTTP 接口让前端展示记忆统计、检索、清空

**三种记忆存储**：
- `episodes.jsonl`：情景记忆，追加写入，保留最近 1000 条，每条含 user_input / tool_calls / success / agent_response / duration
- `knowledge.json`：知识库，问题→工具链→成功率映射，自动从 episode 提炼，最多 500 个 pattern
- `preferences.json`：用户偏好，工具使用统计 + 关键词统计 + 滑动平均成功率

**实现方案**：

**1. memory.py 新模块**（583 行）
- `Episode` / `KnowledgePattern` / `UserPreferences` 三个 dataclass
- `_extract_keywords(text)`：中文 2-6 字片段 + 英文 3+ 字符单词，停用词过滤
- `MemoryStore` 类：`record_episode()` / `query_episodes()` / `get_relevant_knowledge()` / `get_context_for_prompt()` / `get_stats()` / `clear_all()`
- `get_memory_store()`：全局单例
- 线程安全（`threading.Lock()`），无外部依赖（纯 JSON 文件）
- 容量可配置（`max_episodes` / `max_knowledge_patterns`）

**2. tool_defs.py 新增 `build_memory_recall_tool()`**（L580-626）
- `[记忆] 检索过去的相关交互经验`
- 参数：`query`（必填）+ `limit`（可选，默认 5，最多 20）
- 在 `build_tool_defs` 中 `tools.insert(10, build_memory_recall_tool())`

**3. agent.py 集成记忆系统**
- `_execute_memory_recall` 函数：调 `store.get_relevant_knowledge()` + `store.query_episodes()`，格式化结果给 LLM
- `_execute_tool` 加 `memory_recall` 调度（L313-316）
- `_record_episode` / `_record_episode_streaming` 辅助函数：在 run_agent / run_agent_streaming 的 5 个返回点记录 episode
- system prompt 加 G 节（记忆工具说明）+ `{memory_context}` 占位符（自动注入）
- system prompt 构造时调 `memory_store.get_context_for_prompt(user_text)` 注入相关经验
- 工具选择示例表加 memory_recall 行

**4. config.py 新增 `MemoryConfig` dataclass**
- `enabled: bool = True`：是否启用记忆系统
- `max_episodes: int = 1000` / `max_knowledge_patterns: int = 500`：容量限制
- `inject_context: bool = True`：是否在 system prompt 注入记忆上下文
- `_from_dict` 解析 `[memory]` 子表 + `to_toml` 序列化 + 默认配置模板

**5. server.py 新增 4 个 `/api/memory/*` 接口**（L1351-1410）
- `GET /api/memory/stats`：统计信息（episodes 数 / patterns 数 / 成功率 / top 工具 / top 关键词）
- `POST /api/memory/query`：检索记忆（body: `{query, limit}`）
- `DELETE /api/memory/clear`：清空所有记忆
- `GET /api/memory/preferences`：获取用户偏好

**修改文件**：
- `src/lihua/__init__.py`（版本号 0.8.10a0 → 0.8.11a0）
- `pyproject.toml`（版本号）
- `desktop/package.json`（版本号）
- `desktop/src-tauri/Cargo.toml`（版本号 0.8.10 → 0.8.11）
- `desktop/src-tauri/tauri.conf.json`（版本号）
- `desktop/src-tauri/src/lib.rs`（APP_VERSION 0.8.10-alpha → 0.8.11-alpha）
- `src/lihua/memory.py`（新文件，583 行，三种记忆存储 + 关键词提取 + 上下文注入）
- `src/lihua/tool_defs.py`（+ `build_memory_recall_tool` + `build_tool_defs` 注册）
- `src/lihua/agent.py`（+ `_execute_memory_recall` + `_record_episode` + `_record_episode_streaming` + system prompt G 节 + `{memory_context}` 注入 + 5 个返回点记录 episode）
- `src/lihua/config.py`（+ `MemoryConfig` dataclass + `_from_dict` 解析 + `to_toml` 序列化 + 默认模板）
- `src/lihua/server.py`（+ 4 个 `/api/memory/*` 接口）

**验证**：
- 5 个文件语法检查通过 ✓
- `build_memory_recall_tool` 工具定义正确（parameters: query + limit）✓
- `build_tool_defs` 共 94 个工具，memory_recall 在第 11 位 ✓
- MemoryStore 初始化 + 关键词提取 + Episode 记录 + Episode 检索 + 知识库检索 + 统计 全部通过 ✓
- 空记忆时 `get_context_for_prompt` 返回空字符串（不报错）✓
- MemoryConfig 默认值正确（enabled=True, max_episodes=1000, inject_context=True）✓
- TOML `[memory]` 段解析 + 序列化 通过 ✓
- MemoryStore 支持配置参数（max_episodes=50, max_knowledge_patterns=20）✓
- `cfg.memory.enabled=False` 时跳过 episode 记录 ✓
- server 路由注册 4 个 `/api/memory/*` 接口 ✓
- 6 个版本号文件一致升级到 v0.8.11 ✓

**二次进化五大支柱进度**：
- ✅ Pillar 1：记忆系统（本版本完成）
- ⏳ Pillar 2：技能自生成 `skill_generator.py` + `create_skill` 工具
- ⏳ Pillar 3：模块化 Prompt 系统 `prompt_builder.py`
- ⏳ Pillar 4：插件架构 `plugin_loader.py`
- ⏳ Pillar 5：自监控分析 `analytics.py` + `self_analyze` 工具

---

### v0.8.9-alpha (2026-07-21) — 自进化能力：LLM 能修改自己的代码、重启、编译

**问题背景**：用户要求"拥有自进化的能力，可以修改自己的项目代码，操作自己重启，编译等，实现自我更新"。之前 LLM 已经能用 edit_file/write_file 改项目代码（项目目录在 ~ 下），但改完代码后无法重启后端让代码生效，也无法编译桌面端让 Rust 改动生效。

**核心改造**：新增 3 个自进化工具 + 3 个 HTTP 接口，让 LLM 能：
1. **self_restart**：重启后端让 Python 代码改动生效
2. **self_build**：后台编译桌面端 Tauri 二进制让 Rust 代码改动生效
3. **self_status**：查询编译/重启状态（轮询进度）

**实现方案**：

**1. server.py 新增 3 个 HTTP 接口**（L1000-1207）
- `POST /api/self/restart`：spawn 独立重启脚本（detached），脚本 sleep 1s → pkill 旧 uvicorn → sleep 2s → nohup spawn 新 uvicorn。接口立即返回，不阻塞
- `POST /api/self/build`：spawn 后台编译脚本（`npx tauri build --no-bundle`），状态写到 `~/.local/share/lihua/build-status.json`
- `GET /api/self/status`：查询编译/重启状态 + 当前后端 PID + 版本号

**2. agent.py 新增 3 个工具执行函数**（L2039-2338）
- `_execute_self_restart`：走 confirm（会中断当前 SSE 流），调 `/api/self/restart`
- `_execute_self_build`：走 confirm（长时间任务），调 `/api/self/build`
- `_execute_self_status`：只读不走 confirm，调 `/api/self/status`，格式化状态信息给 LLM

**3. tool_defs.py 新增 3 个工具定义**（L429-533）
- `build_self_restart_tool()`：`[自进化] 重启后端服务`
- `build_self_build_tool()`：`[自进化] 后台编译桌面端 Tauri 二进制`
- `build_self_status_tool()`：`[自进化] 查询编译/重启状态`

**4. agent.py system prompt 新增 F 节**（L133-161）
- 自进化工具组使用说明
- 项目代码编辑流程（edit_file → self_restart / self_build）
- 版本号升级（6 个文件）
- git 提交作为回滚点
- 工具选择示例表新增 3 行

**5. _execute_tool 加工具调度**（L262-271）
- self_restart / self_build / self_status 三个工具名转发到对应执行函数

**修改文件**：
- `src/lihua/__init__.py`（版本号 0.8.8a0 → 0.8.9a0）
- `pyproject.toml`（版本号）
- `desktop/package.json`（版本号）
- `desktop/src-tauri/Cargo.toml`（版本号 0.8.8 → 0.8.9）
- `desktop/src-tauri/tauri.conf.json`（版本号）
- `desktop/src-tauri/src/lib.rs`（APP_VERSION 0.8.8-alpha → 0.8.9-alpha）
- `src/lihua/server.py`（+3 个 HTTP 接口：self/restart、self/build、self/status）
- `src/lihua/agent.py`（+3 个工具执行函数 + system prompt F 节 + _execute_tool 调度）
- `src/lihua/tool_defs.py`（+3 个工具定义 + build_tool_defs 注册）

**验证**：
- 模块导入成功，版本 0.8.9a0
- 工具列表包含 self_restart / self_build / self_status（工具总数 92）
- `/api/self/status` 初始状态正确返回 `{"build":null,"restart":null,"current_pid":887719}`
- `/api/self/build` 启动后台编译，3 秒后状态变 `running`，22 秒后完成 `exit_code=0`
- `/api/self/restart` 触发重启，旧后端 PID=887719 被 kill，3 秒后新后端 PID=892420 就绪
- LLM 端到端验证：发送"查一下你的编译和重启状态" → LLM 2.063s 调用 self_status 工具 → 返回状态 → 5.966s Agent 完成，用 markdown 表格格式化状态

**T074 关键挡路 bug 修复**（SSE 流接口 auto_confirm confirm_cb 返回类型）：
- 现象：LLM 自进化闭环测试时，auto_confirm=True 模式下 edit_file 返回"❌ 用户取消了编辑"
- 根因：v0.8.6 把 ConfirmCallback 返回类型从 bool 改成 str，只修了非流式接口，漏了流式接口（L519 仍返回 `True`）
- `True != "confirmed"` 被误判为取消，导致 auto_confirm=True 时 edit_file/write_file 都被取消
- 修复：L519 `lambda msg, cmd: True` → `lambda msg, cmd: "confirmed"`
- 这正是 goal 第 (1) 条"系统性排查并修复所有挡路 bug"的典型案例——v0.8.6 引入的回归 bug 阻止了 LLM 自编辑代码

**T075 状态同步 bug 修复**（self_restart 后 SSE 流提前断开）：
- 现象：LLM 调 self_restart 后，SSE 流在 done 事件发出前断开，前端显示"连接失败"
- 根因：重启脚本 sleep 1s 太短，LLM 生成回复需要 2-3s，1s 后后端就被 kill
- 修复：重启脚本 sleep 从 1s 延长到 5s（kill 后 sleep 从 2s 延长到 3s），总共约 8s
- 同步更新所有用户可见消息（"约 3 秒"→"约 8 秒"）
- 这是 goal 第 (1) 条"状态同步问题"的典型案例——异步操作（重启）与同步流程（SSE）的时序协调

**LLM 自进化闭环验证完全通过**（`/tmp/test_llm_self_evolve_v3.py`）：
- 技术闭环验证（手动 edit + self_restart）：加字段 → 重启 → health 返回新字段；回滚 → 重启 → 字段消失
- LLM 闭环验证：让 LLM "edit_file 加 test_sse 字段 → self_restart 重启"
  - LLM 完成完整工具链：read_file → run_shell → read_file → edit_file → self_restart
  - SSE 流正常收到 done 事件（15.7s 调 self_restart → 18.6s 收到 done，**未断开**）
  - 代码中 test_sse 出现 1 次（代码已改）
  - 重启后 health 接口返回 test_sse=ok（新代码生效）
  - 总耗时 28.8s（含 10s 等待新后端）
- 验证了 goal 第 (4) 条"拥有自进化的能力"——LLM 能 read_file → edit_file → self_restart 完成自我更新闭环

---

### v0.8.10-alpha (2026-07-21) — 自进化完善：self_version_bump + 前端 SSE 恢复

**问题背景**：v0.8.9 的自进化能力有 3 个工具（self_restart / self_build / self_status），但版本号升级仍需 LLM 手动 edit_file 改 6 个文件（容易遗漏）。此外 self_restart 后 SSE 流断开时前端只显示"连接失败"，不自动检测后端恢复。

**核心改造**：

**1. self_version_bump 工具——一键升级 6 个版本号文件**
- `src/lihua/server.py` L1219-1349：`POST /api/self/version_bump` 接口
  - 支持自动 patch+1（如 0.8.9a0 → 0.8.10a0）或指定版本号
  - 正则替换 6 个文件：__init__.py / pyproject.toml / package.json / Cargo.toml / tauri.conf.json / lib.rs
  - 三种格式自动派生：Python `0.8.10a0` / Rust JSON/TOML `0.8.10` / Rust code `0.8.10-alpha`
- `src/lihua/agent.py` L2402-2513：`_execute_self_version_bump` 工具执行函数
  - 走 confirm（修改项目文件，用户应知道）
  - 调 `/api/self/version_bump` 接口（支持 JSON body）
  - 返回升级结果（old_version → new_version + 更新文件列表）
- `src/lihua/agent.py` L308-310：`_execute_tool` 加 self_version_bump 调度
- `src/lihua/tool_defs.py` L536-577：`build_self_version_bump_tool()` 工具定义
- `src/lihua/tool_defs.py` L601：`build_tool_defs` 注册（insert 9）
- `src/lihua/agent.py` L133-160：system prompt F 节加 self_version_bump 说明
- `src/lihua/agent.py` L187,190,199-200：工具选择示例表 + 关键规则更新

**2. _http_post 支持 JSON body**
- `src/lihua/agent.py` L2094-2117：新增 `body: dict | None = None` 参数
  - body 不为 None 时发送 JSON（Content-Type: application/json）
  - body 为 None 时保持旧行为（空 POST），向后兼容

**3. 前端 SSE 断开自动检测恢复**
- `desktop/src/App.tsx` L307-344：catch 块改进
  - SSE 流断开时先显示"连接中断（可能是后端重启中），3 秒后自动检测恢复..."
  - 3 秒后调 health API 检测后端是否恢复
  - 恢复则显示"✅ 后端已重启恢复，可以继续对话了"
  - 未恢复则显示原始错误 + "如果刚执行了 self_restart，请等几秒后重试"

**修改文件**：
- 6 个版本号文件（0.8.9a0 → 0.8.10a0 / 0.8.10 / 0.8.10-alpha）
- `src/lihua/server.py`（+version_bump 接口，v0.8.9 已添加）
- `src/lihua/agent.py`（+_execute_self_version_bump + _http_post body 支持 + system prompt + 调度）
- `src/lihua/tool_defs.py`（+build_self_version_bump_tool + 注册）
- `desktop/src/App.tsx`（catch 块改进，需重新编译桌面端才生效）

**验证**：
- 语法检查通过（agent.py / tool_defs.py / server.py）
- `/api/self/version_bump` 接口直接调用：0.8.9a0 → 0.8.10a0，6/6 文件更新成功
- 6 个文件版本号验证：Python 0.8.10a0 / Rust 0.8.10 / Rust code 0.8.10-alpha ✓
- 重启后端后 health 报告 0.8.10a0 ✓
- LLM 端到端验证（`/tmp/test_self_version_bump.py`）：
  - LLM 成功调用 self_version_bump(intent="...", version="0.8.11a0")
  - 工具返回"✅ 版本号升级完成：0.8.10a0 → 0.8.11a0，6/6 文件更新"
  - LLM 生成 markdown 表格回复，列出 6 个文件更新状态
  - 6 个文件实际版本号验证全部通过
- 验证后恢复版本号为 0.8.10a0

**自进化工具组完整闭环**（v0.8.10 完成）：
1. `read_file` 看代码 → `edit_file` 改代码
2. `self_version_bump` 一键升级 6 个版本号文件
3. `self_restart` 重启后端让 Python 改动生效 / `self_build` 编译桌面端让 Rust 改动生效
4. `self_status` 验证重启/编译状态
5. `git commit` 作为回滚点（run_shell）

---

### v0.8.8-alpha (2026-07-21) — confirm 流程致命 bug 修复

**问题背景**：用户反馈"确认执行的弹窗 GUI 老是跳出不来，等待时间结束了才跳出来并且报超时"。日志中有 5 次 confirm_id 不匹配 + 1 次 "流式 Agent 异常：name 'log' is not defined"。端到端测试发现用户点击确认后报 "'str' object has no attribute 'level'"。

**根因**：confirm 流程有两个致命 bug：
1. `_make_interactive_confirm_cb`（模块级函数）使用了 `log` 变量，但 `log` 只在 `create_app` 内部定义 → confirm 超时时抛 NameError → Agent 流异常终止
2. `confirm(msg, cmd)` 返回字符串赋给 `decision` 变量，覆盖了原来的 SafetyDecision 对象 → 后续 `decision.level` 访问字符串的 `.level` 属性报错 → 用户点击确认后 Agent 异常终止

**修复方案**：

**1. Phase 1 修复 _make_interactive_confirm_cb 中 log 变量未定义 bug**
- `src/lihua/server.py` L138-140：`_make_interactive_confirm_cb` 函数内部获取 logger
  ```python
  from lihua.logging_config import get_logger
  _log = get_logger(__name__)
  ```
- L168：`log.warning(...)` → `_log.warning(...)`
- 修复后 confirm 超时分支不再抛 NameError，正常返回 "timeout"

**2. Phase 2 修复 confirm 返回值覆盖 decision 变量 bug**
- `src/lihua/agent.py` 4 处 confirm 调用：`decision = confirm(...)` → `confirm_decision = confirm(...)`
  - `_execute_run_shell` L462（有 `decision.level` bug，导致 'str' has no attribute 'level'）
  - `_execute_run_python` L631（统一改名）
  - `_execute_write_file` L1139（统一改名）
  - `_execute_edit_file` L1322（统一改名）
- `src/lihua/skill_runner.py` L406：`decision = confirm(...)` → `confirm_decision = confirm(...)`
- 修复后 `decision` 保持 SafetyDecision 对象不变，`confirm_decision` 存储 confirm 返回字符串

**3. Phase 3 v0.8.7 第二轮修复（补记）**
- `src/lihua/safety.py` L602-622：GPU/图形/显示诊断命令白名单
  - nvidia-smi / glxinfo / vainfo / vulkaninfo / drm_info / lscpu / lsblk / lsmod / dbus-send / gdbus
  - blkid 正则 `\bblkid\b\s*$` → `\bblkid\b(?:\s|$)` 支持带参数
  - xrandr 只匹配只读子命令（--query/--current 等），修改类子命令走 grey
- `desktop/src-tauri/src/lib.rs` L78-107：start_backend 端口占用检测
  - 启动前检测端口是否被占用，被占用用 `fuser -k` / `pkill -f` kill 旧进程
  - 等待端口释放后再启动新后端

**修改文件**：
- `src/lihua/__init__.py`（版本号 0.8.7a0 → 0.8.8a0）
- `pyproject.toml`（版本号）
- `desktop/package.json`（版本号）
- `desktop/src-tauri/Cargo.toml`（版本号 0.8.7 → 0.8.8）
- `desktop/src-tauri/tauri.conf.json`（版本号）
- `desktop/src-tauri/src/lib.rs`（APP_VERSION 0.8.7-alpha → 0.8.8-alpha）
- `src/lihua/server.py`（_make_interactive_confirm_cb 内部获取 logger）
- `src/lihua/agent.py`（4 处 confirm 调用 decision → confirm_decision）
- `src/lihua/skill_runner.py`（1 处 confirm 调用 decision → confirm_decision）
- `traps.md`（T068-T071 新增）

**踩坑**：T068（nvidia-smi/blkid 白名单正则太严格）、T069（桌面端端口占用检测）、T070（_make_interactive_confirm_cb log 变量未定义）、T071（confirm 返回值覆盖 decision 变量）

**验证**：
- 后端重启 v0.8.8a0 生效（curl /api/health 返回 version=0.8.8a0）
- `_make_interactive_confirm_cb` 超时分支测试通过（mock _CONFIRM_TIMEOUT=1s，返回 "timeout"，无 NameError）
- 桌面端 Tauri 二进制重新编译完成（`npx tauri build --no-bundle`，二进制含 `0.8.8-alpha` 版本字符串）
- 旧桌面端（PID 830607）+ 手动启动后端（PID 839481）清理后启动新桌面端（PID 857613）
- 桌面端自动拉起 v0.8.8a0 后端（PID 857639），health 接口返回 `{"version":"0.8.8a0","llm_available":true,...}`
- confirm 流程端到端测试通过（`/tmp/test_confirm_v0_8_8.py`）：
  - 发送 "执行命令 pkexec echo hello"
  - needs_confirm 事件在 2.718s 后到达（LLM 思考时间，正常）
  - 用户点击确认后（1s 延迟模拟），命令成功执行（pkexec echo hello 输出 hello）
  - 6.576s 收到 tool_call_end success=True
  - 8.850s 收到 done 事件，Agent 正常完成
  - 无 'str' has no attribute 'level' 错误
  - 无 name 'log' is not defined 错误
  - 后端日志无异常

---

### v0.8.7-alpha (2026-07-20) — LLM 自我诊断能力增强 + 修复挡路 bug

**问题背景**：用户反馈"代码的执行过程还有很多问题。我们有 LLM，理论上可以更快更精准地定位问题，解决问题。不能让执行确认这种 bug 挡在了解决问题的路上。Linux 是非常好的适合 LLM 操作的系统。我们要利用好 Linux 的终端，把 Linux 完全地操控起来。"

核心诉求：(1) 修复所有"挡路 bug"让 LLM 操作 Linux 不被卡住；(2) 增强 LLM 利用 Linux 终端可观测性的能力（自我诊断）；(3) 优化执行流程减少不必要确认/超时。

**修复方案**：

**1. Phase 1 新增 read_log 工具——LLM 自我诊断的利器**
- `src/lihua/agent.py` L791-913 新增 `_execute_read_log` 函数：
  - 读 Lihua 自己的日志（默认 `~/.local/share/lihua/lihua.log`）或任意日志文件
  - 高效读最后 N 行（`deque(maxlen=lines)`）+ level 过滤（ERROR/WARNING/INFO/DEBUG）+ 行号显示
  - 参数：`lines`（默认 100，最多 500）/ `level`（可选）/ `log_file`（默认自己日志）
  - 不走 confirm（只读操作）
- `src/lihua/agent.py` L257-260 新增 `_execute_tool` 调度：`tool_name == "read_log"` 路由到 `_execute_read_log`
- `src/lihua/tool_defs.py` L374-426 新增 `build_read_log_tool` 函数：工具定义 + description（触发场景：自我诊断/错误回溯/行为审计）
- `src/lihua/tool_defs.py` L439-446 `build_tool_defs` 插入 read_log（第 6 个工具）
- `src/lihua/agent.py` L118-131 system prompt 新增 E. read_log 工具说明：
  - 触发场景：自我诊断（"点确认却提示取消" → read_log 看 confirm_cb 超时）/ 错误回溯 / 行为审计
  - 优先用 read_log 诊断问题——比 run_shell + tail/grep 更高效

**2. Phase 2 run_shell 调用次数 15→30**
- `src/lihua/agent.py` L527-529 `MAX_RUN_SHELL_CALLS = 30`
- 原因：诊断场景需要多次跑命令（看日志、查进程、读配置、验证假设），15 次不够

**3. Phase 3 safety.py 白名单补充 9 个只读诊断命令**
- `src/lihua/safety.py` L506-515 新增：
  - `dmesg`（查看内核日志）/ `w` `who`（查看登录用户）/ `id`（查看用户身份）
  - `last`（查看最近登录记录）/ `type`（查看命令类型）/ `alias`（查看命令别名）/ `history`（查看 shell 历史）
- 原因：LLM 诊断问题时这些命令被分到 unknown 走 confirm 挡路

**4. Phase 4 修复非流式 /api/chat 端点 confirm_cb=None bug**
- `src/lihua/server.py` L426-440 修复：
  - 旧代码 `(lambda msg, cmd: req.auto_confirm) if req.auto_confirm else None` 有两个 bug：
    1. `auto_confirm=True` 时返回 bool `True`，但 `ConfirmCallback` 类型是 `Callable[..., str]`，`True != "confirmed"` 被误判为取消
    2. `auto_confirm=False` 时 `confirm_cb=None`，灰名单操作返回"需要确认但未提供确认回调"
  - 修复后：`auto_confirm=True` → `"confirmed"`；`auto_confirm=False` → `"denied"`（明确拒绝）
  - 非流式接口没有 SSE 流，不支持交互式 confirm，需要 confirm 的操作必须用 `/api/chat/stream`

**修改文件**：
- `src/lihua/__init__.py`（版本号 0.8.6a0 → 0.8.7a0）
- `pyproject.toml`（版本号）
- `desktop/package.json`（版本号）
- `desktop/src-tauri/Cargo.toml`（版本号 0.8.6 → 0.8.7）
- `desktop/src-tauri/tauri.conf.json`（版本号）
- `desktop/src-tauri/src/lib.rs`（APP_VERSION 0.8.6-alpha → 0.8.7-alpha）
- `src/lihua/agent.py`（read_log 工具实现 + _execute_tool 调度 + MAX_RUN_SHELL_CALLS + system prompt E 段）
- `src/lihua/tool_defs.py`（build_read_log_tool + build_tool_defs 插入）
- `src/lihua/safety.py`（白名单补充 9 个只读诊断命令）
- `src/lihua/server.py`（非流式 /api/chat confirm_cb 修复）

**踩坑**：T066（非流式 /api/chat 端点 confirm_cb=None bug）、T067（dmesg/w/id 等只读命令被分到 unknown 走 confirm）

**验证**：
- Python 包安装成功（`~/.local/share/lihua/venv/bin/pip install -e .`）
- 待桌面端重新编译（`lihua gui --build`）后实测

---

### v0.8.6-alpha (2026-07-20) — confirm 超时修复 + run_shell timeout 优化

**问题背景**：用户反馈"点击确认执行，但是提示取消"。后端日志显示：
- 23:24:20.981 — 工具 install_app 失败（60.00s）  # _CONFIRM_TIMEOUT 超时
- 23:24:23.492 — 收到 confirm 请求 decision=True  # 用户在 60s 后才点击
- 23:24:23.492 — confirm_id 不匹配，_pending_confirms 已空  # session 已被超时 pop

**根因**：`_CONFIRM_TIMEOUT = 60.0` 太短。用户读 confirm 内容 + 思考就超过 60 秒，
超时后 `confirm_cb` 返回 False，session 被 pop。用户后来点击确认时找不到 confirm_id。
前端 v0.8.5 已修复 `handleConfirm` 在 api 调用失败时显示错误反馈，但根因（超时太短）未解决。

**修复方案**：

**1. Phase 1 延长 confirm 超时**
- `src/lihua/server.py` L74: `_CONFIRM_TIMEOUT` 从 60.0 → 600.0（10 分钟）
- 注释更新：说明 60s 太短导致"点确认却提示取消"的 UX bug

**2. Phase 2 ConfirmCallback 类型从 bool 改成 str**
- `src/lihua/skill_runner.py` L37 + `src/lihua/agent.py` L206:
  `ConfirmCallback = Callable[[str, str], str]`
- 返回值：`"confirmed"` / `"denied"` / `"timeout"`（区分用户取消和超时）
- `src/lihua/server.py` `_make_interactive_confirm_cb`:
  - 用户确认 → `"confirmed"`
  - 用户取消 → `"denied"`
  - 超时 → `"timeout"` + log.warning

**3. Phase 3 6 处 confirm 调用方根据返回值显示准确错误信息**
- `src/lihua/skill_runner.py` L406（command/verify step）
- `src/lihua/agent.py` L440（run_shell）
- `src/lihua/agent.py` L608（run_python）
- `src/lihua/agent.py` L991（write_file）
- `src/lihua/agent.py` L1174（edit_file）
- `"timeout"` → error="确认超时"，result_message="❌ 确认超时（10 分钟内未响应）"
- `"denied"` → error="用户取消"，result_message="❌ 用户取消了执行/写入/编辑"

**4. Phase 4 /api/chat/confirm 错误信息更明确**
- confirm_id 过期时返回 `"确认已超时（600s 内未响应），请重新发送指令"`
- 替代旧文案 `"confirm_id 不存在或已过期"`

**5. Phase 5 loop 检查发现 run_shell 默认 timeout 60s 也太短**
- `src/lihua/agent.py` L361: 默认 timeout 60 → 300（5 分钟），上限 600 → 1800（30 分钟）
- `src/lihua/skill_runner.py` L418: 扩大长命令关键字检测：
  - 旧：`300.0 if "install" in cmd else 60.0`
  - 新：长命令关键字 `install / update / upgrade / dist-upgrade / download / clone / build / make` → 600s（10 分钟）
  - 默认 60s → 120s（2 分钟）

**修改文件**：
- `src/lihua/__init__.py`（版本号 0.8.5a0 → 0.8.6a0）
- `pyproject.toml`（版本号）
- `desktop/package.json`（版本号）
- `desktop/src-tauri/Cargo.toml`（版本号 0.8.5 → 0.8.6）
- `desktop/src-tauri/tauri.conf.json`（版本号）
- `desktop/src-tauri/src/lib.rs`（APP_VERSION）
- `src/lihua/server.py`（`_CONFIRM_TIMEOUT`、`_make_interactive_confirm_cb`、`/api/chat/confirm`）
- `src/lihua/skill_runner.py`（`ConfirmCallback` 类型 + L406 调用方 + L418 timeout 检测）
- `src/lihua/agent.py`（`ConfirmCallback` 类型 + 4 处 confirm 调用方 + run_shell timeout 默认值）

**踩坑**：T064（confirm 超时 60s 太短）、T065（run_shell 默认 timeout 60s 太短）

**验证**：
- Python 代码语法 OK（`from lihua.server import _CONFIRM_TIMEOUT` 返回 600.0）
- 后端重启后 v0.8.6a0 加载成功
- 待用户实测：输入"美化成 macOS 风格" → 点击确认执行 → 应能正常执行（不再 60s 超时）

---

### v0.8.5-alpha (2026-07-20) — 新用户引导（LLM 未配置时 WelcomeScreen 显示醒目引导 + send 拦截）

**问题背景**：v0.8.3 引入 run_python 万能工具后，Lihua 已经具备完整的 Agent 能力（5 类工具：83 个 skill + run_shell + 文件操作 + run_python），但新用户第一次打开应用时：
1. 如果没配置 LLM，WelcomeScreen 显示正常欢迎语和快捷动作，用户点击快捷动作后会看到"502 Bad Gateway"或"连接失败"等技术性错误
2. StatusBar 虽然显示"未启用 LLM · 点击设置"，但不够醒目，新用户可能没注意
3. 缺乏明确的"先配置才能用"的引导，用户体验差，影响首次留存

**改造方案**：WelcomeScreen 检测 LLM 未配置时显示醒目引导卡片 + send 函数前置拦截

**1. Phase 1 WelcomeScreen.tsx 加 LLM 未配置引导卡片**
- 扩展 WelcomeScreenProps 加 `health?: Health | null` 和 `onOpenModelSettings?: () => void`
- 新增 `llmNotConfigured = health !== null && health !== undefined && !health.llm_available` 检测
- LLM 未配置时在快捷动作上方显示警告色引导卡片：
  - 警告色背景（bg-warn/10）+ 警告色边框（border-warn/30）+ AlertCircle 图标
  - 标题："需要先配置 AI 模型"
  - 副标题："Lihua 需要 AI 模型才能理解你的需求并执行任务。点击下方按钮配置模型后即可开始使用。"
  - "配置模型"按钮（accent 色，点击调 onOpenModelSettings → 打开 ModelSheet）

**2. Phase 2 App.tsx 的 send 函数前置拦截**
- App.tsx 的 WelcomeScreen 调用加 `health` 和 `onOpenModelSettings` props 传递
- send 函数在 `if (!text.trim() || loading) return` 之后加 LLM 可用性检查：
  - `if (health && !health.llm_available)` → 不调用后端，直接显示友好提示消息
  - 用户消息正常添加到 messages（让用户看到自己发了什么）
  - 助手消息 error 字段写："还没配置 AI 模型哦～请先点击底部的"配置模型"按钮设置模型后再开始对话。"
  - return 不进入流式 SSE 流程
- useCallback deps 加 health（避免 stale closure 读到旧 health）

**3. Phase 3 版本号升级**
- pyproject.toml: 0.8.4a0 → 0.8.5a0
- src/lihua/__init__.py: 0.8.4a0 → 0.8.5a0
- desktop/package.json: 0.8.4a0 → 0.8.5a0
- desktop/src-tauri/Cargo.toml: 0.8.4 → 0.8.5
- desktop/src-tauri/tauri.conf.json: 0.8.4 → 0.8.5
- desktop/src-tauri/src/lib.rs: 0.8.4-alpha → 0.8.5-alpha

**4. 设计决策**
- 为什么不直接禁用 InputBar？— 用户输入了东西再提示"未配置"比一开始就禁用更友好，让用户知道"工具是好的，只是缺一步配置"
- 为什么同时改 WelcomeScreen 和 send？— WelcomeScreen 引导新用户首次看到，send 拦截覆盖用户已开始对话但中途取消配置的场景（双保险）
- 为什么 send 拦截不直接弹 ModelSheet？— 强制弹窗会打断用户思路，更友好是显示提示让用户自己决定何时去配置

### v0.8.4-alpha (2026-07-20) — confirm 弹窗富文本展示（run_python 代码块 + run_shell 命令块）

**问题背景**：v0.8.0-v0.8.3 的 ConfirmSheet 用纯文本展示 message，但：
1. run_python 的 message 含 ```python\n...\n``` 代码块标记——前端纯文本展示会原样显示 ``` 标记，不美观
2. run_shell 的 message 含 "\n命令：{cmd}" 前缀——命令和意图混在一起，不清晰
3. 用户看到 confirm 弹窗时难以快速区分"LLM 要干什么"和"具体代码/命令是什么"

**改造方案**：后端解析 msg 提取结构化字段 + 前端根据工具类型富文本展示

**1. Phase 1 server.py 加 _enrich_confirm_event 函数**
- 在 `_make_interactive_confirm_cb` 的 cb 里调用 `_enrich_confirm_event(event, msg, cmd)`
- 解析规则（按优先级）：
  - run_python：检测 ```python\n 代码块标记 → 提取 intent（代码块前部分 strip）+ code（代码块内容）
  - run_shell：检测 "\n命令：" 前缀 → 提取 intent（命令前部分 strip）+ command_text（命令内容 strip）
  - file_op：检测 "写入文件" / "编辑文件" / "路径：" / "覆盖文件" / "新建文件" 关键词 → 标记 tool_name
  - 默认：不加额外字段，前端按纯文本展示（兼容旧路径）
- needs_confirm SSE 事件加可选字段：tool_name / intent / code / command_text

**2. Phase 2 前端 ConfirmSheet.tsx 富文本展示**
- 扩展 ConfirmSheetProps 加 toolName / intent / code / commandText 字段
- App.tsx 的 needs_confirm 事件处理传递结构化字段到 confirmPending 状态
- types.ts 的 ConfirmPending 接口加 toolName / intent / code / commandText 字段
- api.ts 的 SSE 事件类型加 tool_name / intent / code / command_text 可选字段
- ConfirmSheet 展示逻辑：
  - `isRunPython = toolName === 'run_python' && Boolean(code)` → 结构化展示
  - `isRunShell = toolName === 'run_shell' && Boolean(commandText)` → 结构化展示
  - `useStructured = isRunPython || isRunShell` → 决定走结构化还是纯文本路径
  - run_python 展示：意图卡片（bg-primary/60）+ Python 代码块（Code 图标 + 深色背景 #1e1e2e + 等宽字体 + max-h-60 滚动）
  - run_shell 展示：意图卡片 + 命令块（Terminal 图标 + 深色背景 + 等宽字体 + max-h-40 滚动）
  - 文件操作 / 默认：保持纯文本 messages 展示（兼容旧行为）
  - 底部辅助说明根据工具类型调整（run_python 提示"代码能力很强"，run_shell 提示"会修改系统"）

**3. Phase 3 测试覆盖**
- TestEnrichConfirmEventRunPython（4 个）：基础解析 / 多行代码 / 无 intent / 截断代码
- TestEnrichConfirmEventRunShell（3 个）：基础解析 / 多行命令 / 无 intent
- TestEnrichConfirmEventFileOp（3 个）：写入文件 / 编辑文件 / 路径关键词
- TestEnrichConfirmEventDefault（3 个）：默认不加字段 / 保留原有字段 / run_python 优先级高于 run_shell
- 全量 872 pytest 通过（v0.8.3 是 859，新增 13 个测试）

**4. 版本号升级**
- pyproject.toml: 0.8.3a0 → 0.8.4a0
- src/lihua/__init__.py: 0.8.3a0 → 0.8.4a0
- desktop/package.json: 0.8.3a0 → 0.8.4a0
- desktop/src-tauri/Cargo.toml: 0.8.3 → 0.8.4
- desktop/src-tauri/tauri.conf.json: 0.8.3 → 0.8.4
- desktop/src-tauri/src/lib.rs: 0.8.3-alpha → 0.8.4-alpha

### v0.8.3-alpha (2026-07-20) — run_python 万能工具（Python 代码执行，覆盖 shell 不擅长的场景）

**问题背景**：v0.8.0 引入 run_shell 后，LLM 能执行任意 shell 命令，但 shell 不擅长：
1. **数据处理**：JSON/CSV 解析、正则复杂替换、数据清洗——shell 的 awk/sed/jq 语法晦涩
2. **网络请求**：HTTP API 调用、爬虫——curl + jq 组合不灵活，无法处理复杂响应
3. **批量操作**：批量重命名、目录遍历统计——shell for 循环 + find 语法不直观
4. **复杂逻辑**：算法、循环、条件判断、异常处理——shell 不支持结构化编程

**改造方案**：引入 run_python 万能工具，让 LLM 能执行任意 Python 3 代码

**1. Phase 1 tool_defs.py 加 run_python 工具定义**
- `build_run_python_tool()` 直接 Python 构造（不依赖 YAML）
- `build_tool_defs` 在 tools 列表第 5 位插入 run_python（前 5 个：run_shell / read_file / write_file / edit_file / run_python）
- parameters 含 code（必填）/ intent（必填，给用户看 confirm 弹窗）/ timeout（默认 30，上限 300）
- description 写清楚触发场景（数据处理 / 系统管理 / 网络请求 / 复杂逻辑 / 文件操作高级）+ "不要用 run_python 替代简单 shell 命令"

**2. Phase 2 agent.py 加 _execute_run_python 执行函数**
- `MAX_RUN_PYTHON_CALLS = 10`（比 run_shell 更严，Python 能做更多事）
- `_execute_run_python()` 核心流程：
  - 提取 code / intent / timeout 参数（timeout clamp 1~300s）
  - 强制走 confirm（不走 safety.py，Python 代码能力太强必须用户确认）
  - confirm 消息：intent + 代码预览（前 500 字符，超长截断 + 共多少字符提示）
  - 用 `_sp.run([_sys.executable, "-"], input=code, ...)` 通过 stdin 传代码——避免 shell 转义问题
  - 用 venv 的 python（能 import 已装库如 requests / psutil / numpy）
  - 默认 cwd = 用户主目录（~）
  - TimeoutExpired 异常处理：返回 stdout/stderr + 超时提示
  - 手动写审计日志（`write_audit(AuditEntry(...))`，safety_level 统一标记 grey）
  - result_details 含完整 stdout（4000 字符截断）/ stderr（2000）/ exit_code / duration / safety_level=grey / timed_out / code_length / cwd / python 路径
- `_execute_tool` 加 run_python 分支：`if tool_name == "run_python": return _execute_run_python(...)`
- run_agent 循环加 `run_python_count` 计数器 + 速率限制（超过 10 次拒绝 + 注入提醒）
- run_agent_streaming 循环加 `run_python_count` 计数器 + 速率限制（对称 run_shell，额外 yield tool_call_start / tool_call_end SSE 事件）

**3. Phase 3 system prompt 更新**
- 顶部「三类工具」→「四类工具」
- 加「D. run_python（Python 代码执行，v0.8.3 新增）」段落：
  - 触发场景：数据处理 / 系统管理 / 网络请求 / 复杂逻辑 / 文件操作高级
  - 必填参数：code + intent；可选：timeout
  - 强制走 confirm（用户看到代码预览再决定）
  - 用 venv 的 python（能 import 已装库）
  - 工作目录是用户主目录（~）
  - 限制：单次对话最多 10 次
  - 不要用 run_python 替代简单 shell 命令
- 工具选择示例表加 4 行 run_python 场景：
  - "把 ~/Downloads 所有 .txt 改成 .md" → run_python（批量 rename）
  - "调用 GitHub API 查我的仓库" → run_python（HTTP 请求）
  - "解析 nginx 日志找出 Top 10 IP" → run_python（数据分析）
  - "测试这个 API 返回啥" → run_python（API 测试）
- 更新「使用顺序」：加第 4 条"shell 不擅长的复杂任务用 run_python"
- 更新「关键规则」：加"不要用 run_python 替代简单 shell 命令" + "run_python 强制走 confirm"
- 更新底部「可用工具」一行加 run_python

**4. Phase 4 测试覆盖**
- TestRunPythonRateLimit（2 个）：常量检查 + 流式模式速率限制触发
- TestExecuteRunPython（9 个）：简单 print / import 标准库 / 异常 stderr / 空代码 / confirm 拒绝 / 无 confirm 回调 / dry_run / timeout clamp / 审计日志写入
- TestRunPythonTool（4 个）：工具结构 / 必填参数 / 在 build_tool_defs 中 / 在前 5 个工具中
- TestChatStreamRunPython（3 个）：SSE 事件流 / 异常事件流 / done 事件含 details
- TestChatStreamRunPythonConfirm（1 个）：auto_confirm=False 触发 needs_confirm
- TestRunPythonArgumentsExtraction（1 个）：timeout clamp 在 SSE 中生效
- 修复 2 个 v0.8.2 回归测试（builtin 工具数 4→5）
- 全量 859 pytest 通过（v0.8.2 是 839，新增 20 个测试）

**5. Phase 5 前端 ToolCallCard 加 run_python 展示**
- 导入 Code 图标（lucide-react）
- 扩展 ToolItem 接口加 isRunPython / code / codeLength / pythonPath 字段
- normalizeItems 加 run_python 分支：从 details 提取 stdout/stderr/exit_code/safety_level/timed_out/code_length/python + 从 arguments 提取 code/intent
- ToolItemRow 加 run_python 展示分支（在 isFileOp 和默认之间）：
  - 标题行：intent 或代码首行（截断 60 字符）+ py 标签（蓝色）+ exit_code 标签（非 0 红色）+ 超时标签（橙色）
  - 展开后：意图 + Python 代码（Code 图标 + 代码块，带行数提示）+ stdout（蓝色）+ stderr（红色）+ 超时提示 + 无输出提示
- TypeScript 编译无错误（GetDiagnostics 只报 1 个预先存在的 hint）

**6. 版本号升级**
- pyproject.toml: 0.8.2a0 → 0.8.3a0
- src/lihua/__init__.py: 0.8.2a0 → 0.8.3a0
- desktop/package.json: 0.8.2a0 → 0.8.3a0
- desktop/src-tauri/Cargo.toml: 0.8.2 → 0.8.3
- desktop/src-tauri/tauri.conf.json: 0.8.2 → 0.8.3
- desktop/src-tauri/src/lib.rs: 0.8.2-alpha → 0.8.3-alpha

### v0.8.2-alpha (2026-07-20) — 文件操作工具组（read_file / write_file / edit_file，SWE-agent 风格 ACI）

**问题背景**：v0.8.0 引入 run_shell 万能兜底后，LLM 能执行任意 shell 命令，但用 run_shell + cat/sed 操作文件有 3 个问题：
1. **不安全**：sed -i 的正则错误可能破坏文件（LLM 容易写错正则）
2. **不高效**：run_shell + cat 读文件 → LLM 看 stdout → run_shell + sed -i 改文件，3 次工具调用
3. **没路径限制**：run_shell + cat /etc/passwd 能读，run_shell + sed -i /etc/passwd 也能写

**改造方案**：引入 SWE-agent 风格的 ACI（Agent-Computer Interface）文件操作工具组——3 个专用工具替代 run_shell + cat/sed 组合

**1. Phase 1 tool_defs.py 加 3 个工具定义**
- `build_read_file_tool()`：read_file，parameters 含 path（必填）+ start_line / end_line（可选，默认读全文，最多 200 行）
- `build_write_file_tool()`：write_file，parameters 含 path + content + intent（3 个必填）—— intent 给用户看 confirm 弹窗
- `build_edit_file_tool()`：edit_file，parameters 含 path + old_string + new_string + intent（4 个必填）—— SWE-agent 风格的 old→new 精确替换
- `build_tool_defs` 改为在 tools 列表头插入 4 个内置工具：run_shell / read_file / write_file / edit_file

**2. Phase 2 agent.py 加执行函数**
- `_is_path_in_home(path)` 路径检查函数：
  - abspath + expanduser 规范化路径
  - 检查 abs_path == home 或 abs_path.startswith(home + sep)
  - 防 `~/../etc/passwd` 路径穿越（abspath 会规范化）
- `_execute_file_op()` 调度器：根据 tool_name 分发到 read/write/edit
- `_execute_read_file()`：
  - 自动带行号输出（`{i:>5}→{line.rstrip()}`）
  - 二进制检测（`b"\x00" in raw`）→ 返回提示而不是乱码
  - 编码自动检测（utf-8 → gbk → latin-1）
  - 长文件截断 200 行 + 提示"用 start_line={end_line+1} 继续读"
  - 支持 start_line / end_line 读指定段落
  - 路径支持 ~ 展开
  - 无路径限制（只读，可以读 /etc/nginx/nginx.conf 等）
- `_execute_write_file()`：
  - 路径限制：`_is_path_in_home()` 检查，越界直接拒绝
  - 走灰名单 confirm：confirm_parts = intent + 路径 + 覆盖警告（"⚠️ 文件已存在，会被覆盖"）+ 内容预览（前 200 字符）
  - 自动 `mkdir -p` 父目录
  - 覆盖模式（truncate + write）
- `_execute_edit_file()`：
  - 路径限制：`_is_path_in_home()` 检查
  - old_string 唯一性检查：`content.count(old_string)` —— 0 次报错"未找到" / >1 次报"不唯一，需要更多上下文" / =1 次执行替换
  - 走灰名单 confirm：confirm_parts = intent + 路径 + `--- old ---\n{old_string}` + `--- new ---\n{new_string}`
  - `content.replace(old_string, new_string, 1)` 精确替换（虽然 count==1，但 replace 1 次更明确）
- `_execute_tool` 加文件操作分支：`if tool_name in ("read_file", "write_file", "edit_file"): return _execute_file_op(...)`

**3. Phase 3 system prompt 更新**
- 加「C. 文件操作工具（read_file / write_file / edit_file）」段落：
  - read_file：读文件，自动带行号，长文件截断 200 行，支持 start_line/end_line
  - write_file：写文件（覆盖模式），自动 mkdir -p 父目录，路径必须在 ~ 下
  - edit_file：精确替换（SWE-agent 风格 old_string → new_string），old_string 必须唯一存在
  - write_file / edit_file 走灰名单 confirm
  - 路径限制：只允许在用户主目录内；改 /etc 等请用 run_shell + pkexec
- 加「工具选择示例」表格（8 行）—— 给 LLM 看具体场景对应工具：
  - "装 QQ" → install_app skill
  - "看 nginx.conf" → read_file
  - "改端口 8080→9090" → read_file → edit_file
  - "写清理脚本" → write_file
  - "查端口占用" → run_shell + lsof
  - "电脑慢" → system_info + hardware_info + run_shell ps/top
  - "改 /etc/hosts" → run_shell + pkexec tee
  - "看 ~/.bashrc 第 50-60 行" → read_file + start_line/end_line
- 加「关键规则」段落：read_file 无路径限制 / write_file/edit_file 只能写 ~ 下 / old_string 必须唯一 / 不要用 run_shell+cat/sed 替代
- 更新「使用顺序」：
  1. 先看有没有合适的预定义 skill
  2. 文件操作优先用 read_file / write_file / edit_file（比 run_shell + cat/sed 更安全）
  3. 没有合适的 skill 也没法用文件工具 → 才用 run_shell
  4. run_shell 一次只跑一条命令
  5. 修改类操作前先说明意图

**4. Phase 4 前端 ToolCallCard 加文件操作特殊展示**
- 扩展 `ToolItem` 接口加文件操作字段：isFileOp / fileOpKind / filePath / fileSize / isBinary / totalLines / shownLines / startLine / endLine / contentPreview / oldString / newString / occurrences / overwrote / inHome / truncated
- `normalizeItems` 检测 read_file / write_file / edit_file，从 details + arguments 提取完整信息
- `ToolItemRow` 加文件操作展示分支（在 isRunShell 和默认分支之间）：
  - 标题行：路径（截断 60 字符，过长显示尾部）+ kind 标签（read/write/edit 颜色：灰/绿/橙）+ 行数标签（read_file）+ 新建/覆盖标签（write_file）+ 越界标签（inHome=false 时红色"越界"）
  - 展开后：意图 + 路径（FileText/FilePlus2/FilePen 图标）+ 元数据（行数/大小/二进制标记）+ 内容预览（read_file 显示带行号内容 / write_file 显示前 200 字符）+ diff（edit_file 显示 - old 红色 + new 绿色）
  - 错误态：路径越界 / old_string 未找到等，红色显示错误信息
- TypeScript 编译无错误（GetDiagnostics 只报 1 个预先存在的 hint）

**5. Phase 5 端到端集成测试**
- 新建 `tests/test_server_file_ops.py`（8 个测试）：
  - TestChatStreamReadFile：read_file 完整 SSE 事件流 / 读不存在文件失败
  - TestChatStreamWriteFile：write_file auto_confirm 成功 / 路径越界拒绝 / needs_confirm 事件
  - TestChatStreamEditFile：edit_file auto_confirm 成功 / old_string 不唯一失败
  - TestChatStreamFileOpsDoneEvent：done 事件的 tool_calls[0].details 含 path/total_lines/is_binary
- 验证 SSE 流：tool_call_start（含 path/content/old_string 参数）→ tool_call_end（含 details.path/size/total_lines/is_binary/overwrote/occurrences/in_home）→ done
- 验证 confirm 流程：write_file + auto_confirm=False 触发 needs_confirm 事件

**6. 测试覆盖**
- TestIsPathInHome 4 个测试：home 本身 / 子目录 / 系统目录 / 路径穿越
- TestExecuteReadFile 9 个测试：带行号读 / 不存在 / 目录 / 空路径 / 二进制 / 长文件截断 / start_line / dry_run / ~ 展开
- TestExecuteWriteFile 7 个测试：写新文件 / 路径越界 / 空路径 / 无 confirm 拒绝 / confirm 取消 / 自动 mkdir / dry_run
- TestExecuteEditFile 8 个测试：精确替换 / old 不存在 / old 不唯一 / 路径越界 / 文件不存在 / 空 old_string / confirm 取消 / dry_run
- TestFormatFileOpResultForLLM 5 个测试：read_file 内容回传 / 二进制提示 / write_file 成功 / edit_file 成功 / write_file 越界拒绝
- TestFileOpTools（test_tool_defs.py）4 个测试：3 个工具结构 + 在 build_tool_defs 里
- TestServerFileOps（test_server_file_ops.py）8 个端到端测试：SSE 事件流 + confirm 流程
- 全量 839 pytest 通过（v0.8.1 是 794，新增 45 个测试）

**7. 版本号升级**：6 个文件 → v0.8.2a0 / v0.8.2 / 0.8.2-alpha

**架构对比**：
| 维度 | run_shell + cat/sed | read_file / write_file / edit_file |
|------|---------------------|------------------------------------|
| 读文件 | run_shell(command="cat file") → LLM 看 stdout | read_file(path) → 自动带行号 + 二进制检测 + 长文件截断 |
| 写文件 | run_shell(command="echo 'x' > file") → 走 safety 灰名单 | write_file(path, content, intent) → 走 confirm + 路径限制 |
| 改文件 | run_shell(command="sed -i 's/x/y/' file") → 正则易错 | edit_file(path, old_string, new_string, intent) → 精确替换 + 唯一性检查 |
| 路径限制 | 无（safety 灰名单拦 sed -i /etc/passwd） | write_file / edit_file 限制在 ~ 下（read_file 无限制） |

**8. 未来计划**（未实施）：
- Phase 6（v0.8.3）能力扩展：run_python 工具 + Skill 自动生成（频繁 run_shell 序列提示保存为自定义 skill）
- Phase 7（v0.9）沙箱化：bwrap/firejail 轻量沙箱 + Docker 沙箱模式 + 网络隔离

---

### v0.8.1-alpha (2026-07-19) — run_shell 安全增强（17 条黑名单 + 速率限制 + cwd 控制）

**问题背景**：v0.8.0 引入 run_shell 万能兜底后，需要加强安全防护——LLM 可能生成各种危险命令。

**1. Phase 1 safety.py 黑名单扩展 17 条**
- find / -delete / find / -exec rm / find / -exec shred（递归删除/覆写根目录）
- mv ... /dev/null（永久丢失文件）
- cp /dev/zero /dev/sdX（覆写磁盘数据）
- chmod 777 /etc/passwd / chmod -R 777 ~ / /home / /etc / /usr / /boot 等（权限失控）
- > /proc/sys/kernel/sysrq（暴露内核调试接口）
- shutdown / poweroff / reboot（从灰名单升级为黑名单——LLM 不应关机/重启用户机器）
- > /boot/（破坏系统引导）
- iptables -F / ip6tables -F（清空防火墙规则）
- systemctl stop sshd/NetworkManager/networking（停关键服务）

**2. Phase 2 速率限制**
- `MAX_RUN_SHELL_CALLS = 15` 常量
- run_agent + run_agent_streaming 循环内：每次 run_shell 调用 +1，超过 15 次直接拒绝
- 拒绝时推送 tool_call_end(success=False) + 注入提醒消息给 LLM："请基于已有信息总结发现 + 给用户下一步建议，不要继续调 run_shell"

**3. Phase 3 cwd 控制**
- `_execute_run_shell` 默认 `cwd = os.path.expanduser("~")`
- ExecOptions(shell=True, timeout, audit=True, cwd=default_cwd)
- result_details 加 `cwd` 字段告诉 LLM 当前工作目录
- 防止 LLM 在 / 或其他系统目录乱搞

**4. 测试覆盖**
- TestRunShellSafetyV081 10 个测试：find -delete / find -exec rm / mv to /dev/null / chmod 777 home / chmod 777 /etc/passwd / shutdown / reboot / iptables -F / systemctl stop ssh / cwd is home
- TestRunShellRateLimit 1 个测试：MAX_RUN_SHELL_CALLS 常量
- test_safety.py TestBlacklist 加 17 个新黑名单命令
- test_safety.py TestGreylist 移除 shutdown/reboot/poweroff（保留 halt/systemctl suspend）
- 全量 794 pytest 通过（v0.8.0 是 766，新增 28 个测试）

**5. 版本号升级**：6 个文件 → v0.8.1a0 / v0.8.1 / 0.8.1-alpha

---

### v0.8.0-alpha (2026-07-19) — run_shell 万能兜底工具（解除 LLM 不能执行命令的限制 + 混合模式 Agent）

**问题背景**：用户提出「linux 本身终端能做的操作非常多，但是是不是我们现在的 prompt 把 LLM 局限住了？理论上，和其他 agent 一样，它应该能实现按照用户的需求完成指定的任务」——质疑当前 prompt + skill 架构是否把 LLM 关进笼子。

**架构审视结论**：
- 当前 Lihua 的 prompt + skill 架构**确实把 LLM 锁死了**
- `_SYSTEM_PROMPT` 第 82 行（v0.7.15）明确写「不要编造命令：只用提供的工具，不要建议用户手动执行命令」——LLM 不敢生成命令
- LLM 只能调用 83 个预定义 skill，不能自由生成命令；Linux 终端能做的事远超 83 个 skill 的覆盖
- 安全引擎 safety.py 有 500+ 白名单 + 100 灰名单 + 30 黑名单，但只用于 skill 固定命令分类，**没被 LLM 直接利用**
- 对比 Open Interpreter / SWE-agent：它们让 LLM 直接生成 shell 命令 + 用安全引擎分类 + 用户确认

**改造方案**：混合模式——保留预定义 skill 作为"快捷方式"，新增 `run_shell` 工具作为"万能兜底"

**1. Phase 1 tool_defs.py 加 build_run_shell_tool()**
- 直接 Python 构造 run_shell 工具（不依赖 YAML，避免给 SkillRegistry 加特殊 skill）
- parameters：command（必填，shell 命令）+ intent（必填，中文一句话说明意图给用户看确认弹窗）+ timeout（默认 60，最长 600）
- description 写清楚：优先用预定义 skill，run_shell 是兜底；黑名单拒绝/灰名单确认/白名单自动
- `build_tool_defs` 把 run_shell 插到 tools 列表第一个，让 LLM 优先看到

**2. Phase 2 agent.py 改 system prompt + _execute_tool + _format_tool_result_for_llm**
- system prompt 改造：
  - 删除「不要编造命令：只用提供的工具，不要建议用户手动执行命令」
  - 加「工具使用策略」：A. 预定义 skill 优先（稳定可靠）；B. run_shell 兜底（任意 shell 命令）；使用顺序：先看有没有合适 skill，没有才用 run_shell
- `_execute_tool` 加 run_shell 分支：`tool_name == "run_shell"` → `_execute_run_shell()`
- `_execute_run_shell()` 流程：
  1. 提取 command/intent/timeout（timeout clamp 1~600s）
  2. 走 `safety.classify(cmd)` 分类
  3. 黑名单 → 直接拒绝（返回 ToolCallRecord.success=False）
  4. 灰名单 + always_confirm_grey=True → 交互式 confirm（confirm_parts = intent + command）
  5. 灰名单 + confirm_cb=None → 拒绝（保守策略）
  6. 执行 `execute_safely(cmd, ExecOptions(shell=True, timeout, audit=True))`
  7. stdout 截断 4000 字符 / stderr 2000 字符防爆 token
  8. result_details 含完整 stdout/stderr/exit_code/safety_level/timed_out
- `_format_tool_result_for_llm` 对 run_shell 特殊处理：
  - 预定义 skill：只回传 final_message + steps 摘要
  - run_shell：回传完整 stdout/stderr/exit_code/safety_level（LLM 必须看到 stdout 才能决策下一步）

**3. Phase 3 safety.py 补漏（v0.7.13 替换 sudo→pkexec 的遗留）**
- 加 `pkexec` 到灰名单（v0.7.13 替换 sudo→pkexec 时遗漏，导致 pkexec 命令走 unknown 默认灰名单但不带 reason/human_message）
- 加 echo/printf/true/false 到白名单（run_shell 常用无害命令，避免走 unknown 默认灰名单每次都弹确认）

**4. 测试覆盖（test_agent.py + test_tool_defs.py）**
- TestExecuteRunShell 9 个测试：白名单自动执行 / 空命令拒绝 / 黑名单拒绝 / 灰名单无 confirm 拒绝 / 灰名单 confirm 取消 / dry-run / timeout clamp / 格式化 stdout / 格式化 stderr
- TestRunShellTool 3 个测试：工具结构 / 必填参数 / 在 build_tool_defs 里
- TestBuildToolDefs 改造：test_returns_all_skills_plus_run_shell / test_run_shell_is_first_tool / test_skill_tools_sorted_after_run_shell
- 全量 761 pytest 通过（v0.7.15 是 748，新增 13 个测试）

**5. 版本号升级**：6 个文件 → v0.8.0a0 / v0.8.0 / 0.8.0-alpha

**架构对比**：
| 维度 | Lihua v0.7.x | Lihua v0.8.0 | Open Interpreter | SWE-agent |
|------|--------------|--------------|------------------|-----------|
| LLM 角色 | 调度员（选 skill） | 调度员 + 代码作者 | 代码作者 | 命令生成器 |
| 能力上限 | 83 个 skill 覆盖 | 任意 Linux 任务 | 任意 Linux 任务 | 任意 Linux 任务 |
| 安全模型 | safety 分类固定命令 | safety 分类 LLM 命令 + skill 命令 | 预审+确认+沙箱 | Docker 沙箱+超时 |

**未来计划**（未实施）：
- Phase 2（v0.8.1）安全增强：run_shell 速率限制（单次对话最多 10 次）+ 黑名单加 LLM 危险模式（find / -delete / chmod -R 777 ~）
- Phase 3（v0.8.2）能力扩展：write_file/read_file/edit_file 工具 + run_python 工具 + Skill 自动生成（频繁 run_shell 序列提示保存为自定义 skill）
- Phase 4（v0.9）沙箱化：bwrap/firejail 轻量沙箱 + Docker 沙箱模式 + 网络隔离

**6. 端到端验证 + 前端改造（v0.8.0 收尾）**

验证 server.py 的 chat_stream SSE 流能否正确转发 run_shell 事件到前端：
- ✅ **SSE 事件流验证**：`tool_call_start`（含 command/intent 参数）+ `tool_call_end`（含 details.stdout/safety_level/exit_code）+ `done`（含 tool_calls 数组）都能正确转发
- ✅ **灰名单 confirm 流程验证**：run_shell 走灰名单时，`_execute_run_shell` 调 `confirm(msg, cmd)` → server.py 的 `_make_interactive_confirm_cb` 推 `needs_confirm` 事件 → 前端弹 ConfirmSheet → 用户响应后 POST `/api/chat/confirm` → confirm_cb 解除阻塞。**这个流程对 run_shell 自动生效**（confirm_cb 是通用的，不区分 skill 还是 run_shell）
- ✅ **前端 ToolCallCard 改造**：原版只显示 `result_message`，看不到 run_shell 的完整信息。改造后：
  - `normalizeItems` 检测 `tool_name === 'run_shell'`，从 `details` 提取 command/intent/safety_level/exit_code/stdout/stderr/timed_out/duration
  - `ToolItemRow` 对 run_shell 特殊展示：标题行显示命令（截断 60 字符）+ safety 标签（black=红/grey=橙/white=灰）+ exit_code（非 0 显示）+ duration
  - 展开后分块显示：意图 / 命令 / stdout（max-h-80 滚动）/ stderr（红色，max-h-60 滚动）/ 超时警告
  - duration 单位转换：run_shell 是秒，formatDuration 期望 ms → *1000
- ✅ **5 个 server 集成测试**（tests/test_server_run_shell.py）：
  - 白名单 echo 完整事件流（start/tool_call_start/tool_call_end/done）
  - 黑名单 rm -rf / 拒绝事件流
  - done 事件的 tool_calls 数组含 details
  - 灰名单 pkexec 触发 needs_confirm 事件
  - timeout clamp 在 SSE 流中正常
- ✅ **TypeScript 类型检查通过**（VS Code diagnostics 无错误）
- ✅ **全量 766 pytest 通过**（v0.8.0 Phase 1 是 761，新增 5 个 server 集成测试）

文件改动：
- `desktop/src/components/ToolCallCard.tsx`（normalizeItems + ToolItemRow 改造，支持 run_shell 特殊展示）
- `tests/test_server_run_shell.py`（新增 5 个端到端集成测试）

### v0.7.15-alpha (2026-07-19) — 修复谎报成功 + 版本不匹配检测（install/uninstall verify on_failure=stop + 前端检测后端版本）

**问题背景**：用户实测诊断"Steam Proton 启动黑神话悟空失败"时，Agent 出现两个严重问题：
1. **uninstall_app 谎报成功**：Agent 说"Snap 版 Steam 已经成功卸载了"，但用户说"你搞错了吧？steam还在啊？"
2. **install_app confirm 弹窗没显示**：Agent 反复调 install_app 都返回"需要确认但未提供确认回调"，但前端没弹窗

**根因分析**：
1. **uninstall_app 谎报成功**：
   - `resolve_package` 把 steam 解析为 flatpak（alias 第一个是 `com.valvesoftware.steam`），但实际是 snap 版
   - `uninstall_flatpak` 失败但 `on_failure: continue` 继续
   - `uninstall_snap` 因 `package_type != snap` 被跳过
   - `verify` 命令只检查 `which` 和 `flatpak list`（没检查 `snap list`），snap 版 steam 不在 PATH → verify 误判通过
   - `verify` 的 `on_failure: continue` → 失败也继续 → `notify` 执行 → 谎报"已卸载"
   - `run_skill` 返回 `success=True`（所有步骤 continue 了）→ Agent 说"卸载成功了"
2. **install_app confirm 弹窗没显示**：
   - **后端 Python 服务没重启**（HMR 只对前端生效，uvicorn 跑的是旧代码）
   - v0.7.13 的交互式 confirm 机制没加载，confirm_cb=None → 灰名单直接拒绝

**1. Phase 1 修复 uninstall_app 谎报成功（uninstall-app.yaml）**
- `verify` 步骤改造：
  - 命令从 `! which {{package}} && ! flatpak list | grep -i {{package}}` 改为 `! snap list | grep -i '{{target}}' && ! flatpak list | grep -i '{{target}}' && ! dpkg -l | grep -i '{{target}}' && ! which '{{target}}'`
  - 用 `{{target}}` 检查（不是 `{{package}}`），因为 resolve_package 可能解析为 flatpak ID 但实际是 snap 版
  - 检查 snap/flatpak/dpkg/which 四种安装方式
  - `on_failure` 从 `continue` 改为 `stop`：失败就停止，不执行 notify，run_skill 返回 success=False

**2. Phase 2 修复 install_app 谎报成功（install-app.yaml）**
- `verify` 步骤改造：
  - 命令从 `which {{package}} || flatpak list | grep -i {{package}}` 改为 `which '{{target}}' || flatpak list | grep -i '{{target}}' || snap list | grep -i '{{target}}' || dpkg -l | grep -i '{{target}}'`
  - 用 `{{target}}` 检查（不是 `{{package}}`），覆盖 snap/flatpak/apt 三种安装方式
  - `on_failure` 从 `continue` 改为 `stop`：失败就停止，不执行 notify，run_skill 返回 success=False
  - 修复 YAML 冒号陷阱（T024 复发：description 里 `v0.7.15: 加` 的 `: ` 被解析为 mapping，加双引号）

**3. Phase 3 前端检测后端版本不匹配（App.tsx）**
- 新增 `versionMismatch` state
- 新增 useEffect：`Promise.all([getVersion(), api.health()])` 对比前后端版本号
  - 前端 `getVersion()` 返回 tauri.conf.json 的 version（如 `0.7.15`）
  - 后端 `health.version` 返回 `__version__`（如 `0.7.15a0`）
  - 对比时去掉 alpha 后缀（`0.7.15a0` → `0.7.15`）
- 版本不匹配时显示顶部警告横幅："⚠️ 后端服务版本不匹配，请重启应用以加载新功能"
- 横幅可关闭（✕ 按钮），z-50 浮在最上层

**4. 测试 + 已知问题**
- 748 pytest 全通过（修复 YAML 冒号陷阱后）
- 详见 traps.md T058（verify on_failure=continue 导致谎报成功）/ T024（YAML 冒号陷阱第 N 次复发）

---

### v0.7.14-alpha (2026-07-19) — Agent 行为优化（system prompt 重写 + 重复调用检测 + 达上限 LLM 总结）

**问题背景**：用户实测诊断"Steam Proton 启动黑神话悟空失败"时，Agent 出现三个问题：
1. **AI 太激进**：list_apps 找不到 steam → 下结论"未安装"，用户说"steam我安装了啊"还继续死磕，还激进建议"换成 Flatpak 版 Steam"
2. **重复调工具**：list_apps 调 3 次、process_manager 调 3 次、file_search 调 2 次，8 次迭代用完
3. **机械放弃**：达到 max_iterations=8 后返回固定文案"已经处理了多步操作，但可能还需要继续。请告诉我下一步"

**1. Phase 1 system prompt 重写（agent.py _SYSTEM_PROMPT）**
- 加 5 条核心原则（重要程度从高到低）：
  1. **用户说的是事实，工具结果可能不全**：工具找不到时相信用户，不要质疑现状
  2. **不要激进建议换软件/换版本**：诊断失败原因优先，用户说"别换"就严格尊重
  3. **避免重复调用相同工具**：同工具+同参数调一次就够，诊断类最多 5-6 个不同工具
  4. **诊断类任务的工作流**：先收集信息 → 再分析 → 最后给建议，不要一上来就调修改类工具
  5. **修复类任务要确认**：修改前说明"我准备做 X，因为 Y"，用户同意再调
- 加"达到迭代上限时：总结已收集的信息 + 已排除的原因 + 下一步建议，不要机械说'请告诉我下一步'"

**2. Phase 2 agent.py 改造（run_agent + run_agent_streaming）**
- **迭代次数 8 → 12**：给诊断类任务留足空间（用户实测 8 次不够）
- **重复调用检测**（call_history: dict[tool_name+args_str, count]）：
  - 第 1 次：正常执行
  - 第 2 次：执行但注入 system 消息提醒 LLM"你已经调过一次了，这是第 2 次"
  - 第 3 次及以上：拒绝执行 + 注入 tool 消息"⚠️ 这个工具调用你已经做过 N 次了，结果都一样。请换不同参数或换不同工具，或者直接给用户总结"
  - 流式版还推送 tool_call_start + tool_call_end(success=False) 让前端知道
- **达上限时 LLM 总结**（_summarize_on_max_iterations 函数）：
  - 再调一次 LLM（不带 tools，tools=[]），让它看完整对话历史
  - prompt 要求输出：已收集到的关键信息 / 已排除的可能原因 / 还需要检查的方向 + 下一步建议
  - LLM 失败时兜底：根据工具调用历史生成简单总结（成功 N / 失败 N + 失败的工具列表）
  - 流式版先推送一条 text 事件"*达到迭代上限，正在总结当前发现...*"，再推送 done 事件

**3. 测试 + 已知问题**
- 748 pytest 全通过（24 agent 测试 + 其他）
- 现有 test_max_iterations_limit / test_streaming_max_iterations 用 max_iterations=2 + 同 tool_call，第 2 次执行（注入提醒但执行），测试仍通过
- 详见 traps.md T057（AI 太激进 + 重复调工具 + 机械放弃）

---

### v0.7.13-alpha (2026-07-19) — 交互式 confirm + sudo→pkexec（解决 Agent 灰名单操作无法确认的问题）

**问题背景**：用户实测发现 Agent 调用 install_app 安装 Steam 时，灰名单操作需要 confirm，但 GUI 模式下 confirm_cb=None，导致「需要确认但未提供确认回调」错误，Agent 卡死无法继续。根因是 `server.py` 的 confirm_cb 是二选一死设计（auto_confirm=True 全自动通过 / False 全拒绝）。

**设计决策**：用户问「lihua 是否应该直接运行在管理员权限？」。回答：**绝对不应该**——root 进程的任何漏洞都是灾难，违背 Linux 安全模型。正确做法是普通用户运行 + 交互式 confirm + sudo 改 pkexec。

**1. Phase 1 后端交互式 confirm 机制（server.py）**
- 新增 `ConfirmRequest` 模型（confirm_id + decision）
- 新增 `_ConfirmSession` dataclass（confirm_id + response_event + response_result）
- 新增全局 `_pending_confirms: dict[confirm_id, _ConfirmSession]` + `_pending_lock`
- 新增 `_make_interactive_confirm_cb(event_queue)` 工厂函数：
  - confirm_cb 被调用时生成 confirm_id，存入 _pending_confirms
  - 推 `{"type": "needs_confirm", "id": ..., "message": ..., "command": ...}` 事件到 event_queue
  - 阻塞等待 `response_event.wait(timeout=60)`（60s 超时自动拒绝）
- 改造 `chat_stream` 端点：
  - auto_confirm=False 时用子线程跑 `run_agent_streaming`，主线程从 event_queue 取事件 yield
  - confirm_cb 阻塞时，主线程仍能 yield needs_confirm 事件到 SSE 流
  - auto_confirm=True 时走旧的同步路径（向后兼容）
- 新增 `POST /api/chat/confirm` 端点：前端用户点击后调用，设置 response_event 解除阻塞

**2. Phase 2 前端 confirm UI（App.tsx + api.ts + types.ts）**
- `api.ts`：
  - `AgentStreamEvent` 新增 `needs_confirm` 类型（id + message + command）
  - 新增 `confirmChat(confirm_id, decision)` 方法调 `/api/chat/confirm`
- `types.ts`：扩展 `ConfirmPending` 支持 Agent 模式（confirmId + confirmMessage）
- `App.tsx`：
  - SSE switch 加 `case 'needs_confirm'`：setConfirmPending({confirmId, confirmMessage})
  - `handleConfirm` 改造：有 confirmId → Agent 模式调 api.confirmChat；无 confirmId → 规则模式重新发送
  - 删除旧的「灰名单被拒绝 → 弹确认框」兜底（已被 needs_confirm 事件取代）
  - 删除死代码 `pendingToolCalls`（只写不读）
  - `confirmMessages` 支持 Agent 模式（用 confirmMessage）+ 规则模式（用 response.result.steps）

**3. Phase 3 sudo → pkexec 全量替换（36 个文件 137 处）**
- 用 Python 脚本批量替换，规则：
  - `sudo <command>` → `pkexec <command>`（命令行）
  - `sudo -u <user>` → `pkexec --user <user>`（1 处，beautify-ubuntu.yaml 的 gdm 用户）
  - 注释里的 sudo 保留原样（1 处，beautify-ubuntu.yaml line 429）
- pkexec 优势：PolicyKit 系统密码框（GNOME 集成好），比 sudo 在非交互式环境更可靠
- 36 个文件全部替换完成：beautify-ubuntu(26) / mirror-source(15) / troubleshoot(11) / firewall(6) / share-folder(6) / ppa-management(6) / hardware-info(5) / service-manager(5) / cleanup-residual(5) / system-update(4) / apt-repository(4) / clean-cache(3) / cleanup-apt(3) / snap-channel(3) / 其他(33)

**4. 测试 + 已知问题**
- 748 pytest 全通过（修了 2 个 beautify 测试期望：sudo → pkexec）
- 51 server/agent 测试通过（后端 confirm 机制不破坏现有测试）
- 前端 HMR 热重载正常，无新类型错误
- 详见 traps.md T055（confirm_cb 二选一死设计）/ T056（sudo→pkexec 替换注意事项）

---

### v0.7.12-alpha (2026-07-19) — Skill 库三层整合（L1 分类 + L2 troubleshoot 合并 + L3 catalog 精简）

针对用户提出的「新增没有问题，但是对于 agent 来说，是不是需要分类整合？」问题，对 Skill 库做三层整合，降低 LLM token 成本，提升工具查找效率。整合前 90 个 skill + catalog 双重冗余约 24000 token；整合后 83 个 skill + catalog 按类别分组约 12000 token，节省约 50%。

**1. L1 分类字段：SkillDef 加 category + 82 个 YAML 加 category**
- `skills.py` 的 `SkillDef` dataclass 新增 `category: str = "other"` 字段
- `_parse_skill()` 解析 YAML 的 `category` 字段
- `tool_defs.py` 新增 `SKILL_CATEGORIES` 常量（16 个类别中文名映射）：
  - system(系统管理) / file(文件操作) / file_adv(文件管理高级) / network(网络) / network_sys(网络系统高级) / hardware(硬件外设) / desktop(桌面环境) / desktop_hw(桌面硬件扩展) / mirror(软件源镜像) / install(软件安装增强) / app(应用操作) / process(进程性能) / media_dev(多媒体开发环境) / troubleshoot(新手救急诊断) / mvp(MVP 基础) / other(其他)
- 82 个 YAML 文件批量添加 `category` 字段（在 `version:` 行后、`author:` 行前）

**2. L2 合并 troubleshoot-* 8→1（消除冗余 + 降低 LLM 选择成本）**
- 删除 8 个独立文件：`troubleshoot-no-sound.yaml` / `troubleshoot-no-wifi.yaml` / `troubleshoot-no-internet.yaml` / `troubleshoot-disk-full.yaml` / `troubleshoot-memory-high.yaml` / `troubleshoot-cpu-high.yaml` / `troubleshoot-app-crash.yaml` / `troubleshoot-slow-system.yaml`
- 新建 `troubleshoot.yaml` 合并版（v0.2）：
  - 82 个 triggers（8 类问题场景）
  - 3 个参数：`issue`（必填，中文值如「没声音」/「wifi」/「磁盘满」/「崩溃」等）/ `action`（诊断/修复，默认诊断）/ `app`（crash 场景用，默认 firefox）
  - 37 个 aliases（中文词 → [troubleshoot]，让 alias_hit=1 在冲突中胜出）
  - 29 steps，按 8 个 issue 分段，用双重 condition `{{issue}} in [中文词列表] && {{action}} != 修复`
  - 诊断步骤 safety=white，修复步骤 safety=grey + confirm
  - slow_fix_hint 例外：修复步骤但只 echo 建议，safety=white 无 confirm
- `skill_runner.py` 的 condition 求值已支持 `in` 操作符（`_eval_atom` 解析 `[a, b, c]` 列表）
- `eval_condition` 已支持 `&&` / `||` 复合条件（拆分 `||` 低优先级 → `&&` 高优先级）

**3. L3 catalog 精简（按类别分组 + 去双重冗余 + skill_to_tool 加类别前缀）**
- `build_skill_catalog_for_prompt` 重写：按 category 分组，紧凑格式
  ```
  == 系统管理 ==
  - apt_update: 更新 apt 软件源索引
  - apt_upgrade: 升级所有已安装的软件包

  == 文件操作 ==
  - file_search: 搜索文件
  ```
  - 去掉 triggers / params（已在 tools 列表里，避免冗余）
  - catalog 总长从约 6000 字符降到 4176 字符（-30%）
- `skill_to_tool` description 加 `[类别]` 前缀，让 LLM 在 tools 列表里也能看到类别
  - 示例：`[软件安装增强] 安装应用程序\n触发场景：装 / 安装 / 装个\n示例：装QQ | 装个微信`

**4. 测试覆盖（test_skills_troubleshoot.py 重写 80 用例 + test_tool_defs.py 18 用例）**
- `TestTroubleshootSkillLoaded`（7 个）：加载 / 3 参数 / 8 issue steps / notify / condition 含 issue+action / category 字段
- `TestTroubleshootTriggerMatch`（32 个）：24 个 trigger 匹配 + 8 个 intent_match（覆盖 8 类问题场景）
- `TestTroubleshootExtractParams`：24 个 issue 提取（中文值）+ 6 个 action 提取 + 3 个 app 提取
- `TestTroubleshootPriorityConflict`（3 个）：troubleshoot vs disk_usage/cpu_monitor/memory_monitor（alias_hit 取胜）
- `TestTroubleshootStepConditions`（5 个）：诊断步骤 condition / 修复步骤 condition / grey safety（排除 slow_fix_hint）/ white safety / confirm 文案（排除 slow_fix_hint）
- `test_tool_defs.py` 新增 `test_description_has_category_prefix` + `test_catalog_grouped_by_category`

**5. 已知问题**
- troubleshoot 的 alias「卡顿」太宽泛会误匹配「动画卡顿」（应匹配 beautify_ubuntu），已删除该 alias（保留 trigger），让 beautify_ubuntu 靠更长的 trigger「动画卡顿」(4字) 胜出
- 详见 traps.md T053（中文 issue 值的 `in` 操作符）/ T054（alias 过宽泛导致误匹配）

---

### v0.7.11-alpha (2026-07-19) — beautify_ubuntu 能力扩展（让 Lihua 拥有重构 Ubuntu 系统风格和界面的能力）

扩展 `beautify_ubuntu` Skill 的 macOS 风格流程，从原来 8 个 step 扩展到 24 个 step，覆盖字体安装 + GDM 登录界面 + GRUB 美化 + 壁纸 + 窗口按钮位置等极致细节。让 Lihua 能帮用户把 Ubuntu 系统界面美化成 macOS 风格（不是重构 Lihua 自身的 UI）。

**1. beautify-ubuntu.yaml v0.2 → v0.3（macOS 风格 16 个新 step）**

字体安装（5 个 step，对应 macOS 苹方/宋体/SF Mono 的 Linux 方案）：
- `install_source_han_fonts`：从 Adobe GitHub 下载思源黑体 SC + 思源宋体 SC 全字重 OTF（ExtraLight → Heavy 7 个字重），apt 补装 fonts-noto-cjk / fonts-noto-cjk-extra
- `install_jetbrains_mono`：从 JetBrains 官网下载 JetBrains Mono 编程等宽字体
- `install_fira_code`：从 GitHub 下载 Fira Code 连字编程字体（可选）
- `apply_fonts_to_gnome`：gsettings 设置界面/文档/等宽/标题栏字体（思源黑体/思源宋体/JetBrains Mono）+ 文本缩放 1.0 + 光标 32
- `config_font_rendering_extreme`：fontconfig `~/.config/fontconfig/fonts.conf` 全局渲染配置（rgba 次像素 + hintslight 微调 + lcdfilter + 默认字体映射 sans-serif/serif/monospace）+ gsettings font-antialiasing/font-hinting

窗口按钮位置（1 个 step）：
- `config_window_buttons_macos`：gsettings `button-layout 'close,minimize,maximize:appmenu'`（关闭/最小化/最大化 移到左上，macOS 风格）

壁纸（2 个 step）：
- `download_macos_wallpaper`：wget macOS Sonoma/Sequoia 风格壁纸到 `~/Pictures/Wallpapers/`
- `set_wallpaper`：gsettings `picture-uri` 设置桌面 + 锁屏壁纸

GDM 登录界面（4 个 step）：
- `install_gdm_settings`：apt install gdm-settings（图形化配置 GDM 工具）
- `backup_gdm_resources`：时间戳备份 `/usr/share/gnome-shell/gnome-shell-theme.gresource`
- `apply_gdm_whitesur`：调用 WhiteSur-gtk-theme 的 `tweaks.sh -g` 脚本重新编译 gresource，让 GDM 用 WhiteSur 主题
- `set_gdm_wallpaper`：设置 GDM 登录界面壁纸（与桌面壁纸一致）

GRUB 美化（4 个 step）：
- `install_whitesur_grub_theme`：git clone WhiteSur-grub-theme + install.sh，复制到 `/boot/grub/themes/`
- `config_grub_resolution`：xrandr 自动检测屏幕分辨率，写入 `/etc/default/grub` 的 `GRUB_GFXMODE`
- `config_grub_timeout`：`GRUB_TIMEOUT=3`（5s → 3s，加快启动）
- `update_grub_config`：`sudo update-grub` 应用配置

**2. restore_default 增强**
- 重置窗口按钮到右上（`button-layout 'appmenu:minimize,maximize,close'`）
- 删除 fontconfig 配置文件 + `fc-cache -f` 刷新

**3. final_hint 更新**
- 8 条建议：注销重新登录 / 重启 GDM / 重启生效 / 字体渲染 / GDM 主题 / GRUB 主题 / 壁纸 / 窗口按钮

**4. trigger / extract 策略调整**
- 新增 triggers：`登录界面` / `开机界面` / `grub美化` / `GRUB美化`
- 删除与 install_font 冲突的 triggers：`装字体` / `思源黑体` / `jetbrains mono` / `JetBrains Mono`（让单纯装字体走 install_font，beautify_ubuntu 通过"美化ubuntu"/"macos风格"/"登录界面"/"grub美化"触发）
- extract 正则去掉 `登录|开机|grub`（让「美化登录界面」/「GRUB美化」走 target=macos 全套流程，避免局部执行导致依赖缺失——GDM 主题依赖 WhiteSur GTK 主题）

**5. 测试覆盖（93 个测试全通过，全量 687 pytest 通过）**
- `TestBeautifyUbuntuStepStructure` 新增 6 个方法：字体 5 step / GDM 4 step / GRUB 4 step / 壁纸 2 step / 窗口按钮 1 step
- `TestBeautifyUbuntuV0711Commands`（14 个测试）：验证命令内容（Adobe GitHub / JetBrains / gsettings / fontconfig / button-layout / wget / gdm.sh / WhiteSur-grub-theme / xrandr / GRUB_TIMEOUT=3 / update-grub / restore 重置按钮）
- `TestBeautifyUbuntuV0711Conditions`（3 个测试）：condition 含 `{{target}} == macos` / safety 全为 grey / confirm 不含原始命令
- `TestBeautifyUbuntuV0711TriggerMatch`：新 trigger 匹配 + target 提取走 macos 全套流程

**6. 已知问题**
- 无（修复了 YAML 冒号陷阱复发，见 traps.md T024 v0.7.11 复发记录）

---

### v0.7.10-alpha (2026-07-19) — AuditSheet 独立审计日志（JSON 行格式 + 结构化 API + 过滤搜索 + 导出 + 清空）

把审计日志从纯文本格式升级为 JSON 行结构化存储，新增独立 AuditSheet UI 面板，支持过滤、搜索、导出、清空。

**1. executor.py 审计日志重构**
- `AuditEntry.to_dict()` 新增：序列化为 dict（用于 JSON 行存储）
- `parse_audit_line()` 新增：解析一行审计日志，支持两种格式：
  - JSON 行（v0.7.10+ 新格式）：直接 `json.loads`
  - 旧文本格式（v0.7.10 之前）：正则解析 `[ts] STATUS exit=N safety=L duration=Xs cmd='...' [user_input='...'] [reason='...']`
  - 解析失败返回 `{"raw": line}` 不抛异常
- `write_audit()` 改为写 JSON 行（`json.dumps(entry.to_dict(), ensure_ascii=False) + "\n"`）
- 向后兼容：旧文本格式仍能被 `parse_audit_line` 解析（用于读取历史日志）

**2. server.py 审计 API 重构**
- `GET /api/audit` 结构化返回 + 过滤搜索：
  - 参数：`n`（最近 N 条，默认 100）、`success`（true/false）、`safety`（white/grey/black/unknown）、`q`（搜索关键词）
  - 返回：`{"entries": [...], "count": N, "log_file": "..."}`
  - 最新在前（reversed 读取）
  - 搜索匹配 command 或 user_input，大小写不敏感
- `GET /api/audit/export` 新增：下载完整审计日志文件
  - `PlainTextResponse` + `Content-Disposition: attachment; filename="lihua-audit-{version}.log"`
- `DELETE /api/audit` 新增：清空审计日志（备份后清空）
  - 先 `path.rename(path.with_suffix(".log.bak"))` 备份
  - 再 `path.touch()` 创建空文件
  - 返回 `{"ok": true, "message": "已清空，备份至 ..."}`

**3. cli.py audit 命令美化**
- 用 `parse_audit_line` 解析每行
- Rich 美化输出：safety 颜色编码（white=绿、grey=黄、black=红、unknown=灰）
- 显示时间 + ✓/✗ + safety + 命令 + duration + exit_code

**4. api.ts 前端 API 封装**
- 新增类型：`AuditEntry`（ts/command/safety_level/success/exit_code/duration/user_input/decision_reason/raw）
- 新增类型：`AuditResponse`（entries/count/log_file）
- `api.audit(n, filters)` 方法：URLSearchParams 构造查询
- `api.auditExportUrl()` 方法：返回导出 URL
- `api.auditClear()` 方法：DELETE 请求清空

**5. AuditSheet.tsx 独立审计日志 UI（新增组件）**
- 复用 LogSheet 模式：Portal + 退出动画（150ms）+ max-w-[760px] h-[80vh]
- 顶部栏：Shield 图标 + 标题 + 条数 + 刷新 + 关闭
- 工具栏：
  - 成功状态筛选（全部/成功/失败）
  - safety 级别筛选（全部/白名单/灰名单/黑名单/未知）
  - 搜索框（250ms 防抖，按 command 或 user_input 过滤）
- 审计列表：每条显示
  - 时间（月-日 时:分:秒）
  - ✓/✗ 成功/失败图标
  - safety 颜色标签（带 ShieldCheck/Shield/ShieldAlert 图标）
  - 命令（break-all 不截断）
  - 元数据：exit_code / duration / user_input / decision_reason / 旧格式警告
- 底部栏：
  - 导出按钮（`window.open(exportUrl)` 下载）
  - 清空按钮（二次确认：黄色警告 + 确认/取消）
  - 日志文件路径（truncate + title 完整路径）

**6. App.tsx 集成 AuditSheet**
- import AuditSheet
- 新增 `auditSheetOpen` state
- StatusBar 新增 `onOpenAudit` prop（Shield 图标按钮）
- 托盘 `open-audit` 事件改为打开 AuditSheet（之前是打开 Sidebar 历史 tab）
- 渲染 `<AuditSheet open={auditSheetOpen} onClose={...} />`

**7. StatusBar.tsx 加审计按钮**
- import Shield 图标
- 新增 `onOpenAudit?: () => void` prop
- 右侧加 Shield 图标按钮（12px，hover 变亮）

**8. 测试覆盖（test_audit.py 新增 27 个用例）**
- `TestParseAuditLine`（7 个）：JSON 行 / 旧文本格式（简单/带 user_input/带 reason）/ 空行 / 无效行 / 无效 JSON 回退
- `TestAuditEntryToDict`（2 个）：完整字段序列化 / 可选字段为 None
- `TestWriteAudit`（2 个）：创建文件 / 追加到现有
- `TestAuditEndpoint`（11 个）：基本查询 / success 过滤（true/false）/ safety 过滤 / q 搜索（command/user_input/大小写不敏感）/ 组合过滤 / n 限制 / log_file 路径 / 文件不存在
- `TestAuditExportEndpoint`（2 个）：下载内容 / 文件不存在 404
- `TestAuditClearEndpoint`（3 个）：清空 + 备份 / 文件不存在 / 二次清空备份覆盖

**9. 版本号升级（6 文件）**
- pyproject.toml / __init__.py / package.json: `0.7.9a0` → `0.7.10a0`
- Cargo.toml / tauri.conf.json: `0.7.9` → `0.7.10`
- lib.rs APP_VERSION: `0.7.9-alpha` → `0.7.10-alpha`

**验证**：tsc 0 错误 + vite 209KB（+21KB AuditSheet）+ 657 pytest 全通过（630 → 657，新增 27 个审计测试）+ 后端 /api/audit 过滤搜索正常 + /api/audit/export 下载正常 + DELETE /api/audit 清空 + 备份正常

---

### v0.7.9-alpha (2026-07-19) — 流式输出 + Agent 多轮对话（SSE 实时推送 + 上下文续接 + 实时 UI 反馈）

让用户看到 Agent 的思考和工具调用过程，减少等待焦虑；支持多轮对话上下文续接。

**1. agent.py 流式生成器（新增 `run_agent_streaming`）**
- `Iterator[dict[str, Any]]` 生成器，yield 7 种事件：
  - `start`（tools_count）→ `iteration`（n, max）→ `text`（content）→ `tool_call_start`（name, arguments）→ `tool_call_end`（name, success, message, details, error）→ `done`（text, success, tool_calls）或 `error`（message）
- 与 `run_agent` 共享相同的 LLM 调用 + 工具执行逻辑，只是改为 yield 事件
- 支持 `history` 参数（多轮对话历史，最多 20 条避免 token 爆炸）
- `run_agent` 也加 `history` 参数（非流式模式也支持多轮）

**2. server.py 流式端点（新增 `POST /api/chat/stream`）**
- FastAPI `StreamingResponse` + `text/event-stream`
- 每个事件 `data: {...JSON...}\n\n` 格式
- `X-Accel-Buffering: no` header 禁用 nginx 缓冲
- `ChatRequest` 新增 `history: list[dict[str, str]]` 字段（默认空列表）
- 异常容错：生成器内 try/except，异常转为 error 事件

**3. api.ts 前端流式消费**
- 新增类型：`ChatHistoryEntry` / `ToolCallRecord` / `AgentStreamEvent`（7 种 union type）
- `api.chatStream()` async generator：`fetch` + `ReadableStream` + `TextDecoder` + SSE 解析
- 缓冲区处理：按 `\n\n` 分隔事件，`data: ` 前缀解析 JSON
- `api.chat()` 也支持 `history` 参数（非流式模式）

**4. App.tsx send 函数重写（流式版）**
- `messagesRef` + `useEffect` 同步，避免 stale closure 读不到最新 messages
- 构建 history：从已有 messages 过滤出 user/assistant 对话（最多 20 条）
- `for await (const event of api.chatStream(...))` 消费流
- 每种事件类型 switch 处理：
  - `text`：实时更新消息内容（边生成边显示）
  - `tool_call_start`：追加 tool_call 到列表 + 设置 currentTool
  - `tool_call_end`：更新最后一个 tool_call 的结果
  - `done`：设置最终文本 + tool_calls + 清除流式状态
  - `error`：设置错误信息
- 灰名单确认检测：done 事件后扫描 tool_calls 的 details.steps 查找 needs_confirm + denied

**5. MessageBubble.tsx 流式 UI**
- `isThinking` 状态：loading + 无内容 + 无工具调用 + 无 currentTool → 显示 "思考中..."
- 流式时也显示 content（实时更新）和 tool_calls（实时追加）
- `currentTool` 时显示 Loader2 spinner + "正在执行 X..."

**6. ToolCallCard.tsx 流式状态**
- 新增 `streaming` prop
- `running` 状态：流式时最后一个无结果的工具标记为 running
- `StatusIcon`：running 显示 Loader2 旋转动画
- 折叠态文案：running 时显示 "正在执行 X..." 或 "正在执行（M/N 完成）"
- running 时默认展开（让用户看到执行过程）

**7. types.ts Message 扩展**
- `streaming?: boolean` — 是否正在流式
- `iteration?: number` — 当前迭代轮数
- `currentTool?: string` — 当前正在执行的工具名

**8. 测试覆盖（test_agent.py 新增 TestRunAgentStreaming 6 个用例）**
- `test_streaming_no_llm`：无 LLM 时第一个事件是 error
- `test_streaming_text_only`：纯文本回复事件流（start → iteration → text → done）
- `test_streaming_with_tool_call`：工具调用事件流（含 tool_call_start/end）
- `test_streaming_llm_error`：LLM 失败事件流（error 结束）
- `test_streaming_with_history`：多轮对话历史传入 LLM 的 messages
- `test_streaming_max_iterations`：达到 max_iterations 优雅退出

**9. 版本号升级（6 文件）**
- pyproject.toml / __init__.py / package.json: `0.7.8a0` → `0.7.9a0`
- Cargo.toml / tauri.conf.json: `0.7.8` → `0.7.9`
- lib.rs APP_VERSION: `0.7.8-alpha` → `0.7.9-alpha`

**验证**：tsc 0 错误 + vite 200KB + 630 pytest 全通过（624 → 630，新增 6 个流式测试）+ 后端 /api/chat/stream SSE 正常推送 + 多轮 history 被接受

---

### v0.7.8-alpha (2026-07-19) — LogSheet 日志查看 UI（SSE 实时流 + 级别筛选 + 搜索 + 暂停 + 运行时级别调整）

复用 v0.7.7 日志系统 API，让用户在 GUI 中实时查看日志，方便 debug。

**1. LogSheet.tsx 新建（desktop/src/components/LogSheet.tsx）**
- **SSE 实时流**：`new EventSource(api.logStreamUrl())` 监听 `/api/logs/stream`，新日志自动追加
- **paused ref 优化**：`pausedRef` + `useEffect` 同步，避免 toggle 暂停时重建 EventSource 连接（原 `[open, paused]` deps 会导致每次 toggle 都 close+reconnect，丢失中间消息）
- **级别筛选**：ALL/DEBUG/INFO/WARNING/ERROR/CRITICAL segmented control（6 个按钮）
- **搜索**：按消息内容或 logger 名过滤（实时大小写不敏感）
- **暂停/继续**：Play/Pause 图标切换，暂停时 SSE 消息不追加到列表（但连接保持）
- **运行时级别调整**：自绘 Portal dropdown（DEBUG/INFO/WARNING/ERROR），调用 `POST /api/logs/level`
- **清空**：清空当前视图（不影响后端环形缓冲区）
- **自动滚动**：新消息到达时自动滚到底部（暂停时不滚）
- **退出动画**：`closing` 状态 + `prevOpenRef` 跟踪 + `animate-fade-out`（150ms）
- **Portal 渲染**：整个 Sheet + 运行时级别下拉都 `createPortal(document.body)`，避免父容器 overflow 裁剪
- **MAX_ENTRIES = 500**：前端最多保留 500 条，超出自动丢弃最旧的，防止内存爆炸
- **级别颜色**：DEBUG=cyan / INFO=green / WARNING=yellow / ERROR=red / CRITICAL=purple

**2. App.tsx 集成**
- import `LogSheet`
- 新增 `logSheetOpen` state
- StatusBar 加 `onOpenLog={() => setLogSheetOpen(true)}`
- 渲染 `<LogSheet open={logSheetOpen} onClose={...} />`

**3. StatusBar.tsx 加日志按钮**
- 新增 `onOpenLog?: () => void` prop
- 右侧加 Terminal 图标按钮（12px，hover 变亮）
- 位于 kbd 快捷键提示之前

**4. 版本号升级（6 文件）**
- pyproject.toml / __init__.py / package.json: `0.7.7a0` → `0.7.8a0`
- Cargo.toml / tauri.conf.json: `0.7.7` → `0.7.8`
- lib.rs APP_VERSION: `0.7.7-alpha` → `0.7.8-alpha`

**验证**：tsc 0 错误 + 624 pytest 全通过 + 后端重启 /api/logs 返回版本 0.7.8a0

---

### v0.7.7-alpha (2026-07-19) — 日志系统（Python logging 结构化 + /api/logs + SSE + 关键路径日志）

用户原话「我还想增加一个日志系统，用于debug」，本轮围绕"可调试性"建设日志基础设施。

**1. logging_config.py 核心（新建）**
- `LOGGER_NAME = "lihua"` 根 logger + 子 logger 自动加 `lihua.` 前缀
- `_RING_BUFFER`（1000 条内存环形缓冲区）+ `_SSE_SUBSCRIBERS`（订阅者列表）
- `_JsonFormatter`：JSON 单行格式写入文件（`ts/level/logger/module/line/msg/extra`）
- `_HumanFormatter`：彩色人类可读格式输出到 stderr（`2026-07-19 17:21:22 INFO  [server] FastAPI app 创建`）
- `_RingBufferHandler`：写入缓冲区 + 推送 SSE 订阅者
- `setup_logging(level, enable_stderr)`：初始化（幂等，多次调用只更新级别）+ RotatingFileHandler（10MB×5 轮转）
- `get_logger(name)` / `set_level(level)` / `get_recent_logs(n, level)` / `subscribe_sse()` / `unsubscribe_sse(q)` / `log_file_path()`
- 日志文件：`~/.local/share/lihua/lihua.log`（当前）+ `.log.1` ~ `.log.5`（轮转）

**2. Config 扩展**
- `Config` dataclass 新增 `log_level: str = "INFO"` 字段
- `_from_dict` 解析 `log_level`（`.upper()` 标准化）
- `to_toml` 序列化 `log_level = "INFO"`
- 默认配置模板加入 `log_level` 注释

**3. server.py 4 个日志 API 路由**
- `GET /api/logs?n=100&level=INFO` — 从环形缓冲区读最近 N 条（最新在前）
- `GET /api/logs/stream` — SSE 流式推送实时日志（`text/event-stream` + `asyncio.sleep(0.2)` 轮询 queue）
- `POST /api/logs/level` — 运行时调整级别（持久化到 config.toml）
- `GET /api/logs/file?n=200` — 直接读日志文件最后 N 行
- `create_app()` 开头调用 `setup_logging(level=cfg.log_level, enable_stderr=True)` + `log.info(f"FastAPI app 创建，版本 {__version__}")`
- `/api/chat` 路由加日志：用户输入 + Agent 完成 + 异常

**4. cli.py serve 命令初始化日志**
- `serve()` 函数开头调用 `setup_logging(level=cfg.log_level)` + `log.info("启动 Lihua HTTP 服务")`

**5. 关键模块加日志（agent.py / skill_runner.py / intent.py）**
- `agent.py`：
  - `run_agent` 入口：`Agent 启动：用户输入「...」`（extra: tools_count/max_iter/dry_run）
  - 每轮迭代：`迭代 N/MAX：调用 LLM` / `迭代 N：LLM 请求调用 K 个工具`
  - LLM 失败：`LLM 调用失败（迭代 N）：...`
  - Agent 完成：`Agent 完成：迭代 N，工具 K 个，回复 M 字`
  - 达到 max_iterations：`达到最大迭代次数 N，工具调用 K 个`
  - `_execute_tool`：`调用工具 X` + `工具 X 成功/失败（Y.YYs）`（extra: steps/final）
  - 工具异常：`log.exception`（含完整堆栈）
- `skill_runner.py`：
  - `run_skill` 入口：`执行 Skill「X」`（extra: params/steps）
  - `run_skill` 完成：`Skill「X」完成/失败（Y.YYs）`（extra: steps_run/final）
  - Skill 未找到：`Skill 未找到：X`
- `intent.py`：
  - `understand` 入口：`意图理解：「...」`
  - 规则匹配：`规则匹配：skill=X, params={...}`
  - LLM 增强：`别名表未命中「X」，调 LLM 增强` / `LLM 增强：params={...}`
  - LLM 识别：`LLM 识别：skill=X, params={...}`
  - 未匹配：`规则未匹配且 LLM 未启用` / `意图理解失败（LLM 也未识别）`

**6. 前端 api.ts 日志 API 封装**
- 新增 `LogEntry` / `LogsResponse` / `LogLevelUpdate` 类型
- `api.logs(n, level)` — 查询最近 N 条日志
- `api.setLogLevel(level)` — 运行时调整级别
- `api.logStreamUrl()` — SSE 流式推送 URL（供前端 EventSource 用）

**7. 测试覆盖**
- 新增 `tests/test_logging.py`（22 个测试）：
  - `TestSetupLogging`：初始化、幂等、无效级别回退
  - `TestGetLogger`：子 logger 前缀处理
  - `TestLoggingOutputs`：环形缓冲区、JSON 文件、extra 字段、异常信息、全级别
  - `TestGetRecentLogs`：N 条返回、级别过滤、无效级别、空查询
  - `TestSetLevel`：运行时过滤、无效级别回退
  - `TestSSESubscription`：订阅返回 queue、取消订阅、多订阅者广播
  - `TestRingBufferLimit`：1000 条上限 + 自动丢弃最旧
- 全量 624 个 pytest 全通过（602 + 22 新增）

**8. 版本号同步升级**
- pyproject.toml + __init__.py + package.json + Cargo.toml + tauri.conf.json + lib.rs APP_VERSION 全部 0.7.7 / 0.7.7a0 / 0.7.7-alpha

### 测试

- pytest 624 全通过（22 个新增 logging 测试）
- 后端重启验证：
  - `/api/logs` 返回 `{"entries":[{"msg":"FastAPI app 创建，版本 0.7.7a0"},...],"count":3}`
  - stderr 输出彩色日志：`2026-07-19 17:26:55 INFO  [intent] 规则匹配：skill=install_app, params={'target': 'QQ dry-run'}`
  - 触发 `/api/chat` 后日志按预期写入（用户输入 + 规则匹配 + Agent 完成）

### 已知问题

- T052: /api/logs 返回空（后端进程加载旧版 server.py，重启后修复）
- TODO v0.7.8+: elementary.io 风格 UI 优化（6 色 Palette + 圆角收敛 + 阴影减淡 + 字重对比）
- TODO v0.7.8+: AuditSheet 独立显示审计日志（含日志查看 + 级别调整）
- TODO v0.7.9+: 流式输出 + Agent 多轮对话（SSE 流式 + 上下文续接）
- TODO v0.7.10+: 新增更多 Skill（截图增强/系统监控/网络配置/文件管理）

---

### v0.7.6-alpha (2026-07-19) — ModelSheet 下拉菜单 Portal 修复 + 后端数据格式同步

用户反馈「模型设置的请选择模型下拉菜单没办法弹出来啊」，排查发现两层叠加问题。

**1. 下拉菜单 Portal 修复（T051 问题 1）**
- 原因：sheet 容器 `overflow-hidden`（圆角裁剪）+ 主体内容区 `overflow-y-auto`（滚动）双层裁剪，导致 `absolute top-full` 定位的下拉列表根本无法显示
- 修复：
  - 引入 `createPortal` 把下拉列表渲染到 `document.body`
  - 新增 `dropdownPos` 状态存储 `getBoundingClientRect()` 计算的位置
  - 新增 `handleToggleDropdown`：点击 trigger 时计算位置后展开
  - 下拉列表用 `position: fixed` + `zIndex: 9999` 脱离父容器 overflow 限制
  - 滚动/resize 时自动关闭（避免位置错乱）
  - 点击外部关闭：同时检查 trigger ref 和 list ref
- 同时去掉 sheet 容器的 `overflow-hidden`（圆角改由顶部栏 `rounded-t-2xl` + 底部按钮栏 `rounded-b-2xl` 实现）
- 文件：`desktop/src/components/ModelSheet.tsx` 大改

**2. 后端数据格式同步（T051 问题 2）**
- 原因：后端 `lihua serve` 进程是 09:46 启动的，没重启，还在用旧版 `model_presets.py`（返回字符串数组 `["deepseek-chat"]`），但前端期望对象数组（有 `name`/`tier`/`is_free` 字段）
- `model.name` 取到 undefined（字符串没有 .name 属性），React 渲染 `{undefined}` 就是空字符串
- 修复：kill 旧进程 + 重新启动 `lihua serve`，加载新版 model_presets.py
- 验证：`curl /api/models/presets` 确认返回对象数组，前端下拉显示 ["DeepSeek V4 Flash", "DeepSeek V4 Pro旗舰"]
- 教训：**改了 Python 代码必须重启后端**（FastAPI/uvicorn 默认不热重载）

**3. 版本号同步升级**
- pyproject.toml + __init__.py + package.json + Cargo.toml + tauri.conf.json + lib.rs APP_VERSION 全部 0.7.6 / 0.7.6a0 / 0.7.6-alpha

### 测试

- tsc 0 错误
- 浏览器端到端验证：下拉菜单正常弹出 + 文字正常显示 + 切换厂商/模型 + 保存

### 已知问题

- T051: ModelSheet 下拉菜单不显示字（v0.7.6 Portal 修复 + 后端重启修复）
- TODO v0.7.7+: elementary.io 风格 UI 优化（6 色 Palette + 圆角收敛 + 阴影减淡 + 字重对比）
- TODO v0.7.7+: 功能完善（增加更多 Skill / 流式输出 / AuditSheet 等）

---

### v0.7.5-alpha (2026-07-19) — vignette 跟圆角 + Sheet 四角圆角 + WebKitGTK GPU 加速 + beautify_ubuntu 性能模式

用户原话「Gui 四周的透明渐变的遮罩没有跟这主界面的圆角变化，这你能接受？模型选择界面也是只有上面两个是圆角，下面两个角又是方的。感觉你没有严格按照我们定下来的设计原则去做。细节细节细节。/ Ubuntu底层确实稀碎。但是我们这个软件就是来解决这个体验问题的。看看能不能通过这个软件优化Ubuntu的底层。/ 并且能不能开启GPU加速这个GUI啊？/ 总之，如果mac是精装修，windows是标准间，ubuntu就是一个垃圾遍地的毛坯。我要的是mac一样的无限的优雅和细节控」，本轮追求「mac 一样的无限优雅和细节控」。

**1. 主窗口 vignette 跟圆角（修复 T048）**
- 原因：v0.7.4 App.tsx 外层 `p-3`（12px padding）让 .window-glass 和窗口边缘有 12px 间隙；Wayland Mutter 不支持真透明，间隙显示为黑色矩形，vignette inset shadow 被黑色矩形包围，整体看起来方形
- 修复：
  - 去掉外层 `p-3`，让 .window-glass 占满整个窗口
  - 新增 `.window-outer` 类（`border-radius: 16px` + `overflow: hidden` + `will-change: transform` + `transform: translateZ(0)` + `contain: layout paint`），让 webview 内圆角外区域完全不渲染
  - `.window-glass` 重写 4 层 inset shadow：
    - `inset 0 1px 0 rgba(255,255,255,0.10)` 顶部 1px 高光线
    - `inset 0 0 0 1px rgba(255,255,255,0.06)` 整体 1px 内边框
    - `inset 0 0 32px rgba(0,0,0,0.30)` 边缘 32px 深渐变（强化圆角）
    - `inset 0 0 120px rgba(0,0,0,0.12)` 边缘 120px 柔和渐变（vignette）
- 文件：`desktop/src/App.tsx` + `desktop/src/index.css` 修改

**2. ModelSheet / LogoSheet 四角圆角 + 漂浮边距（修复 T049）**
- 原因：v0.7.4 sheet 容器用 `rounded-t-2xl`（只圆顶部），底部方角，与主窗口圆角风格不一致
- 修复：
  - `rounded-t-2xl` → `rounded-2xl`（四角都圆角）
  - overlay 加 `p-3`（padding 12px），让 sheet 与窗口边缘留 12px 边距，"漂浮"在窗口内
  - 加 `shadow-popover` 强化漂浮感
- 教训：macOS Sheet 风格（贴底部 + 顶部圆角）在 Linux 方形窗口下看起来割裂，四角圆角 + 漂浮边距更精致
- 文件：`desktop/src/components/ModelSheet.tsx` + `desktop/src/components/LogoSheet.tsx` 修改

**3. WebKitGTK GPU 加速（修复 T050）**
- 原因：Tauri Linux 用 WebKitGTK 渲染，默认未启用 GPU 合成层，动画卡顿
- 修复：
  - `lib.rs` 的 `run()` 函数开头设置环境变量（必须在 Tauri Builder 之前）：
    - `WEBKIT_DISABLE_COMPOSITING_MODE=0` 启用 GPU 合成层
    - `WEBKIT_DISABLE_DMABUF_RENDERER=0` 启用 dmabuf 渲染器
  - 用 `is_err()` 检查：只在用户未显式设置时才设默认值，允许环境变量覆盖
  - CSS 层配合：所有毛玻璃类（`.window-outer` / `.window-glass` / `.card-glass` / `.input-glass`）加 `will-change: transform` + `transform: translateZ(0)` 强制合成层 + `contain: layout paint` 限制重排重绘范围
- 注意：Wayland + NVIDIA 专有驱动下 dmabuf 可能黑屏，需 `WEBKIT_DISABLE_DMABUF_RENDERER=1` 回退
- 文件：`desktop/src-tauri/src/lib.rs` + `desktop/src/index.css` 修改

**4. beautify_ubuntu 扩展 performance 模式（响应"通过这个软件优化Ubuntu的底层"）**
- 原 v0.7.3 只有 macos / elementary / restore 三个 target，本次新增 performance 模式
- `beautify-ubuntu.yaml` 大幅扩展（version 0.1 → 0.2）：
  - triggers 从 14 个扩展到 27 个（新增「优化ubuntu / 优化系统 / 提升性能 / 系统优化 / gpu加速 / GPU加速 / 字体模糊 / 字体太模糊 / 太模糊 / 字体渲染 / 动画卡顿 / 装修系统 / 装修ubuntu」）
  - extract 正则扩展：`(macos|mac os|elementary|performance|性能|优化|gpu|字体|动画|恢复|还原|默认)`
  - 新增 6 个 performance 步骤：
    - `detect_gpu_info`（safety: white 只读）— GPU 硬件 + 驱动 + 会话类型检测（lspci -nn | grep VGA + glxinfo | grep "OpenGL renderer" + echo $XDG_SESSION_TYPE）
    - `enable_font_smoothing`（safety: grey）— rgba 次像素抗锯齿 + slight hinting（gsettings set font-antialiasing / font-hinting）
    - `enable_gnome_animations`（safety: grey）— enable-animations true + 延迟扩展 1000ms
    - `install_mesa_tools`（safety: grey）— mesa-utils + vulkan-tools（GPU 诊断工具）
    - `config_gnome_perf`（safety: grey）— 搜索/缩略图/键盘性能优化（关 .rpm/.doc 搜索 + 关缩略图缓存 + 关键盘延迟）
    - `cleanup_unnecessary_startup`（safety: white 只读）— 列出 GNOME 自启动项（gnome-extensions list --enabled + ~/.config/autostart/ 列表）
  - 拆分 final_hint → `final_hint`（beauty）+ `final_hint_perf`（performance）
  - 拆分 notify → `notify_beauty` + `notify_perf`
  - 所有 performance condition 用 `in` 操作符：`{{target}} in [performance, 性能, 优化, gpu, GPU, 字体, 动画]`
  - beauty mode condition 用正向列表：`{{target}} in [macos, elementary, 恢复, 还原, 默认]`（避免 `not in` 不支持）
- 文件：`src/lihua/data/skills/beautify-ubuntu.yaml` 大幅扩展

**5. condition 表达式语法改进**
- 原来用 `{{target}} == performance` 无法匹配 extract 返回的 `GPU` / `优化` / `字体` 等值
- 改用 `in` 操作符支持多关键词：`{{target}} in [performance, 性能, 优化, gpu, GPU, 字体, 动画]`
- beauty mode 用正向列表避免 `not in` 不支持的问题
- 文件：`src/lihua/skill_runner.py` 的 `eval_condition`（已有 `in` 操作符支持）

**6. 测试扩展**
- `tests/test_skills_beautify.py` 完全重写：
  - `test_skill_has_three_targets` → `test_skill_has_four_targets`（覆盖 performance target）
  - 新增 performance trigger 到 parametrize（优化ubuntu / GPU加速 / 字体太模糊了 / 动画卡顿 / 装修系统 等）
  - 新增 `test_has_performance_steps`（GPU 检测 + 字体渲染 + 动画 + 性能优化 6 个步骤）
  - `test_all_steps_grey_safety` → `test_grey_safety_for_modify_steps`（detect_gpu_info 和 cleanup_unnecessary_startup 是 white 例外）
  - 新增 `test_performance_steps_have_target_performance_condition`（检查 `in` 操作符）
  - 新增 `test_performance_font_smoothing`、`test_performance_gpu_detect`、`test_performance_animations`
  - `test_parameters_extract` 中 GPU expected 改为 `"GPU"`（正则 IGNORECASE 返回原文大写）
- 全量 pytest 602 个测试通过（581 + 21 新增）

**7. 版本号同步升级**
- pyproject.toml + __init__.py + package.json + Cargo.toml + tauri.conf.json + lib.rs APP_VERSION 全部 0.7.5 / 0.7.5a0 / 0.7.5-alpha

### 测试

- tsc 0 错误
- vite build 成功：dist/assets/index-*.js 188KB / dist/assets/index-*.css 24KB
- pytest 602 全通过（21 个新增 beautify performance 测试）
- `lihua --version` → `lihua 0.7.5a0`

### 已知问题

- T048: GUI 四周 vignette 渐变遮罩不跟圆角（v0.7.5 去 p-3 + .window-outer overflow:hidden + 4 层 inset shadow 修复）
- T049: ModelSheet/LogoSheet 圆角不一致（v0.7.5 rounded-2xl + p-3 漂浮 + shadow-popover 修复）
- T050: WebKitGTK GPU 加速默认未启用（v0.7.5 lib.rs 环境变量 + CSS will-change/translateZ 修复）
- TODO v0.7.6+: AuditSheet 独立显示审计日志（当前 open-audit 暂时打开 history sidebar）
- Wayland + NVIDIA 专有驱动下 dmabuf 渲染器可能黑屏（用户需 `WEBKIT_DISABLE_DMABUF_RENDERER=1` 回退）

---

### v0.7.4-alpha (2026-07-19) — ModelSheet 自绘下拉 + 退出动画 + Logo emoji 化 + 托盘菜单全监听

用户原话「选模型的界面是白底白字吗？还是黑底黑字。我看web里面是黑的，Gui运行的是白的。估计调用ubuntu原生的下拉菜单了。好丑。有字吗？至少我没看到字 / 要不你直接找个猫的emoji贴上去吧。然后设置一个用户可以自定义图片的功能 / Gui 主界面边上的透明度渐变遮罩好像没有起作用，一个方形的界面。最搞的是退出模型选择界面竟然有残影 / 状态栏的按钮入口很多选项点了都没效果啊？是没做吗？」，本轮解决 v0.7.3 真机实测发现的 4 个问题。

**1. ModelSheet 自绘下拉菜单（修复 Tauri WebView 白底白字）**
- 原因：v0.7.3 用原生 `<select>`，Ubuntu 原生下拉菜单是白底白字，在暗色背景下看不见字
- 修复：完全自绘下拉菜单（`<button>` + 绝对定位的弹层列表），用项目暗色主题（bg-bg-secondary 黑底 + text-text-primary 白字）
- 选中态显示绿色对勾（Check 图标 + bg-accent-soft）
- 旗舰/免费徽章保留（绿色「旗舰」/ 蓝色「免费」）
- 下拉展开时 ChevronDown 旋转 180°
- 点击外部自动关闭（useRef + mousedown 监听）
- ESC 键优先关闭下拉，再关闭整个面板
- 文件：`desktop/src/components/ModelSheet.tsx` 修改

**2. ModelSheet 退出动画（修复退出残影）**
- 原因：v0.7.3 `open=false` 时直接 `return null`，组件突然消失，没有 fade-out 过渡，视觉上感觉「有残影」
- 修复：引入 `closing` 状态 + `prevOpenRef` 跟踪上一次 open
  - open=true→false 时：setClosing(true) → 渲染 `animate-fade-out` → 150ms 后 setClosing(false) → 真正 unmount
  - 避免初始 mount 时误触发退出动画（prevOpenRef 初值 false）
- ESC / 点击遮罩 / 关闭按钮三种关闭路径都走退出动画（统一调 handleClose）
- 文件：`desktop/src/components/ModelSheet.tsx` 修改

**3. LihuaLogo 改用 emoji 🐱 + 支持自定义图片**
- 用户原话「狸花猫的图标甚至不如第一版的 emoji」（v0.7.3 反馈）+ 「要不你直接找个猫的emoji贴上去吧。然后设置一个用户可以自定义图片的功能」（v0.7.4 明确方向）
- 彻底放弃自绘 SVG（v0.7.0-v0.7.3 失败 3 次），改用系统 emoji 🐱（每家平台都有成熟设计）
- 默认渲染：`<span style={{ fontSize: size, ... }}>🐱</span>`（系统 emoji 字体）
- 自定义图片渲染：`<img src={customSrc} ... />`（base64 data URL）
- 渲染优先级：customSrc > 默认 emoji
- 文件：`desktop/src/components/LihuaLogo.tsx` 完全重写

**4. 新增 LogoSheet（自定义图片上传 UI）**
- 触发方式：点击 TitleBar 的 Logo
- 功能：
  - 显示当前 logo 预览（emoji 或自定义图片）
  - 上传自定义图片（FileReader → base64 → localStorage `lihua:custom-logo`）
  - 拖拽上传支持（onDragOver / onDragLeave / onDrop）
  - 重置为默认 emoji（清 localStorage）
  - 校验：image/* 类型 + < 500KB 大小
- 与 ModelSheet 同样的退出动画（closing 状态 + fade-out）
- 文件：`desktop/src/components/LogoSheet.tsx` 新增（256 行）

**5. TitleBar Logo 可点击**
- Logo 加 onClick（打开 LogoSheet）+ hover 背景（hover:bg-bg-tertiary/30）+ padding 让点击区域稍大
- 文件：`desktop/src/components/TitleBar.tsx` 修改

**6. App.tsx 监听托盘菜单 open-settings / open-audit 事件**
- 原因：lib.rs 托盘菜单的「设置」emit `open-settings`、「审计日志」emit `open-audit`，但 App.tsx 只监听了 `new-chat` 和 `open-history`，导致这两个菜单项点击后只显示主窗口但不做对应事情
- 修复：
  - `open-settings` → setModelSheetOpen(true)
  - `open-audit` → 暂时打开 Sidebar 历史 tab（TODO v0.7.5+: 做独立 AuditSheet 显示 ~/.local/share/lihua/audit.log）
- 文件：`desktop/src/App.tsx` 修改

**7. 窗口 vignette 内阴影（缓解 Wayland 方形窗口问题）**
- 用户反馈「Gui 主界面边上的透明度渐变遮罩好像没有起作用，一个方形的界面」
- 原因：Wayland 下 Tauri `transparent: true` 可能不生效，窗口呈现方形硬边
- 修复：`.window-glass` 加两层 inset 阴影：
  - `inset 0 0 24px rgba(0,0,0,0.35)` → 边缘 24px 范围较深渐变，强化圆角感
  - `inset 0 0 80px rgba(0,0,0,0.15)` → 边缘 80px 范围柔和渐变，模拟 vignette
- 文件：`desktop/src/index.css` 修改

**8. 版本号同步升级**
- pyproject.toml + __init__.py + package.json + Cargo.toml + tauri.conf.json + lib.rs APP_VERSION 全部 0.7.4 / 0.7.4a0 / 0.7.4-alpha

### 测试

- tsc 0 错误
- vite build 成功：dist/assets/index-C0ohg3DN.js 188.28 KB / dist/assets/index-DZaCc0Ee.css 23.88 KB
- pytest 581 全通过（65.88s）
- `lihua --version` → `lihua 0.7.4a0`

### 已知问题

- T044: Tauri WebView 下原生 `<select>` 白底白字（v0.7.4 自绘下拉修复）
- T045: ModelSheet 退出无动画导致残影（v0.7.4 closing 状态 + fade-out 修复）
- T046: 托盘菜单「设置」「审计日志」emit 事件未被前端监听（v0.7.4 App.tsx 加 listen 修复）
- T047: Wayland 下窗口透明不生效，方形硬边（v0.7.4 vignette 内阴影缓解，根本解决需 layer-shell 协议）
- TODO v0.7.5+: AuditSheet 独立显示审计日志（当前 open-audit 暂时打开 history sidebar）

---

### v0.7.3-alpha (2026-07-19) — ModelSheet 极简化 + 默认 pro 旗舰 + 能力下限警告 + beautify_ubuntu Skill

用户原话「这个模型设置需要搞这么大的阵仗吗？我是用户填个token选个模型就行了 / 感觉你没有把用户当成挑剔的懒人，并且是不在乎花钱的人 / 完全可以默认用最贵的模型 / 明确提示不建议使用能力低于deepseek-v4-flash的 / 狸花猫的图标甚至不如第一版的emoji / Ubuntu的界面很老登，可以给有需求的用户安装Elementary OS的界面 / 通过优化Ubuntu的显示/壁纸之类的，实现类似MAC OS的精致度」，本轮解决 4 个核心问题。

**1. ModelSheet 极简化（去掉大阵仗）**
- 去掉 v0.7.2 的 6 个预设卡片 2 列网格 + tier 分组（基础/Pro）独立区 + 免费徽章 + 上下文长度 + 当前状态卡片 + 描述卡片
- 厂商改为 segmented control（一行排开，iOS 风格，6 个按钮）
- 模型用原生 `<select>` 下拉（最简单），选项后缀「（旗舰）/ · 免费」标识 tier
- API Key 简化为单一输入框（带显隐 + 获取链接）
- 整个面板结构：厂商 segmented → 模型 select → API Key → 底部警告条 → 保存按钮
- 文件：`desktop/src/components/ModelSheet.tsx` 完全重写

**2. 默认推荐 pro 旗舰 + 能力下限警告**
- 所有 5 个厂商的 `recommended_model` 改为 pro 旗舰：
  - 智谱 → `glm-5.2`
  - DeepSeek → `deepseek-v4-pro`
  - Kimi → `kimi-k3`（2026-07 最新 2.8T 参数）
  - MiMo → `mimo-v2.5-pro`（1T MoE）
  - MiniMax → `MiniMax-M2.7`（2026-03 最新旗舰）
- 新增 `MIN_RECOMMENDED_MODEL = "deepseek-v4-flash"` 常量 + `MIN_RECOMMENDED_WARNING` 文案
- 新增 `get_min_recommended()` 函数（前端展示用）
- ModelSheet 底部固定黄色警告条（AlertTriangle 图标 + 能力下限提示）：
  > 不建议使用能力低于 DeepSeek V4 Flash 的模型，否则 Agent 可能无法正确调用工具
- 文件：`src/lihua/model_presets.py` 修改 + `desktop/src/components/ModelSheet.tsx` 集成警告条

**3. LihuaLogo 圆润卡通版（连续第 3 次重做）**
- v0.7.1 几何化（被嫌弃「像猪」）→ v0.7.2 盾形脸 + 尖耳朵 + 杏仁眼 + ω 嘴（被嫌弃「不如第一版 emoji」）→ v0.7.3 纯圆形构图
- 纯圆形构图（圆头 + 圆耳朵），参考 Pusheen / Hello Kitty 风格
- 圆点眼睛（不再是杏仁形），更萌更简单
- 小三角鼻 + 单一微笑弧线（不是 ω 形）
- 完全去掉胡须（之前太杂乱）
- 描边 1.8（比 v0.7.2 的 1.6 略粗，更醒目）
- 文件：`desktop/src/components/LihuaLogo.tsx` 完全重写

**4. 新增 beautify_ubuntu Skill（Ubuntu 美化：macOS + Elementary 风格）**
- 新增 `src/lihua/data/skills/beautify-ubuntu.yaml`（90 行）
- triggers: 美化ubuntu / 美化桌面 / macos风格 / elementary风格 / 桌面太丑 / 主题美化 / 精致度 等 14 个
- parameters: target（macos / elementary / 恢复/还原/默认，默认 macos）
- macOS 风格步骤（8 个）：安装依赖 → WhiteSur GTK 主题 → WhiteSur 图标 → WhiteSur 光标 → 应用主题（gsettings set）→ 安装 GNOME 扩展（user-theme）→ 配置 dash-to-dock（底部居中 + 动态透明）→ 配置 blur-my-shell（毛玻璃）
- Elementary 风格步骤（3 个）：安装 Plank dock → 安装 elementary 图标 → 应用 Elementary 主题（浅色 + Plank 自启动）
- 恢复默认步骤（1 个）：恢复 Yaru 主题 + Ubuntu 字体
- 所有 command 步骤 `safety: grey`，强制走灰名单确认（confirm 文案为人类语言，不展示原始命令）
- 最终提示：注销重新登录 + Extension Manager 安装扩展 + Tweaks 微调 + wallhaven.cc 壁纸推荐

**安全引擎验证**：
- `apt install` 在白名单 → YAML `safety: grey` 强制走 grey（取更严格一方）
- `gsettings set` 在白名单 → YAML `safety: grey` 强制走 grey
- `gnome-extensions enable` 在白名单 → YAML `safety: grey` 强制走 grey
- `git clone` / `wget`（非 --spider）→ unknown → YAML `safety: grey` 提升为 grey
- `sudo apt install` → 灰名单 `^\s*sudo\s+`
- `nohup` → 灰名单
- `rm -rf WhiteSur-gtk-theme`（/tmp 下）→ 不在黑名单 → unknown → grey
- 所有命令都会走 grey 确认流程，符合预期

**Trigger 冲突防护**：
- `desktop-icon.yaml` 有 trigger "桌面"（2 字符）
- `beautify-ubuntu.yaml` 有 "美化桌面"（4 字符）、"桌面太丑"（4 字符）、"桌面丑"（3 字符）
- 依赖"最长 trigger 优先"策略消歧，无实际冲突

**测试扩展**：
- 新增 `tests/test_skills_beautify.py`（42 个测试）：
  - TestBeautifyUbuntuSkill：3 个（加载 + 三种 target + 参数提取）
  - TestBeautifyUbuntuTriggerMatch：21 个（14 个 trigger 匹配 + 7 个 intent 匹配）
  - TestBeautifyUbuntuTriggerConflict：4 个（"美化桌面" 4字符 vs "桌面" 2字符 消歧）
  - TestBeautifyUbuntuStepStructure：6 个（macOS/elementary/restore 步骤 + safety/confirm 校验）
  - TestBeautifyUbuntuConditions：4 个（macOS/elementary/restore/install_deps condition 表达式）
  - TestBeautifyUbuntuCommands：4 个（git clone / gsettings / Yaru / Plank 命令验证）
- 全量 pytest 581 个测试通过（539 + 42 新增）

**实测验证**：
- TypeScript 编译 0 错误（tsc --noEmit）
- Vite build 成功（180.91 KB JS / 22.96 KB CSS，gzip 后 56.83 KB / 5.43 KB）
- pytest 581 全通过
- `lihua --version` → `lihua 0.7.3a0`
- 版本号同步升级：pyproject.toml + __init__.py + package.json + Cargo.toml + tauri.conf.json 全部 0.7.3a0 / 0.7.3

**已知问题**：
- 用户连续 3 次反馈 Logo 不满意（v0.7.1 像猪 / v0.7.2 不如 emoji / v0.7.3 待用户验证）— 见 traps.md T041
- ModelSheet v0.7.2 的 tier 分组 + 免费徽章 + 上下文长度信息过载，被用户反馈「大阵仗」— 见 traps.md T042
- 默认推荐免费模型不符合「挑剔的懒人不在乎花钱」的用户画像 — 见 traps.md T043
- sandbox 环境下无法写入 `~/.config/lihua/config.toml`（权限错误），实际运行不受影响 — 见 traps.md T036

---

### v0.7.2-alpha (2026-07-19) — ModelSheet 主窗口内 overlay + 最新模型清单 + Logo 重设计

用户原话「模型设置界面跑出主界面之外了 / 都是老黄历模型了 / 没有sidebar时内容不居中 / 新的狸花猫图标太丑了不可爱」，本轮解决 4 个核心问题。

**1. ModelSheet 改为主窗口内 overlay（不再跑出主界面）**
- 定位从 `fixed inset-0`（脱离主窗口、覆盖浏览器视口）改为 `absolute inset-0`（相对主窗口容器）
- 动画从 `animate-slide-right`（右侧滑入）改为 `animate-slide-up`（从底部滑上）
- 文件：`desktop/src/components/ModelSheet.tsx` 完全重写

**2. 最新模型清单（2026-07 各家最新版）+ tier 分级 + 免费优先**
- 通过 WebSearch 查询 5 家厂商最新模型清单
- 新增 `ModelOption` dataclass：id / name / tier（basic/pro）/ is_free / context_length / description
- `ModelPreset.recommended_model` 取代 `default_model`，`models` 从 `list[str]` 改为 `list[ModelOption]`
- 6 个预设按免费优先排序：智谱（GLM-4-Flash 完全免费！）→ DeepSeek V4 → Kimi K2.6/K3 → MiMo V2.5 → MiniMax M2.7 → 自定义
- 后端 `apply_preset` API 支持 body 选择具体 `model_id`，custom 预设允许任意 api_base + model_id
- 前端 `ModelSheet` 新增 `ModelSelector` 子组件按 tier 分组（基础模型 / Pro 旗舰）+ 免费徽章（Gift 图标）+ 上下文长度显示
- 文件：`src/lihua/model_presets.py` 完全重写 + `src/lihua/server.py` 修改 + `desktop/src/api.ts` 类型更新 + `desktop/src/components/ModelSheet.tsx` 重写

**最新模型清单**：
- 智谱 GLM：glm-4-flash-250414（免费！）/ glm-4.5-flash / glm-4.5-air / glm-5.2（旗舰）
- DeepSeek V4：deepseek-v4-flash（经济）/ deepseek-v4-pro（旗舰）
- Kimi：kimi-k2.6（开源旗舰）/ kimi-k3（最新旗舰 2.8T 参数）
- MiMo：mimo-v2.5（基础 310B）/ mimo-v2.5-pro（旗舰 1T）
- MiniMax：abab6.5s-chat（基础）/ MiniMax-M2.7（旗舰）

**3. 主内容区无 sidebar 时居中显示**
- `WelcomeScreen` 外层 div 加 `flex-1`（之前缺失导致无 sidebar 时取自然宽度左对齐）
- `MessageList` 内容包 `max-w-[640px] mx-auto`（ChatGPT 风格的居中消息列）
- `InputBar` 外层加 `max-w-[640px] mx-auto w-full`（与消息列对齐）
- 文件：`desktop/src/components/WelcomeScreen.tsx` + `MessageList.tsx` + `InputBar.tsx`

**4. LihuaLogo 重设计（可爱优雅，简笔画风）**
- 综合两个 subagent 方案的优点：方案 B 的内耳小三角 + 方案 A 的优雅杏仁眼 + ω 形可爱嘴
- 盾形脸（上宽下窄，区别于猪的圆脸）
- 高耸尖耳朵（M 5 3 → L 6 9 → ... → L 19 3 → L 15 7 → Q 12 8 9 7 → Z 一笔画）
- 内耳开口三角（不闭合，更轻盈）
- 水滴形杏仁眼（Q 曲线，上尖下圆）
- 小倒三角鼻 + 鼻下短垂线 + ω 形两弧（经典猫咪嘴型）
- 4 根胡须（左右各 2，opacity 0.4 不抢主视觉）
- 描边 1.6（比之前 1.5 略粗，更醒目）
- 文件：`desktop/src/components/LihuaLogo.tsx` 完全重写

**实测验证**：
- TypeScript 编译 0 错误（tsc --noEmit）
- Vite build 成功（185.61 KB JS / 23.36 KB CSS，gzip 后 57.61 KB / 5.48 KB）
- pytest 539 全通过
- `lihua --version` → `lihua 0.7.2a0`
- 版本号同步升级：pyproject.toml + __init__.py + package.json + Cargo.toml + tauri.conf.json 全部 0.7.2a0

**已知问题**：
- sandbox 环境下无法写入 `~/.config/lihua/config.toml`（权限错误），实际运行不受影响 — 见 traps.md T036
- 当前 SenseNova + deepseek-v4-flash 配置会被识别为「自定义」（因 api_base 不在预设里），这是预期行为

---

### v0.7.1-alpha (2026-07-19) — 视觉精修 + 模型切换 UI

用户原话「动画效果不够、猫头太丑像猪、模型设置入口缺失」，本轮解决 4 个核心问题。

**1. 重新设计 LihuaLogo SVG**（原创，取代 lucide Cat）
- 几何化尖耳朵轮廓（猫的特征，区别于猪的贴头小耳）
- 圆润下颌 + 杏仁眼（上扬，有神）+ 小倒三角鼻 + M 形嘴 + 4 根胡须
- 描边宽度 1.5，line-cap round，跟随 currentColor
- 文件：`desktop/src/components/LihuaLogo.tsx`

**2. Sidebar 双向动画 + 主内容区配合**
- 始终 mounted，通过 `width + opacity transition` 实现滑入/滑出
- 主内容区配合收缩（width 0 → 288px 平滑过渡，flex layout 自动重排）
- 内容固定宽度 `w-72`，外层 `overflow-hidden` 避免缩放期变形
- `transition-[width,opacity] duration-base ease-out-soft`（240ms 缓动）

**3. 按钮微动效增强**
- IconButton：hover scale(1.05) + active scale(0.95) 明确按压反馈
- WelcomeScreen 快捷动作卡片：hover -translate-y-0.5 + shadow-md + active scale(0.98)
- Tab 切换：hover 加 bg-tertiary/30 微底色
- 列表项 hover 加 transition-all

**4. 模型切换功能（端到端）**

后端（`src/lihua/`）：
- 新增 `model_presets.py`：6 个预设（DeepSeek / Kimi / MiniMax / 智谱 / MiMo / 自定义）
- `config.py`：新增 `Config.to_toml() / save() / update_llm()` 方法（增量更新 + 持久化）
- `server.py` 新增 4 个 API：
  - `GET /api/models/presets` — 预设清单
  - `GET /api/config/llm` — 当前配置（API Key 脱敏）
  - `POST /api/config/llm` — 增量更新（字段可选）
  - `POST /api/config/llm/preset/{id}` — 一键应用预设

前端（`desktop/src/`）：
- 新增 `components/ModelSheet.tsx`（440px 宽，从右侧滑入）：
  - 6 个预设卡片（2 列网格，hover -translate-y + shadow）
  - 当前激活预设显示绿色 ✓ 徽章
  - 选中后展开详情：描述 + docs_note + 获取 API Key 链接
  - API Key 默认脱敏显示，点击切换编辑模式 + 显隐切换
  - custom 模式：手动填 api_base + model
  - 保存后 1.2 秒自动关闭 + 通知父组件刷新 health
- `api.ts` 新增 `ModelPreset / LLMConfig / LLMConfigUpdatePayload` 类型 + 4 个 API 方法
- `StatusBar.tsx` 增强：
  - 左侧 LLM 状态可点击（onOpenModelSettings 回调）
  - 状态点呼吸光晕动画（在线时 `animate-pulse-soft`）
  - 显示 ChevronRight 图标暗示可点击
  - 离线时显示「未启用 LLM · 点击设置」
- `App.tsx` 集成 ModelSheet（modelSheetOpen state + onSaved 刷新 health）

**实测验证**：
- 后端 API：6 个预设返回正确，当前配置脱敏正常，应用预设写入 config.toml 成功（sandbox 外）
- 前端构建：tsc + vite build 通过（181KB JS / 23KB CSS）
- 浏览器截图验证：
  - 新 logo 几何化尖耳朵猫头，不再像猪 ✅
  - ModelSheet 从右侧滑入流畅 ✅
  - 6 个预设卡片对称、错落有致 ✅
  - Sidebar 双向动画 + 主内容区配合 ✅
  - 状态栏点击打开 ModelSheet ✅
- 539 pytest 全通过

**已知问题**：
- sandbox 环境下无法写入 `~/.config/lihua/config.toml`（权限错误），实际运行不受影响
- 当前 SenseNova + deepseek-v4-flash 配置会被识别为「自定义」（因 api_base 不在预设里），这是预期行为

---

### v0.7.0-alpha (2026-07-19)

UI 全量重构：从"粗俗廉价"的浏览器风格升级为 macOS Sequoia 原生暗色风。用户原话「现在的设计我不想每天见到它」，目标是「每天看到不烦」的高级感。

**核心改动**：

1. **设计系统重写**（`desktop/tailwind.config.js` + `desktop/src/index.css`）
   - 色板：macOS System Green #30D158 + 9 阶灰阶 + rgba 三阶边框（soft/default/strong）
   - 8 点栅格间距系统（2/4/6/8/12/16/20/24/32/40/48px）
   - 分层圆角：sm(6) / md(10) / lg(14) / xl(18) / 2xl(24)，取代一刀切 rounded-2xl
   - 三层毛玻璃：window-glass (blur 40px) / card-glass (blur 16px) / input-glass (blur 20px)
   - 字体：思源黑体（正文）+ 思源宋体（欢迎语）+ JetBrains Mono（等宽）
   - macOS 风格字号阶梯：xs(11) / sm(13) / base(15) / lg(17) / xl(22) / 2xl(28)
   - 动画：fade-in/out, slide-down/up/right, scale-in, pulse-soft, shimmer
   - 缓动函数：out-soft / in-out-soft / spring (cubic-bezier(0.34, 1.56, 0.64, 1))
   - CSS 变量定义在 :root，Tailwind config 全部引用变量

2. **组件层拆分**（`desktop/src/components/`，10 个新文件）
   - `LihuaLogo.tsx` - 狸花猫品牌 logo（lucide-react Cat 占位，后期换定制 SVG）
   - `IconButton.tsx` - 通用图标按钮（32×32，default / hoverDanger 两种 variant）
   - `TitleBar.tsx` - 顶部标题栏 48px（可拖动 + logo + 标题 + 侧栏切换 + 关闭）
   - `InputBar.tsx` - 输入区（毛玻璃卡片 + 圆形发送按钮 + 思考中呼吸光晕）
   - `WelcomeScreen.tsx` - 空状态欢迎屏（logo 卡片 + 思源宋体欢迎语 + 6 快捷动作）
   - `MessageBubble.tsx` - 消息气泡（用户右对齐淡绿 / 助手左对齐毛玻璃）
   - `MessageList.tsx` - 对话流容器（大留白 + 自动滚动 + 上滚暂停检测）
   - `ToolCallCard.tsx` - **核心创新**：工具调用过程默认折叠，出错自动展开
   - `ConfirmSheet.tsx` - macOS Sheet 风格确认弹窗（从顶部滑下 + ShieldCheck 图标）
   - `Sidebar.tsx` - 侧边栏 280px（Skills / 历史 双 tab + slide-right 动画）
   - `StatusBar.tsx` - 底部状态栏 28px（LLM 状态点 + kbd 标签）

3. **App.tsx 完全重写**（从 450 行单文件 → 240 行 + 10 个组件）
   - 导入 10 个子组件，组合成完整应用
   - Agent 模式支持：判断 `res.text || res.tool_calls` 区分 Agent / 规则模式
   - 监听 Tauri 事件：backend-ready / new-chat / open-history
   - Esc 键行为：有确认弹窗→取消；无→隐藏窗口
   - 布局：TitleBar(48px) + [MessageList/WelcomeScreen + Sidebar](flex-1) + InputBar(auto) + StatusBar(28px)

4. **Tauri 单窗口架构**（`desktop/src-tauri/src/lib.rs` 完全重写）
   - 移除 bubble 浮动小球窗口（用户反馈「小球不太需要，托盘可以替代」）
   - 主窗口 720×640（maxWidth/maxHeight 限制）
   - 托盘菜单重新设计：状态行（禁用）+ 显示/新对话 + 分隔 + 设置/历史/审计 + 分隔 + 关于/退出
   - 新增菜单事件 emit 到前端：new-chat / settings / history / audit
   - `APP_VERSION = "0.7.0-alpha"` 常量
   - `toggle_main_window` 移除 `win.center()`（保持位置不变）

5. **API 类型扩展**（`desktop/src/api.ts` + `desktop/src/types.ts`）
   - 新增 `ToolCall` 接口（tool_name / arguments / success / result_message / error / details）
   - `ChatResponse` 新增 `text?` 和 `tool_calls?` 字段（Agent 模式）
   - 新增 `chatRule()` 方法（规则模式兜底端点 /api/chat/rule）
   - `Message` 接口新增 text / tool_calls / isAgent / error 字段

6. **删除文件**（3 个）
   - `desktop/src/Bubble.tsx` - 浮动小球组件
   - `desktop/src/bubble-entry.tsx` - 浮球 React 入口
   - `desktop/bubble.html` - 浮球 HTML 入口

**视觉细节精修（24 处）**：

- WelcomeScreen：logo 圆角 18px（rounded-xl）+ 欢迎语 text-2xl（28px）+ 快捷动作 max-w-480px + Sparkles 图标 + label/hint 双行
- MessageBubble：用户消息 bg-accent/25（更明显）+ 助手消息 max-w-92%（呼吸空间）+ padding 统一 px-4 py-2.5
- InputBar：pl-3 pr-1.5（按钮侧更窄）+ text-base（避免过大）+ hover:shadow-md
- ToolCallCard：折叠文案「调用了 N 个工具」（修正「查看了」语义错）+ detail bg-bg-tertiary/40（深一阶）+ 状态图标 15px
- ConfirmSheet：ShieldCheck 用 accent-soft 绿色底（非橙色警示）+ autoFocus 在取消按钮（防误确认）+ max-w-lg
- Sidebar：去 font-mono（中文不用等宽）+ animate-slide-right + bg-secondary/70 backdrop-blur-xl
- StatusBar：状态点 w-2 h-2（8px，更显眼）+ kbd 标签带边框 + 圆角 + bg-secondary/60
- TitleBar：标题 font-medium（不 semibold，更克制）+ 底部分隔线 border-default（更可见）
- App.tsx：外层 p-3（更宽松）+ 窗口边框 border-default
- index.css：滚动条选择器修复（`*:hover > ::-webkit-scrollbar-thumb` 语法错误）
- tailwind.config.js：新增 slide-right keyframes + animation

**实测验证**：
- `lihua 0.7.0a0` + 89 skills + 539 pytest 全通过
- TypeScript 编译通过（tsc -b）
- Vite 构建通过（170KB JS / 19.5KB CSS gzip 后 54KB / 5KB）
- Rust cargo build --release 通过（18.8s）
- Tauri dev 模式启动成功，HMR 热重载所有改动
- 浏览器截图验证：欢迎屏 + 侧边栏 + 输入栏 + 状态栏 全部正常渲染
- DOM 快照验证：10 个组件元素结构完整

**版本号升级**：pyproject.toml + __init__.py + package.json + Cargo.toml 全部 0.7.0a0

**已知问题**：
- GNOME Wayland 下窗口无法透明（牺牲真透明，保视觉层次，见 traps T022）
- 全局快捷键 Ctrl+Alt+L 在 GNOME Wayland 下不工作（见 traps T020）
- 截图工具在当前环境受限（无法精确读取像素颜色，但 DOM 验证 + 估算颜色符合设计目标）

---

### v0.6.0-alpha (2026-07-19)

架构大重构：从"规则优先 + LLM 增强"改为"LLM Agent 主导 + 工具调用 + 规则兜底"。LLM 真正成为智能助手，不再是别名表查不到时的兜底。

**核心改动**：

1. **新增 `src/lihua/tool_defs.py`**：把 89 个 Skill YAML 自动转成 OpenAI function calling 格式的工具定义
   - `skill_to_tool(skill)` 单个 skill → tool
   - `build_tool_defs(registry)` 整个 registry → tool 列表
   - `build_tool_index(registry)` tool name → SkillDef 映射
   - `build_skill_catalog_for_prompt(registry)` 紧凑格式的 skill 索引（给系统 prompt 用）
   - tool description 含 skill 描述 + 触发场景 + 示例，便于 LLM 选择

2. **新增 `src/lihua/agent.py`**：LLM Agent 主循环
   - `run_agent(user_text, cfg, registry, confirm, on_progress, dry_run, max_iterations)` 主入口
   - 系统 prompt 含 skill 索引 + 使用指南 + 安全规则
   - 主循环：用户输入 → LLM 决策 tool_calls → 执行 skill → 结果回传 LLM → LLM 总结反馈
   - 支持多轮对话（LLM 可以追问澄清）
   - 支持组合任务（LLM 可以连续调多个工具）
   - 安全：skill 执行时仍走 safety.py（黑名单 ban / 灰名单 confirm）
   - max_iterations 防止 LLM 死循环（默认 8 轮）
   - `AgentResponse` 含最终文本 + 所有 tool_calls 记录 + 完整对话历史

3. **扩展 `src/lihua/router.py`**：
   - 新增 `call_llm_with_tools(cfg, messages, tools, tool_choice)` 函数
   - 新增 `_call_openai_compat_with_tools()` urllib 实现（支持 function calling）
   - `LLMResponse` 新增 `tool_calls` 和 `finish_reason` 字段
   - `LLMResponse.has_tool_calls` / `LLMResponse.ok` 属性

4. **改造 `src/lihua/cli.py`**：
   - `run` 命令默认走 LLM Agent 模式
   - 新增 `--rule` 选项强制走规则匹配模式（离线/调试用）
   - `chat` 命令同样默认 Agent，支持 `--rule`
   - Agent 模式下打印工具调用过程 + 最终回复（Panel 卡片）

5. **改造 `src/lihua/server.py`**：
   - `/api/chat` 默认走 LLM Agent 模式
   - 新增 `/api/chat/rule` 端点保留规则模式（离线兜底）
   - `ChatResponse` 新增 `text` 和 `tool_calls` 字段（兼容旧前端的 `intent` / `result`）

6. **保留 `src/lihua/intent.py`**：规则匹配作为离线兜底，无 LLM 或 `--rule` 时使用

**Agent 工作流程**：
```
用户："电脑怎么这么卡啊"
  ↓
[Agent] LLM 看工具列表（89 个 skill 自动转 tool 定义）
  ↓ LLM 理解意图，决定调用 troubleshoot_slow_system
[skill_runner] 执行诊断步骤（YAML 不变）
  ↓ 结果回传
[Agent] LLM 用中文总结："慢是因为 XX，建议 YY"
  ↓
[反馈] 自然语言 + 主动追问澄清 + 建议相关工具
```

**双轨模式**：
- 有 LLM → Agent 主导（智能对话 + 工具调用 + 多轮）
- 无 LLM 或 `--rule` → 规则匹配（离线可用）

**实测验证**：
- `lihua --version` → `lihua 0.6.0a0`
- `lihua "看下 CPU 使用情况" --dry-run` → LLM 调用 cpu_monitor 工具，给出 CPU 信息表格 + 主动建议相关工具
- `lihua "电脑怎么这么卡啊" --dry-run` → 规则模式下会失败（"卡"不是任何 trigger），Agent 模式下 LLM 理解意图，给出完整诊断建议 + 主动追问"一直卡还是偶尔卡？"
- 539 个 pytest 全通过（新增 34 个：test_agent.py 16 个 + test_tool_defs.py 18 个）
- `lihua skills list` → 89 个内置 Skill 全部加载

**版本号升级**：pyproject.toml + __init__.py + package.json 全部 0.6.0a0

**已知问题**：
- 规则模式仍保留作为离线兜底（见 traps T029）
- LLM Agent 模式每次都要调 LLM（成本 + 延迟），未来可考虑缓存常见意图
- 系统 prompt 含 89 个 skill 索引，token 数较多（约 5K tokens），未来可考虑分段加载

### v0.5.0-alpha (2026-07-19)

Skill 库大扩展：从 v0.4.2 的 61 个 Skill 扩展到 89 个（新增 40 个，分 6 组），覆盖"Linux 新手能遇到的坑"全场景。配套扩展安全引擎与测试。

**新增 Skill（40 个，按 6 组分类）**：

组 A：新手救急诊断类（8 个，文件名 `troubleshoot-*.yaml`）：
- `troubleshoot_no_sound` 没声音诊断（ALSA / PulseAudio / PipeWire / 内核声卡，可重启 pipewire）
- `troubleshoot_no_wifi` 连不上 WiFi 诊断（网卡 / rfkill / NetworkManager / 驱动 / 日志）
- `troubleshoot_no_internet` 没网诊断（网卡 / 网关 / DNS / HTTP / 路由）
- `troubleshoot_disk_full` 磁盘满诊断（df / 大目录 / 大文件 / 日志 / 缓存，可清理）
- `troubleshoot_memory_high` 内存高诊断（free / top 进程 / swap / OOM，可 drop_caches）
- `troubleshoot_cpu_high` CPU 高诊断（top / mpstat / 负载 / 温度 / 频率）
- `troubleshoot_app_crash` 应用崩溃诊断（pgrep / journal / coredump / 依赖，含 app 参数）
- `troubleshoot_slow_system` 系统慢诊断（负载 / CPU+内存 / IO / 启动项 / 启动时间）

组 B：软件源镜像类（5 个）：
- `mirror_source` 切换国内镜像源（清华 / 中科大 / 阿里 / 华为 / 腾讯，兼容 Ubuntu 24.04 `ubuntu.sources` 新格式）
- `apt_repository` apt 仓库管理（add-apt-repository 添加 / 删除 / 查看）
- `ppa_management` PPA 管理（添加 / 删除 / purge，自动剥离 `ppa:` 前缀）
- `flatpak_remote` Flatpak 远程仓库管理（flathub 一键添加 / 自定义 / 删除）
- `snap_channel` Snap 通道管理（查看 / 切换 stable/candidate/beta/edge + refresh）

组 C：文件管理高级类（7 个）：
- `file_backup` 文件备份（rsync 增量同步）
- `file_encrypt` 文件加密 / 解密（gpg 对称加密）
- `file_shred` 安全删除（shred 覆写 3 次）
- `disk_mount` 挂载 / 卸载磁盘分区
- `usb_bootable` 制作 USB 启动盘（dd 写入 ISO，高风险）
- `file_convert_pdf` 文档转 PDF（libreoffice）
- `image_convert` 图片格式转换（ImageMagick）

组 D：多媒体+开发环境类（7 个）：
- `video_convert` 视频格式转换（ffmpeg）
- `screen_record` 屏幕录制（X11 ffmpeg + Wayland wf-recorder）
- `pdf_merge_split` PDF 合并 / 拆分（pdfunite / pdfseparate）
- `git_config` Git 配置管理（查看 / 用户名 / 邮箱 / 初始化）
- `docker_run` Docker 容器管理（查看 / 拉取 / 运行 / 停止）
- `python_venv` Python 虚拟环境（创建 / 激活 / 退出 / 查看）
- `ssh_key` SSH 密钥管理（生成 ed25519 / 查看 / 拷贝到主机）

组 E：网络+系统高级类（7 个）：
- `vpn_connect` VPN 连接管理（OpenVPN / WireGuard）
- `ssh_connect` SSH 远程连接
- `hotspot_create` WiFi 热点创建 / 关闭（nmcli）
- `share_folder` Samba 文件共享（安装 / 创建 / 查看）
- `kernel_management` 内核管理（查看 / 切换 / 清理旧内核）
- `cron_job` 定时任务管理（cron 添加 / 查看 / 编辑 / 删除）
- `log_view` 日志查看（系统 / 内核 / 启动 / 服务 / 应用 / 错误）

组 F：桌面+硬件类（6 个）：
- `gnome_extension` GNOME 扩展管理（查看 / 启用 / 禁用 / 安装提示）
- `clipboard_history` 剪贴板管理（查看 / 清空 / 安装 CopyQ）
- `gpu_driver` 显卡驱动管理（查看 GPU / 安装驱动 / 切换 PRIME）
- `keyboard_layout` 键盘布局（查看 / 切换）
- `touchpad_config` 触摸板配置（开关 / 轻触点击）
- `virus_scan` 病毒扫描（ClamAV 安装 / 更新 / 扫描）

**安全引擎扩展（safety.py）**：
- 新增黑名单 2 条：`shred /dev/sd*` 覆写整个磁盘、`sed -i /etc/(passwd|shadow|sudoers|fstab|grub)` 直接改关键系统文件
- 新增灰名单 20+ 条：rsync 实际同步、gpg 加解密、shred 安全删除、git config --global、docker 容器操作、python venv 创建、ssh-keygen / ssh-copy-id、wg-quick / openvpn、nmcli 热点、crontab -e/-r、freshclam、ubuntu-drivers autoinstall、prime-select 切换、apt autoremove --purge linux-、sed -i /etc/、add-apt-repository、flatpak remote-add/delete、snap switch/refresh
- 新增白名单 50+ 条：rsync --version / --dry-run / -avn、gpg --list-keys / -k、wg show、docker ps/images/logs/stats/version/info、coredumpctl list/info、clamscan -r（不含 --remove）、ubuntu-drivers list/devices、prime-select --query、systemd-analyze blame/critical-chain/time、localectl list-x11-keymap-layouts、setxkbmap -query、smbstatus / smbclient / testparm、iotop、ssh-keygen -l/-y、pdfunite / pdfseparate 等
- 关键技巧：用负向先行断言（negative lookahead）区分查询命令和修改命令
  - `rsync\s+(?!.*--dry-run)(?!.*--version)(?!.*-avn)` 排除查询 / 模拟
  - `ssh-keygen\s+(?!-l\b)(?!-y\b)(?!--help\b)` 排除查看指纹 / 导出公钥
  - `prime-select\s+(?!-?-query\b)\S+` 排除查询当前显卡

**测试扩展**：
- 新增 207 个测试（298 → 505）：
  - `tests/test_safety.py::TestV050NewRules` 新增 81 个测试（4 黑 + 30 灰 + 47 白 + 2 边界）
  - `tests/test_skills_troubleshoot.py` 21 个测试（组 A）
  - `tests/test_skills_mirror.py` 33 个测试（组 B）
  - `tests/test_skills_file_adv.py` 14 个测试（组 C）
  - `tests/test_skills_media_dev.py` 21 个测试（组 D）
  - `tests/test_skills_network_sys.py` 19 个测试（组 E）
  - `tests/test_skills_desktop_hw.py` 18 个测试（组 F）
- 全量 505 个 pytest 全通过

**Trigger 冲突处理（自动消歧）**：
- `troubleshoot_disk_full` 的 "磁盘满了" 与 `disk_usage` 的 "磁盘" 完全重叠 → 用 aliases 技巧让 disk_full 的 alias_hit=1 > 0
- `troubleshoot_cpu_high` 的 "cpu占用高" 与 `cpu_monitor` 的 "cpu" 子串重叠 → 同上 aliases 技巧
- `disk_mount` 的 "卸载" 与 `uninstall_app` 的 "卸载" → trigger 长度 4>2
- `file_shred` 的 "安全删除" 与 `uninstall_app` 的 "删除" → trigger 长度 4>2
- `image_convert` 的 "缩放图片" 与 `screen_display` 的 "缩放" → trigger 长度 4>2
- `gpu_driver` 的 "看显卡" 与 `hardware_info` 的 "显卡" → trigger 长度 4>3
- `touchpad_config` 的 "关闭触摸板" 与 `close_app` 的 "关闭" → trigger 长度 5>2
- `hotspot_create` 的 "开热点" 与 `open_app` 的 "开" → trigger 长度 3>1
- `ppa_management.yaml` description 含 `ppa:` 冒号+空格导致 YAML 解析错误 → 用双引号包裹修复（见 traps.md T024）
- 提取正则 `\s+` 不适配中文无空格场景 → 改为 `\s*`（见 traps.md T025）

**实测验证**：
- `lihua --version` → `lihua 0.5.0a0`
- `lihua skills list` → 89 个内置 Skill 全部加载
- 505 个 pytest 全通过

**版本号升级**：pyproject.toml + __init__.py + package.json + Cargo.toml + tauri.conf.json 全部 0.5.0a0

**已知问题**：
- 全局快捷键 Ctrl+Alt+L 在 GNOME Wayland 下仍不工作 — 见 traps.md T020
- 浮动小球位置由 GNOME 决定 — 见 traps.md T021
- 透明窗口在 GNOME Wayland 下不显示 — 见 traps.md T022
- YAML description 含 `冒号+空格` 会被解析为 mapping — 见 traps.md T024
- 参数提取正则 `\s+` 在关键词与参数无空格相邻时失效 — 见 traps.md T025
- safety 灰名单正则未排除查询命令导致 rsync --version / ssh-keygen -l 误判 grey — 见 traps.md T026
- safety 黑名单 shred 正则无法匹配带参数的 flag 如 `-n 3` — 见 traps.md T027
- safety 白名单 `\s+$` 要求至少一个空白字符导致 `systemd-analyze` 无参数时 unknown — 见 traps.md T028
- 并行 subagent 开发时多个 subagent 修改同一文档导致版本号冲突 — 见 traps.md T029

### v0.4.2-alpha (2026-07-19)

软件源 / 镜像类 Skill 扩展。新增 5 个 apt / flatpak / snap / ppa 源管理 Skill。

**新增 Skill（5 个，软件源镜像类）**：
- `mirror_source` 切换国内镜像源（清华 / 中科大 / 阿里 / 华为 / 腾讯，兼容 Ubuntu 24.04 `ubuntu.sources` 新格式，含备份与官方源恢复）
- `apt_repository` apt 仓库管理（add-apt-repository 添加 / 删除 / 查看）
- `ppa_management` PPA 管理（添加 / 删除 / purge，命令自动剥离 `ppa:` 前缀避免重复）
- `flatpak_remote` Flatpak 远程仓库管理（flathub 一键添加 / 自定义 remote / 删除）
- `snap_channel` Snap 通道管理（查看 / 切换 stable/candidate/beta/edge 通道 + refresh）

**测试**：
- 新增 `tests/test_skills_mirror.py`（33 个测试：5 个加载 + 6 个意图匹配 + 6 个镜像变体提取 + 11 个步骤 / 参数结构 + 5 个 trigger 冲突防护）
- 全量 pytest 403 个测试通过（含新增 33 个），未破坏任何已有测试

**Trigger 冲突处理**：
- `mirror_source` 的 "apt源"（3 字符）与 `apt_repository` 的 "apt源管理"（5 字符）重叠：依赖"命中最长 trigger 优先"策略，"apt源管理" 优先匹配 apt_repository；裸 "apt源" / "换源" 匹配 mirror_source
- `apt_repository` 不使用裸 "添加源" trigger（任务提示可能与 mirror_source 冲突），改用更具体的 "添加仓库"
- `flatpak_remote` 不使用裸 "flathub" trigger（任务提示已被 install_app 占用，实际只在注释中），改用复合 "添加flathub" trigger，配合 nospace 匹配命中 "添加 flathub"
- `ppa_management` 的 "ppa"（3 字符）与 `apt_repository` 的 "添加仓库"（4 字符）在 "添加仓库 ppa:obsproject/obs-studio" 上重叠：最长匹配策略使 apt_repository 胜出；裸 "添加 ppa:..." 仅命中 ppa_management
- `snap_channel` 的 "切换snap"（nospace，5 字符）与 `install_snap` 的 "装 snap" 等不重叠（动词不同），"切换 snap firefox 通道 beta" 仅匹配 snap_channel
- `uninstall_app` 的 "删除"（2 字符）/ "移除"（2 字符）与 `apt_repository` 的 "删除仓库"（4 字符）/ `flatpak_remote` 的 "删除flatpak仓库"（7 字符）重叠：最长匹配策略使新 Skill 胜出

**condition 语法注意**：
- `eval_condition` 不支持括号 `()`，`||` 优先级低于 `&&`。表达 `(A || B) && C` 需展开为 `A && C || B && C`（如 apt_repository 的 remove_repo、flatpak_remote 的 add_flathub）

**已知问题**：
- 全局快捷键 Ctrl+Alt+L 在 GNOME Wayland 下仍不工作 — 见 traps.md T020
- 浮动小球位置由 GNOME 决定 — 见 traps.md T021
- 透明窗口在 GNOME Wayland 下不显示 — 见 traps.md T022
- YAML description 含 `冒号+空格` 会被解析为 mapping — 见 traps.md T024
- 参数提取正则 `\s+` 在关键词与参数无空格相邻时失效 — 见 traps.md T025

### v0.4.1-alpha (2026-07-19)

文件管理高级类 Skill 扩展。新增 7 个文件 / 磁盘高级操作 Skill。

**新增 Skill（7 个，文件管理高级类）**：
- `file_backup` 文件备份（rsync 增量同步，保留权限和软链接）
- `file_encrypt` 文件加密 / 解密（gpg 对称加密，加密后保留原文件由用户自行删除）
- `file_shred` 安全删除（shred 覆写 3 次后删除，不可恢复，confirm 中明确警告）
- `disk_mount` 挂载 / 卸载磁盘分区（mount / umount，含 lsblk 设备列表）
- `usb_bootable` 制作 USB 启动盘（dd 写入 ISO，高风险，confirm 中明确警告不可恢复）
- `file_convert_pdf` 文档转 PDF（libreoffice --headless，支持 doc/docx/ppt/pptx/xls/xlsx/odt/md）
- `image_convert` 图片格式转换（ImageMagick convert，支持 png/jpg/jpeg/webp/bmp/tiff/gif）

**测试**：
- 新增 `tests/test_skills_file_adv.py`（14 个测试：7 个加载 + 7 个意图匹配）
- 全量 pytest 351 个测试通过（含新增 14 个），未破坏任何已有测试

**Trigger 冲突处理**：
- `disk_mount` 的 "卸载" trigger 与 `uninstall_app` 的 "卸载" trigger 重叠：依赖"命中最长 trigger 优先"策略，"卸载磁盘 /dev/sdb1" 优先匹配 disk_mount（4 字符 > 2 字符）；"卸载 firefox" 优先匹配 uninstall_app（别名表命中 alias_hit=1 > 0）
- `file_shred` 的 "安全删除" trigger 与 `uninstall_app` 的 "删除" trigger 重叠：同上策略，"安全删除"（4 字符）> "删除"（2 字符）
- `image_convert` 的 "缩放图片" trigger 与 `screen_display` 的 "缩放" trigger 重叠：同上策略，"缩放图片"（4 字符）> "缩放"（2 字符）
- 未与 `file_compress`（压缩/打包）、`file_extract`（解压/提取）触发词冲突

**安全引擎适配**：
- `usb_bootable` 的 `dd if=... of=/dev/sd...` 命令：因模板渲染后 `of='/dev/sdb'` 带引号，黑名单 `dd\s+of=/dev/sd` 正则不匹配（要求 `=` 后直接是 `/`），命中灰名单 `\bdd\b\s+if=` → grey，配合 YAML `safety: grey` + confirm 警告，走灰名单确认流程
- `file_shred` / `file_backup` / `file_encrypt` 的 shred/rsync/gpg 命令不在安全名单 → unknown，YAML `safety: grey` 提升为 grey，走确认流程
- `file_convert_pdf` 的 libreoffice 命令在白名单，但 YAML `safety: grey` 优先（取更严格一方），仍走确认流程

**参数提取正则改进**：
- `file_backup` source 提取：任务原给 `"备份\s+(.+?)\s+到"` 会捕获 "文件 /home/user/docs"（含 "文件 " 前缀），改进为 `"(?:备份|同步备份|备份一下|rsync备份)\s+(?:文件\s+|目录\s+|文件夹\s+)?(.+?)\s+到"` 正确去除前缀
- `image_convert` file 提取：任务原给 `"(?:转|转换|缩放|调整).*?(?:图片|图片大小)?.*?(.+?\.jpg)"` 对 "转png image.jpg" 会捕获 "png image.jpg"（含 "png " 前缀），改进为 `"(\S+\.(?:png|jpg|jpeg|webp|bmp|tiff|gif))\s*$"` 用 `\S+` 限定非空白字符，正确捕获 "image.jpg"
- `file_convert_pdf` file 提取：同样改为 `"(\S+\.(?:doc|docx|ppt|pptx|xls|xlsx|odt|md))\s*$"`
- `file_encrypt` 解密命令：任务原给 `gpg -d '{{file}}.gpg' > '{{file}}'` 假设用户输入不带 .gpg 后缀，改进为 `F='{{file}}' ; OUT="${F%.gpg}" ; gpg -d "$F" > "$OUT"` 用 shell 参数展开自动去 .gpg 后缀，更鲁棒

**已知问题**：
- 全局快捷键 Ctrl+Alt+L 在 GNOME Wayland 下仍不工作 — 见 traps.md T020
- 浮动小球位置由 GNOME 决定 — 见 traps.md T021
- 透明窗口在 GNOME Wayland 下不显示 — 见 traps.md T022

### v0.4.0-alpha (2026-07-19)

Skill 库大扩展 + 引擎升级。围绕"Linux 新手会遇到的坑"补全 49 个内置 Skill。

**新增 Skill（31 个，按类别）**：

系统管理类（10 个）：
- `system_update` 系统更新（apt + flatpak + snap 一键全更新）
- `system_info` 系统信息（lsb_release + uname + hostnamectl + lscpu + free + df + uptime）
- `power_management` 电源管理（关机 / 重启 / 休眠 / 待机 / 锁屏）
- `service_manager` 服务管理（status / start / stop / restart / enable / disable）
- `disk_usage` 磁盘占用（df + du top 20）
- `cleanup_residual` 清理残留（autoremove + clean + dpkg purge rc + flatpak unused + journal vacuum + thumbnail）
- `user_password` 修改密码（passwd / sudo passwd）
- `timezone` 设置时区（timedatectl set-timezone，含中文别名表）
- `locale` 设置语言环境（locale-gen + update-locale，含中文别名表）
- `startup_apps` 启动项管理（list / add / remove autostart .desktop）

文件操作类（5 个）：
- `file_extract` 解压文件（zip / tar.gz / tar.bz2 / tar.xz / tar / 7z / rar）
- `file_compress` 压缩文件（zip / tar.gz / tar.bz2 / 7z）
- `file_search` 搜索文件（find + locate + grep）
- `file_permission` 文件权限（chmod / chown）
- `file_association` 文件关联（xdg-mime default）

网络类（5 个）：
- `network_info` 网络信息（ip addr + route + DNS + WiFi + 公网IP + nmcli）
- `firewall` 防火墙管理（ufw status / enable / disable / allow / deny）
- `wifi_connect` WiFi 连接（scan + connect with/without password）
- `network_test` 网络测试（ping / traceroute / DNS / HTTP / 综合检测）
- `proxy_setting` 代理设置（gsettings proxy mode manual/none）

硬件外设类（5 个）：
- `hardware_info` 硬件信息（CPU / 内存 / 磁盘 / GPU / 网卡 / USB / PCI / 主板 / 序列号）
- `bluetooth` 蓝牙管理（list / connect / disconnect / pair / trust / remove / on / off）
- `printer` 打印机管理（list / add / remove / default / test / queue）
- `screen_display` 屏幕显示（分辨率 / 刷新率 / 亮度 / 缩放 / 多屏 / 镜像）
- `audio_control` 音频控制（音量 / 静音 / 麦克风 / 输入输出设备 / 播放控制）

桌面环境类（5 个）：
- `screenshot` 截图（全屏 / 区域 / 窗口 / 延时，GNOME/Wayland/X11 全兼容）
- `night_light` 夜灯 / 护眼模式（色温调节）
- `change_wallpaper` 更换壁纸（GNOME + Sway）
- `change_theme` 切换主题（深色 / 浅色 / 强调色 / 图标主题）
- `desktop_icon` 桌面图标（显示 / 隐藏 / 状态，支持 ding / desktop-icons 扩展）

软件安装增强类（5 个）：
- `install_deb` 安装本地 .deb 包（apt install + 依赖修复）
- `install_appimage` 安装 AppImage（集成到应用菜单 + 提取图标）
- `install_snap` 通过 Snap 安装应用
- `install_dev_tools` 安装开发工具链（Python / Node / Go / Rust / Java / C / Docker / 数据库）
- `cleanup_apt` 清理 apt 缓存（autoclean + clean + autoremove）

应用操作类（4 个）：
- `open_app` 打开应用（支持 flatpak ID / 命令名 / desktop 文件 / 中文别名）
- `close_app` 关闭应用（先 SIGTERM 再 SIGKILL）
- `list_apps` 列出应用（apt / flatpak / snap / 应用菜单）
- `default_apps` 默认应用管理（浏览器 / 编辑器 / 播放器 / 邮件 / 终端 / 图片）

进程与性能类（5 个）：
- `process_manager` 进程管理（查看 / 排序 / 按名查找 / 资源总览）
- `kill_process` 终止进程（按 PID / 名称 / 端口）
- `cpu_monitor` CPU 监控（使用率 / 负载 / 频率 / 核心数 / 温度）
- `memory_monitor` 内存监控（使用率 / swap / 占用最高的进程 / OOM 计分）
- `battery` 电池管理（电量 / 状态 / 健康度 / 省电 / 平衡 / 性能模式）

**引擎升级**：
- `skill_runner.py`：
  - `render_template` 支持 `{{var|default:value}}` 默认值语法（变量未定义或为空字符串时使用默认值）
  - `eval_condition` 支持 `&&` 和 `||` 复合条件（优先级：&& 高于 ||）
  - 修复 `_ATOM_CONDITION_RE` 的 rhs 用 `(.+)` 导致 `"{{var}} != "` 末尾无字符时不匹配的 bug（改为 `(.*)`）
- `skills.py`：
  - `match_trigger` 对纯英文 trigger 加单词边界匹配（避免 `du` 误匹配 `baidu`、`df` 误匹配 `pdf`）
  - `match_by_text` 优先级排序改为"命中的最长 trigger"（原为"所有 trigger 中最长"），解决 "装 deb" 误匹配 install_app
- `safety.py`：
  - 黑白灰名单大幅扩展（新增 80+ 条规则），覆盖新增 Skill 的所有命令分类
  - `passwd` 规则改为 `(?:^|sudo\s+)passwd\b` 避免误匹配 `/etc/passwd` 文件参数
  - `shutdown` / `reboot` / `halt` / `poweroff` 从黑名单移到灰名单（允许用户确认后执行）
  - 新增灰名单：`ufw` / `iptables` / `nft` / `nmcli connection delete` / `hostnamectl set-hostname` / `bluetoothctl connect` / `rfkill block` / `dpkg-reconfigure` / `apt-mark hold` / `update-alternatives --set` / `xrandr --output --off` / `modprobe` / `sysctl -w` / `swapon` / `swapoff` / `fstrim` / `chmod 系统目录` / `chown 系统目录` / `tee 系统文件` 等
  - 新增白名单：`timedatectl status` / `locale` / `hostnamectl` / `systemctl status` / `journalctl` / `dmidecode` / `lshw` / `lscpu` / `lsblk` / `lsmod` / `lspci` / `lsusb` / `iwconfig` / `nmcli show` / `ss` / `netstat` / `nmap` / `traceroute` / `mtr` / `sensors` / `htop` / `btop` / `vmstat` / `iostat` / `sar` / `lsof` / `pactl list` / `wpctl status` / `lpstat` / `xinput list` / `xrandr --listmonitors` / `hyprctl monitors` / `swaymsg get_outputs` / `bluetoothctl list` / `rfkill list` 等

**测试升级**：
- 新增 109 个测试（189 → 298），覆盖：
  - 44 个新 Skill 的加载与触发（`test_skill_loaded` + `test_intent_match`）
  - 英文 trigger 单词边界匹配（`TestTriggerWordBoundary`）
  - `render_template` default 过滤器（`TestRenderTemplateDefault`）
  - `eval_condition` 复合条件 && / ||（`TestEvalConditionCompound`）
  - Skill 优先级排序（`TestSkillPriority`）
- 修复 `test_safety.py` 中 4 个 shutdown/reboot/halt/poweroff 用例（从黑名单测试移到灰名单测试）

**实测验证**：
- `lihua --version` → `lihua 0.4.0a0`
- `lihua skills list` → 49 个内置 Skill 全部加载
- `lihua "看硬件" --dry-run` → hardware_info ✓
- `lihua "ping baidu.com" --dry-run` → network_test ✓（不再误匹配 disk_usage）
- `lihua "调音量 50%" --dry-run` → audio_control ✓
- `lihua "切深色模式" --dry-run` → change_theme ✓
- `lihua "查看蓝牙" --dry-run` → bluetooth ✓
- `lihua "看电量" --dry-run` → battery ✓
- `lihua "截全屏" --dry-run` → screenshot ✓
- `lihua "杀进程 nginx" --dry-run` → kill_process ✓
- `lihua "默认浏览器 firefox" --dry-run` → default_apps ✓（不再误匹配 file_association）
- `lihua "装 deb /tmp/x.deb" --dry-run` → install_deb ✓（不再误匹配 install_app）
- `lihua "清理 apt 缓存" --dry-run` → cleanup_apt ✓（不再误匹配 cleanup_residual）
- 298 个 pytest 全通过

**版本号升级**：pyproject.toml + __init__.py + package.json + Cargo.toml + tauri.conf.json 全部 0.4.0a0

**已知问题**：
- 全局快捷键 Ctrl+Alt+L 在 GNOME Wayland 下仍不工作 — 见 traps.md T020
- 浮动小球位置由 GNOME 决定 — 见 traps.md T021
- 透明窗口在 GNOME Wayland 下不显示 — 见 traps.md T022

### v0.3.0-alpha (2026-07-19)

Tauri 桌面应用版本，真正的系统浮窗（不再是浏览器）。

**新增**：
- `desktop/src-tauri/` Tauri 2.0 Rust 主进程（Rust 1.93 + tauri 2.11）
  - 系统托盘 🐱 图标（libayatana-appindicator，GNOME ubuntu-appindicators 扩展支持）
  - 托盘菜单：显示主窗口 / 隐藏主窗口 / 关于 / 退出
  - 托盘左键点击切换主窗口可见性
  - 多窗口：主浮窗（760×800，默认显示，居中）+ 桌面浮动小球（96×96，置顶）
  - Python sidecar：Tauri 主进程内嵌启动 uvicorn（端口 7531），用 `std::process::Command`
  - 端口就绪检测（`std::net::TcpStream` 轮询，超时 20s）
  - 全局快捷键 Ctrl+Alt+L（注册成功，但 Wayland 下不工作 — 见 traps.md T020）
  - Tauri 命令：`cmd_toggle_main` / `cmd_show_main` / `cmd_hide_main` / `cmd_quit` / `backend_url`
  - 主窗口关闭按钮改为隐藏（不退出），通过 `on_window_event` 拦截 CloseRequested
  - tauri-plugin-log 统一日志（写入 `~/.local/share/cn.lihua.desktop/logs/Lihua.log`）
- `desktop/src/Bubble.tsx` 桌面浮动小球组件
  - 96×96 圆角深色方块 + 中心 72×72 绿色渐变圆形 🐱
  - 整个区域 `data-tauri-drag-region` 可拖动
  - 单击调用 `cmd_show_main` 显示主窗口
  - hover 放大 + pulse 动画
- `desktop/src/App.tsx` 主浮窗改造
  - 顶部可拖动标题栏（🐱 + 标题 + 侧边栏按钮 + 最小化/关闭按钮）
  - 关闭按钮调用 `cmd_hide_main` 隐藏到托盘（不退出）
  - 添加 `import { invoke } from '@tauri-apps/api/core'`
- `desktop/src/api.ts` 改为绝对 URL `http://127.0.0.1:7531`（Tauri build 模式 file:// 协议不支持相对路径）
- `desktop/src/types.ts` 改为 re-export `api.ts` 的类型，避免双源不一致
- `desktop/vite.config.ts` 多入口构建（main + bubble）
- `desktop/bubble.html` + `desktop/src/bubble-entry.tsx` 浮动小球入口
- `desktop/src-tauri/tauri.conf.json` 两窗口配置
- `desktop/src-tauri/capabilities/default.json` 权限配置（main + bubble 窗口）
- `desktop/src-tauri/Cargo.toml` Rust 依赖（tauri 2 + tray-icon + global-shortcut + notification + log + shell）
- `lihua gui` 命令完全重写：
  - 不再启动浏览器，直接启动 Tauri 二进制
  - `--build` 选项：用 `npx tauri build --no-bundle` 编译（嵌入前端资源）
  - `--dev` 选项：用 `npx tauri dev` 开发模式（热重载）
  - `--foreground` 选项：前台运行（看日志）
  - 默认后台运行：`systemd-run --user --unit=lihua-desktop`（脱离 sandbox，不被清理）
  - 回退方案：`subprocess.Popen + start_new_session=True`（nohup 风格）
  - 进程检测：`pgrep -f lihua-desktop` 防止重复启动
- 版本号升级：pyproject.toml + __init__.py + package.json + Cargo.toml + tauri.conf.json 全部 0.3.0a0

**实测验证**：
- `lihua --version` → `lihua 0.3.0a0`
- `lihua gui` 后台启动 Tauri 应用（PID 稳定运行）
- `curl /api/health` → `{"ok":true,"version":"0.3.0a0","llm_available":true,...}`
- 系统托盘 🐱 图标可见
- 主浮窗正常显示（不再 "Could not connect to localhost"）
- 浮动小球可见（96×96 圆角方块 + 绿色圆形 🐱）
- 小球点击 → 主浮窗显示 ✓
- 托盘左键点击 → 主浮窗切换 ✓
- 小球可拖动到任意位置 ✓
- 输入"装QQ" → 灰名单确认弹窗 ✓
- 157 个 pytest 全通过

**已知问题**：
- 全局快捷键 Ctrl+Alt+L 在 GNOME Wayland 下不工作（Wayland 安全限制不允许应用全局监听键盘）— 见 traps.md T020
- 浮动小球窗口位置由 GNOME 决定（Wayland 不允许应用主动 set_position）— 见 traps.md T021
- 透明窗口在 GNOME Wayland 下不显示，bubble 窗口改为非透明 + 圆角方块 — 见 traps.md T022

**安装方式**：
- Python 端：venv + 软链（`~/.local/share/lihua/venv` + `~/.local/bin/lihua`）
- 桌面端：`desktop/src-tauri/target/release/lihua-desktop` 二进制（15.7 MB，前端资源已嵌入）
- 启动：`lihua gui`（后台）或 `lihua gui --foreground`（前台）
- 停止：`pkill -f lihua-desktop` 或 `systemctl --user stop lihua-desktop`

### v0.2.0-alpha (2026-07-19)

GUI 浮窗版本，端到端跑通。

**新增**：
- `desktop/` Vite + React 18 + TypeScript + Tailwind CSS 3 前端项目
- 浮窗 UI：760×90vh 居中暗色卡片，含输入框 / 对话流 / 进度卡片 / 灰名单确认弹窗 / 侧边栏（Skills+历史）
- `src/api.ts` API 封装：health / skills / parse / chat / history / audit
- `lihua gui` 命令：一键启动 FastAPI 后端（7531）+ Vite dev server（5173）+ 浏览器
  - 端口就绪检测、子进程优雅退出（SIGTERM→SIGKILL）、Ctrl+C 信号转发、atexit 兜底清理
  - 自动定位 desktop/ 目录（源码同级 / cwd / 用户 data 目录）
  - `--no-browser` / `--backend-port` / `--frontend-port` 选项
- 灰名单确认 GUI 流程：auto_confirm=false → 检测 needs_confirm+denied → 弹窗 → 用户确认 → auto_confirm=true 重发
- `skill_runner.py` 修复：YAML `safety` 字段优先于 `classify()`（取更严格一方），解决 flatpak install 被 `_WHITELIST` 误判 white 而不弹确认
- `install-app.yaml` flatpak 命令改为不指定 remote（用户系统有 flathub system+user 同名时不再报错）
- `install-app.yaml` QQ alias 修正：`com.tencent.qq` → `com.qq.QQ`（实际 flatpak ID）
- `install-app.yaml` install_via_flatpak 从 white 改为 grey（安装应用下载几百 MB 应让用户确认）
- 端口统一为 7531（serve / install systemd / vite proxy 一致）
- `__main__.py` `_KNOWN_SUBCOMMANDS` 加入 `gui`

**实测验证**：
- `lihua --version` → `lihua 0.2.0a0`
- `lihua gui` 自动启动后端 + 前端 + 浏览器，端口 7531/5173 双双就绪
- `curl /api/health` → `{"ok":true,"version":"0.2.0a0","llm_available":true,...}`
- 浏览器实测「装QQ」：
  - 用户气泡（绿色右侧）+ 助手气泡（灰色左侧）显示 skill=install_app/rule/80%
  - 步骤列表：resolve ✓ / install_via_flatpak ⊘ needs_confirm
  - 灰名单确认弹窗：「需要你的确认」+「安装 QQ（通过 Flatpak，会下载若干数据）」+ 确认/取消按钮
  - 点取消正常关闭，不执行 flatpak install
- 157 个 pytest 全通过

**安装方式**：venv + 软链（`~/.local/share/lihua/venv` + `~/.local/bin/lihua`），desktop/ 目录随源码部署

**已知问题**：
- 浏览器偶发 `[vite] server connection lost`（开发模式 HMR 重连，不影响功能）
- flatpak 多个同名 remote 仍是用户系统层面的配置问题，lihua 仅做命令层规避

### v0.1.0-alpha (2026-07-19)

首个可用版本，CLI 核心闭环跑通。

**新增**：
- 完整 Python 包结构（src layout + hatchling 构建）
- 9 个核心模块：`cli` / `config` / `safety` / `executor` / `skills` / `skill_runner` / `intent` / `router` / `server`
- 5 个 MVP Skill YAML：`install-app` / `uninstall-app` / `switch-im` / `install-font` / `clean-cache`
- 安全分层引擎：黑名单 21 条 / 灰名单 27 条 / 白名单 60+ 条
- 复合命令拆分 + 整体黑名单检测（解决 `curl|bash` 漏检）
- LLM 路由：urllib 兜底 OpenAI 兼容端点 + litellm 可选
- 意图理解：规则优先 + LLM 增强（双轨模式）
- Skill 优先级：alias 命中 > trigger 长度（解决"装个思源黑体"误匹配 install_app）
- FastAPI HTTP 服务（可选）+ systemd user service 模板
- 审计日志 + 历史记录
- 测试覆盖：157 个测试全通过（safety / skills / intent）

**实测验证**：
- `lihua doctor` 全绿（Python 3.14.4 / LLM 可用 / 5 Skill 加载 / 所有系统工具检测通过）
- `lihua "装QQ" --dry-run` 识别正确（install_app, target=QQ）
- `lihua "装个思源黑体" --dry-run` 识别正确（install_font, target=思源黑体）
- `lihua "切换到 fcitx5" --dry-run` LLM 增强成功（source=hybrid, confidence=0.90）
- `lihua "清一下垃圾" --dry-run` 识别正确（clean_cache, scope=all）
- `lihua "卸载 firefox" --dry-run` 识别正确（uninstall_app, target=firefox）

**安装方式**：venv + 软链（`~/.local/share/lihua/venv` + `~/.local/bin/lihua`）

**已知问题**：
- 无（开发中遇到的 10 个坑均已修复，见 traps.md T001-T010）

### v0.0.1-design (2026-07-19)
- 完成 PRD.md v0.1
- 完成 ARCHITECTURE.md v0.1
- 完成 README.md 项目入口
- 完成 SESSION_CONTEXT.md 会话交接文档（含 7 条历史踩坑提炼自 Linux 配置阶段）
- 删除空的 inputM 文件夹

### v0.0.0-init (2026-07-19)
- 项目立项
- 确定项目名 Lihua（狸花猫）
- 确定目录 /home/vitasguo/文档/SOLO/lihua
- 确定技术栈：Tauri 2.0 + React + Python sidecar + litellm
- 确定安全模型：黑 / 白 / 灰三层
- 确定差异化：中文原生 + Linux 桌面场景 + 傻瓜式交互

## 已知问题

- 全局快捷键 Ctrl+Alt+L 在 GNOME Wayland 下不工作（Wayland 安全模型不允许应用全局监听键盘）— 见 traps.md T020
- 浮动小球窗口位置由 GNOME Mutter 决定，无法主动 set_position — 见 traps.md T021
- 透明窗口在 GNOME Wayland 下不显示，bubble 改为非透明 + 圆角方块 — 见 traps.md T022
- 并行 subagent 开发时多个 subagent 修改同一文档（process.md / traps.md）会导致版本号冲突，需人工整理 — 见 traps.md T029

## 下一步

### v0.5.0-beta（短期）
1. 真机端到端测试 v0.5.0 新增的 40 个 Skill（含灰名单确认 + 实际命令执行）
2. 用户实机走查："没声音 / 没网 / 磁盘满 / 装显卡驱动 / 切换镜像源 / 制作 U 盘启动盘"等高频场景
3. 设置面板（配置 LLM / Skill 启用 / 历史记录清理 / 灰名单默认策略）
4. 全局快捷键 Super+Space 唤起浮窗（GNOME Shell 扩展或 DBus 接口）
5. 集成测试（mock LLM + mock subprocess）
6. 打 .deb 包（含 desktop/ 预构建产物 + systemd service）

### v0.6.0+
- 多发行版适配（Fedora / Arch：dnf / pacman 包管理器适配）
- 多桌面适配（KDE / Cosmic：kwriteconfig5 / plasma-apply-* / cosmicctl）
- Skill 市场（社区贡献 YAML）
- 语音输入（whisper.cpp 本地 ASR + 实时转写）
- Tauri 透明窗口 + layer-shell 协议（解决 Wayland 浮球位置 / 透明问题）
- LLM 多模型路由优化（DeepSeek 默认 + Claude 复杂任务 + Ollama 离线兜底）

