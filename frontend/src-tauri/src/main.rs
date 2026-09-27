//! Jarvis display app: a thin native shell around the TS/React UI.

// Prevents an extra console window on Windows in release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod logging;

fn main() {
    logging::init();
    log::info!(version = logging::VERSION; "app starting");
    let result = tauri::Builder::default()
        // Only the webview's `log` command: logging::init() installed the logger.
        .plugin(tauri_plugin_log::Builder::new().skip_logger().build())
        .plugin(logging::level_plugin())
        .run(tauri::generate_context!());
    if let Err(err) = result {
        logging::fatal!("error while running the Jarvis app: {err}");
    }
}
