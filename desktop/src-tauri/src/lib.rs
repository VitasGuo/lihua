// Lihua 狸花猫桌面端主进程
//
// v0.7.0 重构：
//   1. 移除桌面浮动小球（用户反馈：粗俗、抢眼、不需要）
//   2. 优化系统托盘菜单：状态行 + 分组 + 快捷键提示（macOS 风格）
//   3. 主窗口尺寸 720×640，圆角 24px，decorations:false 自定义标题栏
//   4. 启动 Python FastAPI 后端（uvicorn，端口 7531）作为 sidecar
//   5. 注册全局快捷键 Ctrl+Alt+L 切换主窗口
//   6. 暴露 Tauri 命令给前端：toggle_main / show_main / hide_main / quit_app

#![cfg_attr(mobile, tauri::mobile_entry_point)]

use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Emitter, Manager, WebviewWindow};
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};
use tauri_plugin_notification::NotificationExt;

// 后端配置
const BACKEND_HOST: &str = "127.0.0.1";
const BACKEND_PORT: u16 = 7531;
const BACKEND_READY_TIMEOUT: Duration = Duration::from_secs(20);

/// 全局状态：Python 后端子进程句柄（用于退出时清理）
struct BackendHandle(Mutex<Option<Child>>);

/// 应用版本（用于关于对话框）
const APP_VERSION: &str = "0.8.26-alpha";

fn main_window(app: &AppHandle) -> Option<WebviewWindow> {
    app.get_webview_window("main")
}

/// 切换主窗口可见性（显示则聚焦，隐藏则藏到托盘）
fn toggle_main_window(app: &AppHandle) {
    if let Some(win) = main_window(app) {
        if win.is_visible().unwrap_or(false) {
            let _ = win.hide();
        } else {
            let _ = win.show();
            let _ = win.set_focus();
        }
    } else {
        log::warn!("main window not found");
    }
}

/// 显示主窗口
fn show_main_window(app: &AppHandle) {
    if let Some(win) = main_window(app) {
        let _ = win.show();
        let _ = win.set_focus();
    }
}

/// 隐藏主窗口（不退出）
fn hide_main_window(app: &AppHandle) {
    if let Some(win) = main_window(app) {
        let _ = win.hide();
    }
}

/// 启动 Python 后端 sidecar
fn start_backend(app: AppHandle) {
    std::thread::spawn(move || {
        // 找 Python 解释器：优先 venv，其次系统 python3
        let venv_python = dirs_home().join(".local/share/lihua/venv/bin/python");
        let python_bin = if venv_python.exists() {
            venv_python
        } else {
            which_python3().unwrap_or_else(|| "python3".into())
        };

        // v0.8.7: 启动前检测端口是否被旧后端占用
        // 问题场景：用户重启桌面端，但旧后端（uvicorn）还在跑，
        // 新后端 spawn 时 uvicorn 因端口冲突立即退出，
        // 但 wait_for_port 检测到端口可连接（旧后端在监听），以为后端就绪。
        // 修复：启动前先 kill 占用端口的旧进程，确保新后端能正常启动。
        if std::net::TcpStream::connect((BACKEND_HOST, BACKEND_PORT)).is_ok() {
            log::warn!(
                "端口 {} 被旧后端占用，尝试清理...",
                BACKEND_PORT
            );
            // 优先用 fuser -k PORT/tcp（精准 kill 占用端口的进程）
            let _ = Command::new("fuser")
                .arg("-k")
                .arg(format!("{}/tcp", BACKEND_PORT))
                .output();
            // 兜底用 pkill -f "uvicorn.*PORT"（fuser 不存在时）
            let _ = Command::new("pkill")
                .arg("-f")
                .arg(format!("uvicorn.*{}", BACKEND_PORT))
                .output();
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

        log::info!("启动后端：{} -m uvicorn ...", python_bin.display());

        let child = Command::new(&python_bin)
            .arg("-m")
            .arg("uvicorn")
            .arg("lihua.server:create_app")
            .arg("--factory")
            .arg("--host")
            .arg(BACKEND_HOST)
            .arg("--port")
            .arg(BACKEND_PORT.to_string())
            .arg("--log-level")
            .arg("warning")
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit())
            .spawn();

        match child {
            Ok(c) => {
                if let Some(state) = app.try_state::<BackendHandle>() {
                    *state.0.lock().unwrap() = Some(c);
                }
                if wait_for_port(BACKEND_HOST, BACKEND_PORT, BACKEND_READY_TIMEOUT) {
                    log::info!("后端就绪 http://{}:{}", BACKEND_HOST, BACKEND_PORT);
                    let _ = app.emit("backend-ready", ());
                } else {
                    log::error!("后端启动超时（{}s）", BACKEND_READY_TIMEOUT.as_secs());
                }
            }
            Err(e) => {
                log::error!("启动后端失败: {}", e);
                let _ = app.notification()
                    .builder()
                    .title("狸花猫")
                    .body(format!("后端启动失败：{e}"))
                    .show();
            }
        }
    });
}

