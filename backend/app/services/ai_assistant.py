from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.db.database import get_connection
from app.services.image_audit import audit_images
from app.services.seo_audit import audit_page
from app.services.site_audit import audit_site
from app.services.project_memory import remember_site_audit, remember_task
from app.services.content_assistant import generate_content
from app.services.work_prioritizer import build_work_plan, render_plan

URL_RE = re.compile(r"https?://[^\s<>()\[\]{}\"']+", re.I)


def _json(value: str, default: Any):
    try:
        return json.loads(value)
    except Exception:
        return default


def _get_project(project_id: int | None) -> dict[str, Any] | None:
    if not project_id:
        return None
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return dict(row) if row else None


def _latest_site_audit(project_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM site_audits WHERE project_id = ? ORDER BY id DESC LIMIT 1", (project_id,)
        ).fetchone()
    if not row:
        return None
    result = _json(row["result_json"], {})
    return {"id": row["id"], "created_at": row["created_at"], **result}


def _latest_linking(project_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM internal_link_audits WHERE project_id = ? ORDER BY id DESC LIMIT 1", (project_id,)
        ).fetchone()
    if not row:
        return None
    result = _json(row["result_json"], {})
    return {"id": row["id"], "created_at": row["created_at"], **result}


def _open_tasks(project_id: int | None) -> list[dict[str, Any]]:
    with get_connection() as conn:
        if project_id:
            rows = conn.execute(
                "SELECT * FROM saved_tasks WHERE project_id = ? AND status != 'done' ORDER BY updated_at DESC LIMIT 12",
                (project_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM saved_tasks WHERE status != 'done' ORDER BY updated_at DESC LIMIT 12"
            ).fetchall()
    output = []
    for row in rows:
        parsed = _json(row["parsed_json"], {})
        done = set(_json(row["done_json"], []))
        task_keys = [f"task-{i.get('id')}" for g in parsed.get("role_groups", []) for i in g.get("items", [])]
        qa_keys = [f"qa-{i}" for i, _ in enumerate(parsed.get("qa_checklist", []))]
        valid = task_keys + qa_keys
        completed = len([x for x in valid if x in done])
        output.append({
            "id": row["id"], "title": row["title"], "project_name": row["project_name"],
            "priority": row["priority"], "deadline": row["deadline"], "status": row["status"],
            "completed": completed, "total": len(valid),
        })
    return output


def _content_profile(project_id: int | None) -> dict[str, Any] | None:
    if not project_id:
        return None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT profile_json FROM project_content_profiles WHERE project_id = ?", (project_id,)
        ).fetchone()
    return _json(row["profile_json"], {}) if row else None


def project_context(project_id: int | None) -> dict[str, Any]:
    project = _get_project(project_id)
    return {
        "project": project,
        "latest_site_audit": _latest_site_audit(project_id) if project_id else None,
        "latest_linking": _latest_linking(project_id) if project_id else None,
        "open_tasks": _open_tasks(project_id),
        "content_profile": _content_profile(project_id),
    }


def _human_issue_name(code: str) -> str:
    names = {
        "http_status": "HTTP-ошибки",
        "fetch_error": "ошибки загрузки",
        "missing_title": "страницы без Title",
        "title_length": "проблемы длины Title",
        "missing_description": "страницы без Description",
        "description_length": "проблемы длины Description",
        "missing_h1": "страницы без H1",
        "multiple_h1": "несколько H1",
        "missing_canonical": "страницы без canonical",
        "noindex": "страницы с noindex",
        "thin_content": "тонкий контент",
        "few_internal_links": "мало внутренних ссылок",
        "missing_alt": "изображения без ALT",
        "duplicate_title": "дубли Title",
        "duplicate_description": "дубли Description",
        "duplicate_h1": "дубли H1",
    }
    return names.get(code, code.replace("_", " "))


def _site_summary(audit: dict[str, Any] | None) -> str:
    if not audit:
        return "По этому проекту ещё нет сохранённого полного аудита сайта. Запусти полный аудит, и я смогу использовать его результаты здесь."
    issue_counts = audit.get("issue_counts", {}) or {}
    top = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    lines = [
        f"Последний аудит сайта: {audit.get('score', 0)}/100.",
        f"Проверено страниц: {audit.get('pages_total', 0)}, успешно: {audit.get('pages_success', 0)}.",
        f"Критических: {audit.get('critical', 0)}, предупреждений: {audit.get('warnings', 0)}, рекомендаций: {audit.get('recommendations', 0)}.",
    ]
    if top:
        lines.append("Чаще всего встречаются: " + ", ".join(f"{_human_issue_name(k)} — {v}" for k, v in top) + ".")
    return "\n".join(lines)


def _linking_summary(report: dict[str, Any] | None) -> str:
    if not report:
        return "Сохранённого отчёта по перелинковке пока нет. Запусти раздел «Перелинковка», после этого я смогу разбирать слабые страницы и рекомендации."
    score = report.get("score", 0)
    weak = report.get("weak_pages", 0)
    orphans = report.get("orphans", 0)
    broken = report.get("broken_links_count", 0)
    deep = report.get("deep_pages", 0)
    lines = [
        f"Перелинковка: {score}/100. Страниц: {report.get('pages_total', 0)}, внутренних ссылок: {report.get('links_total', 0)}.",
        f"Сирот: {orphans}, слабых страниц: {weak}, глубоких: {deep}, битых ссылок: {broken}.",
    ]
    if orphans or broken:
        lines.append("Приоритет: сначала исправить страницы-сироты и битые внутренние ссылки.")
    elif weak:
        lines.append(f"Критичных проблем по графу не видно. Основная зона роста — {weak} слабых страниц с малым количеством входящих ссылок.")
    elif deep:
        lines.append(f"Перелинковка выглядит хорошо. Стоит отдельно проверить {deep} глубоких страниц.")
    else:
        lines.append("По основным метрикам перелинковка выглядит хорошо.")
    return "\n".join(lines)


