use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::{CommandEvent, CommandChild};
use tauri::{Emitter, Manager};
use std::path::PathBuf;
use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};

fn download_children() -> &'static Mutex<HashMap<String, CommandChild>> {
    static CHILDREN: OnceLock<Mutex<HashMap<String, CommandChild>>> = OnceLock::new();
    CHILDREN.get_or_init(|| Mutex::new(HashMap::new()))
}

fn chrome_pids() -> &'static Mutex<HashMap<String, u32>> {
    static PIDS: OnceLock<Mutex<HashMap<String, u32>>> = OnceLock::new();
    PIDS.get_or_init(|| Mutex::new(HashMap::new()))
}

fn chrome_profiles() -> &'static Mutex<HashMap<String, String>> {
    static PROFILES: OnceLock<Mutex<HashMap<String, String>>> = OnceLock::new();
    PROFILES.get_or_init(|| Mutex::new(HashMap::new()))
}

fn kill_chrome_pid(pid: u32) {
    let _ = std::process::Command::new("taskkill")
        .args(["/F", "/T", "/PID", &pid.to_string()])
        .output();
}

/// Kill all chrome.exe processes whose command line contains the profile directory name.
/// More robust than PID-based kill for Chrome's multi-process architecture.
fn kill_chrome_profile(profile: &str) {
    let profile_name = std::path::Path::new(profile)
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or(profile);
    let ps_cmd = format!(
        "$pids = (Get-CimInstance Win32_Process -Filter \"name='chrome.exe'\" \
         | Where-Object {{$_.CommandLine -like '*{}*'}}).ProcessId; \
         if ($pids) {{ $pids | ForEach-Object {{ & taskkill /F /T /PID $_ 2>$null }}; \
         Start-Sleep -Milliseconds 800 }}",
        profile_name.replace('\'', "\\'")
    );
    let _ = std::process::Command::new("powershell")
        .args(["-NoProfile", "-NonInteractive", "-Command", &ps_cmd])
        .output();
}

/// Kill all chrome.exe processes whose command line contains "jc-chrome-job-".
/// Handles the case where cancel arrives before chrome_pid JSON is emitted so
/// neither chrome_pids nor chrome_profiles maps have an entry yet.
fn kill_all_jc_chrome_sessions() {
    let ps_cmd = "$pids = (Get-CimInstance Win32_Process -Filter \"name='chrome.exe'\" \
        | Where-Object {$_.CommandLine -like '*jc-chrome-job-*'}).ProcessId; \
        if ($pids) { $pids | ForEach-Object { & taskkill /F /T /PID $_ 2>$null }; \
        Start-Sleep -Milliseconds 500 }";
    let _ = std::process::Command::new("powershell")
        .args(["-NoProfile", "-NonInteractive", "-Command", ps_cmd])
        .output();
}

