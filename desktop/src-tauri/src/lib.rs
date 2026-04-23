use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandEvent;
use tauri::{Emitter, Manager};
use std::path::PathBuf;

#[derive(serde::Serialize, serde::Deserialize, Default, Clone)]
struct StoredCreds {
    huji_email: String,
    huji_password: String,
    chrome_profile: String,
    app_username: String,
    app_password: String,
}

fn creds_path(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    app.path()
        .app_data_dir()
        .map(|d| d.join("credentials.json"))
        .map_err(|e| e.to_string())
}

fn load_stored_creds(app: &tauri::AppHandle) -> StoredCreds {
    let Ok(path) = creds_path(app) else { return StoredCreds::default(); };
    let Ok(data) = std::fs::read_to_string(&path) else { return StoredCreds::default(); };
    serde_json::from_str(&data).unwrap_or_default()
}

fn write_stored_creds(app: &tauri::AppHandle, creds: &StoredCreds) -> Result<(), String> {
    let path = creds_path(app)?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let data = serde_json::to_string(creds).map_err(|e| e.to_string())?;
    std::fs::write(&path, data).map_err(|e| e.to_string())
}

#[tauri::command]
fn get_huji_credentials(app: tauri::AppHandle) -> Result<(String, String, String), String> {
    let c = load_stored_creds(&app);
    Ok((c.huji_email, c.huji_password, c.chrome_profile))
}

#[tauri::command]
fn save_huji_credentials(app: tauri::AppHandle, email: String, password: String, chrome_profile: String) -> Result<(), String> {
    let mut c = load_stored_creds(&app);
    c.huji_email = email;
    c.huji_password = password;
    c.chrome_profile = chrome_profile;
    write_stored_creds(&app, &c)
}

#[tauri::command]
fn get_app_credentials(app: tauri::AppHandle) -> Result<(String, String), String> {
    let c = load_stored_creds(&app);
    Ok((c.app_username, c.app_password))
}

#[tauri::command]
fn save_app_credentials(app: tauri::AppHandle, username: String, password: String) -> Result<(), String> {
    let mut c = load_stored_creds(&app);
    c.app_username = username;
    c.app_password = password;
    write_stored_creds(&app, &c)
}

#[tauri::command]
fn clear_huji_credentials(app: tauri::AppHandle) -> Result<(), String> {
    let mut c = load_stored_creds(&app);
    c.huji_email = String::new();
    c.huji_password = String::new();
    c.chrome_profile = String::new();
    write_stored_creds(&app, &c)
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
    // Persistent per-user Playwright browser cache. Survives app updates so
    // Chromium is only downloaded on first run.
    let browsers_dir = app
        .path()
        .app_data_dir()
        .map_err(|e| e.to_string())?
        .join("browsers");
    std::fs::create_dir_all(&browsers_dir).map_err(|e| e.to_string())?;

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
        "browsers_dir":  browsers_dir.to_string_lossy(),
    });
    let stdin_bytes = serde_json::to_vec(&stdin_payload).map_err(|e| e.to_string())?;

    let (mut rx, mut child) = app
        .shell()
        .sidecar("jc-download")
        .map_err(|e| e.to_string())?
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
        .plugin(tauri_plugin_updater::Builder::new().build())
        .invoke_handler(tauri::generate_handler![
            start_download,
            get_huji_credentials,
            save_huji_credentials,
            clear_huji_credentials,
            get_app_credentials,
            save_app_credentials,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
