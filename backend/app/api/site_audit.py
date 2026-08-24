from __future__ import annotations

import json
import csv
import io
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.db.database import get_connection
from app.services.site_audit import audit_site
from app.services.project_memory import remember_site_audit

router = APIRouter(prefix="/site-audits", tags=["Site audit"])


class SiteAuditRequest(BaseModel):
    project_id: int
    sitemap_url: str = Field(default="", max_length=2048)
    max_pages: int = Field(default=200, ge=1, le=500)


def _row_summary(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "sitemap_url": row["sitemap_url"],
        "score": row["score"],
        "pages_total": row["pages_total"],
        "pages_success": row["pages_success"],
        "critical": row["critical"],
        "warnings": row["warnings"],
        "recommendations": row["recommendations"],
        "created_at": row["created_at"],
    }


@router.post("/run")
async def run_site_audit(payload: SiteAuditRequest):
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
        result = await audit_site(project["domain"], sitemap, payload.max_pages, patterns)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO site_audits (
                project_id, sitemap_url, score, pages_total, pages_success,
                critical, warnings, recommendations, result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.project_id,
                result["sitemap_url"],
                result["score"],
                result["pages_total"],
                result["pages_success"],
                result["critical"],
                result["warnings"],
                result["recommendations"],
                json.dumps(result, ensure_ascii=False),
            ),
        )
        conn.commit()
        audit_id = int(cursor.lastrowid)

    remember_site_audit(payload.project_id, audit_id, result)
    return {"id": audit_id, "project_id": payload.project_id, "project_name": project["name"], **result}


@router.get("/overview")
def projects_audit_overview():
    with get_connection() as conn:
        projects = conn.execute("SELECT * FROM projects ORDER BY id DESC").fetchall()
        output = []
        for project in projects:
            latest = conn.execute(
                "SELECT * FROM site_audits WHERE project_id = ? ORDER BY id DESC LIMIT 1",
                (project["id"],),
            ).fetchone()
            previous = None
            if latest:
                previous = conn.execute(
                    "SELECT score FROM site_audits WHERE project_id = ? AND id < ? ORDER BY id DESC LIMIT 1",
                    (project["id"], latest["id"]),
                ).fetchone()
            item = dict(project)
            item["latest_audit"] = _row_summary(latest) if latest else None
            item["score_change"] = (latest["score"] - previous["score"]) if latest and previous else None
            output.append(item)
    return output


@router.get("/project/{project_id}")
def project_audit_history(project_id: int):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM site_audits WHERE project_id = ? ORDER BY id DESC LIMIT 20",
            (project_id,),
        ).fetchall()
    return [_row_summary(row) for row in rows]