def _tasks_summary(tasks: list[dict[str, Any]]) -> str:
    if not tasks:
        return "Открытых сохранённых задач нет."
    lines = [f"Открытых задач: {len(tasks)}."]
    for task in tasks[:7]:
        progress = f"{task['completed']}/{task['total']}" if task["total"] else "0/0"
        lines.append(f"• {task['title']} — {task['priority']}, {task['deadline']}, {progress}.")
    return "\n".join(lines)


def _page_audit_summary(result: dict[str, Any]) -> str:
    summary = result.get("summary", {})
    issues = [c for c in result.get("checks", []) if c.get("status") != "good"]
    lines = [
        f"SEO-аудит страницы: {result.get('score', 0)}/100, HTTP {result.get('status_code', '—')}.",
        f"Title: {summary.get('title') or 'не найден'}.",
        f"H1: {', '.join(summary.get('h1', [])) or 'не найден'}.",
        f"Слов: {summary.get('word_count', 0)}, внутренних ссылок: {summary.get('internal_links', 0)}, изображений без ALT: {summary.get('missing_alt', 0)}.",
    ]
    if issues:
        lines.append("Что исправить в первую очередь:")
        for check in issues[:7]:
            lines.append(f"• {check.get('label')}: {check.get('recommendation') or check.get('value', '')}")
    return "\n".join(lines)


def _image_summary(result: dict[str, Any]) -> str:
    s = result.get("summary", {})
    return (
        f"Проверено изображений: {result.get('count', 0)}. Без ALT: {s.get('missing_alt', 0)}, "
        f"битых: {s.get('broken_images', 0)}, тяжелее 1 МБ: {s.get('large_images', 0)}, "
        f"старых форматов: {s.get('legacy_format', 0)}, без размеров в HTML: {s.get('missing_dimensions', 0)}."
    )


def _extract_url(message: str) -> str | None:
    match = URL_RE.search(message)
    return match.group(0).rstrip(".,;:!?") if match else None


def _is_full_audit_intent(text: str) -> bool:
    phrases = [
        "полный аудит", "аудит фулл", "фулл аудит", "full audit", "проверь весь сайт",
        "проверить весь сайт", "просканируй сайт", "просканировать сайт", "проверь проект целиком",
        "проверить проект целиком", "полный seo аудит", "полный seo-аудит", "аудит всего сайта",
    ]
    return any(p in text for p in phrases)


def _is_project_health_intent(text: str) -> bool:
    phrases = [
        "что сейчас не так", "что не так с сайтом", "что с сайтом", "проблемы сайта", "состояние сайта",
        "что исправить в первую очередь", "что делать в первую очередь", "что нужно исправить", "приоритетные проблемы",
        "что по проекту", "сводка по проекту", "сводка сайта",
    ]
    return any(p in text for p in phrases)


def _site_problem_pages(audit: dict[str, Any] | None, limit: int = 10) -> list[dict[str, Any]]:
    if not audit:
        return []
    pages = audit.get("pages", []) or []
    ranked = sorted(
        pages,
        key=lambda p: (
            p.get("score", 100),
            -sum(1 for i in p.get("issues", []) if i.get("severity") == "critical"),
            -len(p.get("issues", [])),
        ),
    )
    return ranked[:limit]


def _weak_linking_pages(report: dict[str, Any] | None, limit: int = 10) -> list[dict[str, Any]]:
    if not report:
        return []
    pages = report.get("pages", []) or []
    weak = [p for p in pages if p.get("is_orphan") or p.get("is_weak") or p.get("deep") or p.get("unreachable")]
    weak.sort(key=lambda p: (0 if p.get("is_orphan") else 1, p.get("incoming", 999), -(p.get("depth") or 0)))
    return weak[:limit]


