//! App logging per docs/logging.md: one formatter for Rust `log` records and for the
//! webview's records (sent over `tauri-plugin-log`'s `log` command), writing stderr and,
//! when `JARVIS_LOG_DIR` is set, the daily file.
//!
//! The plugin runs with `skip_logger()`: its fern chain rebuilds each record after
//! formatting and drops the key-values (logger, turn, attributes), and its files rotate
//! by size, so this module is the global logger instead.

mod file;
mod line;

use std::ffi::OsString;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use log::kv::{Key, Value, VisitSource};
use time::OffsetDateTime;

pub use file::{DAILY_CAP_BYTES, DailyFile};
pub use line::{Level, Line, format_attrs};

/// The app's canonical build version (build.rs).
pub const VERSION: &str = env!("JARVIS_APP_VERSION");

/// Target prefix of records the plugin's `log` command creates for the webview.
const WEBVIEW_TARGET: &str = "webview";
/// This crate's module path, shown as `main` (its root) or stripped from sub-modules.
const CRATE: &str = env!("CARGO_CRATE_NAME");

/// The Pi's log folder (docs/logging.md), used when `JARVIS_LOG_DIR` isn't set.
pub const DEFAULT_LOG_DIR: &str = "/var/log/jarvis";

/// The log folder: `JARVIS_LOG_DIR` if set and not empty; otherwise the Pi's folder when
/// it exists (a desktop launcher may not pass the session environment); otherwise none.
pub fn resolve_dir(env: Option<OsString>, default: &Path) -> Option<PathBuf> {
    match env.filter(|d| !d.is_empty()) {
        Some(dir) => Some(PathBuf::from(dir)),
        None => default.is_dir().then(|| default.to_path_buf()),
    }
}

/// Settings read from the environment at startup.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Config {
    pub level: Level,
    pub dir: Option<PathBuf>,
}

impl Config {
    /// `JARVIS_LOG_LEVEL` (default INFO) and the log folder (see [`resolve_dir`]).
    pub fn from_env() -> (Self, Option<String>) {
        let raw = std::env::var("JARVIS_LOG_LEVEL").unwrap_or_default();
        let (level, bad) = match Level::parse(&raw) {
            Some(level) => (level, None),
            None if raw.trim().is_empty() => (Level::Info, None),
            None => (Level::Info, Some(raw)),
        };
        let dir = resolve_dir(
            std::env::var_os("JARVIS_LOG_DIR"),
            Path::new(DEFAULT_LOG_DIR),
        );
        (Self { level, dir }, bad)
    }
}

/// The global `log::Log`.
pub struct Logger {
    level: Level,
    clock: fn() -> OffsetDateTime,
    file: Option<Mutex<DailyFile>>,
    /// Test hook: collects lines instead of printing them.
    #[cfg(test)]
    captured: Mutex<Vec<String>>,
}

impl Logger {
    pub fn new(config: &Config, clock: fn() -> OffsetDateTime) -> Self {
        Self {
            level: config.level,
            clock,
            file: config
                .dir
                .as_ref()
                .map(|dir| Mutex::new(DailyFile::new(dir, DAILY_CAP_BYTES, VERSION))),
            #[cfg(test)]
            captured: Mutex::new(Vec::new()),
        }
    }

    /// Lowest level let through for a target: third-party crates stay at INFO and up.
    fn min_level(&self, target: &str) -> Level {
        if target.starts_with(WEBVIEW_TARGET) || target.starts_with(CRATE) {
            self.level
        } else {
            self.level.max(Level::Info)
        }
    }

    /// Format and write one record; returns its severity.
    fn emit(&self, record: &log::Record) -> Option<Level> {
        let fields = Fields::of(record);
        if fields.level < self.min_level(record.target()) {
            return None;
        }
        let now = (self.clock)();
        let text = Line {
            time: now,
            level: fields.level,
            logger: &fields.logger,
            turn: fields.turn.as_deref(),
            message: &record.args().to_string(),
            attrs: &fields.attrs,
            detail: &fields.detail,
        }
        .format();
        #[cfg(test)]
        self.captured.lock().unwrap().push(text.clone());
        #[cfg(not(test))]
        eprintln!("{text}");
        if let Some(file) = &self.file {
            let mut file = file.lock().unwrap_or_else(|e| e.into_inner());
            if let Err(err) = file.write(now, fields.level, &text) {
                eprintln!("jarvis-app: cannot write the log file: {err}");
            }
        }
        Some(fields.level)
    }
}

