from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db.database import get_connection
from app.services.background_jobs import (
    cancel_job,
    create_job,
    get_job,
    is_duplicate_active,
    list_jobs,
    start_job,
)
from app.services.internal_linking import analyze_internal_links
from app.services.site_audit import audit_site
from app.services.indexing_check import run_indexing_check
from app.services.meta_description_audit import run_meta_description_audit
from app.services.project_memory import remember_site_audit, remember_linking_audit, remember_indexing, remember_meta_audit

router = APIRouter(prefix="/jobs", tags=["Background jobs"])


class JobLaunchRequest(BaseModel):
    project_id: int
    sitemap_url: str = Field(default="", max_length=2048)
    max_pages: int = Field(default=200, ge=1, le=500)

class IndexingJobLaunchRequest(BaseModel):
    project_id: int
    urls: list[str] = Field(min_length=1, max_length=2000)
    source_name: str = Field(default="", max_length=255)
    sitemap_url: str = Field(default="", max_length=2048)
    max_pages: int = Field(default=500, ge=1, le=1000)
    import_summary: dict[str, Any] = Field(default_factory=dict)

class MetaDescriptionJobLaunchRequest(BaseModel):
    project_id: int
    urls: list[str] = Field(min_length=1, max_length=5000)
    source_name: str = Field(default="", max_length=255)
    sitemap_url: str = Field(default="", max_length=2048)


def _project_and_options(payload: JobLaunchRequest) -> tuple[Any, list[str], str]:
    with get_connection() as conn:
        project = conn.execute("SELECT * FROM projects WHERE id=?", (payload.project_id,)).fetchone()
        settings_row = conn.execute("SELECT settings_json FROM app_settings WHERE id=1").fetchone()
    if not project:
        raise HTTPException(status_code=404, detail="Проект не найден")
    settings = json.loads(settings_row["settings_json"]) if settings_row else {}
    patterns = [
        x.strip()
        for x in (settings.get("global_excludes", "") + "\n" + (project["exclude_patterns"] or "")).splitlines()
        if x.strip()
    ]
    sitemap = payload.sitemap_url or project["sitemap_url"] or ""
    return project, patterns, sitemap


async def _save_site_audit(project: Any, payload: JobLaunchRequest, patterns: list[str], sitemap: str, cancel_event, progress) -> dict[str, Any]:
    result = await audit_site(
        project["domain"], sitemap, payload.max_pages, patterns,
        progress_callback=progress, cancel_event=cancel_event,
    )
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO site_audits (
                project_id, sitemap_url, score, pages_total, pages_success,
                critical, warnings, recommendations, result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.project_id, result["sitemap_url"], result["score"], result["pages_total"],
                result["pages_success"], result["critical"], result["warnings"], result["recommendations"],
                json.dumps(result, ensure_ascii=False),
            ),
        )
        report_id = int(cursor.lastrowid)
        conn.execute(
            "INSERT INTO activity_log(kind,title,detail,href,project_id) VALUES ('site_audit',?,?,?,?)",
            (f"Аудит сайта: {project['name']}", f"{result['score']}/100 · {result['pages_total']} стр.", f"/site-audit/{report_id}", payload.project_id),
        )
        conn.commit()
    remember_site_audit(payload.project_id, report_id, result)
    return {"report_id": report_id, "href": f"/site-audit/{report_id}", "score": result["score"], "pages_total": result["pages_total"]}


async def _save_internal_linking(project: Any, payload: JobLaunchRequest, patterns: list[str], sitemap: str, cancel_event, progress) -> dict[str, Any]:
    result = await analyze_internal_links(
        project["domain"], sitemap, payload.max_pages, patterns,
        progress_callback=progress, cancel_event=cancel_event,
    )
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO internal_link_audits (
                project_id, sitemap_url, score, pages_total, links_total, orphans, broken_links, result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.project_id, result["sitemap_url"], result["score"], result["pages_total"],
                result["links_total"], result["orphans"], result["broken_links_count"],
                json.dumps(result, ensure_ascii=False),
            ),
        )
        report_id = int(cursor.lastrowid)
        conn.execute(
            "INSERT INTO activity_log(kind,title,detail,href,project_id) VALUES ('linking',?,?,?,?)",
            (f"Перелинковка: {project['name']}", f"{result['score']}/100 · {result['pages_total']} стр.", f"/linking/{report_id}", payload.project_id),
        )
        conn.commit()
    remember_linking_audit(payload.project_id, report_id, result)
    return {"report_id": report_id, "href": f"/linking/{report_id}", "score": result["score"], "pages_total": result["pages_total"]}


