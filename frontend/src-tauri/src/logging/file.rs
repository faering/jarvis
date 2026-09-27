//! The daily file `<dir>/jarvis-app-YYYY-MM-DD.log` (UTC date) with the per-day budget
//! (docs/logging.md "Files and budget"). Pruning is the Pi's `jarvis-logs prune`.

use std::fs::{File, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};

use time::{Date, OffsetDateTime, UtcOffset};

use super::line::{COMPONENT, Level, Line, format_attrs};

/// 500 MiB per component per day.
pub const DAILY_CAP_BYTES: u64 = 500 * 1024 * 1024;

/// Appends lines to today's file, switching files at UTC midnight.
///
/// At the daily cap it keeps only WARN and above and writes one ERROR saying so; at 110%
/// it stops until the next UTC day.
#[derive(Debug)]
pub struct DailyFile {
    dir: PathBuf,
    cap: u64,
    version: String,
    pid: u32,
    day: Option<Date>,
    file: Option<File>,
    bytes: u64,
    capped: bool,
    stopped: bool,
}

impl DailyFile {
    pub fn new(dir: impl Into<PathBuf>, cap: u64, version: impl Into<String>) -> Self {
        Self {
            dir: dir.into(),
            cap,
            version: version.into(),
            pid: std::process::id(),
            day: None,
            file: None,
            bytes: 0,
            capped: false,
            stopped: false,
        }
    }

    /// The file for one UTC day.
    pub fn path_for(dir: &Path, day: Date) -> PathBuf {
        dir.join(format!(
            "jarvis-{COMPONENT}-{:04}-{:02}-{:02}.log",
            day.year(),
            u8::from(day.month()),
            day.day()
        ))
    }

    /// Write one formatted record logged at `now`.
    pub fn write(&mut self, now: OffsetDateTime, level: Level, record: &str) -> io::Result<()> {
        let day = now.to_offset(UtcOffset::UTC).date();
        if self.day != Some(day) {
            self.open(now, day)?;
        }
        self.put(now, level, record)
    }

    fn open(&mut self, now: OffsetDateTime, day: Date) -> io::Result<()> {
        // Mark the day first: a file that can't be opened isn't retried until tomorrow.
        self.day = Some(day);
        self.file = None;
        self.capped = false;
        self.stopped = false;
        std::fs::create_dir_all(&self.dir)?;
        let mut options = OpenOptions::new();
        options.create(true).append(true);
        #[cfg(unix)]
        std::os::unix::fs::OpenOptionsExt::mode(&mut options, 0o640);
        let file = options.open(Self::path_for(&self.dir, day))?;
        self.bytes = file.metadata()?.len();
        self.file = Some(file);
        let attrs = format_attrs(&[
            ("service.version", self.version.as_str()),
            ("pid", &self.pid.to_string()),
        ]);
        let header = Line {
            time: now,
            level: Level::Info,
            logger: "log",
            turn: None,
            message: "log opened",
            attrs: &attrs,
            detail: "",
        };
        self.put(now, Level::Info, &header.format())
    }

    fn put(&mut self, now: OffsetDateTime, level: Level, record: &str) -> io::Result<()> {
        if self.stopped || self.file.is_none() {
            return Ok(());
        }
        if !self.capped && self.bytes >= self.cap {
            self.capped = true;
            let attrs = format_attrs(&[("cap_mib", (self.cap / (1024 * 1024)).to_string())]);
            let notice = Line {
                time: now,
                level: Level::Error,
                logger: "log",
                turn: None,
                message: "daily log cap reached, keeping only WARN and above until tomorrow",
                attrs: &attrs,
                detail: "",
            };
            self.append(&notice.format())?;
        }
        if self.capped && level < Level::Warn {
            return Ok(());
        }
        if self.bytes + record.len() as u64 + 1 > self.cap + self.cap / 10 {
            self.stopped = true;
            eprintln!(
                "{}",
                Line {
                    time: now,
                    level: Level::Error,
                    logger: "log",
                    turn: None,
                    message: "daily log limit reached, file writes stop until tomorrow",
                    attrs: "",
                    detail: "",
                }
                .format()
            );
            return Ok(());
        }
        self.append(record)
    }

