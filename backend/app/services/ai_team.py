from __future__ import annotations

import json
import re
from typing import Any

from app.db.database import get_connection
from app.services.ai_providers import ollama_chat, ProviderReply
from app.services.project_memory import get_project_state, get_project_events

ROLES: dict[str, dict[str, str]] = {
    "coordinator": {
        "name": "Координатор",
        "icon": "✦",
        "description": "Разбирает задачу, использует контекст проекта и объединяет результаты ContentDesk.",
        "system": (
            "Ты — Координатор AI-команды ContentDesk. Отвечай по-русски, очень кратко и практично. "
            "Ты не должен пересказывать весь аудит. Твоя задача — выбрать приоритеты и следующий шаг. "
            "Если пользователь спрашивает, чем заняться по контенту, не уводи ответ в общий технический SEO-аудит: "
            "сначала контент, структура, мета, изображения и дубли; технические ошибки упоминай только если они блокируют работу. "
            "Используй только факты из ContentDesk, не выдумывай проверки. Формат по умолчанию: 3 приоритета максимум, "
            "для каждого — что сделать и почему. Не более 900 символов, если пользователь прямо не просит подробности."
        ),
    },
    "content_editor": {
        "name": "Контент-редактор",
        "icon": "✎",
        "description": "Тексты, редактура, Description, FAQ, преимущества, статьи и кейсы.",
        "system": (
            "Ты — профессиональный контент-редактор ContentDesk. Пиши естественный русский B2B-текст без рекламных клише и воды. "
            "Используй только факты из переданного контекста. Не придумывай характеристики, сроки, цены, гарантии, сертификаты или опыт компании. "
            "Сохраняй терминологию и правила проекта. Если исходных фактов недостаточно — перечисли, чего не хватает."
        ),
    },
    "seo_specialist": {
        "name": "SEO-специалист",
        "icon": "⌁",
        "description": "SEO-разбор, индексация, мета-теги, перелинковка и приоритеты.",
        "system": (
            "Ты — SEO-специалист ContentDesk. Анализируй только полученные результаты аудитов, HTML и данные проекта. "
            "Не придумывай позиции, трафик, частотность или состояние индексации, если ContentDesk этого не проверял. "
            "Приоритет: техническая доступность и индексируемость → структура и перелинковка → контент. Давай конкретные действия."
        ),
    },
    "fact_checker": {
        "name": "Фактчекер",
        "icon": "✓",
        "description": "Проверяет утверждения и конфликты фактов по памяти и данным проекта.",
        "system": (
            "Ты — Фактчекер ContentDesk. Не создавай новые факты. Для каждого значимого утверждения оцени, подтверждается ли оно предоставленным контекстом. "
            "Если источников недостаточно или есть конфликт — явно пометь это. Не исправляй конфликт догадкой. "
            "Формат ответа: подтверждено / требует проверки / не подтверждено, затем краткое объяснение."
        ),
    },
}

ROLE_HINTS = {
    "content_editor": ["напиши", "перепиши", "сократи", "текст", "description", "описание", "faq", "аннотац", "стать", "кейс"],
    "seo_specialist": ["seo", "сео", "индексац", "перелинков", "canonical", "сайтмап", "sitemap", "title", "мета", "донор"],
    "fact_checker": ["факт", "проверь утверж", "точно ли", "проверить данные", "реквизит", "не выдум"],
}


def list_roles() -> list[dict[str, str]]:
    return [{"id": role_id, **data} for role_id, data in ROLES.items()]


def select_role(message: str) -> str:
    text = message.lower()
    scored: list[tuple[int, str]] = []
    for role, hints in ROLE_HINTS.items():
        scored.append((sum(1 for h in hints if h in text), role))
    scored.sort(reverse=True)
    return scored[0][1] if scored and scored[0][0] > 0 else "coordinator"


