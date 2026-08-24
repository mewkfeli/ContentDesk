from __future__ import annotations

import json
from typing import Any

from app.db.database import get_connection

# Curated starter context distilled from the user's previous work in ChatGPT.
# It is matched to existing projects by domain/name and inserted idempotently.
STARTER_CONTEXT: list[dict[str, Any]] = [
    {
        "match_domains": ["ekolab24.ru"],
        "match_names": ["эколаб", "ekolab"],
        "items": [
            {"kind":"fact","title":"Аккредитация","content":"Испытательная лаборатория работает по ГОСТ ISO/IEC 17025-2019. Номер аккредитации: RA.RU.21ОК68.","source":"ChatGPT · стартовый контекст","confidence":"confirmed"},
            {"kind":"fact","title":"Основные направления","content":"Основные направления каталога: анализ воды, анализ атмосферного воздуха, анализ почвы и грунта, анализ и исследование отходов, контроль промышленных выбросов.","source":"ChatGPT · стартовый контекст","confidence":"confirmed"},
            {"kind":"decision","title":"Физические факторы","content":"В текущем каталоге ЭкоЛаб услуг по физическим факторам нет. Не предлагать их как существующее направление без отдельного подтверждения.","source":"ChatGPT · стартовый контекст","confidence":"confirmed"},
            {"kind":"rule","title":"Стиль контента","content":"B2B-тон: профессионально, конкретно, без рекламных клише и неподтверждённых обещаний. Целевая аудитория: юрлица, предприятия, госорганы, проектные институты.","source":"ChatGPT · стартовый контекст","confidence":"confirmed"},
            {"kind":"rule","title":"Изображения лаборатории","content":"Изображения должны быть фотореалистичными, без текста и AI-артефактов, с корректными СИЗ и реальным/правдоподобным лабораторным оборудованием. Не использовать визуально неверные приборы и процессы.","source":"ChatGPT · стартовый контекст","confidence":"confirmed"},
            {"kind":"decision","title":"Актуальный URL анализа воды","content":"Старая страница /kompleksnyj-analiz-vody/ больше не является актуальной страницей услуги. Актуальный URL: /analiz-vody/.","source":"ChatGPT · стартовый контекст","confidence":"confirmed"},
            {"kind":"observation","title":"Проверка индексации","content":"Последняя проверка 39 URL из статуса «Обнаружена, не проиндексирована»: 37 без существенных проблем, 2 требуют внимания. /himicheskij-analiz-vody/ имеет реального донора /analiz-vody/; /kompleksnyj-analiz-vody/ выглядел как orphan-кандидат.","source":"ChatGPT · стартовый контекст","confidence":"confirmed"},
            {"kind":"observation","title":"Meta Description Audit","content":"На стабильной версии аудита было 234 URL: 15 OK, 3 на проверку, 43 ручных исправления, 53 проблемы шаблона Description, 75 HTTP-ошибок/битых страниц, 45 технических проблем. Среди товаров: 12 ручных контентных исправлений и 53 шаблонных.","source":"ChatGPT · стартовый контекст","confidence":"confirmed"},
        ],
    },
    {
        "match_domains": ["eklt.ru"],
        "match_names": ["эклт", "eklt", "завод электротранспорта"],
        "items": [
            {"kind":"fact","title":"Проект","content":"eklt.ru — ООО ТПП «Завод электротранспорта» (Сарапул). Основной контент связан с электротележками и промышленным электротранспортом.","source":"ChatGPT · стартовый контекст","confidence":"confirmed"},
            {"kind":"decision","title":"К-12 Отраслевые материалы","content":"Вместо реальных кейсов принято делать статьи с предполагаемыми отраслевыми сценариями и контекстными ссылками на подходящие модели, включая перелинковку на платформенные электротележки.","source":"ChatGPT · стартовый контекст","confidence":"confirmed"},
            {"kind":"decision","title":"К-13 Региональные блоки","content":"Региональные блоки «Доставка и сервис» размещаются на страницах категорий, например /catalog/elektrotelezhki/. Источник фактов о доставке: /help/delivery/.","source":"ChatGPT · стартовый контекст","confidence":"confirmed"},
            {"kind":"observation","title":"Документация и ALT","content":"В проекте есть отдельные задачи по документации (руководства PDF + текст) и по ALT для товарных изображений. Для рекомендаций учитывать уже существующие задачи, чтобы не дублировать работу.","source":"ChatGPT · стартовый контекст","confidence":"confirmed"},
        ],
    },
    {
        "match_domains": ["ra-lux.ru"],
        "match_names": ["ра групп", "ra group", "ра-групп"],
        "items": [
            {"kind":"fact","title":"Профиль проекта","content":"РА Групп — проект по инженерным решениям. На сайте используются страницы услуг и кейсы/проекты с заказчиком, заголовком, локацией, объёмом/периодом, направлением, кратким описанием, основным текстом, годом и аннотацией.","source":"ChatGPT · стартовый контекст","confidence":"confirmed"},
            {"kind":"rule","title":"Структура услуг","content":"Для услуг предпочтительны короткое описание, блок «что входит в услугу» из 3 пунктов и короткий текст под сеткой преимуществ. Избегать громоздких формулировок и повторов.","source":"ChatGPT · стартовый контекст","confidence":"confirmed"},
            {"kind":"rule","title":"Изображения услуг","content":"Hero-изображения услуг — без текста. Для услуги «Покраска инженерного оборудования» предпочтение изображениям без человека; иконки — 2D минималистичные.","source":"ChatGPT · стартовый контекст","confidence":"confirmed"},
            {"kind":"fact","title":"Реквизиты для политики","content":"ООО «РА ГРУПП»; email ragrupp@yandex.ru; ИНН/КПП 0278949433/027801001; адрес: 450005, РБ, г. Уфа, ул. 50-летия Октября, д.11/2, офис 408.","source":"ChatGPT · стартовый контекст","confidence":"confirmed"},
        ],
    },
]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def seed_starter_context() -> dict[str, int]:
    inserted = 0
    matched_projects = 0
    with get_connection() as conn:
        projects = [dict(row) for row in conn.execute("SELECT id,name,domain FROM projects").fetchall()]
        for project in projects:
            name = str(project.get("name") or "").lower()
            domain = str(project.get("domain") or "").lower().replace("https://", "").replace("http://", "").strip("/")
            block = next((b for b in STARTER_CONTEXT if domain in b["match_domains"] or any(x in name for x in b["match_names"])), None)
            if not block:
                continue
            matched_projects += 1
            for item in block["items"]:
                exists = conn.execute(
                    "SELECT id FROM ai_project_memory WHERE project_id=? AND title=? AND source=? AND is_active=1 LIMIT 1",
                    (project["id"], item["title"], item["source"]),
                ).fetchone()
                if exists:
                    continue
                conn.execute(
                    "INSERT INTO ai_project_memory(project_id,kind,title,content,source,confidence) VALUES (?,?,?,?,?,?)",
                    (project["id"], item["kind"], item["title"], item["content"], item["source"], item["confidence"]),
                )
                inserted += 1
        conn.commit()
    return {"matched_projects": matched_projects, "inserted": inserted}


