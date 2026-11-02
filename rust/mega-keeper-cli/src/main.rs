use std::env;
use std::process::Command;

fn megatools_path() -> Option<String> {
    let out = Command::new("command").arg("-v").arg("megatools").output().ok()?;
    if out.status.success() {
        Some(String::from_utf8_lossy(&out.stdout).trim().to_string())
    } else {
        None
    }
}

fn main() {
    let args: Vec<String> = env::args().collect();

    if args.len() < 2 || args[1] == "--help" || args[1] == "-h" {
        println!("Mega-Keeper (Rust) 2.0.0");
        println!("Usage: mega-keeper-rs [doctor|--version]");
        println!();
        println!("Commands:");
        println!("  doctor    check the local environment");
        println!("  --version print the version");
        return;
    }

    match args[1].as_str() {
        "--version" | "-V" => println!("mega-keeper-rs 2.0.0"),
        "doctor" => {
            println!("Mega-Keeper doctor (rust)");
            if let Some(path) = megatools_path() {
                println!("megatools  : {}", path);
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
            let db = env::var("MEGA_KEEPER_DB").unwrap_or_else(|_| "accounts.json".to_string());
            println!("database   : {}", db);
            if let Ok(contents) = std::fs::read_to_string(&db) {
                let count = contents.matches("\"email\"").count();
                println!("nodes      : {}", count);
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