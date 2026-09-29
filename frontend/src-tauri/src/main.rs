//! Jarvis display app: a thin native shell around the TS/React UI.

// Prevents an extra console window on Windows in release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod logging;

use tauri::Manager;

/// Who may ask for a minimize: the agent's `window.minimize` command, or Ctrl+M.
const MINIMIZE_SOURCES: [&str; 2] = ["agent", "keyboard"];

/// Minimize the window (ADR 0013: the agent decides, the app executes). The UI calls this
/// for the agent's `window.minimize` command and for Ctrl+M; the taskbar brings it back.
#[tauri::command]
fn minimize_window(window: tauri::WebviewWindow, source: String) -> Result<(), String> {
    check_minimize_source(&source)?;
    log::info!(source = source.as_str(); "window minimize requested");
    window.minimize().map_err(|err| err.to_string())
}

fn check_minimize_source(source: &str) -> Result<(), String> {
    if MINIMIZE_SOURCES.contains(&source) {
        return Ok(());
    }
    log::warn!(source; "window minimize from unknown source refused");
    Err(format!("unknown minimize source: {source}"))
}

fn main() {
    // WebKitGTK's DMA-BUF renderer draws only lines and flicker on the Pi 5 (verified on
    // the device, #167); Tauri's Linux graphics guide suggests this switch. Set before any
    // thread starts; an explicit value in the environment still wins.
    #[cfg(target_os = "linux")]
    if std::env::var_os("WEBKIT_DISABLE_DMABUF_RENDERER").is_none() {
        // SAFETY: single-threaded here, before the logger, Tauri or WebKit start threads.
        unsafe { std::env::set_var("WEBKIT_DISABLE_DMABUF_RENDERER", "1") };
    }
    // `--fullscreen`: how the Pi's autostart opens it (a device boots into Jarvis).
    let fullscreen = std::env::args().skip(1).any(|arg| arg == "--fullscreen");

    logging::init();
    log::info!(version = logging::VERSION, fullscreen; "app starting");
    let result = tauri::Builder::default()
        .setup(move |app| {
            if fullscreen && let Some(window) = app.get_webview_window("main") {
                window.set_fullscreen(true)?;
            }
            Ok(())
        })
        // Only the webview's `log` command: logging::init() installed the logger.
        .plugin(tauri_plugin_log::Builder::new().skip_logger().build())
        .plugin(logging::level_plugin())
        .invoke_handler(tauri::generate_handler![minimize_window])
        .run(tauri::generate_context!());
    if let Err(err) = result {
        logging::fatal!("error while running the Jarvis app: {err}");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn minimize_accepts_only_known_sources() {
        assert_eq!(check_minimize_source("agent"), Ok(()));
        assert_eq!(check_minimize_source("keyboard"), Ok(()));
        assert!(check_minimize_source("script").is_err());
        assert!(check_minimize_source("").is_err());
    }
}