def record_event(project_id: int | None, event_type: str, title: str, summary: str, payload: Any | None = None, source: str = "ContentDesk") -> None:
    if not project_id:
        return
    payload_json = _json(payload if payload is not None else {})
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO project_memory_events(project_id,event_type,title,summary,payload_json,source) VALUES (?,?,?,?,?,?)",
            (project_id, event_type, title[:220], summary[:5000], payload_json, source[:160]),
        )
        conn.commit()


def update_state(project_id: int | None, state_key: str, title: str, summary: str, payload: Any | None = None, source: str = "ContentDesk") -> None:
    if not project_id:
        return
    payload_json = _json(payload if payload is not None else {})
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO project_memory_state(project_id,state_key,title,summary,payload_json,source,updated_at)
               VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(project_id,state_key) DO UPDATE SET
                 title=excluded.title, summary=excluded.summary, payload_json=excluded.payload_json,
                 source=excluded.source, updated_at=CURRENT_TIMESTAMP""",
            (project_id, state_key[:120], title[:220], summary[:5000], payload_json, source[:160]),
        )
        conn.commit()


def get_project_state(project_id: int | None, limit: int = 20) -> list[dict[str, Any]]:
    if not project_id:
        return []
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM project_memory_state WHERE project_id=? ORDER BY updated_at DESC LIMIT ?",
            (project_id, max(1, min(limit, 100))),
        ).fetchall()
    return [dict(row) for row in rows]


def get_project_events(project_id: int | None, limit: int = 30) -> list[dict[str, Any]]:
    if not project_id:
        return []
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM project_memory_events WHERE project_id=? ORDER BY id DESC LIMIT ?",
            (project_id, max(1, min(limit, 200))),
        ).fetchall()
    return [dict(row) for row in rows]


def remember_site_audit(project_id: int, report_id: int, result: dict[str, Any]) -> None:
    issue_counts = result.get("issue_counts") or {}
    top = sorted(((str(k), int(v)) for k,v in issue_counts.items() if isinstance(v, (int,float))), key=lambda x:x[1], reverse=True)[:8]
    summary = f"Аудит сайта #{report_id}: оценка {result.get('score', 0)}/100; страниц {result.get('pages_total', 0)}; критических {result.get('critical', 0)}; предупреждений {result.get('warnings', 0)}; рекомендаций {result.get('recommendations', 0)}."
    payload = {"report_id":report_id,"score":result.get("score"),"pages_total":result.get("pages_total"),"critical":result.get("critical"),"warnings":result.get("warnings"),"recommendations":result.get("recommendations"),"top_issues":top}
    update_state(project_id, "site_audit", "Текущее состояние · аудит сайта", summary, payload, "Аудит сайта")
    record_event(project_id, "site_audit", "Завершён аудит сайта", summary, payload, "Аудит сайта")


def remember_linking_audit(project_id: int, report_id: int, result: dict[str, Any]) -> None:
    summary = f"Аудит перелинковки #{report_id}: оценка {result.get('score', 0)}/100; страниц {result.get('pages_total', 0)}; ссылок {result.get('links_total', 0)}; сирот {result.get('orphans', 0)}; битых ссылок {result.get('broken_links_count', result.get('broken_links', 0))}."
    payload = {"report_id":report_id,"score":result.get("score"),"pages_total":result.get("pages_total"),"links_total":result.get("links_total"),"orphans":result.get("orphans"),"weak_pages":result.get("weak_pages"),"deep_pages":result.get("deep_pages"),"broken_links":result.get("broken_links_count", result.get("broken_links"))}
    update_state(project_id, "internal_linking", "Текущее состояние · перелинковка", summary, payload, "Перелинковка")
    record_event(project_id, "internal_linking", "Завершён аудит перелинковки", summary, payload, "Перелинковка")


def remember_meta_audit(project_id: int, report_id: int, result: dict[str, Any]) -> None:
    counts = result.get("status_counts") or result.get("summary") or {}
    summary = f"Аудит Description #{report_id}: проверено {result.get('urls_total', 0)} URL. OK: {counts.get('ok', result.get('ok_count', 0))}; на проверку: {counts.get('review', result.get('review_count', 0))}; исправить: {counts.get('replace', result.get('replace_count', 0))}; технических: {counts.get('technical', result.get('technical_count', 0))}."
    payload = {"report_id":report_id,"urls_total":result.get("urls_total"),"counts":counts}
    update_state(project_id, "meta_descriptions", "Текущее состояние · Description", summary, payload, "Meta Description Audit")
    record_event(project_id, "meta_description_audit", "Завершён аудит Description", summary, payload, "Meta Description Audit")


def remember_indexing(project_id: int, report_id: int, result: dict[str, Any]) -> None:
    counts = result.get("status_counts") or {}
    summary = f"Проверка индексации #{report_id}: URL {result.get('urls_total', 0)}; нормально {counts.get('ok', 0)}; контент-менеджеру {counts.get('content', 0)}; разработчику {counts.get('developer', 0)}; недостаточно данных {counts.get('insufficient', 0)}."
    payload = {"report_id":report_id,"urls_total":result.get("urls_total"),"status_counts":counts,"crawl":result.get("crawl", {})}
    update_state(project_id, "indexing", "Текущее состояние · индексация", summary, payload, "Проверка индексации")
    record_event(project_id, "indexing_check", "Завершена проверка индексации", summary, payload, "Проверка индексации")


def remember_task(project_id: int | None, task_id: int, title: str, status: str, event: str) -> None:
    if not project_id:
        return
    summary = f"Задача #{task_id} «{title}»: {event}. Текущий статус: {status}."
    record_event(project_id, "task", f"Задача · {event}", summary, {"task_id":task_id,"title":title,"status":status}, "Задачи")


def backfill_current_state() -> dict[str, int]:
    """Build current-state memory from reports that already existed before v2.1."""
    updated = 0
    with get_connection() as conn:
        project_ids = [int(r[0]) for r in conn.execute("SELECT id FROM projects").fetchall()]
    for project_id in project_ids:
        with get_connection() as conn:
            site = conn.execute("SELECT id,result_json FROM site_audits WHERE project_id=? ORDER BY id DESC LIMIT 1", (project_id,)).fetchone()
            linking = conn.execute("SELECT id,result_json FROM internal_link_audits WHERE project_id=? ORDER BY id DESC LIMIT 1", (project_id,)).fetchone()
            meta = conn.execute("SELECT id,result_json FROM meta_description_audits WHERE project_id=? ORDER BY id DESC LIMIT 1", (project_id,)).fetchone()
            indexing = conn.execute("SELECT id,result_json FROM indexing_checks WHERE project_id=? ORDER BY id DESC LIMIT 1", (project_id,)).fetchone()
        for row, fn in ((site, remember_site_audit), (linking, remember_linking_audit), (meta, remember_meta_audit), (indexing, remember_indexing)):
            if not row:
                continue
            try:
                result = json.loads(row["result_json"])
                # Backfill only current state; remove the synthetic event immediately after helper call.
                fn(project_id, int(row["id"]), result)
                with get_connection() as conn:
                    conn.execute("DELETE FROM project_memory_events WHERE id=(SELECT MAX(id) FROM project_memory_events WHERE project_id=?)", (project_id,))
                    conn.commit()
                updated += 1
            except Exception:
                continue
    return {"updated": updated}
