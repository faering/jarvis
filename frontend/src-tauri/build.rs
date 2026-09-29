use std::process::Command;

fn main() {
    // The app's canonical version for the log header (docs/logging.md), resolved like
    // app-version.ts: VITE_APP_VERSION when CI injects it, else scripts/version.sh app.
    println!("cargo:rustc-env=JARVIS_APP_VERSION={}", app_version());
    println!("cargo:rerun-if-env-changed=VITE_APP_VERSION");
    // Re-resolve after a commit, checkout or tag (dirty edits alone don't re-run this).
    let dirs = [
        ("--git-dir", ["HEAD", "index"]),
        ("--git-common-dir", ["packed-refs", "refs/tags"]),
    ];
    for (flag, files) in dirs {
        if let Some(dir) = git(&["rev-parse", "--path-format=absolute", flag]) {
            for file in files {
                println!("cargo:rerun-if-changed={dir}/{file}");
            }
        }
    }
    // Only the webview's own commands, each behind a generated `allow-*` permission that
    // capabilities/default.json grants (ADR 0013).
    tauri_build::try_build(
        tauri_build::Attributes::new()
            .app_manifest(tauri_build::AppManifest::new().commands(&["minimize_window"])),
    )
    .expect("failed to run tauri-build");
}

fn app_version() -> String {
    if let Some(v) = std::env::var("VITE_APP_VERSION")
        .ok()
        .filter(|v| !v.is_empty())
    {
        return v;
    }
    Command::new("../../scripts/version.sh")
        .arg("app")
        .output()
        .ok()
        .filter(|out| out.status.success())
        .and_then(|out| {
            String::from_utf8_lossy(&out.stdout)
                .lines()
                .find_map(|l| l.strip_prefix("CANONICAL=").map(str::to_owned))
        })
        .unwrap_or_else(|| "dev".to_owned())
}

fn git(args: &[&str]) -> Option<String> {
    let out = Command::new("git").args(args).output().ok()?;
    out.status
        .success()
        .then(|| String::from_utf8_lossy(&out.stdout).trim().to_owned())
}
