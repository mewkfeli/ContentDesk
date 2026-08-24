from __future__ import annotations
import json, shutil, sqlite3, tempfile
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from app.db.database import DB_PATH, get_connection, SCHEMA_VERSION
from app.logging_setup import LOG_PATH

router = APIRouter(prefix="/system", tags=["system"])

DEFAULTS = {
    "audit_max_pages": 200, "request_timeout": 15, "image_max_files": 60,
    "global_excludes": "/wp-admin/\n/wp-content/uploads/\n/feed/\n?utm_\n*.pdf\n*.zip",
    "confirm_destructive": True, "autosave_drafts": True,
}

class SettingsPayload(BaseModel):
    audit_max_pages: int = 200
    request_timeout: int = 15
    image_max_files: int = 60
    global_excludes: str = DEFAULTS["global_excludes"]
    confirm_destructive: bool = True
    autosave_drafts: bool = True


def log_activity(kind: str, title: str, detail: str = "", href: str = "", project_id: int | None = None):
    with get_connection() as conn:
        conn.execute("INSERT INTO activity_log(kind,title,detail,href,project_id) VALUES (?,?,?,?,?)", (kind,title,detail,href,project_id))
        conn.commit()

@router.get("/settings")
def get_settings():
    with get_connection() as conn:
        row = conn.execute("SELECT settings_json FROM app_settings WHERE id=1").fetchone()
    data = DEFAULTS.copy()
    if row:
        try: data.update(json.loads(row["settings_json"]))
        except Exception: pass
    return data

@router.put("/settings")
def save_settings(payload: SettingsPayload):
    data = payload.model_dump()
    with get_connection() as conn:
        conn.execute("UPDATE app_settings SET settings_json=?, updated_at=CURRENT_TIMESTAMP WHERE id=1", (json.dumps(data, ensure_ascii=False),))
        conn.commit()
    log_activity("settings", "Настройки ContentDesk обновлены")
    return data

@router.get("/diagnostics")
def diagnostics():
    db_ok = True
    try:
        with get_connection() as conn:
            conn.execute("SELECT 1").fetchone()
            schema = conn.execute("SELECT version FROM schema_meta WHERE id=1").fetchone()
    except Exception:
        db_ok = False; schema = None
    usage = shutil.disk_usage(DB_PATH.parent)
    return {
        "backend": True, "database": db_ok, "schema_version": schema["version"] if schema else None,
        "expected_schema_version": SCHEMA_VERSION, "db_path": str(DB_PATH), "db_size": DB_PATH.stat().st_size if DB_PATH.exists() else 0,
        "disk_free": usage.free, "disk_total": usage.total, "log_path": str(LOG_PATH), "log_size": LOG_PATH.stat().st_size if LOG_PATH.exists() else 0,
    }

@router.get("/activity")
def activity(limit: int = 20):
    limit = max(1, min(100, limit))
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM activity_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        if not rows:
            rows = conn.execute("""
              SELECT id, 'task' kind, title, 'Задача' detail, '/tasks/manage/'||id href, project_id, updated_at created_at FROM saved_tasks
              UNION ALL SELECT id, 'audit', 'SEO-аудит сайта', score||'/100 · '||pages_total||' стр.', '/site-audit/'||id, project_id, created_at FROM site_audits
              ORDER BY created_at DESC LIMIT ?
            """, (limit,)).fetchall()
    return [dict(x) for x in rows]

@router.get("/backup")
def backup():
    if not DB_PATH.exists(): raise HTTPException(404, "База ещё не создана")
    tmp = Path(tempfile.gettempdir()) / "contentdesk-backup.db"
    with sqlite3.connect(DB_PATH) as src, sqlite3.connect(tmp) as dst:
        src.backup(dst)
    log_activity("backup", "Создана резервная копия базы")
    return FileResponse(tmp, media_type="application/octet-stream", filename="contentdesk-backup.db")

@router.post("/restore")
async def restore(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith((".db", ".sqlite", ".sqlite3")):
        raise HTTPException(400, "Нужен файл резервной копии .db")
    content = await file.read()
    if len(content) < 100: raise HTTPException(400, "Файл слишком мал или повреждён")
    tmp = DB_PATH.with_suffix(".restore.tmp")
    tmp.write_bytes(content)
    try:
        conn = sqlite3.connect(tmp); conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone(); conn.close()
    except Exception as exc:
        tmp.unlink(missing_ok=True); raise HTTPException(400, "Это невалидная SQLite-база") from exc
    safety = DB_PATH.with_suffix(".before-restore.db")
    if DB_PATH.exists(): shutil.copy2(DB_PATH, safety)
    tmp.replace(DB_PATH)
    return {"ok": True, "message": "База восстановлена. Перезапусти backend ContentDesk."}

@router.get("/about")
def about():
    return {
        "name": "ContentDesk",
        "version": "2.8.0",
        "channel": "stable",
        "schema_version": SCHEMA_VERSION,
        "mode": "local",
    }

@router.get("/onboarding")
def onboarding_status():
    with get_connection() as conn:
        projects = conn.execute("SELECT COUNT(*) n FROM projects").fetchone()["n"]
        audits = conn.execute("SELECT COUNT(*) n FROM site_audits").fetchone()["n"]
        tasks = conn.execute("SELECT COUNT(*) n FROM saved_tasks").fetchone()["n"]
        conversations = conn.execute("SELECT COUNT(*) n FROM assistant_conversations").fetchone()["n"]
        meta = conn.execute("SELECT first_run_completed FROM app_release_meta WHERE id=1").fetchone()
    steps = [
        {"key": "project", "title": "Добавить проект", "done": projects > 0, "href": "/projects"},
        {"key": "audit", "title": "Запустить первый аудит", "done": audits > 0, "href": "/site-audit"},
        {"key": "task", "title": "Создать или сохранить задачу", "done": tasks > 0, "href": "/tasks"},
        {"key": "assistant", "title": "Открыть AI-ассистента", "done": conversations > 0, "href": "/assistant"},
    ]
    completed = sum(1 for step in steps if step["done"])
    return {
        "completed": completed,
        "total": len(steps),
        "progress": round(completed / len(steps) * 100),
        "dismissed": bool(meta["first_run_completed"]) if meta else False,
        "steps": steps,
    }

@router.post("/onboarding/complete")
def onboarding_complete():
    with get_connection() as conn:
        conn.execute("UPDATE app_release_meta SET first_run_completed=1, updated_at=CURRENT_TIMESTAMP WHERE id=1")
        conn.commit()
    log_activity("system", "Онбординг ContentDesk завершён")
    return {"ok": True}