impl log::Log for Logger {
    fn enabled(&self, metadata: &log::Metadata) -> bool {
        Level::from_log(metadata.level()) >= self.min_level(metadata.target())
            || metadata.level() == log::Level::Error // may be FATAL
    }

    fn log(&self, record: &log::Record) {
        let fatal_from_webview =
            self.emit(record) == Some(Level::Fatal) && record.target().starts_with(WEBVIEW_TARGET);
        // The UI's `fatal()` means "terminate now" (docs/logging.md); the record is
        // already on disk (unbuffered writes).
        if fatal_from_webview {
            std::process::exit(1);
        }
    }

    fn flush(&self) {}
}

/// The slots of a record, from its target and key-values.
///
/// Webview records carry `logger`, `turn`, `attrs` (formatted by the TS logger, which
/// keeps their order), `detail` and `severity`. Rust records may carry `turn`,
/// `severity = "FATAL"`, `function`, and any other pairs as attributes.
#[derive(Debug)]
struct Fields {
    level: Level,
    logger: String,
    turn: Option<String>,
    attrs: String,
    detail: String,
}

#[derive(Default)]
struct Pairs(Vec<(String, String)>);

impl<'kvs> VisitSource<'kvs> for Pairs {
    fn visit_pair(&mut self, key: Key<'kvs>, value: Value<'kvs>) -> Result<(), log::kv::Error> {
        self.0.push((key.to_string(), value.to_string()));
        Ok(())
    }
}

impl Fields {
    fn of(record: &log::Record) -> Self {
        let mut pairs = Pairs::default();
        let _ = record.key_values().visit(&mut pairs);
        let mut take = |key: &str| {
            pairs
                .0
                .iter()
                .position(|(k, _)| k == key)
                .map(|i| pairs.0.remove(i).1)
        };
        let fatal = take("severity").is_some_and(|s| s.eq_ignore_ascii_case("FATAL"));
        let level = match Level::from_log(record.level()) {
            Level::Error if fatal => Level::Fatal,
            level => level,
        };
        let turn = take("turn");

        if record.target().starts_with(WEBVIEW_TARGET) {
            let logger = take("logger").unwrap_or_else(|| WEBVIEW_TARGET.to_owned());
            let attrs = take("attrs").unwrap_or_default();
            let detail = take("detail").unwrap_or_default();
            return Self {
                level,
                logger,
                turn,
                attrs,
                detail,
            };
        }

        let function = take("function");
        let turn = turn.or_else(|| {
            pairs
                .0
                .iter()
                .find(|(k, _)| k == "trace_id")
                .map(|(_, v)| v.clone())
        });
        let detail = if level >= Level::Error {
            at_line(record, function.as_deref())
        } else {
            String::new()
        };
        Self {
            level,
            logger: logger_name(record.target()),
            turn,
            attrs: format_attrs(&pairs.0),
            detail,
        }
    }
}

/// `jarvis_app` -> `main`, `jarvis_app::logging` -> `logging`, `tao::event_loop` ->
/// `tao.event_loop`.
fn logger_name(target: &str) -> String {
    let name = match target.strip_prefix(CRATE) {
        Some("") => return "main".to_owned(),
        Some(rest) if rest.starts_with("::") => &rest[2..],
        _ => target,
    };
    name.replace("::", ".")
}

/// `at <file>:<line> in <function>` for an ERROR/FATAL Rust record (repo-relative path
/// for this crate's files; the module path when the function isn't known).
fn at_line(record: &log::Record, function: Option<&str>) -> String {
    let file = record.file().unwrap_or("?");
    let file = if file.starts_with("src/") {
        format!("src-tauri/{file}")
    } else {
        file.to_owned()
    };
    let line = record
        .line()
        .map_or_else(|| "?".to_owned(), |l| l.to_string());
    let function = function
        .or(record.module_path())
        .map_or_else(|| "?".to_owned(), logger_name);
    format!("at {file}:{line} in {function}")
}