def _project_health_summary(context: dict[str, Any]) -> str:
    project = context.get("project")
    audit = context.get("latest_site_audit")
    linking = context.get("latest_linking")
    tasks = context.get("open_tasks", [])
    name = project.get("name") if project else "проект"

    lines = [f"{name} · состояние проекта"]
    if audit:
        lines.append(f"SEO: {audit.get('score', 0)}/100 · критических {audit.get('critical', 0)} · предупреждений {audit.get('warnings', 0)}")
    else:
        lines.append("SEO: полный аудит ещё не запускался")
    if linking:
        lines.append(
            f"Перелинковка: {linking.get('score', 0)}/100 · сирот {linking.get('orphans', 0)} · "
            f"слабых {linking.get('weak_pages', 0)} · глубоких {linking.get('deep_pages', 0)} · битых {linking.get('broken_links_count', 0)}"
        )
    else:
        lines.append("Перелинковка: отчёта ещё нет")
    lines.append(f"Открытых задач: {len(tasks)}")

    critical: list[str] = []
    improve: list[str] = []
    actions: list[str] = []
    if audit:
        issue_counts = audit.get("issue_counts", {}) or {}
        for code in ["http_status", "fetch_error", "missing_title", "missing_h1", "noindex"]:
            count = int(issue_counts.get(code, 0) or 0)
            if count:
                critical.append(f"{_human_issue_name(code)} — {count}")
                actions.append(f"Исправить {_human_issue_name(code)} — {count}.")
        warning_total = int(audit.get("warnings", 0) or 0)
        if warning_total:
            improve.append(f"SEO-предупреждений — {warning_total}")
    if linking:
        if linking.get("orphans", 0):
            critical.append(f"страниц-сирот — {linking.get('orphans', 0)}")
            actions.append(f"Добавить входящие ссылки на страницы-сироты — {linking.get('orphans', 0)}.")
        if linking.get("broken_links_count", 0):
            critical.append(f"битых внутренних ссылок — {linking.get('broken_links_count', 0)}")
            actions.append(f"Исправить битые внутренние ссылки — {linking.get('broken_links_count', 0)}.")
        if linking.get("weak_pages", 0):
            improve.append(f"слабых страниц по перелинковке — {linking.get('weak_pages', 0)}")
            if not actions:
                actions.append(f"Усилить внутренними ссылками слабые страницы — {linking.get('weak_pages', 0)}.")
        if linking.get("deep_pages", 0):
            improve.append(f"глубоких страниц — {linking.get('deep_pages', 0)}")
    unfinished = sum(max(0, t.get("total", 0) - t.get("completed", 0)) for t in tasks)
    if unfinished:
        improve.append(f"невыполненных пунктов в задачах — {unfinished}")
        actions.append(f"Закрыть сохранённые задачи: осталось пунктов — {unfinished}.")

    if critical:
        lines.append("\nКритично:")
        lines.extend(f"• {x}" for x in critical)
    if improve:
        lines.append("\nСтоит улучшить:")
        lines.extend(f"• {x}" for x in improve)
    if actions:
        lines.append("\nЧто делать:")
        for i, action in enumerate(actions[:5], 1):
            lines.append(f"{i}. {action}")
    else:
        lines.append("\nПо имеющимся данным критичных действий сейчас не видно.")
    return "\n".join(lines)