def get_project_memory(project_id: int | None, limit: int = 30) -> list[dict[str, Any]]:
    if not project_id:
        return []
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM ai_project_memory WHERE project_id=? AND is_active=1 ORDER BY id DESC LIMIT ?",
            (project_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def _trim_text(value: Any, limit: int = 900) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def _compact_value(value: Any, *, depth: int = 0) -> Any:
    """Protect the local model from oversized audit/project payloads.

    ContentDesk keeps full results in SQLite, but the AI receives only a bounded
    representation. The exact audit remains the source of truth in the app.
    """
    if depth >= 4:
        if isinstance(value, (dict, list)):
            return "[сокращено]"
        return _trim_text(value, 500)
    if isinstance(value, str):
        return _trim_text(value, 900)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        items = value[:12]
        result = [_compact_value(x, depth=depth + 1) for x in items]
        if len(value) > len(items):
            result.append({"_more": len(value) - len(items)})
        return result
    if isinstance(value, dict):
        # Large result objects usually contain page-by-page arrays. Keep the
        # metrics and only a small sample of records for interpretation.
        preferred = [
            "id", "created_at", "score", "pages_total", "pages_success",
            "critical", "warnings", "recommendations", "issue_counts",
            "links_total", "orphans", "weak_pages", "deep_pages",
            "broken_links_count", "status", "summary", "url", "title",
            "h1", "description", "type", "page_type", "indexability",
            "issues", "checks", "result", "action", "label", "data",
        ]
        keys = [k for k in preferred if k in value]
        # Preserve small ordinary dictionaries too, but cap the key count.
        if len(value) <= 16:
            keys = list(value.keys())[:16]
        elif not keys:
            keys = list(value.keys())[:12]
        result = {str(k): _compact_value(value[k], depth=depth + 1) for k in keys}
        for list_key in ("pages", "items", "rows", "results", "urls"):
            if list_key in value and list_key not in result:
                result[list_key] = _compact_value(value[list_key], depth=depth + 1)
        if len(value) > len(keys) + sum(1 for x in ("pages", "items", "rows", "results", "urls") if x in value and x not in keys):
            result["_note"] = "часть полей скрыта менеджером контекста"
        return result
    return _trim_text(value, 700)


def compact_memory(project_id: int | None) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {}
    # Recent memories are more likely to be relevant; cap every record so one
    # pasted specification cannot consume the entire model context.
    for item in reversed(get_project_memory(project_id, limit=24)):
        bucket = result.setdefault(item["kind"], [])
        if len(bucket) >= 8:
            continue
        bucket.append({
            "title": _trim_text(item.get("title"), 180),
            "content": _trim_text(item.get("content"), 650),
            "source": _trim_text(item.get("source"), 180),
        })
    return result


def _compact_project(project: Any) -> Any:
    if not isinstance(project, dict):
        return project
    allowed = ["id", "name", "domain", "description", "status", "created_at", "updated_at"]
    return {k: _trim_text(project[k], 500) if isinstance(project.get(k), str) else project.get(k) for k in allowed if k in project}


def _top_issue_counts(value: Any, limit: int = 6) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    pairs: list[tuple[str, int]] = []
    for key, raw in value.items():
        try:
            count = int(raw)
        except Exception:
            continue
        pairs.append((str(key), count))
    pairs.sort(key=lambda x: x[1], reverse=True)
    return [{"issue": key, "count": count} for key, count in pairs[:limit]]


def _audit_summary(value: Any) -> Any:
    if not isinstance(value, dict):
        return None
    result: dict[str, Any] = {}
    for key in ("created_at", "score", "pages_total", "pages_success", "critical", "warnings", "recommendations", "status"):
        if key in value:
            result[key] = value.get(key)
    if isinstance(value.get("issue_counts"), dict):
        result["top_issues"] = _top_issue_counts(value.get("issue_counts"), 6)
    elif isinstance(value.get("issues"), dict):
        result["top_issues"] = _top_issue_counts(value.get("issues"), 6)
    return result or _compact_value(value)


def _linking_summary(value: Any) -> Any:
    if not isinstance(value, dict):
        return None
    result = {k: value.get(k) for k in ("created_at", "score", "links_total", "orphans", "weak_pages", "deep_pages", "broken_links_count", "status") if k in value}
    return result or None


def _coordinator_payload(user_message: str, context: dict[str, Any], project: Any, project_id: int | None) -> dict[str, Any]:
    text = user_message.lower()
    payload: dict[str, Any] = {
        "project": _compact_project(project),
        "site_audit": _audit_summary(context.get("latest_site_audit")),
        "open_tasks": _compact_value((context.get("open_tasks") or [])[:5]),
        "project_memory": {k: v[:3] for k, v in compact_memory(project_id).items()},
        "current_state": _compact_value(get_project_state(project_id, limit=8)),
        "recent_events": _compact_value(get_project_events(project_id, limit=8)),
    }
    if any(x in text for x in ("перелинков", "ссыл", "донор", "сирот", "глубин")):
        payload["linking"] = _linking_summary(context.get("latest_linking"))
    if any(x in text for x in ("контент", "текст", "страниц", "description", "описан", "h1", "h2", "h3", "alt", "изображ")):
        payload["content_profile"] = _compact_value(context.get("content_profile"))
    if context.get("tool_result") is not None:
        payload["tool_result"] = _compact_value(context.get("tool_result"))
    return payload


def _messages(role: str, user_message: str, context: dict[str, Any], history: list[dict[str, str]]) -> list[dict[str, str]]:
    project = context.get("project") if isinstance(context.get("project"), dict) else None
    project_id = project.get("id") if project else None
    memory = compact_memory(project_id)

    if role == "coordinator":
        payload = _coordinator_payload(user_message, context, project, project_id)
    else:
        payload = {
            "project": _compact_project(project),
            "latest_site_audit": _compact_value(context.get("latest_site_audit")),
            "latest_linking": _compact_value(context.get("latest_linking")),
            "open_tasks": _compact_value((context.get("open_tasks") or [])[:8]),
            "content_profile": _compact_value(context.get("content_profile")),
            "tool_result": _compact_value(context.get("tool_result")),
            "project_memory": memory,
            "current_state": _compact_value(get_project_state(project_id, limit=12)),
            "recent_events": _compact_value(get_project_events(project_id, limit=12)),
        }

    # Local models often run with a much smaller context than their theoretical
    # maximum. Keep only recent turns and cap each turn independently.
    messages: list[dict[str, str]] = [{"role": "system", "content": ROLES[role]["system"]}]
    fast_role = role in {"coordinator", "content_editor"}
    history_items = history[-1:] if role == "coordinator" else (history[-2:] if fast_role else history[-4:])
    history_limit = 450 if role == "coordinator" else (700 if fast_role else 1200)
    for msg in history_items:
        if msg.get("role") in {"user", "assistant"}:
            messages.append({"role": msg["role"], "content": _trim_text(msg.get("content"), history_limit)})

    context_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # Fast roles must remain genuinely interactive on local 7B/8B models.
    # Coordinator receives a compact project snapshot; reasoning roles keep more evidence.
    context_limit = 3400 if role == "coordinator" else (9000 if role == "content_editor" else 14000)
    if len(context_json) > context_limit:
        context_json = context_json[:context_limit].rstrip() + '\n[контекст автоматически сокращён]'
    user_limit = 1400 if role == "coordinator" else (3000 if fast_role else 6000)
    prompt = _trim_text(user_message, user_limit) + "\n\nДанные ContentDesk (сокращённый контекст):\n" + context_json
    messages.append({"role": "user", "content": prompt})
    return messages

def _role_route(settings: dict[str, Any], role: str) -> str:
    routes = settings.get("role_routes") or {}
    provider = str(routes.get(role) or settings.get("provider") or "builtin")
    return provider if provider in {"builtin", "ollama"} else "builtin"


async def role_answer(*, role: str, settings: dict[str, Any], user_message: str, context: dict[str, Any], history: list[dict[str, str]]) -> ProviderReply | None:
    provider = _role_route(settings, role)
    if provider == "builtin":
        return None
    messages = _messages(role, user_message, context, history)
    if provider == "ollama":
        role_models = settings.get("role_models") or {}
        model = str(role_models.get(role) or settings.get("ollama_model") or "")
        # Fast roles should answer without a long reasoning trace. DeepSeek is kept
        # in reasoning mode for SEO/fact checking where the extra latency is useful.
        think = bool(role in {"seo_specialist", "fact_checker"} and model.lower().startswith("deepseek-r1"))
        if role == "coordinator":
            # Router/coordinator should be quick: short answer, small KV cache, no thinking.
            num_ctx, num_predict, timeout = 3072, 180, 60.0
        elif role == "content_editor":
            num_ctx, num_predict, timeout = 6144, 700, 180.0
        else:
            num_ctx, num_predict, timeout = 8192, 900, 600.0
        return await ollama_chat(
            base_url=str(settings.get("ollama_url") or "http://127.0.0.1:11434"),
            model=model,
            messages=messages,
            think=think,
            num_ctx=num_ctx,
            num_predict=num_predict,
            timeout=timeout,
            temperature=0.15 if role == "coordinator" else 0.25,
        )
    return None


def wants_consilium(message: str) -> bool:
    text = message.lower()
    return "консилиум" in text or "всей команд" in text or "несколько специалистов" in text


async def consilium_answer(*, settings: dict[str, Any], user_message: str, context: dict[str, Any], history: list[dict[str, str]], fallback: str) -> tuple[str, list[dict[str, Any]]]:
    opinions: list[dict[str, Any]] = []
    for role in ["content_editor", "seo_specialist", "fact_checker"]:
        try:
            reply = await role_answer(role=role, settings=settings, user_message=user_message, context=context, history=history)
            if reply:
                opinions.append({"role": role, "role_name": ROLES[role]["name"], "provider": reply.provider, "model": reply.model, "content": reply.content})
        except Exception as exc:
            opinions.append({"role": role, "role_name": ROLES[role]["name"], "provider": _role_route(settings, role), "error": str(exc), "content": ""})
    good = [x for x in opinions if x.get("content")]
    if not good:
        return fallback, opinions
    synthesis_prompt = user_message + "\n\nЗаключения специалистов:\n" + "\n\n".join(f"### {x['role_name']}\n{x['content']}" for x in good)
    try:
        reply = await role_answer(role="coordinator", settings=settings, user_message=synthesis_prompt, context=context, history=[])
        if reply:
            return reply.content, opinions
    except Exception:
        pass
    text = "\n\n".join(f"**{x['role_name']}**\n{x['content']}" for x in good)
    return "Консилиум AI-команды:\n\n" + text, opinions
