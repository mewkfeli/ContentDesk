import json
from typing import Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.db.database import get_connection
from app.services.project_memory import remember_task
from app.services.task_parser import parse_docx, parse_task

router = APIRouter(prefix="/tasks", tags=["Tasks"])

TaskStatus = Literal["new", "in_progress", "done", "paused"]


class TaskParseRequest(BaseModel):
    text: str = Field(min_length=5, max_length=80000)
    project_names: list[str] = []


class SavedTaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    project_id: int | None = None
    project_name: str = Field(default="", max_length=120)
    priority: str = Field(default="Не указан", max_length=30)
    deadline: str = Field(default="Не указан", max_length=120)
    status: TaskStatus = "new"
    parsed: dict[str, Any]
    done_keys: list[str] = []
    resolved_urls: list[str] = []
    source_name: str = Field(default="", max_length=255)


class SavedTaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    project_id: int | None = None
    project_name: str | None = Field(default=None, max_length=120)
    priority: str | None = Field(default=None, max_length=30)
    deadline: str | None = Field(default=None, max_length=120)
    status: TaskStatus | None = None
    done_keys: list[str] | None = None
    resolved_urls: list[str] | None = None


def _deserialize(row) -> dict[str, Any]:
    item = dict(row)
    try:
        item["parsed"] = json.loads(item.pop("parsed_json"))
    except Exception:
        item["parsed"] = {}
    try:
        item["done_keys"] = json.loads(item.pop("done_json"))
    except Exception:
        item["done_keys"] = []
    try:
        item["resolved_urls"] = json.loads(item.pop("resolved_urls_json"))
    except Exception:
        item["resolved_urls"] = []
    return item


def _progress(parsed: dict[str, Any], done_keys: list[str]) -> tuple[int, int, int]:
    task_count = sum(len(group.get("items", [])) for group in parsed.get("role_groups", []))
    qa_count = len(parsed.get("qa_checklist", []))
    total = task_count + qa_count
    valid = {f"task-{item.get('id')}" for group in parsed.get("role_groups", []) for item in group.get("items", [])}
    valid.update({f"qa-{i}" for i, _ in enumerate(parsed.get("qa_checklist", []))})
    completed = len(set(done_keys) & valid)
    percent = round(completed / total * 100) if total else 0
    return completed, total, percent


@router.post("/parse")
def task_parse(payload: TaskParseRequest):
    try:
        return parse_task(payload.text, payload.project_names)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/parse-docx")
async def task_parse_docx(file: UploadFile = File(...), project_names: str = Form("")):
    if not (file.filename or "").lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Пока поддерживается загрузка только .docx")
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="DOCX слишком большой: максимум 15 МБ")
    names = [x.strip() for x in project_names.split("\n") if x.strip()]
    try:
        result = parse_docx(data, names)
        result["source_name"] = file.filename or ""
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Не удалось прочитать DOCX") from exc


@router.get("/saved")
def list_saved_tasks(task_status: TaskStatus | None = None, project_id: int | None = None):
    clauses: list[str] = []
    params: list[Any] = []
    if task_status:
        clauses.append("status = ?")
        params.append(task_status)
    if project_id is not None:
        clauses.append("project_id = ?")
        params.append(project_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_connection() as conn:
        rows = conn.execute(f"SELECT * FROM saved_tasks {where} ORDER BY updated_at DESC, id DESC", params).fetchall()
    result = []
    for row in rows:
        item = _deserialize(row)
        completed, total, percent = _progress(item["parsed"], item["done_keys"])
        result.append({
            "id": item["id"], "title": item["title"], "project_id": item["project_id"],
            "project_name": item["project_name"], "priority": item["priority"], "deadline": item["deadline"],
            "status": item["status"], "source_name": item["source_name"], "created_at": item["created_at"],
            "updated_at": item["updated_at"], "completed": completed, "total": total, "progress": percent,
        })
    return result


@router.post("/saved", status_code=status.HTTP_201_CREATED)
def create_saved_task(payload: SavedTaskCreate):
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO saved_tasks
            (title, project_id, project_name, priority, deadline, status, parsed_json, done_json, resolved_urls_json, source_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.title.strip(), payload.project_id, payload.project_name.strip(), payload.priority.strip(),
                payload.deadline.strip(), payload.status, json.dumps(payload.parsed, ensure_ascii=False),
                json.dumps(payload.done_keys, ensure_ascii=False), json.dumps(payload.resolved_urls, ensure_ascii=False),
                payload.source_name.strip(),
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM saved_tasks WHERE id = ?", (cursor.lastrowid,)).fetchone()
    item = _deserialize(row)
    remember_task(item.get("project_id"), item["id"], item["title"], item["status"], "создана")
    return item


@router.get("/saved/{task_id}")
def get_saved_task(task_id: int):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM saved_tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    item = _deserialize(row)
    completed, total, percent = _progress(item["parsed"], item["done_keys"])
    item.update({"completed": completed, "total": total, "progress": percent})
    return item


@router.patch("/saved/{task_id}")
def update_saved_task(task_id: int, payload: SavedTaskUpdate):
    values = payload.model_dump(exclude_unset=True)
    mapping = {
        "title": "title", "project_id": "project_id", "project_name": "project_name",
        "priority": "priority", "deadline": "deadline", "status": "status",
        "done_keys": "done_json", "resolved_urls": "resolved_urls_json",
    }
    updates: list[str] = []
    params: list[Any] = []
    for key, value in values.items():
        column = mapping[key]
        if key in {"done_keys", "resolved_urls"}:
            value = json.dumps(value, ensure_ascii=False)
        updates.append(f"{column} = ?")
        params.append(value)
    if not updates:
        return get_saved_task(task_id)
    updates.append("updated_at = CURRENT_TIMESTAMP")
    params.append(task_id)
    with get_connection() as conn:
        result = conn.execute(f"UPDATE saved_tasks SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    item = get_saved_task(task_id)
    event = "закрыта" if item.get("status") in {"done", "completed", "closed"} else "обновлена"
    remember_task(item.get("project_id"), item["id"], item["title"], item["status"], event)
    return item


@router.delete("/saved/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_task(task_id: int):
    with get_connection() as conn:
        result = conn.execute("DELETE FROM saved_tasks WHERE id = ?", (task_id,))
        conn.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Задача не найдена")

@router.get("/saved-export.csv")
def export_saved_tasks_csv():
    import csv, io
    from fastapi.responses import StreamingResponse
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM saved_tasks ORDER BY updated_at DESC, id DESC").fetchall()
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=';')
    writer.writerow(["ID","Проект","Задача","Приоритет","Срок","Статус","Выполнено","Всего","Прогресс","Обновлено"])
    labels = {"new":"Новая","in_progress":"В работе","paused":"Пауза","done":"Готово"}
    for row in rows:
        item = _deserialize(row)
        completed,total,percent = _progress(item["parsed"], item["done_keys"])
        writer.writerow([item["id"],item["project_name"],item["title"],item["priority"],item["deadline"],labels.get(item["status"],item["status"]),completed,total,f"{percent}%",item["updated_at"]])
    data = ('\ufeff' + buf.getvalue()).encode('utf-8')
    headers={"Content-Disposition":'attachment; filename="contentdesk-tasks.csv"'}
    return StreamingResponse(iter([data]), media_type="text/csv; charset=utf-8", headers=headers)
