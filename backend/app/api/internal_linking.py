from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db.database import get_connection
from app.services.internal_linking import analyze_internal_links
from app.services.project_memory import remember_linking_audit

router = APIRouter(prefix="/internal-linking", tags=["Internal linking"])


class InternalLinkingRequest(BaseModel):
    project_id: int
    sitemap_url: str = Field(default="", max_length=2048)
    max_pages: int = Field(default=200, ge=1, le=500)


def _summary(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "score": row["score"],
        "pages_total": row["pages_total"],
        "links_total": row["links_total"],
        "orphans": row["orphans"],
        "broken_links": row["broken_links"],
        "created_at": row["created_at"],
    }


@router.post("/run")
async def run_internal_linking(payload: InternalLinkingRequest):
    with get_connection() as conn:
        project = conn.execute("SELECT * FROM projects WHERE id = ?", (payload.project_id,)).fetchone()
    if not project:
        raise HTTPException(status_code=404, detail="Проект не найден")

    try:
        with get_connection() as settings_conn:
            settings_row = settings_conn.execute("SELECT settings_json FROM app_settings WHERE id=1").fetchone()
        settings = json.loads(settings_row["settings_json"]) if settings_row else {}
        patterns = [x for x in (settings.get("global_excludes", "") + "\n" + (project["exclude_patterns"] or "")).splitlines() if x.strip()]
        sitemap = payload.sitemap_url or project["sitemap_url"] or ""
        result = await analyze_internal_links(project["domain"], sitemap, payload.max_pages, patterns)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO internal_link_audits (
                project_id, sitemap_url, score, pages_total, links_total, orphans, broken_links, result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.project_id,
                result["sitemap_url"],
                result["score"],
                result["pages_total"],
                result["links_total"],
                result["orphans"],
                result["broken_links_count"],
                json.dumps(result, ensure_ascii=False),
            ),
        )
        conn.commit()
        report_id = int(cursor.lastrowid)

    remember_linking_audit(payload.project_id, report_id, result)
    return {"id": report_id, "project_id": payload.project_id, "project_name": project["name"], **result}


@router.get("/project/{project_id}")
def project_history(project_id: int):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM internal_link_audits WHERE project_id = ? ORDER BY id DESC LIMIT 20",
            (project_id,),
        ).fetchall()
    return [_summary(row) for row in rows]


@router.get("/{report_id}")
def get_report(report_id: int):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT a.*, p.name AS project_name, p.domain AS project_domain
            FROM internal_link_audits a JOIN projects p ON p.id = a.project_id
            WHERE a.id = ?
            """,
            (report_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Отчёт перелинковки не найден")
    result = json.loads(row["result_json"])
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "project_name": row["project_name"],
        "project_domain": row["project_domain"],
        "created_at": row["created_at"],
        **result,
    }
