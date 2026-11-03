use std::env;
use std::path::PathBuf;
use std::process::Command;

const VERSION: &str = env!("CARGO_PKG_VERSION");

fn megatools_path() -> Option<PathBuf> {
    let path = env::var_os("PATH")?;
    env::split_paths(&path)
        .map(|dir| dir.join("megatools"))
        .find(|candidate| candidate.is_file())
}

fn count_email_keys(contents: &str) -> usize {
    let bytes = contents.as_bytes();
    let needle = b"\"email\"";
    let mut count = 0;
    let mut i = 0;
    while i + needle.len() <= bytes.len() {
        if &bytes[i..i + needle.len()] == needle {
            let mut j = i + needle.len();
            while j < bytes.len() && (bytes[j] as char).is_whitespace() {
                j += 1;
            }
            if j < bytes.len() && bytes[j] == b':' {
                count += 1;
            }
        }
        i += 1;
    }
    count
}

fn main() {
    let args: Vec<String> = env::args().collect();

    if args.len() < 2 || args[1] == "--help" || args[1] == "-h" {
        println!("M-Keeper (Rust) {}", VERSION);
        println!("Usage: m-keeper-rs [doctor|--version]");
        println!();
        println!("Commands:");
        println!("  doctor    check the local environment");
        println!("  --version print the version");
        return;
    }

    match args[1].as_str() {
        "--version" | "-V" => println!("m-keeper-rs {}", VERSION),
        "doctor" => {
            println!("M-Keeper doctor (rust)");
            if let Some(path) = megatools_path() {
                println!("megatools  : {}", path.display());
                let out = Command::new("megatools").arg("--version").output();
                match out {
                    Ok(o) if o.status.success() => {
                        let text = String::from_utf8_lossy(&o.stdout);
                        if let Some(line) = text.lines().next() {
                            println!("version    : {}", line);
                        }
                    }
                    _ => println!("version    : unknown"),
                }
            } else {
                println!("megatools  : NOT FOUND");
            }
            let db = env::var("M_KEEPER_DB").unwrap_or_else(|_| "accounts.json".to_string());
            println!("database   : {}", db);
            if let Ok(contents) = std::fs::read_to_string(&db) {
                println!("nodes      : {}", count_email_keys(&contents));
            } else {
                println!("nodes      : 0 (database missing)");
            }
        }
        other => {
            eprintln!("unknown command: {}", other);
            std::process::exit(2);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::count_email_keys;

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
}