/// The name of the function around a `fatal!` call, from the type name of an item
/// nested in it (`jarvis_app::main::{{closure}}::f` -> `main`).
pub fn function_name(nested: &str) -> &str {
    let mut path = nested.strip_suffix("::f").unwrap_or(nested);
    while let Some(outer) = path.strip_suffix("::{{closure}}") {
        path = outer;
    }
    path.rsplit("::").next().unwrap_or(path)
}

/// Log FATAL and exit(1) (docs/logging.md: Rust FATAL is `error!` + exit).
macro_rules! fatal {
    ($($arg:tt)+) => {{
        fn f() {}
        let function = $crate::logging::function_name(::std::any::type_name_of_val(&f));
        ::log::error!(severity = "FATAL", function = function; $($arg)+);
        ::std::process::exit(1)
    }};
}
pub(crate) use fatal;

/// Install the global logger from the environment, and log panics as FATAL.
pub fn init() {
    let (config, bad_level) = Config::from_env();
    let logger = Logger::new(&config, OffsetDateTime::now_utc);
    if log::set_boxed_logger(Box::new(logger)).is_err() {
        return;
    }
    log::set_max_level(config.level.to_filter());
    if let Some(raw) = bad_level {
        log::warn!(value = raw.as_str(); "unknown JARVIS_LOG_LEVEL, using INFO");
    }
    std::panic::set_hook(Box::new(|info| {
        let kvs: [(&str, &str); 2] = [("severity", "FATAL"), ("function", "panic")];
        log::logger().log(
            &log::Record::builder()
                .level(log::Level::Error)
                .target(concat!(env!("CARGO_CRATE_NAME"), "::panic"))
                .file(info.location().map(|l| l.file()))
                .line(info.location().map(|l| l.line()))
                .args(format_args!(
                    "panicked: {}",
                    info.payload_as_str().unwrap_or("(no message)")
                ))
                .key_values(&kvs)
                .build(),
        );
    }));
}

/// A plugin that hands the webview its log threshold (`globalThis.__JARVIS_LOG_LEVEL__`),
/// so the TS logger doesn't send records the file would drop.
pub fn level_plugin<R: tauri::Runtime>() -> tauri::plugin::TauriPlugin<R> {
    let (config, _) = Config::from_env();
    let name = config.level.padded().trim();
    tauri::plugin::Builder::new("jarvis-log-level")
        .js_init_script(format!("globalThis.__JARVIS_LOG_LEVEL__ = \"{name}\";"))
        .build()
}

#[cfg(test)]
mod tests {
    use super::*;
    use log::Log;
    use time::macros::datetime;

    fn clock() -> OffsetDateTime {
        datetime!(2026-09-27 15:44:39.310 UTC)
    }

    fn logger(level: Level, dir: Option<PathBuf>) -> Logger {
        Logger::new(&Config { level, dir }, clock)
    }

    fn lines(logger: &Logger) -> Vec<String> {
        logger.captured.lock().unwrap().clone()
    }

    #[test]
    fn webview_records_fill_the_slots_from_key_values() {
        let l = logger(Level::Trace, None);
        let kvs: [(&str, &str); 4] = [
            ("logger", "presence"),
            ("turn", "4bf92f3577b34da6a3ce929d0e0e4736"),
            ("attrs", "state=thinking"),
            ("detail", ""),
        ];
        l.log(
            &log::Record::builder()
                .level(log::Level::Info)
                .target("webview::f@http://x/y.js:1:2")
                .args(format_args!("state changed"))
                .key_values(&kvs)
                .build(),
        );
        assert_eq!(
            lines(&l),
            [
                "[2026-09-27 15:44:39.310Z] [INFO ] [app] [presence] [4bf92f35] state changed  state=thinking"
            ]
        );
    }

