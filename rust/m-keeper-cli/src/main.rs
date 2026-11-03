use std::env;
use std::path::{Path, PathBuf};
use std::process::Command;

const VERSION: &str = env!("CARGO_PKG_VERSION");
const DEFAULT_DB: &str = "accounts.json";

#[cfg(unix)]
fn is_executable(path: &Path) -> bool {
    use std::os::unix::fs::PermissionsExt;
    path.metadata()
        .map(|meta| meta.is_file() && meta.permissions().mode() & 0o111 != 0)
        .unwrap_or(false)
}

#[cfg(not(unix))]
fn is_executable(path: &Path) -> bool {
    path.is_file()
}

fn megatools_path() -> Option<PathBuf> {
    let path = env::var_os("PATH")?;
    env::split_paths(&path)
        // An empty PATH entry means the current directory; skip it so a local
        // file cannot shadow the real megatools binary.
        .filter(|dir| !dir.as_os_str().is_empty())
        .map(|dir| dir.join("megatools"))
        .find(|candidate| is_executable(candidate))
}

fn count_email_keys(contents: &str) -> usize {
    let bytes = contents.as_bytes();
    let mut count = 0;
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] != b'"' {
            i += 1;
            continue;
        }

        // Skip the whole JSON string, honouring backslash escapes, so that
        // text such as "\"email\": ..." inside a value is not counted.
        let start = i + 1;
        let mut j = start;
        let mut escaped = false;
        while j < bytes.len() {
            match bytes[j] {
                b'\\' if !escaped => {
                    escaped = true;
                    j += 1;
                }
                b'"' if !escaped => break,
                _ => {
                    escaped = false;
                    j += 1;
                }
            }
        }
        if j >= bytes.len() {
            break;
        }

        if &bytes[start..j] == b"email" {
            let mut k = j + 1;
            while k < bytes.len() && bytes[k].is_ascii_whitespace() {
                k += 1;
            }
            if k < bytes.len() && bytes[k] == b':' {
                count += 1;
            }
        }
        i = j + 1;
    }
    count
}

fn print_help() {
    println!("M-Keeper (Rust) {}", VERSION);
    println!("Usage: m-keeper-rs [doctor|--version]");
    println!();
    println!("Commands:");
    println!("  doctor    check the local environment");
    println!("  --version print the version");
}

fn doctor() {
    println!("M-Keeper doctor (rust)");
    match megatools_path() {
        Some(path) => {
            println!("megatools  : {}", path.display());
            match Command::new(&path).arg("--version").output() {
                Ok(out) if out.status.success() => {
                    let text = String::from_utf8_lossy(&out.stdout);
                    match text.lines().next() {
                        Some(line) => println!("version    : {}", line),
                        None => println!("version    : unknown"),
                    }
                }
                _ => println!("version    : unknown"),
            }
        }
        None => println!("megatools  : NOT FOUND"),
    }

    let db = env::var_os("M_KEEPER_DB")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(DEFAULT_DB));
    println!("database   : {}", db.display());
    match std::fs::read_to_string(&db) {
        Ok(contents) => println!("nodes      : {}", count_email_keys(&contents)),
        Err(_) => println!("nodes      : 0 (database missing)"),
    }
}

fn main() {
    let command = match env::args_os().nth(1) {
        Some(value) => value,
        None => {
            print_help();
            return;
        }
    };

    match command.to_str() {
        Some("--help") | Some("-h") => print_help(),
        Some("--version") | Some("-V") => println!("m-keeper-rs {}", VERSION),
        Some("doctor") => doctor(),
        Some(other) => {
            eprintln!("unknown command: {}", other);
            std::process::exit(2);
        }
        None => {
            eprintln!("unknown command: {}", command.to_string_lossy());
            std::process::exit(2);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{count_email_keys, is_executable};

    #[test]
    fn counts_email_keys_in_pretty_json() {
        let data = r#"[
  {
    "email": "a@example.com",
    "password": "p",
    "status": "Pending"
  }
]"#;
        assert_eq!(count_email_keys(data), 1);
    }

    #[test]
    fn ignores_email_text_that_is_not_a_key() {
        let data = r#"{"password": "email: nope", "email": "a@example.com"}"#;
        assert_eq!(count_email_keys(data), 1);
    }

    #[test]
    fn ignores_email_key_inside_an_escaped_string() {
        let data = r#"{"password": "\"email\": \"nope\"", "email": "a@example.com"}"#;
        assert_eq!(count_email_keys(data), 1);
    }

    #[test]
    fn counts_multiple_email_keys() {
        let data = r#"[{"email":"a@example.com"},{"email":"b@example.com"}]"#;
        assert_eq!(count_email_keys(data), 2);
    }

    #[test]
    fn ignores_email_key_without_a_colon() {
        let data = r#"{"email" "a@example.com"}"#;
        assert_eq!(count_email_keys(data), 0);
    }

    #[cfg(unix)]
    #[test]
    fn executable_check_requires_the_execute_bit() {
        use std::os::unix::fs::PermissionsExt;

        let path = std::env::temp_dir().join(format!("m-keeper-exec-test-{}", std::process::id()));
        std::fs::write(&path, b"#!/bin/sh\n").expect("write temporary file");

        let mut permissions = std::fs::metadata(&path).expect("stat").permissions();
        permissions.set_mode(0o644);
        std::fs::set_permissions(&path, permissions).expect("chmod 0644");
        assert!(!is_executable(&path));

        let mut permissions = std::fs::metadata(&path).expect("stat").permissions();
        permissions.set_mode(0o755);
        std::fs::set_permissions(&path, permissions).expect("chmod 0755");
        assert!(is_executable(&path));

        std::fs::remove_file(&path).expect("remove temporary file");
    }
}
