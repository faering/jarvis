//! Restart after an update (#183). A deploy installs a new `.deb` while this process keeps
//! running the old binary, so the screen would show the old version until someone restarts
//! it. This notices that the installed binary changed and tells the UI (`update-installed`),
//! which calls `restart_app` once Jarvis is quiet. The root installer never reaches into the
//! desktop session (ADR 0009).

use std::path::Path;
use std::process::Command;
use std::sync::Mutex;
use std::time::{Duration, SystemTime};

use tauri::{AppHandle, Emitter, Manager, Runtime};

/// The event the UI listens for; its payload is the installed version.
pub const EVENT: &str = "update-installed";
/// The Debian package the deploy installs (frontend/src-tauri/tauri.conf.json).
const PACKAGE: &str = "jarvis";
const POLL: Duration = Duration::from_secs(10);

/// What identifies the installed file. `dpkg` installs by rename, so an upgrade gives the
/// path a new inode (and mtime) while this process still runs the old one.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Identity {
    inode: u64,
    modified: Option<SystemTime>,
    len: u64,
}

pub fn identity(path: &Path) -> Option<Identity> {
    let meta = std::fs::metadata(path).ok()?;
    #[cfg(unix)]
    let inode = std::os::unix::fs::MetadataExt::ino(&meta);
    #[cfg(not(unix))]
    let inode = 0;
    Some(Identity {
        inode,
        modified: meta.modified().ok(),
        len: meta.len(),
    })
}

/// The installed package version, from `dpkg-query -W -f '${Version}'` output.
pub fn parse_version(stdout: &[u8]) -> Option<String> {
    let version = String::from_utf8_lossy(stdout).trim().to_owned();
    (!version.is_empty()).then_some(version)
}

fn installed_version() -> String {
    Command::new("dpkg-query")
        .args(["-W", "-f=${Version}", PACKAGE])
        .output()
        .ok()
        .filter(|out| out.status.success())
        .and_then(|out| parse_version(&out.stdout))
        .unwrap_or_else(|| "unknown".to_owned())
}

/// The version an update installed, once one was seen (for the restart log line).
#[derive(Default)]
pub struct Pending(Mutex<Option<String>>);

/// Watch the running binary's path and emit `update-installed` once it changes. Off in
/// debug builds: `tauri dev` rebuilds the binary all the time.
pub fn watch<R: Runtime>(app: &AppHandle<R>) {
    app.manage(Pending::default());
    if cfg!(debug_assertions) {
        return;
    }
    let Ok(path) = tauri::process::current_binary(&app.env()) else {
        log::warn!("update watch off: running binary unknown");
        return;
    };
    let Some(started) = identity(&path) else {
        log::warn!(path = path.display().to_string(); "update watch off: binary unreadable");
        return;
    };
    let app = app.clone();
    std::thread::spawn(move || {
        loop {
            std::thread::sleep(POLL);
            // Mid-install the path can briefly be missing: check again next time.
            match identity(&path) {
                Some(now) if now != started => break,
                _ => continue,
            }
        }
        let to = installed_version();
        log::info!(from = crate::logging::VERSION, to = to.as_str(); "update installed");
        *app.state::<Pending>()
            .0
            .lock()
            .unwrap_or_else(|e| e.into_inner()) = Some(to.clone());
        if let Err(err) = app.emit(EVENT, to) {
            log::error!(error = err.to_string(); "could not tell the UI about the update");
        }
    });
}

/// Restart into the installed version. The UI calls it once Jarvis is quiet. Tauri relaunches
/// the binary it started from, with the same arguments (`--fullscreen` stays).
#[tauri::command]
pub fn restart_app<R: Runtime>(app: AppHandle<R>) {
    let to = app
        .state::<Pending>()
        .0
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .clone()
        .unwrap_or_else(|| "unknown".to_owned());
    log::info!(from = crate::logging::VERSION, to = to.as_str(); "restarting for update");
    app.restart();
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::path::PathBuf;

    fn scratch(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("jarvis-update-{}-{name}", std::process::id()));
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn a_file_replaced_by_rename_is_a_new_identity() {
        let dir = scratch("rename");
        let bin = dir.join("jarvis-app");
        fs::write(&bin, b"old").unwrap();
        let started = identity(&bin).unwrap();
        assert_eq!(identity(&bin), Some(started.clone()), "unchanged file");

        // How dpkg installs: write the new file beside it, then rename it over.
        let new = dir.join("jarvis-app.dpkg-new");
        fs::write(&new, b"new").unwrap();
        fs::rename(&new, &bin).unwrap();
        assert_ne!(identity(&bin), Some(started));
        fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn a_missing_file_has_no_identity() {
        assert_eq!(identity(Path::new("/nonexistent/jarvis-app")), None);
    }

    #[test]
    fn parses_the_dpkg_version() {
        assert_eq!(parse_version(b"0.3.0\n"), Some("0.3.0".to_owned()));
        assert_eq!(parse_version(b"  "), None);
        assert_eq!(parse_version(b""), None);
    }
}