/// 等待端口可连接
fn wait_for_port(host: &str, port: u16, timeout: Duration) -> bool {
    use std::net::TcpStream;
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if TcpStream::connect((host, port)).is_ok() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    false
}

fn dirs_home() -> std::path::PathBuf {
    std::env::var("HOME")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|_| std::path::PathBuf::from("/root"))
}

fn which_python3() -> Option<std::path::PathBuf> {
    use std::process::Command;
    let out = Command::new("which").arg("python3").output().ok()?;
    if !out.status.success() {
        return None;
    }
    let s = String::from_utf8_lossy(&out.stdout);
    let trimmed = s.trim();
    if trimmed.is_empty() {
        None
    } else {
        Some(std::path::PathBuf::from(trimmed))
    }
}

/// 创建系统托盘（macOS 风格分组菜单 + 状态行）
fn create_tray(app: &AppHandle) -> tauri::Result<()> {
    // 状态行（禁用态，仅展示）
    let status_item = MenuItem::with_id(app, "status", "● 在线 · 狸花猫", false, None::<&str>)?;

    let show_item = MenuItem::with_id(app, "show", "显示主窗口", true, None::<&str>)?;
    let new_chat_item = MenuItem::with_id(app, "new_chat", "新对话", true, None::<&str>)?;

    let sep1 = PredefinedMenuItem::separator(app)?;
    let settings_item = MenuItem::with_id(app, "settings", "设置...", true, None::<&str>)?;
    let history_item = MenuItem::with_id(app, "history", "查看历史", true, None::<&str>)?;
    let audit_item = MenuItem::with_id(app, "audit", "查看审计日志", true, None::<&str>)?;
    // v0.8.20: 记忆管理入口（查看/导出/清空 agent 记忆数据）
    let memory_item = MenuItem::with_id(app, "memory", "记忆管理...", true, None::<&str>)?;

    let sep2 = PredefinedMenuItem::separator(app)?;
    let about_item = MenuItem::with_id(app, "about", "关于狸花猫", true, None::<&str>)?;
    let quit_item = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;

    let menu = Menu::with_items(app, &[
        &status_item,
        &PredefinedMenuItem::separator(app)?,
        &show_item,
        &new_chat_item,
        &sep1,
        &settings_item,
        &history_item,
        &audit_item,
        &memory_item,
        &sep2,
        &about_item,
        &quit_item,
    ])?;

    let icon = app.default_window_icon()
        .cloned()
        .ok_or_else(|| tauri::Error::Anyhow(anyhow::anyhow!("no default window icon")))?;

    TrayIconBuilder::with_id("main")
        .icon(icon)
        .tooltip("狸花猫 Lihua · AI 系统管家")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "show" => show_main_window(app),
            "new_chat" => {
                // 通知前端清空对话
                let _ = app.emit("new-chat", ());
                show_main_window(app);
            }
            "settings" => {
                let _ = app.emit("open-settings", ());
                show_main_window(app);
            }
            "history" => {
                let _ = app.emit("open-history", ());
                show_main_window(app);
            }
            "audit" => {
                let _ = app.emit("open-audit", ());
                show_main_window(app);
            }
            "memory" => {
                // v0.8.20: 打开记忆管理面板（MemorySheet）
                let _ = app.emit("open-memory", ());
                show_main_window(app);
            }
            "about" => {
                let _ = app.notification()
                    .builder()
                    .title("关于狸花猫")
                    .body(format!("狸花猫 Lihua v{}\nAI 系统管家\n让普通用户也能省心用 Linux", APP_VERSION))
                    .show();
            }
            "quit" => {
                log::info!("用户选择退出");
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                toggle_main_window(tray.app_handle());
            }
        })
        .build(app)?;
    Ok(())
}