    #[test]
    fn rust_records_use_the_module_path_and_key_values_as_attributes() {
        let l = logger(Level::Info, None);
        let kvs: [(&str, &str); 3] = [
            ("trace_id", "4bf92f3577b34da6a3ce929d0e0e4736"),
            ("note", "two words"),
            ("severity", "FATAL"),
        ];
        l.log(
            &log::Record::builder()
                .level(log::Level::Error)
                .target("jarvis_app")
                .module_path(Some("jarvis_app"))
                .file(Some("src/main.rs"))
                .line(Some(42))
                .args(format_args!("cannot start"))
                .key_values(&kvs)
                .build(),
        );
        assert_eq!(
            lines(&l),
            [
                "[2026-09-27 15:44:39.310Z] [FATAL] [app] [main] [4bf92f35] cannot start  trace_id=4bf92f3577b34da6a3ce929d0e0e4736 note=\"two words\"\n    at src-tauri/src/main.rs:42 in main"
            ]
        );
    }

    #[test]
    fn filters_by_level_and_keeps_third_party_crates_at_info() {
        let l = logger(Level::Debug, None);
        for (target, level) in [
            ("jarvis_app::x", log::Level::Debug),
            ("jarvis_app::x", log::Level::Trace),
            ("tao::event_loop", log::Level::Debug),
            ("tao::event_loop", log::Level::Info),
        ] {
            l.log(
                &log::Record::builder()
                    .level(level)
                    .target(target)
                    .args(format_args!("m"))
                    .build(),
            );
        }
        let got: Vec<String> = lines(&l).iter().map(|s| s[27..].to_owned()).collect();
        assert_eq!(
            got,
            [
                "[DEBUG] [app] [x] [--------] m",
                "[INFO ] [app] [tao.event_loop] [--------] m"
            ]
        );
    }

    #[test]
    fn writes_the_daily_file_when_a_dir_is_set() {
        let dir =
            std::env::temp_dir().join(format!("jarvis-log-test-logger-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let l = logger(Level::Info, Some(dir.clone()));
        l.log(
            &log::Record::builder()
                .level(log::Level::Warn)
                .target("jarvis_app")
                .args(format_args!("hello"))
                .build(),
        );
        let text = std::fs::read_to_string(dir.join("jarvis-app-2026-09-27.log")).unwrap();
        assert_eq!(
            text,
            format!(
                "[2026-09-27 15:44:39.310Z] [INFO ] [app] [log] [--------] log opened  service.version={VERSION} pid={}\n[2026-09-27 15:44:39.310Z] [WARN ] [app] [main] [--------] hello\n",
                std::process::id()
            )
        );
    }

    #[test]
    fn names_the_enclosing_function() {
        assert_eq!(function_name("jarvis_app::main::f"), "main");
        assert_eq!(function_name("jarvis_app::main::{{closure}}::f"), "main");
        assert_eq!(
            function_name("jarvis_app::logging::setup::{{closure}}::{{closure}}::f"),
            "setup"
        );
        fn f() {}
        assert_eq!(
            function_name(std::any::type_name_of_val(&f)),
            "names_the_enclosing_function"
        );
    }

    #[test]
    fn shortens_module_paths_to_dotted_logger_names() {
        assert_eq!(logger_name("jarvis_app"), "main");
        assert_eq!(logger_name("jarvis_app::logging::file"), "logging.file");
        assert_eq!(logger_name("tao::event_loop"), "tao.event_loop");
        assert_eq!(logger_name("jarvis_apps"), "jarvis_apps");
    }

    #[test]
    fn log_dir_prefers_the_env_then_an_existing_default() {
        let tmp = std::env::temp_dir();
        let missing = tmp.join("jarvis-no-such-dir");
        assert_eq!(
            resolve_dir(Some("/x".into()), &missing),
            Some(PathBuf::from("/x"))
        );
        assert_eq!(resolve_dir(Some("".into()), &tmp), Some(tmp.clone()));
        assert_eq!(resolve_dir(None, &tmp), Some(tmp.clone()));
        assert_eq!(resolve_dir(None, &missing), None);
    }
}
