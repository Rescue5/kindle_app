use serde_json::{json, Value};
use std::io::Write;
use std::process::{Command, Stdio};

#[tauri::command]
fn python_bridge(action: String, payload: Value) -> Result<Value, String> {
    let python = std::env::var("KINDLE_CARDS_PYTHON").unwrap_or_else(|_| "python".to_string());
    let request = json!({
        "action": action,
        "payload": payload
    });

    let mut child = Command::new(python)
        .args(["-m", "kindle_vocab_app.tauri_bridge"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| format!("failed to start Python bridge: {error}"))?;

    if let Some(stdin) = child.stdin.as_mut() {
        stdin
            .write_all(request.to_string().as_bytes())
            .map_err(|error| format!("failed to write bridge request: {error}"))?;
    }

    let output = child
        .wait_with_output()
        .map_err(|error| format!("failed to read bridge response: {error}"))?;

    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    let response: Value = serde_json::from_str(stdout.trim())
        .map_err(|error| format!("invalid bridge JSON: {error}; stderr: {stderr}"))?;

    if response.get("ok").and_then(Value::as_bool).unwrap_or(false) {
        Ok(response.get("result").cloned().unwrap_or(Value::Null))
    } else {
        Err(response
            .get("error")
            .and_then(Value::as_str)
            .unwrap_or("unknown Python bridge error")
            .to_string())
    }
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![python_bridge])
        .run(tauri::generate_context!())
        .expect("error while running Kindle Cards");
}