/// 注册全局快捷键 Ctrl+Alt+L
fn register_global_shortcut(app: &AppHandle) -> tauri::Result<()> {
    let shortcut = Shortcut::new(Some(Modifiers::CONTROL | Modifiers::ALT), Code::KeyL);
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
    log::info!("全局快捷键已注册：Ctrl+Alt+L");
    Ok(())
}

// ---------------------------------------------------------------------------
// Tauri 命令（前端可调用）
// ---------------------------------------------------------------------------

#[tauri::command]
fn cmd_toggle_main(app: AppHandle) {
    toggle_main_window(&app);
}

#[tauri::command]
fn cmd_show_main(app: AppHandle) {
    show_main_window(&app);
}

#[tauri::command]
fn cmd_hide_main(app: AppHandle) {
    hide_main_window(&app);
}

#[tauri::command]
fn cmd_quit(app: AppHandle) {
    app.exit(0);
}

/// v0.8.19: 最小化主窗口
#[tauri::command]
fn cmd_minimize(app: AppHandle) {
    if let Some(win) = main_window(&app) {
        let _ = win.minimize();
    }
}

/// v0.8.19: 切换最大化/还原（手动判断 + maximize/unmaximize）
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

#[tauri::command]
fn backend_url() -> String {
    format!("http://{}:{}", BACKEND_HOST, BACKEND_PORT)
}

#[tauri::command]
fn app_version() -> String {
    APP_VERSION.to_string()
}

pub fn run() {
    // v0.7.5: WebKitGTK GPU 加速
    //   WEBKIT_DISABLE_COMPOSITING_MODE=0 → 启用 GPU 合成层（默认可能禁用）
    //   WEBKIT_DISABLE_DMABUF_RENDERER=0  → 启用 dmabuf 渲染器（更高效的 GPU 路径）
    //   必须在 Tauri Builder 之前设置，让 WebKitGTK 初始化时读取
    //   注意：Wayland + NVIDIA 专有驱动下 dmabuf 可能黑屏，需切换回 X11 或禁用 dmabuf
    if std::env::var("WEBKIT_DISABLE_COMPOSITING_MODE").is_err() {
        std::env::set_var("WEBKIT_DISABLE_COMPOSITING_MODE", "0");
    }
    if std::env::var("WEBKIT_DISABLE_DMABUF_RENDERER").is_err() {
        std::env::set_var("WEBKIT_DISABLE_DMABUF_RENDERER", "0");
    }

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build())
        .manage(BackendHandle(Mutex::new(None)))
        .setup(|app| {
            // 启动 Python 后端
            start_backend(app.handle().clone());

            // 创建系统托盘
            if let Err(e) = create_tray(app.handle()) {
                log::error!("创建系统托盘失败: {}", e);
            }

            // 注册全局快捷键
            if let Err(e) = register_global_shortcut(app.handle()) {
                log::error!("注册全局快捷键失败: {}", e);
            }

            log::info!("狸花猫桌面端已启动 v{}", APP_VERSION);
            Ok(())
        })
        .on_window_event(|window, event| {
            // 主窗口关闭按钮（如果有的话）改为隐藏
            if window.label() == "main" {
                if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            cmd_toggle_main,
            cmd_show_main,
            cmd_hide_main,
            cmd_quit,
            cmd_minimize,
            cmd_toggle_maximize,
            backend_url,
            app_version,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
