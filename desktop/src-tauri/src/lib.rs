use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandEvent;
use tauri::{Emitter, Manager};
use keyring::Entry;

const KEYRING_SERVICE: &str = "com.ysomp.journal-club";
const KEYRING_USER_EMAIL: &str = "huji_email";
const KEYRING_USER_PASSWORD: &str = "huji_password";
const KEYRING_CHROME_PROFILE: &str = "chrome_profile";

#[tauri::command]
fn get_huji_credentials() -> Result<(String, String, String), String> {
    let email = Entry::new(KEYRING_SERVICE, KEYRING_USER_EMAIL)
        .map_err(|e| e.to_string())?
        .get_password()
        .unwrap_or_default();
    let password = Entry::new(KEYRING_SERVICE, KEYRING_USER_PASSWORD)
        .map_err(|e| e.to_string())?
        .get_password()
        .unwrap_or_default();
    let chrome_profile = Entry::new(KEYRING_SERVICE, KEYRING_CHROME_PROFILE)
        .map_err(|e| e.to_string())?
        .get_password()
        .unwrap_or_default();
    Ok((email, password, chrome_profile))
}

#[tauri::command]
fn save_huji_credentials(email: String, password: String, chrome_profile: String) -> Result<(), String> {
    Entry::new(KEYRING_SERVICE, KEYRING_USER_EMAIL)
        .map_err(|e| e.to_string())?
        .set_password(&email)
        .map_err(|e| e.to_string())?;
    Entry::new(KEYRING_SERVICE, KEYRING_USER_PASSWORD)
        .map_err(|e| e.to_string())?
        .set_password(&password)
        .map_err(|e| e.to_string())?;
    Entry::new(KEYRING_SERVICE, KEYRING_CHROME_PROFILE)
        .map_err(|e| e.to_string())?
        .set_password(&chrome_profile)
        .map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
fn clear_huji_credentials() -> Result<(), String> {
    for key in &[KEYRING_USER_EMAIL, KEYRING_USER_PASSWORD, KEYRING_CHROME_PROFILE] {
        let _ = Entry::new(KEYRING_SERVICE, key)
            .map_err(|e| e.to_string())?
            .delete_credential();
    }
    Ok(())
}

#[derive(serde::Deserialize)]
pub struct DownloadCmd {
    pub input: String,
    pub queue_item_id: String,
    pub device_id: String,
    pub api_url: String,
    pub token: String,
    pub huji_email: String,
    pub huji_password: String,
    pub chrome_profile: String,
    pub chrome_path: String,
}

#[tauri::command]
async fn start_download(app: tauri::AppHandle, cmd: DownloadCmd) -> Result<(), String> {
    // Resolve path to sidecar Python script (relative to the app resource dir in production,
    // or the repo root in dev)
    let sidecar_path = {
        let resource_dir = app
            .path()
            .resource_dir()
            .map_err(|e: tauri::Error| e.to_string())?;
        resource_dir.join("sidecar").join("jc-download.py")
    };

    let sidecar_path_str = sidecar_path.to_string_lossy().to_string();

    let stdin_payload = serde_json::json!({
        "input":         cmd.input,
        "queue_item_id": cmd.queue_item_id,
        "device_id":     cmd.device_id,
        "api_url":       cmd.api_url,
        "token":         cmd.token,
        "huji_email":    cmd.huji_email,
        "huji_password": cmd.huji_password,
        "chrome_profile": cmd.chrome_profile,
        "chrome_path":   cmd.chrome_path,
        "output_dir":    std::env::temp_dir().join("jc_downloads").to_string_lossy(),
    });
    let stdin_bytes = serde_json::to_vec(&stdin_payload).map_err(|e| e.to_string())?;

    let (mut rx, mut child) = app
        .shell()
        .command("python3")
        .args([&sidecar_path_str])
        .spawn()
        .map_err(|e| e.to_string())?;

    // Write JSON config to stdin then close it
    child.write(&stdin_bytes).map_err(|e| e.to_string())?;

    // Stream stdout lines as Tauri events to the frontend
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    let _ = app.emit("download-progress", String::from_utf8_lossy(&line).to_string());
                }
                CommandEvent::Stderr(line) => {
                    let _ = app.emit("download-stderr", String::from_utf8_lossy(&line).to_string());
                }
                CommandEvent::Error(e) => {
                    let _ = app.emit("download-error", e);
                    break;
                }
                CommandEvent::Terminated(_) => break,
                _ => {}
            }
        }
    });

    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            start_download,
            get_huji_credentials,
            save_huji_credentials,
            clear_huji_credentials,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
