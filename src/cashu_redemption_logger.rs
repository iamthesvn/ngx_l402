use log::error;
use std::io::Write;
use std::sync::atomic::{AtomicBool, Ordering};

const LOG_FILE_PATH: &str = "/var/log/nginx/cashu_redemption.log";

/// Whether the "cannot open" error has been reported. The redemption loop calls
/// this many times a cycle, and one unreadable path should not fill the log.
static OPEN_FAILURE_REPORTED: AtomicBool = AtomicBool::new(false);

/// Create the log file and give it to the user the workers run as.
///
/// Called from `init_module`, in the master: the log directory is root-owned,
/// but redemption writes from a worker. Ownership follows the Cashu data
/// directory, which the operator already sets — the same rule the database uses.
pub fn prepare_log_file(data_dir_owner: Option<(u32, u32)>) {
    // Ownership and mode are applied to the open descriptor, never to the path:
    // a path-based chown/chmod resolves symlinks, so anyone able to pre-create
    // LOG_FILE_PATH as a link could redirect them onto an arbitrary file.
    let file = match std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(LOG_FILE_PATH)
    {
        Ok(file) => file,
        Err(e) => {
            error!("Cannot create {}: {}", LOG_FILE_PATH, e);
            return;
        }
    };

    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if let Some((uid, gid)) = data_dir_owner {
            let _ = std::os::unix::fs::fchown(&file, Some(uid), Some(gid));
        }
        let _ = file.set_permissions(std::fs::Permissions::from_mode(0o640));
    }
}

/// Helper function to log Cashu redemption task messages to a dedicated file.
/// If file logging fails, errors are logged to the nginx error log.
///
/// `msg` is sanitised before writing: all control characters are stripped to
/// prevent log-injection attacks.
pub fn log_redemption(msg: &str) {
    // Strip every control character rather than an explicit blocklist. Beyond
    // the obvious CR/LF (forged log lines), NUL (entry truncation), ESC (ANSI
    // sequences) and TAB (column injection), this also covers DEL, the rest of
    // C0, and the C1 range — any of which can corrupt a log viewer or parser.
    let sanitised: String = msg.chars().filter(|c| !c.is_control()).collect();

    match std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(LOG_FILE_PATH)
    {
        Ok(mut file) => {
            let timestamp = chrono::Local::now().format("%Y-%m-%d %H:%M:%S");
            if let Err(e) = writeln!(file, "[{}] {}", timestamp, sanitised) {
                error!("Failed to write to cashu redemption log: {}", e);
            }
        }
        Err(e) => {
            // Once only: this runs every redemption cycle.
            if !OPEN_FAILURE_REPORTED.swap(true, Ordering::Relaxed) {
                error!(
                    "Failed to open cashu redemption log file {}: {} — redemption continues, \
                     progress is in the nginx error log",
                    LOG_FILE_PATH, e
                );
            }
        }
    }
}
