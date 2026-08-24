from __future__ import annotations
import json
from collections import Counter
from fastapi import APIRouter, HTTPException
from app.db.database import get_connection
router = APIRouter(prefix="/overview", tags=["overview"])


def _page_issue_rows(audit_result: dict | None) -> list[dict]:
    rows: list[dict] = []
    for page in (audit_result or {}).get("pages", []) or []:
        url = page.get("url", "")
        if not url:
            continue
        issues = page.get("issues", []) or []
        seo_issues = [x for x in issues if not str(x.get("code", "")).startswith("content_") and x.get("code") not in {"missing_cta", "missing_faq", "low_content_fullness", "weak_heading_structure", "weak_paragraph_structure", "no_content_images"}]
        content_issues = [x for x in issues if x not in seo_issues]
        rows.append({
            "url": url,
            "score": int(page.get("score", 0) or 0),
            "content_score": int(page.get("content_score", 0) or 0),
            "missing_alt": int(page.get("missing_alt", 0) or 0),
            "images": int(page.get("images", 0) or 0),
            "seo_issues": seo_issues,
            "content_issues": content_issues,
            "has_faq": bool(page.get("has_faq")),
            "has_cta": bool(page.get("has_cta")),
        })
    return rows


def _priority_pages(audit_result: dict | None, link_result: dict | None, indexing_result: dict | None = None) -> list[dict]:
    combined: dict[str, dict] = {}
    for row in _page_issue_rows(audit_result):
        problems: list[str] = []
        severity = 0
        if row["content_score"] < 60:
            problems.append(f'Наполненность {row["content_score"]}/100')
            severity += max(1, (60 - row["content_score"]) // 8)
        if row["missing_alt"]:
            problems.append(f'Без ALT: {row["missing_alt"]} из {row["images"]}')
            severity += min(4, row["missing_alt"])
        for issue in row["seo_issues"][:3]:
            label = issue.get("label")
            if label:
                problems.append(label)
                severity += 4 if issue.get("severity") == "critical" else 2
        if problems:
            combined[row["url"]] = {"url": row["url"], "problems": problems, "severity": severity, "sources": ["Аудит сайта"]}

    for page in (link_result or {}).get("pages", []) or []:
        url = page.get("url", "")
        if not url:
            continue
        problems: list[str] = []
        severity = 0
        if page.get("is_orphan"):
            problems.append("Страница-сирота")
            severity += 8
        elif page.get("is_weak"):
            problems.append(f'Слабая перелинковка: {page.get("incoming", 0)} входящих')
            severity += 3
        if int(page.get("depth", 0) or 0) >= 4:
            problems.append(f'Глубина {page.get("depth")}')
            severity += 2
        if problems:
            item = combined.setdefault(url, {"url": url, "problems": [], "severity": 0, "sources": []})
            item["problems"].extend(x for x in problems if x not in item["problems"])
            item["severity"] += severity
            if "Перелинковка" not in item["sources"]:
                item["sources"].append("Перелинковка")

    for row in (indexing_result or {}).get("rows", []) or []:
        status = row.get("status")
        if status not in {"developer", "content"}:
            continue
        url = row.get("url", "")
        if not url:
            continue
        issues = (row.get("technical_issues", []) or []) + (row.get("content_issues", []) or [])
        labels = [x.get("label") for x in issues if x.get("label")]
        if not labels:
            labels = ["Требует проверки индексации"]
        item = combined.setdefault(url, {"url": url, "problems": [], "severity": 0, "sources": []})
        prefix = "Индексация: "
        for label in labels[:3]:
            value = prefix + label
            if value not in item["problems"]:
                item["problems"].append(value)
        item["severity"] += 7 if status == "developer" else 3
        if "Индексация" not in item["sources"]:
            item["sources"].append("Индексация")

    rows = sorted(combined.values(), key=lambda x: (-x["severity"], x["url"]))
    for row in rows:
        row["priority"] = "P1" if row["severity"] >= 8 else "P2" if row["severity"] >= 4 else "P3"
    return rows[:20]


@router.get("/project/{project_id}")
def project_overview(project_id: int):
    with get_connection() as conn:
        p = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if not p: raise HTTPException(404, "Проект не найден")
        audit = conn.execute("SELECT * FROM site_audits WHERE project_id=? ORDER BY id DESC LIMIT 1", (project_id,)).fetchone()
        linking = conn.execute("SELECT * FROM internal_link_audits WHERE project_id=? ORDER BY id DESC LIMIT 1", (project_id,)).fetchone()
        indexing = conn.execute("SELECT * FROM indexing_checks WHERE project_id=? ORDER BY id DESC LIMIT 1", (project_id,)).fetchone()
        tasks = conn.execute("SELECT id,title,priority,deadline,status,done_json,parsed_json FROM saved_tasks WHERE project_id=? AND status!='done' ORDER BY id DESC", (project_id,)).fetchall()
        history = conn.execute("SELECT id,score,pages_total,critical,warnings,created_at FROM site_audits WHERE project_id=? ORDER BY id DESC LIMIT 10", (project_id,)).fetchall()
    audit_result = json.loads(audit["result_json"]) if audit else None
    link_result = json.loads(linking["result_json"]) if linking else None
    indexing_result = json.loads(indexing["result_json"]) if indexing else None
    attention=[]
    groups=[]
    if audit:
        if audit["critical"]: attention.append({"level":"critical","text":f'{audit["critical"]} критических SEO-ошибок'})
        if audit["warnings"]: attention.append({"level":"warning","text":f'{audit["warnings"]} SEO-предупреждений'})
        groups.append({"key":"seo","label":"SEO","count":int(audit["critical"] or 0)+int(audit["warnings"] or 0),"level":"critical" if audit["critical"] else "warning","href":f"/site-audit/{audit['id']}"})
        content_score = int((audit_result or {}).get("content_score", 0) or 0)
        low_content = int((audit_result or {}).get("low_content_pages", 0) or 0)
        if low_content:
            attention.append({"level":"warning","text":f'{low_content} страниц с низкой наполненностью'})
        groups.append({"key":"content","label":"Контент","count":low_content,"level":"warning" if low_content else "info","detail":f"Средняя наполненность {content_score}/100","href":f"/site-audit/{audit['id']}"})
        missing_alt = sum(int(page.get("missing_alt", 0) or 0) for page in (audit_result or {}).get("pages", []) or [])
        if missing_alt:
            attention.append({"level":"warning","text":f'{missing_alt} изображений без ALT'})
        groups.append({"key":"images","label":"Изображения","count":missing_alt,"level":"warning" if missing_alt else "info","href":"/images"})
    if linking:
        weak = (link_result or {}).get("summary",{}).get("weak_pages", (link_result or {}).get("weak_pages", 0))
        if weak: attention.append({"level":"warning","text":f'{weak} слабых страниц по перелинковке'})
        if linking["orphans"]: attention.append({"level":"critical","text":f'{linking["orphans"]} страниц-сирот'})
        groups.append({"key":"linking","label":"Перелинковка","count":int(weak or 0)+int(linking["orphans"] or 0),"level":"critical" if linking["orphans"] else "warning" if weak else "info","href":"/linking"})
    if indexing:
        if indexing["developer_count"]: attention.append({"level":"critical","text":f'{indexing["developer_count"]} URL из GSC требуют технической проверки'})
        if indexing["content_count"]: attention.append({"level":"warning","text":f'{indexing["content_count"]} URL из GSC можно улучшить контент-менеджеру'})
        groups.append({"key":"indexing","label":"Индексация","count":int(indexing["developer_count"] or 0)+int(indexing["content_count"] or 0),"level":"critical" if indexing["developer_count"] else "warning" if indexing["content_count"] else "info","href":f"/audit/indexing?project={project_id}"})
    if tasks: attention.append({"level":"info","text":f'{len(tasks)} открытых задач'})
    return {
      "project": dict(p),
      "audit": ({k:audit[k] for k in ["id","score","pages_total","critical","warnings","recommendations","created_at"]} if audit else None),
      "linking": ({"id":linking["id"],"score":linking["score"],"pages_total":linking["pages_total"],"links_total":linking["links_total"],"orphans":linking["orphans"],"broken_links":linking["broken_links"],"created_at":linking["created_at"]} if linking else None),
      "indexing": ({"id":indexing["id"],"urls_total":indexing["urls_total"],"ok_count":indexing["ok_count"],"content_count":indexing["content_count"],"developer_count":indexing["developer_count"],"created_at":indexing["created_at"]} if indexing else None),
      "tasks": [dict(x) for x in tasks], "attention": attention, "attention_groups": groups,
      "priority_pages": _priority_pages(audit_result, link_result, indexing_result),
      "audit_history":[dict(x) for x in history],
      "audit_result": audit_result and {"pages_success":audit_result.get("pages_success",0),"content_score":audit_result.get("content_score",0)},
    }
