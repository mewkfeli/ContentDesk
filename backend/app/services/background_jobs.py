from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from app.db.database import get_connection

RUNNING_TASKS: dict[int, asyncio.Task[Any]] = {}
CANCEL_EVENTS: dict[int, asyncio.Event] = {}
JOB_SEMAPHORE = asyncio.Semaphore(2)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_job(kind: str, project_id: int | None, title: str, payload: dict[str, Any]) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO background_jobs (
                kind, project_id, title, status, progress_current, progress_total,
                message, payload_json, result_json, created_at, updated_at
            ) VALUES (?, ?, ?, 'queued', 0, 0, 'Ожидает запуска', ?, '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (kind, project_id, title, json.dumps(payload, ensure_ascii=False)),
        )
        conn.commit()
        return int(cursor.lastrowid)


def get_job(job_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT j.*, p.name AS project_name
            FROM background_jobs j LEFT JOIN projects p ON p.id=j.project_id
            WHERE j.id=?
            """,
            (job_id,),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    for key in ("payload_json", "result_json"):
        try:
            item[key.removesuffix("_json")] = json.loads(item.get(key) or "{}")
        except json.JSONDecodeError:
            item[key.removesuffix("_json")] = {}
        item.pop(key, None)
    return item


def list_jobs(limit: int = 30, active_only: bool = False) -> list[dict[str, Any]]:
    where = "WHERE j.status IN ('queued','running')" if active_only else ""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT j.*, p.name AS project_name
            FROM background_jobs j LEFT JOIN projects p ON p.id=j.project_id
            {where}
            ORDER BY CASE WHEN j.status='running' THEN 0 WHEN j.status='queued' THEN 1 ELSE 2 END, j.id DESC
            LIMIT ?
            """,
            (max(1, min(limit, 100)),),
        ).fetchall()
    return [get_job(int(row["id"])) for row in rows if row]


def update_job(job_id: int, **fields: Any) -> None:
    allowed = {
        "status", "progress_current", "progress_total", "message", "result_json",
        "started_at", "finished_at", "error",
    }
    pairs = [(key, value) for key, value in fields.items() if key in allowed]
    if not pairs:
        return
    columns = ", ".join(f"{key}=?" for key, _ in pairs)
    values = [value for _, value in pairs]
    values.append(job_id)
    with get_connection() as conn:
        conn.execute(f"UPDATE background_jobs SET {columns}, updated_at=CURRENT_TIMESTAMP WHERE id=?", values)
        conn.commit()


def mark_interrupted_jobs() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE background_jobs
            SET status='failed', error='ContentDesk был перезапущен во время выполнения',
                message='Прервано перезапуском', finished_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
            WHERE status IN ('queued','running')
            """
        )
        conn.commit()


def is_duplicate_active(kind: str, project_id: int | None) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id FROM background_jobs
            WHERE kind=? AND project_id IS ? AND status IN ('queued','running')
            ORDER BY id DESC LIMIT 1
            """,
            (kind, project_id),
        ).fetchone()
    return get_job(int(row["id"])) if row else None


def start_job(job_id: int, runner: Callable[[asyncio.Event, Callable[[int, int, str], Awaitable[None]]], Awaitable[dict[str, Any]]]) -> None:
    cancel_event = asyncio.Event()
    CANCEL_EVENTS[job_id] = cancel_event

    async def progress(current: int, total: int, message: str = "") -> None:
        update_job(job_id, progress_current=current, progress_total=total, message=message or "Выполняется")
        await asyncio.sleep(0)

    async def wrapper() -> None:
        try:
            async with JOB_SEMAPHORE:
                if cancel_event.is_set():
                    update_job(job_id, status="cancelled", message="Остановлено пользователем", finished_at=_now())
                    return
                update_job(job_id, status="running", started_at=_now(), message="Запущено")
                result = await runner(cancel_event, progress)
                if cancel_event.is_set():
                    update_job(job_id, status="cancelled", message="Остановлено пользователем", finished_at=_now())
                else:
                    update_job(
                        job_id,
                        status="completed",
                        message="Готово",
                        result_json=json.dumps(result, ensure_ascii=False),
                        finished_at=_now(),
                    )
        except asyncio.CancelledError:
            update_job(job_id, status="cancelled", message="Остановлено пользователем", finished_at=_now())
        except Exception as exc:  # noqa: BLE001 - error must be persisted for diagnostics
            update_job(job_id, status="failed", message="Ошибка", error=str(exc)[:1200], finished_at=_now())
        finally:
            RUNNING_TASKS.pop(job_id, None)
            CANCEL_EVENTS.pop(job_id, None)

    RUNNING_TASKS[job_id] = asyncio.create_task(wrapper(), name=f"contentdesk-job-{job_id}")


def cancel_job(job_id: int) -> bool:
    job = get_job(job_id)
    if not job or job["status"] not in {"queued", "running"}:
        return False
    event = CANCEL_EVENTS.get(job_id)
    if event:
        event.set()
    task = RUNNING_TASKS.get(job_id)
    if task and not task.done():
        task.cancel()
    else:
        update_job(job_id, status="cancelled", message="Остановлено пользователем", finished_at=_now())
    return True