/// Bring Chrome window to the foreground using Win32 SetForegroundWindow via PowerShell.
fn bring_chrome_to_front(pid: u32) {
    let ps_cmd = format!(
        "Add-Type -TypeDefinition @'\n\
         using System;\n\
         using System.Runtime.InteropServices;\n\
         public class WinHelper {{\n\
           [DllImport(\"user32.dll\")] public static extern bool SetForegroundWindow(IntPtr h);\n\
           [DllImport(\"user32.dll\")] public static extern bool ShowWindow(IntPtr h, int n);\n\
         }}\n\
         '@ -Language CSharp;\n\
         $p = Get-Process -Id {} -ErrorAction SilentlyContinue;\n\
         if ($p -and $p.MainWindowHandle -ne 0) {{\n\
           [WinHelper]::ShowWindow($p.MainWindowHandle, 9);\n\
           [WinHelper]::SetForegroundWindow($p.MainWindowHandle);\n\
         }}",
        pid
    );
    let _ = std::process::Command::new("powershell")
        .args(["-NoProfile", "-NonInteractive", "-Command", &ps_cmd])
        .spawn(); // fire-and-forget
}

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
fn open_pdf_external(app: tauri::AppHandle, bytes: Vec<u8>, filename: String) -> Result<(), String> {
    use tauri_plugin_opener::OpenerExt;
    let safe = filename
        .chars()
        .map(|c| if c.is_ascii_alphanumeric() || c == '.' || c == '-' || c == '_' { c } else { '_' })
        .collect::<String>();
    let name = if safe.to_lowercase().ends_with(".pdf") { safe } else { format!("{}.pdf", safe) };
    let dir = std::env::temp_dir().join("jc_pdf_view");
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let path = dir.join(&name);
    std::fs::write(&path, &bytes).map_err(|e| e.to_string())?;
    app.opener()
        .open_path(path.to_string_lossy().to_string(), None::<&str>)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn cancel_download(queue_item_id: String) -> Result<(), String> {
    // Kill Chrome: try PID-based kill first, then profile-based sweep
    let chrome_pid = chrome_pids().lock().ok().and_then(|mut m| m.remove(&queue_item_id));
    if let Some(pid) = chrome_pid {
        kill_chrome_pid(pid);
    }
    let chrome_profile = chrome_profiles().lock().ok().and_then(|mut m| m.remove(&queue_item_id));
    if let Some(ref profile) = chrome_profile {
        kill_chrome_profile(profile);
    }
    let child_opt = {
        let mut map = download_children().lock().map_err(|e| e.to_string())?;
        map.remove(&queue_item_id)
    };
    if let Some(child) = child_opt {
        child.kill().map_err(|e| e.to_string())?;
    }
    // Final sweep: catches any Chrome spawned before chrome_pid JSON was emitted
    kill_all_jc_chrome_sessions();
    Ok(())
}

#[tauri::command]
fn bring_download_to_front(queue_item_id: String) -> Result<(), String> {
    // Primary: use Win32 SetForegroundWindow via PowerShell (works even when
    // Windows focus-stealing prevention blocks normal window activation).
    if let Some(pid) = chrome_pids().lock().ok().and_then(|m| m.get(&queue_item_id).copied()) {
        bring_chrome_to_front(pid);
    }
    // Secondary: write bring_to_front command to sidecar stdin so Python can
    // also call page.bring_to_front() as a belt-and-suspenders measure.
    let mut map = download_children().lock().map_err(|e| e.to_string())?;
    if let Some(child) = map.get_mut(&queue_item_id) {
        let _ = child.write(b"{\"cmd\":\"bring_to_front\"}\n"); // best-effort
    }
    Ok(())
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
    // Append newline so the sidecar (which uses readline()) unblocks immediately.
    // tauri-plugin-shell's CommandChild has no close_stdin(), so we can't signal EOF.
    let mut stdin_bytes = serde_json::to_vec(&stdin_payload).map_err(|e| e.to_string())?;
    stdin_bytes.push(b'\n');

    let (mut rx, mut child) = app
        .shell()
        .sidecar("jc-download")
        .map_err(|e| e.to_string())?
        .spawn()
        .map_err(|e| e.to_string())?;

    // Write JSON config to stdin then close it
    child.write(&stdin_bytes).map_err(|e| e.to_string())?;

    // Register child so cancel_download can kill it
    let queue_item_id = cmd.queue_item_id.clone();
    if let Ok(mut map) = download_children().lock() {
        map.insert(queue_item_id.clone(), child);
    }

    // Stream stdout lines as Tauri events to the frontend
    let app_for_task = app.clone();
    let qid = queue_item_id.clone();
    tauri::async_runtime::spawn(async move {
        let app = app_for_task;
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    let line_str = String::from_utf8_lossy(&line).to_string();
                    // Intercept chrome_pid messages to track Chrome PID + profile for cleanup
                    if line_str.contains("\"chrome_pid\"") {
                        if let Ok(v) = serde_json::from_str::<serde_json::Value>(&line_str) {
                            if v.get("type").and_then(|t| t.as_str()) == Some("chrome_pid") {
                                if let Some(pid) = v.get("pid").and_then(|p| p.as_u64()) {
                                    if let Ok(mut map) = chrome_pids().lock() {
                                        map.insert(qid.clone(), pid as u32);
                                    }
                                }
                                if let Some(profile) = v.get("profile").and_then(|p| p.as_str()) {
                                    if let Ok(mut map) = chrome_profiles().lock() {
                                        map.insert(qid.clone(), profile.to_string());
                                    }
                                }
                            }
                        }
                    }
                    let _ = app.emit(&format!("download-progress-{}", qid), line_str);
                }
                CommandEvent::Stderr(line) => {
                    let _ = app.emit(&format!("download-stderr-{}", qid), String::from_utf8_lossy(&line).to_string());
                }
                CommandEvent::Error(e) => {
                    let _ = app.emit(&format!("download-error-{}", qid), e);
                    break;
                }
                CommandEvent::Terminated(payload) => {
                    // Always clean up Chrome when the sidecar exits (normal or forced)
                    let chrome_pid = chrome_pids().lock().ok().and_then(|mut m| m.remove(&qid));
                    if let Some(pid) = chrome_pid {
                        kill_chrome_pid(pid);
                    }
                    let chrome_profile = chrome_profiles().lock().ok().and_then(|mut m| m.remove(&qid));
                    if let Some(ref profile) = chrome_profile {
                        kill_chrome_profile(profile);
                    }
                    // Final sweep: catches Chrome if it was spawned before chrome_pid was emitted
                    kill_all_jc_chrome_sessions();
                    if payload.code != Some(0) {
                        let msg = serde_json::json!({
                            "type": "error",
                            "message": format!(
                                "Sidecar exited unexpectedly (code {:?}). Check stderr output above.",
                                payload.code
                            ),
                            "step": "process"
                        });
                        let _ = app.emit(&format!("download-progress-{}", qid), msg.to_string());
                    }
                    break;
                }
                _ => {}
            }
        }
        // Remove from registry once the process has exited
        if let Ok(mut map) = download_children().lock() {
            map.remove(&qid);
        }
        let _ = chrome_pids().lock().ok().map(|mut m| m.remove(&qid));
        let _ = chrome_profiles().lock().ok().map(|mut m| m.remove(&qid));
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
            cancel_download,
            bring_download_to_front,
            open_pdf_external,
            get_huji_credentials,
            save_huji_credentials,
            clear_huji_credentials,
            get_app_credentials,
            save_app_credentials,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