async def _save_indexing_check(project: Any, payload: IndexingJobLaunchRequest, patterns: list[str], sitemap: str, cancel_event, progress) -> dict[str, Any]:
    result = await run_indexing_check(
        domain=project["domain"], urls=payload.urls, sitemap_url=sitemap, max_pages=payload.max_pages,
        exclude_patterns=patterns, progress_callback=progress, cancel_event=cancel_event,
    )
    result["source_name"] = payload.source_name
    result["import_summary"] = payload.import_summary
    counts = result.get("status_counts", {})
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO indexing_checks (
                project_id, source_name, sitemap_url, urls_total, ok_count, content_count, developer_count, insufficient_count, result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (payload.project_id, payload.source_name, result.get("sitemap_url", ""), result.get("urls_total", 0),
             counts.get("ok", 0), counts.get("content", 0), counts.get("developer", 0), counts.get("insufficient", 0),
             json.dumps(result, ensure_ascii=False)),
        )
        report_id = int(cursor.lastrowid)
        conn.execute(
            "INSERT INTO activity_log(kind,title,detail,href,project_id) VALUES ('indexing_check',?,?,?,?)",
            (f"Проверка индексации: {project['name']}",
             f"{result.get('urls_total', 0)} URL · {counts.get('developer', 0)} разработчику · {counts.get('content', 0)} контент",
             f"/audit/indexing/{report_id}", payload.project_id),
        )
        conn.commit()
    remember_indexing(payload.project_id, report_id, result)
    return {"report_id": report_id, "href": f"/audit/indexing/{report_id}", "urls_total": result.get("urls_total", 0)}


async def _save_meta_description_audit(project: Any, payload: MetaDescriptionJobLaunchRequest, sitemap: str, cancel_event, progress) -> dict[str, Any]:
    result = await run_meta_description_audit(project["domain"], payload.urls, source_name=payload.source_name, sitemap_url=sitemap, progress_callback=progress, cancel_event=cancel_event)
    counts = result.get("status_counts", {})
    with get_connection() as conn:
        cursor = conn.execute("""INSERT INTO meta_description_audits (project_id,source_name,sitemap_url,urls_total,ok_count,review_count,replace_count,technical_count,result_json) VALUES (?,?,?,?,?,?,?,?,?)""",
            (payload.project_id,payload.source_name,sitemap,result.get("urls_total",0),counts.get("ok",0),counts.get("review",0),counts.get("replace",0),counts.get("technical",0)+counts.get("broken",0),json.dumps(result,ensure_ascii=False)))
        report_id=int(cursor.lastrowid)
        conn.execute("INSERT INTO activity_log(kind,title,detail,href,project_id) VALUES ('meta_description_audit',?,?,?,?)",
            (f"Аудит Meta Description: {project['name']}",f"{result.get('urls_total',0)} URL · {counts.get('replace',0)} контент · {counts.get('template',0)} шаблон · {counts.get('broken',0)} HTTP · {counts.get('technical',0)} технические",f"/audit/descriptions/{report_id}",payload.project_id))
        conn.commit()
    remember_meta_audit(payload.project_id, report_id, result)
    return {"report_id":report_id,"href":f"/audit/descriptions/{report_id}","urls_total":result.get("urls_total",0)}

