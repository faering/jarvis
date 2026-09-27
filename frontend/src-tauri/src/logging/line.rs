//! The spec line (docs/logging.md):
//! `[timestamp] [LEVEL] [app] [logger] [turn] message  key=value ...`

use std::fmt::Write;

use time::OffsetDateTime;

/// `service.name` of every line this process writes.
pub const COMPONENT: &str = "app";
/// The turn slot of a line outside any turn.
pub const NO_TURN: &str = "--------";

/// OTel severity, lowest first.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum Level {
    Trace,
    Debug,
    Info,
    Warn,
    Error,
    Fatal,
}

impl Level {
    /// The level slot: the OTel name, padded to 5.
    pub fn padded(self) -> &'static str {
        match self {
            Self::Trace => "TRACE",
            Self::Debug => "DEBUG",
            Self::Info => "INFO ",
            Self::Warn => "WARN ",
            Self::Error => "ERROR",
            Self::Fatal => "FATAL",
        }
    }

    /// Parse a configured level (`JARVIS_LOG_LEVEL`), case-insensitive.
    pub fn parse(text: &str) -> Option<Self> {
        Some(match text.trim().to_ascii_uppercase().as_str() {
            "TRACE" => Self::Trace,
            "DEBUG" => Self::Debug,
            "INFO" => Self::Info,
            "WARN" | "WARNING" => Self::Warn,
            "ERROR" => Self::Error,
            "FATAL" | "CRITICAL" => Self::Fatal,
            _ => return None,
        })
    }

    /// Map a `log` crate level (FATAL arrives as `error!` plus `severity = "FATAL"`).
    pub fn from_log(level: log::Level) -> Self {
        match level {
            log::Level::Trace => Self::Trace,
            log::Level::Debug => Self::Debug,
            log::Level::Info => Self::Info,
            log::Level::Warn => Self::Warn,
            log::Level::Error => Self::Error,
        }
    }

    /// The `log` crate filter that lets this level (and above) through.
    pub fn to_filter(self) -> log::LevelFilter {
        match self {
            Self::Trace => log::LevelFilter::Trace,
            Self::Debug => log::LevelFilter::Debug,
            Self::Info => log::LevelFilter::Info,
            Self::Warn => log::LevelFilter::Warn,
            Self::Error | Self::Fatal => log::LevelFilter::Error,
        }
    }
}

/// One record, ready to format.
#[derive(Debug)]
pub struct Line<'a> {
    pub time: OffsetDateTime,
    pub level: Level,
    pub logger: &'a str,
    /// Full trace id (or its prefix); the slot shows its first 8 hex chars.
    pub turn: Option<&'a str>,
    pub message: &'a str,
    /// Already-formatted attributes (see [`format_attrs`]); empty for none.
    pub attrs: &'a str,
    /// Continuation lines (ERROR/FATAL), newline-separated, without the indent.
    pub detail: &'a str,
}

impl Line<'_> {
    /// The record as text: one line, plus indented continuation lines; no trailing newline.
    pub fn format(&self) -> String {
        let t = self.time.to_offset(time::UtcOffset::UTC);
        let mut out = String::with_capacity(96 + self.message.len() + self.attrs.len());
        let _ = write!(
            out,
            "[{:04}-{:02}-{:02} {:02}:{:02}:{:02}.{:03}Z] [{}] [{COMPONENT}] [{}] [{}] {}",
            t.year(),
            u8::from(t.month()),
            t.day(),
            t.hour(),
            t.minute(),
            t.second(),
            t.millisecond(),
            self.level.padded(),
            self.logger,
            turn_slot(self.turn),
            escape_message(self.message),
        );
        if !self.attrs.is_empty() {
            out.push_str("  ");
            out.push_str(self.attrs);
        }
        for line in self.detail.lines().filter(|l| !l.is_empty()) {
            out.push_str("\n    ");
            out.push_str(line);
        }
        out
    }
}

/// First 8 chars of a hex trace id, else `--------`.
pub fn turn_slot(turn: Option<&str>) -> &str {
    match turn.and_then(|t| t.get(..8)) {
        Some(p) if p.bytes().all(|b| b.is_ascii_hexdigit()) => p,
        _ => NO_TURN,
    }
}

/// Keep the message on one line: newlines become a literal `\n`.
pub fn escape_message(message: &str) -> String {
    message
        .replace("\r\n", "\\n")
        .replace('\n', "\\n")
        .replace('\r', "\\r")
}

/// `key=value` pairs joined by one space, values quoted when needed.
pub fn format_attrs<K: AsRef<str>, V: AsRef<str>>(pairs: &[(K, V)]) -> String {
    let mut out = String::new();
    for (k, v) in pairs {
        if !out.is_empty() {
            out.push(' ');
        }
        out.push_str(k.as_ref());
        out.push('=');
        out.push_str(&quote_value(v.as_ref()));
    }
    out
}