    fn append(&mut self, record: &str) -> io::Result<()> {
        if let Some(file) = &mut self.file {
            let mut buf = Vec::with_capacity(record.len() + 1);
            buf.extend_from_slice(record.as_bytes());
            buf.push(b'\n');
            file.write_all(&buf)?; // one write per record (O_APPEND)
            self.bytes += buf.len() as u64;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use time::macros::{date, datetime};

    fn tmp_dir(name: &str) -> PathBuf {
        let dir =
            std::env::temp_dir().join(format!("jarvis-log-test-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        dir
    }

    fn read(dir: &Path, day: Date) -> String {
        std::fs::read_to_string(DailyFile::path_for(dir, day)).unwrap()
    }

    fn rec(level: Level, message: &str) -> String {
        Line {
            time: datetime!(2026-09-27 10:00 UTC),
            level,
            logger: "t",
            turn: None,
            message,
            attrs: "",
            detail: "",
        }
        .format()
    }

    #[test]
    fn names_files_by_utc_date_and_writes_a_header_on_open() {
        let dir = tmp_dir("daily");
        let mut f = DailyFile::new(&dir, DAILY_CAP_BYTES, "1.2.3");
        // 23:30 at UTC-2 is already the 28th in UTC.
        let late = datetime!(2026-09-27 23:30 -2);
        f.write(late, Level::Info, "one").unwrap();
        f.write(datetime!(2026-09-28 02:00 UTC), Level::Info, "two")
            .unwrap();
        f.write(datetime!(2026-09-29 00:00:00.001 UTC), Level::Info, "three")
            .unwrap();

        let pid = std::process::id();
        assert_eq!(
            read(&dir, date!(2026 - 09 - 28)),
            format!(
                "[2026-09-28 01:30:00.000Z] [INFO ] [app] [log] [--------] log opened  service.version=1.2.3 pid={pid}\none\ntwo\n"
            )
        );
        assert!(read(&dir, date!(2026 - 09 - 29)).ends_with(&format!(
            "log opened  service.version=1.2.3 pid={pid}\nthree\n"
        )));
        assert!(!DailyFile::path_for(&dir, date!(2026 - 09 - 27)).exists());
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mode = std::fs::metadata(DailyFile::path_for(&dir, date!(2026 - 09 - 28)))
                .unwrap()
                .permissions()
                .mode();
            assert_eq!(mode & 0o777, 0o640);
        }
    }

    #[test]
    fn at_the_cap_keeps_warn_and_up_then_stops_at_110_percent() {
        let dir = tmp_dir("cap");
        let now = datetime!(2026-09-27 10:00 UTC);
        let warn = rec(Level::Warn, "warn");
        let mut f = DailyFile::new(&dir, 2000, "1.2.3");
        while !f.stopped {
            f.write(now, Level::Warn, &warn).unwrap();
        }
        let size = f.bytes;
        assert!(size <= 2200, "{size}");
        f.write(now, Level::Fatal, &warn).unwrap(); // stopped: even FATAL is dropped
        let text = read(&dir, date!(2026 - 09 - 27));
        assert_eq!(text.len() as u64, size);
        let notices: Vec<&str> = text
            .lines()
            .filter(|l| l.contains("daily log cap reached"))
            .collect();
        assert_eq!(notices.len(), 1);
        assert!(
            notices[0].starts_with("[2026-09-27 10:00:00.000Z] [ERROR] [app] [log] [--------]")
        );
        assert!(notices[0].ends_with("  cap_mib=0"));

        // The next UTC day starts a fresh file.
        f.write(datetime!(2026-09-28 00:00 UTC), Level::Info, "x")
            .unwrap();
        assert!(read(&dir, date!(2026 - 09 - 28)).ends_with("\nx\n"));
    }

    #[test]
    fn keeps_warn_once_capped_below_the_stop_limit() {
        let dir = tmp_dir("warn");
        let now = datetime!(2026-09-27 10:00 UTC);
        let info = rec(Level::Info, "info");
        let warn = rec(Level::Warn, "warn");
        let mut f = DailyFile::new(&dir, 10_000, "v");
        let mut kept = 0;
        while f.bytes < 10_000 {
            f.write(now, Level::Info, &info).unwrap();
            kept += 1;
        }
        f.write(now, Level::Info, &info).unwrap(); // capped: dropped
        f.write(now, Level::Warn, &warn).unwrap();
        f.write(now, Level::Info, &info).unwrap(); // dropped
        f.write(now, Level::Warn, &warn).unwrap();

        let text = read(&dir, date!(2026 - 09 - 27));
        assert_eq!(text.matches("] info").count(), kept);
        assert_eq!(text.matches("daily log cap reached").count(), 1);
        assert_eq!(text.matches("] warn").count(), 2);
        assert!(text.ends_with(&(warn + "\n")));
    }

    #[test]
    fn appends_to_an_existing_file_and_counts_its_size() {
        let dir = tmp_dir("append");
        std::fs::create_dir_all(&dir).unwrap();
        let path = DailyFile::path_for(&dir, date!(2026 - 09 - 27));
        std::fs::write(&path, "earlier\n").unwrap();
        let mut f = DailyFile::new(&dir, DAILY_CAP_BYTES, "v");
        f.write(datetime!(2026-09-27 10:00 UTC), Level::Info, "later")
            .unwrap();
        let text = std::fs::read_to_string(&path).unwrap();
        assert!(text.starts_with("earlier\n["));
        assert!(text.ends_with("later\n"));
        assert_eq!(f.bytes, text.len() as u64);
    }
}