async def _run_full_site_audit(project_id: int, project: dict[str, Any], max_pages: int = 200) -> dict[str, Any]:
    result = await audit_site(project["domain"], "", max_pages)
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO site_audits (
                project_id, sitemap_url, score, pages_total, pages_success,
                critical, warnings, recommendations, result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
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
    remember_site_audit(project_id, audit_id, result)
    return {"id": audit_id, "project_id": project_id, "project_name": project["name"], **result}


def _recent_tool_context(history: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in reversed(history):
        if item.get("role") != "assistant":
            continue
        tools = item.get("tools") or []
        for tool in reversed(tools):
            if tool.get("status") == "done":
                return tool
    return None




def _is_work_plan_intent(text: str) -> str | None:
    if any(p in text for p in ["что делать сегодня", "план на сегодня", "составь план", "мой план", "что мне делать"]):
        return "today"
    if any(p in text for p in ["только срочное", "что срочно", "срочные задачи", "самое срочное"]):
        return "urgent"
    if any(p in text for p in ["что просрочено", "просроченные задачи", "просрочки"]):
        return "overdue"
    if any(p in text for p in ["что можно закрыть быстро", "быстрые задачи", "быстрые победы", "quick wins"]):
        return "quick"
    if any(p in text for p in ["что важнее всего по", "что важнее по проекту", "приоритет по проекту"]):
        return "today"
    return None


def _content_action_kind(text: str) -> str | None:
    # Сначала проверяем составные запросы, иначе фраза «сделай Title и
    # Description» перехватывается более общим условием «сделай Title».
    if any(p in text for p in ["сделай meta", "создай meta", "title и description", "title + description", "title & description", "метатеги", "мета-теги"]):
        return "meta"
    if any(p in text for p in ["сделай title", "создай title", "предложи title", "перепиши title"]):
        return "title"
    if any(p in text for p in ["сделай description", "создай description", "предложи description", "перепиши description"]):
        return "description"
    if any(p in text for p in ["сделай alt", "создай alt", "предложи alt", "сгенерируй alt"]):
        return "alt"
    if any(p in text for p in ["сделай анкоры", "создай анкоры", "предложи анкоры", "сгенерируй анкоры"]):
        return "anchors"
    if any(p in text for p in ["подготовь контент", "создай контент", "сделай текст", "подготовь текст"]):
        return "content"
    return None


def _subject_from_audit(result: dict[str, Any]) -> str:
    summary = result.get("summary", {}) or {}
    h1 = summary.get("h1", []) or []
    if h1:
        return str(h1[0]).strip()
    title = str(summary.get("title") or "").strip()
    return re.split(r"[|—-]", title)[0].strip() or "Страница сайта"


def _draft_from_page_audit(kind: str, result: dict[str, Any], project: dict[str, Any] | None, profile: dict[str, Any] | None) -> tuple[str, dict[str, Any]]:
    summary = result.get("summary", {}) or {}
    subject = _subject_from_audit(result)
    project = project or {"id": None, "name": "Сайт", "project_type": ""}
    profile = profile or {}
    facts = f"Текущий H1: {subject}. Текущий Title: {summary.get('title') or 'не указан'}."
    if summary.get("description"):
        facts += f" Текущий Description: {summary.get('description')}."
    if kind in {"title", "description", "meta"}:
        draft = generate_content(content_type="meta", subject=subject, project=project, profile=profile, facts=facts, target_url=result.get("final_url", ""))
        title = draft.get("title", subject)
        description = draft.get("description", "")
        lines = ["Черновик метатегов:"]
        if kind in {"title", "meta"}:
            lines.append(f"Title ({len(title)} симв.):\n{title}")
        if kind in {"description", "meta"}:
            lines.append(f"Description ({len(description)} симв.):\n{description}")
        lines.append("\nПеред размещением проверь факты и соответствие интенту страницы.")
        return "\n\n".join(lines), {
            "kind": kind, "title": title, "title_length": len(title),
            "description": description, "description_length": len(description),
            "url": result.get("final_url", "")
        }
    if kind == "anchors":
        draft = generate_content(content_type="anchors", subject=subject, project=project, profile=profile, facts=facts, target_url=result.get("final_url", ""))
        items: list[str] = []
        for section in draft.get("sections", []):
            items.extend(section.get("items", []) or [])
        return "Варианты анкора:\n" + "\n".join(f"• {x}" for x in items[:6]), {"kind": kind, "anchors": items[:6], "url": result.get("final_url", "")}
    if kind == "alt":
        missing = [x for x in result.get("images", []) if not (x.get("alt") or "").strip()]
        alts = []
        for i, image in enumerate(missing[:12], 1):
            alts.append({"src": image.get("src", ""), "alt": subject if i == 1 else f"{subject} — изображение {i}"})
        if not alts:
            return "На странице не найдено изображений без ALT.", {"kind": kind, "alts": [], "url": result.get("final_url", "")}
        lines = [f"ALT для изображений без описания ({len(alts)}):"]
        for item in alts:
            lines.append(f"• {item['alt']} — {item['src']}")
        lines.append("\nДекоративные изображения лучше оставлять с пустым alt=\"\".")
        return "\n".join(lines), {"kind": kind, "alts": alts, "url": result.get("final_url", "")}
    draft = generate_content(content_type="service", subject=subject, project=project, profile=profile, facts=facts, target_url=result.get("final_url", ""))
    lines = [f"Черновик структуры для «{subject}»:"]
    for section in draft.get("sections", []):
        if section.get("text"):
            lines.append(f"\n{section.get('title')}:\n{section.get('text')}")
        if section.get("items"):
            lines.append(f"\n{section.get('title')}:\n" + "\n".join(f"• {x}" for x in section.get("items", [])))
    return "\n".join(lines), {"kind": kind, "draft": draft, "url": result.get("final_url", "")}


async def run_tool_first(
    message: str,
    project_id: int | None,
    history: list[dict[str, Any]] | None = None,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    """Route natural-language requests to deterministic ContentDesk tools."""
    text = message.lower().strip()
    history = history or []
    context = project_context(project_id)
    project = context["project"]
    url = _extract_url(message)
    tools: list[dict[str, Any]] = []
    previous_tool = _recent_tool_context(history)

    work_mode = _is_work_plan_intent(text)
    if work_mode:
        plan = build_work_plan(project_id if project_id else None)
        tools.append({"name": "work_plan", "label": "План работы", "status": "done", "data": {"mode": work_mode, "items": plan.get("top", [])}})
        return render_plan(plan, work_mode), tools, {**context, "work_plan": plan}

    content_kind = _content_action_kind(text)
    if content_kind:
        audit_result = None
        if url:
            try:
                audit_result = await audit_page(url)
                tools.append({"name": "page_audit", "label": "SEO-аудит страницы", "status": "done", "data": audit_result})
            except Exception as exc:
                return f"Не удалось открыть страницу для подготовки контента: {exc}", tools, context
        elif previous_tool and previous_tool.get("name") == "page_audit":
            audit_result = previous_tool.get("data")
        if not audit_result:
            return "Пришли URL страницы или сначала попроси меня проверить SEO страницы — тогда я подготовлю черновик по её фактическим данным.", tools, context
        answer, draft_data = _draft_from_page_audit(content_kind, audit_result, project, context.get("content_profile"))
        tools.append({"name": "content_action", "label": "Контент подготовлен", "status": "done", "data": draft_data})
        return answer, tools, {**context, "tool_result": audit_result, "content_draft": draft_data}

    if url and any(word in text for word in ["изображ", "картин", "фото", "alt"]):
        try:
            result = await audit_images(url)
            tools.append({"name": "image_audit", "label": "Аудит изображений", "status": "done", "data": result})
            return _image_summary(result), tools, {**context, "tool_result": result}
        except Exception as exc:
            tools.append({"name": "image_audit", "label": "Аудит изображений", "status": "error", "error": str(exc)})
            return f"Не удалось проверить изображения: {exc}", tools, context

    if url and any(word in text for word in ["seo", "проверь", "аудит", "страниц"]):
        try:
            result = await audit_page(url)
            tools.append({"name": "page_audit", "label": "SEO-аудит страницы", "status": "done", "data": result})
            return _page_audit_summary(result), tools, {**context, "tool_result": result}
        except Exception as exc:
            tools.append({"name": "page_audit", "label": "SEO-аудит страницы", "status": "error", "error": str(exc)})
            return f"Не удалось проверить страницу: {exc}", tools, context

    # Action: run a fresh full audit and immediately turn critical findings into a saved task.
    if _is_full_audit_intent(text) and _is_create_critical_tasks_intent(text):
        if not project or not project_id:
            return "Выбери проект — я запущу аудит и создам задачи по критическим ошибкам.", tools, context
        try:
            result = await _run_full_site_audit(project_id, project)
            tools.append({"name": "full_site_audit", "label": "Полный аудит сайта", "status": "done", "data": {"audit_id": result["id"], "score": result["score"], "pages_total": result["pages_total"]}})
            action = _create_tasks_from_site_audit(project_id, project, result)
            if action.get("reason") == "no_critical":
                return _project_health_summary(project_context(project_id)) + "\n\nКритических ошибок нет — задачу создавать не стал.", tools, project_context(project_id)
            tools.append({"name": "create_task", "label": "Задача создана" if action["created"] else "Задача уже существует", "status": "done", "data": action})
            verb = "Создал" if action["created"] else "Нашёл уже созданную"
            return (
                _project_health_summary(project_context(project_id)) +
                f"\n\n{verb} задачу #{action['task_id']}: {action['items']} блоков работ, затронуто URL — {action['urls']}. "
                f"Открой её в разделе «Мои задачи»."
            ), tools, project_context(project_id)
        except Exception as exc:
            tools.append({"name": "full_site_audit", "label": "Полный аудит сайта", "status": "error", "error": str(exc)})
            return f"Не удалось выполнить аудит и создать задачи: {exc}", tools, context

    # Action: turn the latest saved audit into tasks without rescanning the site.
    if _is_create_critical_tasks_intent(text):
        if not project or not project_id:
            return "Выбери проект — я создам задачи из его последнего аудита.", tools, context
        audit = context.get("latest_site_audit")
        if not audit:
            return "У проекта ещё нет сохранённого полного аудита. Скажи «проверь весь сайт и создай задачи по критическим ошибкам».", tools, context
        action = _create_tasks_from_site_audit(project_id, project, audit)
        if action.get("reason") == "no_critical":
            return "В последнем полном аудите критических ошибок нет — задачу создавать не из чего.", tools, context
        tools.append({"name": "create_task", "label": "Задача создана" if action["created"] else "Задача уже существует", "status": "done", "data": action})
        verb = "Создал" if action["created"] else "Такая задача уже была создана"
        return f"{verb}. Задача #{action['task_id']}: {action['items']} блоков работ, URL — {action['urls']}. Она сохранена в «Мои задачи».", tools, project_context(project_id)

    # Action: create a saved task from the latest internal-linking report.
    if _is_create_linking_tasks_intent(text):
        if not project or not project_id:
            return "Выбери проект — я создам задачи из последнего отчёта перелинковки.", tools, context
        report = context.get("latest_linking")
        if not report:
            return "У проекта ещё нет сохранённого отчёта перелинковки. Сначала запусти раздел «Перелинковка».", tools, context
        action = _create_tasks_from_linking(project_id, project, report)
        if action.get("reason") == "no_linking_issues":
            return "В последнем отчёте нет проблем, из которых стоит автоматически создавать задачу.", tools, context
        tools.append({"name": "create_task", "label": "Задача создана" if action["created"] else "Задача уже существует", "status": "done", "data": action})
        verb = "Создал" if action["created"] else "Такая задача уже была создана"
        return f"{verb}. Задача #{action['task_id']}: {action['items']} блоков работ, URL — {action['urls']}. Она сохранена в «Мои задачи».", tools, project_context(project_id)

    if _is_full_audit_intent(text):
        if not project or not project_id:
            return "Выбери проект — полный аудит запускается по домену проекта.", tools, context
        try:
            result = await _run_full_site_audit(project_id, project)
            tools.append({"name": "full_site_audit", "label": "Полный аудит сайта", "status": "done", "data": {"audit_id": result["id"], "score": result["score"], "pages_total": result["pages_total"]}})
            refreshed = project_context(project_id)
            return _project_health_summary(refreshed), tools, {**refreshed, "tool_result": result}
        except Exception as exc:
            tools.append({"name": "full_site_audit", "label": "Полный аудит сайта", "status": "error", "error": str(exc)})
            return f"Не удалось выполнить полный аудит сайта: {exc}", tools, context

    if _is_project_health_intent(text):
        tools.append({"name": "project_health", "label": "Сводка по проекту", "status": "done"})
        return _project_health_summary(context), tools, context

    if any(p in text for p in ["критичные ошибки", "критические ошибки", "худшие страницы", "самые проблемные страницы"]):
        pages = _site_problem_pages(context.get("latest_site_audit"), 10)
        if not pages:
            return "Нет сохранённого аудита сайта, из которого можно показать проблемные страницы.", tools, context
        lines = [f"Самые проблемные страницы по последнему аудиту ({len(pages)}):"]
        for i, page in enumerate(pages, 1):
            issue_labels = [x.get("label", "") for x in page.get("issues", [])[:3]]
            lines.append(f"{i}. {page.get('url')} — {page.get('score', 0)}/100" + (f" · {'; '.join(issue_labels)}" if issue_labels else ""))
        tools.append({"name": "problem_pages", "label": "Проблемные страницы", "status": "done", "data": {"pages": pages}})
        return "\n".join(lines), tools, {**context, "tool_result": {"pages": pages}}

    if any(p in text for p in ["слабые страницы", "страницы слабые", "покажи слабые", "страницы-сироты", "сироты"]):
        pages = _weak_linking_pages(context.get("latest_linking"), 10)
        if not pages:
            return "В последнем отчёте перелинковки слабые страницы не найдены или отчёта ещё нет.", tools, context
        lines = [f"Слабые страницы по последнему отчёту перелинковки ({len(pages)}):"]
        for i, page in enumerate(pages, 1):
            flags = []
            if page.get("is_orphan"): flags.append("сирота")
            if page.get("is_weak"): flags.append("1 входящая")
            if page.get("deep"): flags.append(f"глубина {page.get('depth')}")
            if page.get("unreachable"): flags.append("недостижима от Главной")
            lines.append(f"{i}. {page.get('url')} — входящих {page.get('incoming', 0)}" + (f" · {', '.join(flags)}" if flags else ""))
        tools.append({"name": "weak_pages", "label": "Слабые страницы", "status": "done", "data": {"pages": pages}})
        return "\n".join(lines), tools, {**context, "tool_result": {"pages": pages}}

    if any(p in text for p in ["худшие 10", "покажи 10", "топ 10 худших", "первые 10"]):
        if previous_tool and previous_tool.get("name") in {"latest_linking", "weak_pages"}:
            pages = _weak_linking_pages(context.get("latest_linking"), 10)
            if pages:
                lines = ["10 страниц, которые стоит разобрать первыми:"]
                for i, page in enumerate(pages, 1):
                    lines.append(f"{i}. {page.get('url')} — входящих {page.get('incoming', 0)}, глубина {page.get('depth') if page.get('depth') is not None else '—'}")
                tools.append({"name": "weak_pages", "label": "Слабые страницы", "status": "done", "data": {"pages": pages}})
                return "\n".join(lines), tools, {**context, "tool_result": {"pages": pages}}
        pages = _site_problem_pages(context.get("latest_site_audit"), 10)
        if pages:
            lines = ["10 самых проблемных страниц по последнему SEO-аудиту:"]
            for i, page in enumerate(pages, 1):
                lines.append(f"{i}. {page.get('url')} — {page.get('score', 0)}/100")
            tools.append({"name": "problem_pages", "label": "Проблемные страницы", "status": "done", "data": {"pages": pages}})
            return "\n".join(lines), tools, {**context, "tool_result": {"pages": pages}}

    if any(p in text for p in ["проверь первую", "проверь первый", "проверить первую", "проверить первый"]):
        data = (previous_tool or {}).get("data") or {}
        pages = data.get("pages") or []
        first = pages[0] if pages else None
        first_url = first.get("url") if isinstance(first, dict) else None
        if first_url:
            try:
                result = await audit_page(first_url)
                tools.append({"name": "page_audit", "label": "SEO-аудит первой страницы", "status": "done", "data": result})
                return _page_audit_summary(result), tools, {**context, "tool_result": result}
            except Exception as exc:
                return f"Не удалось проверить первую страницу: {exc}", tools, context
        return "В предыдущем ответе нет списка страниц, из которого можно взять первую.", tools, context

    if any(word in text for word in ["перелинков", "сирот", "входящих ссыл", "внутренних ссыл"]):
        report = context["latest_linking"]
        tools.append({"name": "latest_linking", "label": "Последний отчёт перелинковки", "status": "done", "data": {"score": (report or {}).get("score"), "pages_total": (report or {}).get("pages_total")}})
        return _linking_summary(report), tools, context

    if any(word in text for word in ["задач", "план работ", "дедлайн", "срок"]):
        tools.append({"name": "tasks", "label": "Открытые задачи", "status": "done"})
        return _tasks_summary(context["open_tasks"]), tools, context

    if any(word in text for word in ["аудит сайта", "состояние сайта", "проблемы сайта", "что с сайтом", "seo проекта"]):
        tools.append({"name": "latest_site_audit", "label": "Последний аудит сайта", "status": "done"})
        return _site_summary(context["latest_site_audit"]), tools, context

    if project:
        fallback = (
            f"Я вижу проект «{project['name']}». Могу сам собрать сводку по сайту, показать слабые страницы, "
            "открытые задачи, последний отчёт перелинковки или запустить полный аудит. Для конкретной страницы пришли URL."
        )
    else:
        fallback = (
            "Выбери проект слева — тогда я подключу его аудиты, задачи и контент-профиль. "
            "Конкретную страницу могу проверить и без проекта, если пришлёшь полный URL."
        )
    return fallback, tools, context



def _make_smart_task_item(item_id: int, title: str, category: str, subtasks: list[str], problem: str = "", solution: str = "", notes: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": item_id,
        "title": title,
        "role": "SEO / Контент",
        "category": category,
        "problem": problem,
        "solution": solution,
        "subtasks": subtasks,
        "notes": notes or [],
        "done": False,
    }


def _save_generated_task(
    *,
    project_id: int,
    project_name: str,
    title: str,
    priority: str,
    source_name: str,
    items: list[dict[str, Any]],
    qa_checklist: list[str],
    goals: list[str] | None = None,
    expected_results: list[str] | None = None,
    resolved_urls: list[str] | None = None,
) -> tuple[int, bool]:
    """Save an assistant-generated task. Exact source_name makes the action idempotent."""
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM saved_tasks WHERE project_id = ? AND source_name = ? ORDER BY id DESC LIMIT 1",
            (project_id, source_name),
        ).fetchone()
        if existing:
            return int(existing["id"]), False

        parsed = {
            "title": title,
            "project": project_name,
            "priority": priority,
            "deadline": "Не указан",
            "urls": resolved_urls or [],
            "relative_urls": [],
            "task_count": len(items),
            "role_groups": [{"role": "SEO / Контент", "items": items}],
            "goals": goals or [],
            "expected_results": expected_results or [],
            "notes": ["Создано AI Assistant на основе фактического отчёта ContentDesk."],
            "references": [],
            "qa_checklist": qa_checklist,
            "ambiguities": ["Срок не указан — при необходимости добавьте его вручную."],
            "source_name": source_name,
        }
        cursor = conn.execute(
            """
            INSERT INTO saved_tasks
            (title, project_id, project_name, priority, deadline, status, parsed_json, done_json, resolved_urls_json, source_name)
            VALUES (?, ?, ?, ?, 'Не указан', 'new', ?, '[]', ?, ?)
            """,
            (
                title, project_id, project_name, priority,
                json.dumps(parsed, ensure_ascii=False),
                json.dumps(resolved_urls or [], ensure_ascii=False),
                source_name,
            ),
        )
        conn.commit()
        task_id = int(cursor.lastrowid)
    remember_task(project_id, task_id, title, "new", "создана ассистентом")
    return task_id, True


def _create_tasks_from_site_audit(project_id: int, project: dict[str, Any], audit: dict[str, Any]) -> dict[str, Any]:
    pages = audit.get("pages", []) or []
    critical_map: dict[str, list[dict[str, Any]]] = {}
    for page in pages:
        for issue in page.get("issues", []) or []:
            if issue.get("severity") == "critical":
                critical_map.setdefault(issue.get("code", "critical"), []).append({
                    "url": page.get("url", ""), "label": issue.get("label", "Критическая ошибка")
                })

    items: list[dict[str, Any]] = []
    urls: list[str] = []
    item_id = 1
    for code, affected in sorted(critical_map.items(), key=lambda x: len(x[1]), reverse=True):
        affected_urls = [x["url"] for x in affected if x.get("url")]
        urls.extend(affected_urls)
        subtasks = affected_urls[:30]
        if len(affected_urls) > 30:
            subtasks.append(f"…и ещё {len(affected_urls) - 30} URL — см. аудит сайта")
        items.append(_make_smart_task_item(
            item_id,
            f"Исправить: {_human_issue_name(code)} ({len(affected)})",
            "Техническое SEO",
            subtasks,
            problem=f"В последнем полном аудите найдено {len(affected)} критических срабатываний типа «{_human_issue_name(code)}». ",
            solution="Исправить проблему на перечисленных URL и повторно запустить аудит сайта.",
        ))
        item_id += 1

    if not items:
        return {"created": False, "reason": "no_critical", "task_id": None, "items": 0}

    audit_id = audit.get("id", "latest")
    title = f"SEO: критические ошибки по аудиту «{project['name']}»"
    task_id, created = _save_generated_task(
        project_id=project_id, project_name=project["name"], title=title, priority="P1",
        source_name=f"AI Assistant / Site Audit #{audit_id} / critical", items=items,
        qa_checklist=[
            "Повторно запустить полный аудит сайта после исправлений",
            "Проверить, что критические ошибки больше не воспроизводятся",
            "Проверить затронутые страницы вручную в браузере",
        ],
        goals=["Устранить критические технические SEO-ошибки, найденные полным аудитом ContentDesk."],
        expected_results=["Критические ошибки из этого аудита устранены или подтверждены как допустимые."],
        resolved_urls=list(dict.fromkeys(urls)),
    )
    return {"created": created, "task_id": task_id, "items": len(items), "urls": len(set(urls))}


def _create_tasks_from_linking(project_id: int, project: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    pages = report.get("pages", []) or []
    items: list[dict[str, Any]] = []
    urls: list[str] = []
    item_id = 1

    groups = [
        ("Страницы-сироты", [p for p in pages if p.get("is_orphan")], "P1", "Перелинковка", "Добавить релевантные входящие внутренние ссылки с тематических страниц-доноров."),
        ("Битые внутренние ссылки", report.get("broken_links", []) or [], "P1", "Техническое SEO", "Исправить или удалить битые внутренние ссылки и повторно проверить сайт."),
        ("Слабые страницы", [p for p in pages if p.get("is_weak") and not p.get("is_orphan")], "P2", "Перелинковка", "Усилить страницы дополнительными релевантными входящими ссылками."),
        ("Глубокие страницы", [p for p in pages if p.get("deep")], "P2", "Перелинковка", "Сократить кликовую глубину за счёт ссылок с хабов, категорий или близких страниц."),
    ]

    highest_priority = "P2"
    for label, affected, priority, category, solution in groups:
        if not affected:
            continue
        affected_urls: list[str] = []
        for x in affected:
            if isinstance(x, dict):
                u = x.get("url") or x.get("target") or x.get("to") or ""
            else:
                u = str(x)
            if u:
                affected_urls.append(u)
        if not affected_urls:
            continue
        if priority == "P1":
            highest_priority = "P1"
        urls.extend(affected_urls)
        subtasks = affected_urls[:30]
        if len(affected_urls) > 30:
            subtasks.append(f"…и ещё {len(affected_urls) - 30} URL — см. отчёт перелинковки")
        items.append(_make_smart_task_item(
            item_id, f"{label} ({len(affected_urls)})", category, subtasks,
            problem=f"Отчёт перелинковки выявил {len(affected_urls)} страниц/ссылок в категории «{label}».",
            solution=solution,
        ))
        item_id += 1

    if not items:
        return {"created": False, "reason": "no_linking_issues", "task_id": None, "items": 0}

    report_id = report.get("id", "latest")
    title = f"Перелинковка: исправления по отчёту «{project['name']}»"
    task_id, created = _save_generated_task(
        project_id=project_id, project_name=project["name"], title=title, priority=highest_priority,
        source_name=f"AI Assistant / Linking #{report_id} / issues", items=items,
        qa_checklist=[
            "Повторно запустить аудит перелинковки",
            "Проверить отсутствие битых внутренних ссылок",
            "Проверить, что ключевые страницы получили входящие ссылки",
        ],
        goals=["Улучшить внутреннюю перелинковку проекта по данным последнего отчёта ContentDesk."],
        expected_results=["Количество сирот, слабых и глубоких страниц снижено; битые ссылки устранены."],
        resolved_urls=list(dict.fromkeys(urls)),
    )
    return {"created": created, "task_id": task_id, "items": len(items), "urls": len(set(urls))}


def _is_create_critical_tasks_intent(text: str) -> bool:
    return "созда" in text and "задач" in text and any(x in text for x in ["критич", "ошибк", "seo", "аудит"])


def _is_create_linking_tasks_intent(text: str) -> bool:
    return "созда" in text and "задач" in text and any(x in text for x in ["перелинков", "слаб", "сирот", "внутренн"] )


def _compact_for_llm(context: dict[str, Any]) -> dict[str, Any]:
    project = context.get("project")
    audit = context.get("latest_site_audit")
    linking = context.get("latest_linking")
    tool_result = context.get("tool_result")
    return {
        "project": None if not project else {
            "id": project.get("id"), "name": project.get("name"), "domain": project.get("domain"),
            "cms": project.get("cms"), "project_type": project.get("project_type"),
        },
        "site_audit": None if not audit else {
            "score": audit.get("score"), "pages_total": audit.get("pages_total"),
            "critical": audit.get("critical"), "warnings": audit.get("warnings"),
            "issue_counts": audit.get("issue_counts", {}),
        },
        "linking": None if not linking else {
            "score": linking.get("score"), "pages_total": linking.get("pages_total"),
            "orphans": linking.get("orphans"), "weak_pages": linking.get("weak_pages"),
            "broken_links_count": linking.get("broken_links_count"),
            "recommendations": linking.get("recommendations", [])[:5],
        },
        "open_tasks": context.get("open_tasks", [])[:10],
        "content_profile": context.get("content_profile"),
        "tool_result": tool_result,
    }


async def ollama_answer(*, base_url: str, model: str, user_message: str, context: dict[str, Any], history: list[dict[str, str]]) -> str:
    system = (
        "Ты — ContentDesk AI, рабочий ассистент контент-менеджера и SEO-специалиста. "
        "Отвечай по-русски, конкретно и компактно. Используй только предоставленные данные проекта и результаты инструментов. "
        "Не выдумывай проведённые проверки, метрики, свойства клиента или факты. Если данных недостаточно — прямо скажи это. "
        "Когда есть проблемы, объясняй что они означают и давай порядок действий: сначала критические технические, затем SEO/перелинковка, затем контент. "
        "Учитывай контекст предыдущих сообщений: короткие фразы вроде «покажи худшие 10» или «проверь первую» относятся к последнему обсуждаемому списку."
    )
    messages = [{"role": "system", "content": system}]
    messages.extend(history[-10:])
    messages.append({
        "role": "user",
        "content": user_message + "\n\nКонтекст ContentDesk:\n" + json.dumps(_compact_for_llm(context), ensure_ascii=False),
    })
    endpoint = base_url.rstrip("/") + "/api/chat"
    async with httpx.AsyncClient(timeout=httpx.Timeout(90.0)) as client:
        response = await client.post(endpoint, json={"model": model, "messages": messages, "stream": False})
        response.raise_for_status()
        data = response.json()
    content = ((data.get("message") or {}).get("content") or "").strip()
    if not content:
        raise RuntimeError("Локальная модель вернула пустой ответ")
    return content


async def ollama_status(base_url: str, model: str) -> dict[str, Any]:
    endpoint = base_url.rstrip("/") + "/api/tags"
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            response = await client.get(endpoint)
            response.raise_for_status()
            data = response.json()
        models = [str(x.get("name", "")) for x in data.get("models", [])]
        matched = bool(model and any(x == model or x.startswith(model + ":") for x in models))
        return {"online": True, "models": models, "model_available": matched if model else None}
    except Exception as exc:
        return {"online": False, "models": [], "model_available": False, "error": str(exc)}