@router.get("/{audit_id}")
def get_site_audit(audit_id: int):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT a.*, p.name AS project_name, p.domain AS project_domain
            FROM site_audits a JOIN projects p ON p.id = a.project_id
            WHERE a.id = ?
            """,
            (audit_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Аудит не найден")
    result = json.loads(row["result_json"])
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "project_name": row["project_name"],
        "project_domain": row["project_domain"],
        "created_at": row["created_at"],
        **result,
    }


@router.get("/{audit_id}/export.csv")
def export_site_audit_csv(audit_id: int):
    with get_connection() as conn:
        row = conn.execute("SELECT a.*, p.name project_name FROM site_audits a JOIN projects p ON p.id=a.project_id WHERE a.id=?", (audit_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Аудит не найден")
    result = json.loads(row["result_json"])
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=';')
    writer.writerow(["URL","HTTP","SEO Score","Content Score","Title","Description","H1","H1 count","H2","H3","Words","Paragraphs","Internal links","Images","Missing ALT","FAQ","CTA","Issues"])
    for page in result.get("pages", []):
        writer.writerow([page.get("url",""),page.get("status_code",""),page.get("score",""),page.get("content_score",""),page.get("title",""),page.get("description",""),page.get("h1",""),page.get("h1_count",0),page.get("h2_count",0),page.get("h3_count",0),page.get("word_count",0),page.get("paragraphs",0),page.get("internal_links",0),page.get("images",0),page.get("missing_alt",0),"да" if page.get("has_faq") else "нет","да" if page.get("has_cta") else "нет"," | ".join(i.get("label","") for i in page.get("issues",[]))])
    data = ('\ufeff' + buf.getvalue()).encode('utf-8')
    headers={"Content-Disposition":f'attachment; filename="site-audit-{audit_id}.csv"'}
    return StreamingResponse(iter([data]), media_type="text/csv; charset=utf-8", headers=headers)

@router.get("/{audit_id}/export.html")
def export_site_audit_html(audit_id: int):
    import html
    from fastapi.responses import HTMLResponse
    with get_connection() as conn:
        row = conn.execute("SELECT a.*, p.name project_name, p.domain project_domain FROM site_audits a JOIN projects p ON p.id=a.project_id WHERE a.id=?", (audit_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Аудит не найден")
    result = json.loads(row["result_json"])
    pages = result.get("pages", [])
    page_rows = []
    for page in pages:
        issues = ", ".join(i.get("label", "") for i in page.get("issues", [])) or "—"
        page_rows.append(
            "<tr>"
            f"<td><a href='{html.escape(page.get('url',''))}'>{html.escape(page.get('url',''))}</a></td>"
            f"<td>{html.escape(str(page.get('status_code','')))}</td>"
            f"<td><strong>{html.escape(str(page.get('score','')))}</strong></td>"
            f"<td><strong>{html.escape(str(page.get('content_score','—')))}</strong></td>"
            f"<td>{html.escape(page.get('title','') or '—')}</td>"
            f"<td>{html.escape(page.get('h1','') or '—')}</td>"
            f"<td>{html.escape(issues)}</td>"
            "</tr>"
        )
    body = f"""<!doctype html><html lang='ru'><head><meta charset='utf-8'><title>SEO-аудит — {html.escape(row['project_name'])}</title>
<style>body{{font-family:Arial,sans-serif;margin:40px;color:#171717}}h1{{margin-bottom:4px}}.muted{{color:#666}}.kpis{{display:flex;gap:12px;margin:28px 0}}.kpi{{border:1px solid #ddd;border-radius:12px;padding:16px 20px;min-width:120px}}.kpi strong{{display:block;font-size:26px}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{border-bottom:1px solid #e5e5e5;text-align:left;padding:10px;vertical-align:top}}th{{background:#f7f7f7;position:sticky;top:0}}a{{color:#1769aa;text-decoration:none}}@media print{{body{{margin:15mm}}th{{position:static}}}}</style></head><body>
<h1>SEO-аудит: {html.escape(row['project_name'])}</h1><div class='muted'>{html.escape(row['project_domain'])} · {html.escape(str(row['created_at']))}</div>
<div class='kpis'><div class='kpi'><span>SEO Score</span><strong>{row['score']}/100</strong></div><div class='kpi'><span>Наполненность</span><strong>{result.get('content_score','—')}/100</strong></div><div class='kpi'><span>Страниц</span><strong>{row['pages_total']}</strong></div><div class='kpi'><span>Критично</span><strong>{row['critical']}</strong></div><div class='kpi'><span>Предупреждения</span><strong>{row['warnings']}</strong></div></div>
<table><thead><tr><th>URL</th><th>HTTP</th><th>SEO</th><th>Контент</th><th>Title</th><th>H1</th><th>Проблемы</th></tr></thead><tbody>{''.join(page_rows)}</tbody></table>
<p class='muted'>Сформировано ContentDesk 2.7.2</p></body></html>"""
    headers = {"Content-Disposition": f'attachment; filename="site-audit-{audit_id}.html"'}
    return HTMLResponse(body, headers=headers)
