use serde_json::{json, Value};
use std::collections::HashMap;
use std::io::{BufRead, BufReader, Read, Write};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;
use tauri::{AppHandle, Emitter, State};

const PROGRESS_PREFIX: &str = "KINDLE_PROGRESS ";

#[derive(Default)]
struct OperationState {
    cancellation: Mutex<HashMap<String, Arc<AtomicBool>>>,
}

#[tauri::command]
fn python_bridge(
    app: AppHandle,
    operations: State<'_, OperationState>,
    action: String,
    payload: Value,
) -> Result<Value, String> {
    let python = std::env::var("KINDLE_CARDS_PYTHON").unwrap_or_else(|_| "python".to_string());
    let workspace = workspace_dir().map_err(|error| format!("failed to resolve workspace directory: {error}"))?;
    let job_id = payload
        .get("job_id")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string();
    let request = json!({
        "action": action,
        "payload": payload
    });

    let cancellation = Arc::new(AtomicBool::new(false));
    if !job_id.is_empty() {
        operations
            .cancellation
            .lock()
            .map_err(|_| "operation registry is poisoned".to_string())?
            .insert(job_id.clone(), Arc::clone(&cancellation));
    }

    let result = run_python_bridge(app, python, workspace, request, &cancellation);
    if !job_id.is_empty() {
        if let Ok(mut registry) = operations.cancellation.lock() {
            registry.remove(&job_id);
        }
    }
    result
}

fn run_python_bridge(
    app: AppHandle,
    python: String,
    workspace: PathBuf,
    request: Value,
    cancellation: &AtomicBool,
) -> Result<Value, String> {
    let mut child = Command::new(python)
        .args(["-m", "kindle_vocab_app.tauri_bridge"])
        .current_dir(&workspace)
        .env("KINDLE_CARDS_WORKSPACE", &workspace)
        .env("PYTHONUTF8", "1")
        .env("PYTHONIOENCODING", "utf-8")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| format!("failed to start Python bridge: {error}"))?;

    if let Some(mut stdin) = child.stdin.take() {
        stdin
            .write_all(request.to_string().as_bytes())
            .map_err(|error| format!("failed to write bridge request: {error}"))?;
    }

    let stdout = child.stdout.take().ok_or_else(|| "missing Python stdout".to_string())?;
    let stderr = child.stderr.take().ok_or_else(|| "missing Python stderr".to_string())?;
    let stdout_reader = thread::spawn(move || {
        let mut text = String::new();
        BufReader::new(stdout).read_to_string(&mut text).map(|_| text)
    });
    let stderr_reader = thread::spawn(move || {
        let mut diagnostics = Vec::new();
        for line in BufReader::new(stderr).lines() {
            let line = line?;
            if let Some(raw) = line.strip_prefix(PROGRESS_PREFIX) {
                if let Ok(progress) = serde_json::from_str::<Value>(raw) {
                    let _ = app.emit("backend-progress", progress);
                    continue;
                }
            }
            diagnostics.push(line);
        }
        Ok::<String, std::io::Error>(diagnostics.join("\n"))
    });

    let status = loop {
        if cancellation.load(Ordering::SeqCst) {
            let _ = child.kill();
            let _ = child.wait();
            let _ = stdout_reader.join();
            let _ = stderr_reader.join();
            return Err("Операция отменена".to_string());
        }
        match child.try_wait() {
            Ok(Some(status)) => break status,
            Ok(None) => thread::sleep(Duration::from_millis(40)),
            Err(error) => return Err(format!("failed to poll Python bridge: {error}")),
        }
    };

    let stdout = stdout_reader
        .join()
        .map_err(|_| "Python stdout reader panicked".to_string())?
        .map_err(|error| format!("failed to read Python stdout: {error}"))?;
    let stderr = stderr_reader
        .join()
        .map_err(|_| "Python stderr reader panicked".to_string())?
        .map_err(|error| format!("failed to read Python stderr: {error}"))?;

    let response: Value = serde_json::from_str(stdout.trim())
        .map_err(|error| format!("invalid bridge JSON: {error}; stderr: {stderr}"))?;
    if !status.success() && response.get("ok").and_then(Value::as_bool).unwrap_or(false) {
        return Err(format!("Python bridge exited with {status}; stderr: {stderr}"));
    }
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

#[tauri::command]
fn cancel_python_bridge(job_id: String, operations: State<'_, OperationState>) -> Result<bool, String> {
    let registry = operations
        .cancellation
        .lock()
        .map_err(|_| "operation registry is poisoned".to_string())?;
    if let Some(token) = registry.get(&job_id) {
        token.store(true, Ordering::SeqCst);
        return Ok(true);
    }
    Ok(false)
}

fn workspace_dir() -> Result<PathBuf, std::io::Error> {
    if let Ok(value) = std::env::var("KINDLE_CARDS_WORKSPACE") {
        return Ok(PathBuf::from(value));
    }
    let current = std::env::current_dir()?;
    if current.file_name().is_some_and(|name| name == "src-tauri") {
        if let Some(parent) = current.parent() {
            return Ok(parent.to_path_buf());
        }
    }
    Ok(current)
}

fn main() {
    tauri::Builder::default()
        .manage(OperationState::default())
        .invoke_handler(tauri::generate_handler![python_bridge, cancel_python_bridge])
        .run(tauri::generate_context!())
        .expect("error while running Kindle Cards");
}