/// Quote a value that is empty or holds whitespace, `=` or `"`; escape `"`, `\` and
/// newlines inside the quotes. Other values stay as they are.
pub fn quote_value(value: &str) -> String {
    let needs = value.is_empty()
        || value
            .chars()
            .any(|c| c.is_whitespace() || c == '=' || c == '"');
    if !needs {
        return value.to_owned();
    }
    let mut out = String::with_capacity(value.len() + 2);
    out.push('"');
    for c in value.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use time::macros::datetime;

    fn line<'a>(level: Level, logger: &'a str, turn: Option<&'a str>, msg: &'a str) -> Line<'a> {
        Line {
            time: datetime!(2026-09-27 15:44:39.310 UTC),
            level,
            logger,
            turn,
            message: msg,
            attrs: "",
            detail: "",
        }
    }

    /// The `[app]` records of the shared fixture, rebuilt from their fields.
    fn fixture_app_records() -> Vec<String> {
        let path = concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../../docs/logging-examples.log"
        );
        let text = std::fs::read_to_string(path).expect("fixture");
        let mut records: Vec<String> = Vec::new();
        for l in text.lines() {
            if l.starts_with('[') {
                records.push(l.to_owned());
            } else if let Some(last) = records.last_mut() {
                last.push('\n');
                last.push_str(l);
            }
        }
        records.retain(|r| r.contains("] [app] ["));
        records
    }

    #[test]
    fn reproduces_the_app_lines_of_the_shared_fixture() {
        let attrs = format_attrs(&[("state", "thinking")]);
        let presence = Line {
            attrs: &attrs,
            ..line(
                Level::Info,
                "presence",
                Some("4bf92f3577b34da6a3ce929d0e0e4736"),
                "state changed",
            )
        };
        let fatal = Line {
            time: datetime!(2026-09-27 16:02:12 UTC),
            detail: "at src-tauri/src/main.rs:42 in main",
            ..line(
                Level::Fatal,
                "main",
                None,
                "cannot start: display not found",
            )
        };
        assert_eq!(
            fixture_app_records(),
            vec![presence.format(), fatal.format()]
        );
    }

    #[test]
    fn pads_levels_to_five_with_otel_names() {
        let names: Vec<_> = [
            Level::Trace,
            Level::Debug,
            Level::Info,
            Level::Warn,
            Level::Error,
            Level::Fatal,
        ]
        .iter()
        .map(|l| l.padded())
        .collect();
        assert_eq!(
            names,
            ["TRACE", "DEBUG", "INFO ", "WARN ", "ERROR", "FATAL"]
        );
        assert_eq!(Level::parse("warning"), Some(Level::Warn));
        assert_eq!(Level::parse(" info "), Some(Level::Info));
        assert_eq!(Level::parse("loud"), None);
    }

    #[test]
    fn escapes_newlines_and_quotes_attribute_values() {
        let attrs = format_attrs(&[
            ("note", r#"has "quotes" and a \ backslash"#),
            ("empty", ""),
            ("path", r"C:\x"),
            ("eq", "a=b"),
            ("n", "2"),
        ]);
        assert_eq!(
            attrs,
            r#"note="has \"quotes\" and a \\ backslash" empty="" path=C:\x eq="a=b" n=2"#
        );
        let l = Line {
            attrs: &attrs,
            ..line(Level::Info, "x", None, "a\nb\r\nc")
        };
        assert_eq!(
            l.format(),
            format!("[2026-09-27 15:44:39.310Z] [INFO ] [app] [x] [--------] a\\nb\\nc  {attrs}")
        );
    }

    #[test]
    fn turn_slot_takes_eight_hex_chars_or_dashes() {
        assert_eq!(
            turn_slot(Some("4bf92f3577b34da6a3ce929d0e0e4736")),
            "4bf92f35"
        );
        assert_eq!(turn_slot(Some("4bf92f35")), "4bf92f35");
        assert_eq!(turn_slot(Some("short")), NO_TURN);
        assert_eq!(turn_slot(Some("zzzzzzzzzz")), NO_TURN);
        assert_eq!(turn_slot(None), NO_TURN);
    }

    #[test]
    fn continuation_lines_are_indented_by_four() {
        let l = Line {
            detail: "at src/x.rs:1 in f\nError: boom\n  at g",
            ..line(Level::Error, "x", None, "failed")
        };
        assert_eq!(
            l.format(),
            "[2026-09-27 15:44:39.310Z] [ERROR] [app] [x] [--------] failed\n    at src/x.rs:1 in f\n    Error: boom\n      at g"
        );
    }
}