def _launch_meta_description(payload: MetaDescriptionJobLaunchRequest) -> dict[str, Any]:
    project, _, sitemap = _project_and_options(JobLaunchRequest(project_id=payload.project_id,sitemap_url=payload.sitemap_url,max_pages=200))
    duplicate=is_duplicate_active("meta_description_audit",payload.project_id)
    if duplicate: return {**duplicate,"duplicate":True}
    job_id=create_job("meta_description_audit",payload.project_id,f"Аудит Meta Description: {project['name']}",payload.model_dump())
    async def runner(cancel_event,progress):
        return await _save_meta_description_audit(project,payload,sitemap,cancel_event,progress)
    start_job(job_id,runner)
    return get_job(job_id) or {"id":job_id}

def _launch_indexing(payload: IndexingJobLaunchRequest) -> dict[str, Any]:
    # Reuse project settings/exclusions with the same semantics as Site Audit.
    project, patterns, sitemap = _project_and_options(JobLaunchRequest(project_id=payload.project_id, sitemap_url=payload.sitemap_url, max_pages=payload.max_pages))
    duplicate = is_duplicate_active("indexing_check", payload.project_id)
    if duplicate:
        return {**duplicate, "duplicate": True}
    job_id = create_job("indexing_check", payload.project_id, f"Проверка индексации: {project['name']}", payload.model_dump())

    async def runner(cancel_event, progress):
        return await _save_indexing_check(project, payload, patterns, sitemap, cancel_event, progress)

    start_job(job_id, runner)
    return get_job(job_id) or {"id": job_id}


def _launch(kind: str, payload: JobLaunchRequest) -> dict[str, Any]:
    project, patterns, sitemap = _project_and_options(payload)
    duplicate = is_duplicate_active(kind, payload.project_id)
    if duplicate:
        return {**duplicate, "duplicate": True}

    title = "Аудит сайта" if kind == "site_audit" else "Анализ перелинковки"
    job_payload = payload.model_dump()
    job_id = create_job(kind, payload.project_id, f"{title}: {project['name']}", job_payload)

    async def runner(cancel_event, progress):
        if kind == "site_audit":
            return await _save_site_audit(project, payload, patterns, sitemap, cancel_event, progress)
        return await _save_internal_linking(project, payload, patterns, sitemap, cancel_event, progress)

    start_job(job_id, runner)
    return get_job(job_id) or {"id": job_id}


@router.post("/site-audit")
async def launch_site_audit(payload: JobLaunchRequest):
    return _launch("site_audit", payload)


@router.post("/internal-linking")
async def launch_internal_linking(payload: JobLaunchRequest):
    return _launch("internal_linking", payload)

@router.post("/indexing-check")
async def launch_indexing_check(payload: IndexingJobLaunchRequest):
    return _launch_indexing(payload)

@router.post("/meta-description-audit")
async def launch_meta_description_audit(payload: MetaDescriptionJobLaunchRequest):
    return _launch_meta_description(payload)


@router.get("")
def jobs(limit: int = 30, active_only: bool = False):
    return list_jobs(limit=limit, active_only=active_only)


@router.get("/{job_id}")
def job(job_id: int):
    item = get_job(job_id)
    if not item:
        raise HTTPException(status_code=404, detail="Фоновая задача не найдена")
    return item


@router.post("/{job_id}/cancel")
def stop_job(job_id: int):
    if not cancel_job(job_id):
        item = get_job(job_id)
        if not item:
            raise HTTPException(status_code=404, detail="Фоновая задача не найдена")
        raise HTTPException(status_code=409, detail="Эту задачу уже нельзя остановить")
    return get_job(job_id)


@router.post("/{job_id}/retry")
async def retry_job(job_id: int):
    item = get_job(job_id)
    if not item:
        raise HTTPException(status_code=404, detail="Фоновая задача не найдена")
    if item["status"] in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="Задача ещё выполняется")
    if item["kind"] == "indexing_check":
        return _launch_indexing(IndexingJobLaunchRequest(**item.get("payload", {})))
    if item["kind"] == "meta_description_audit":
        return _launch_meta_description(MetaDescriptionJobLaunchRequest(**item.get("payload", {})))
    payload = JobLaunchRequest(**item.get("payload", {}))
    return _launch(item["kind"], payload)
