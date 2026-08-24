from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db.database import get_connection
from app.services.ai_assistant import run_tool_first
from app.services.ai_providers import ollama_status
from app.services.ai_team import ROLES, consilium_answer, list_roles, role_answer, select_role, wants_consilium
from app.services.project_memory import get_project_events, get_project_state, seed_starter_context

router = APIRouter(prefix="/assistant", tags=["AI assistant"])

DEFAULT_SETTINGS: dict[str, Any] = {
    "provider": "builtin",
    "ollama_url": "http://127.0.0.1:11434",
    "ollama_model": "deepseek-r1:latest",
    "role_models": {
        "coordinator": "qwen3:4b-instruct",
        "content_editor": "qwen3:8b",
        "seo_specialist": "deepseek-r1:latest",
        "fact_checker": "deepseek-r1:latest",
    },
    "role_routes": {
        "coordinator": "ollama",
        "content_editor": "ollama",
        "seo_specialist": "ollama",
        "fact_checker": "ollama",
    },
}


class SettingsPayload(BaseModel):
    provider: Literal["builtin", "ollama"] = "builtin"
    ollama_url: str = Field(default="http://127.0.0.1:11434", max_length=500)
    ollama_model: str = Field(default="deepseek-r1:latest", max_length=150)
    role_models: dict[str, str] = Field(default_factory=dict)
    role_routes: dict[str, Literal["builtin", "ollama"]] = Field(default_factory=dict)


class ConversationCreate(BaseModel):
    project_id: int | None = None
    title: str = Field(default="Новый диалог", max_length=180)


class ChatPayload(BaseModel):
    message: str = Field(min_length=1, max_length=16000)
    conversation_id: int | None = None
    project_id: int | None = None
    force_role: str | None = None


class MemoryPayload(BaseModel):
    project_id: int
    kind: Literal["fact", "rule", "decision", "note", "observation", "preference"] = "fact"
    title: str = Field(default="", max_length=180)
    content: str = Field(min_length=1, max_length=12000)
    source: str = Field(default="user", max_length=120)
    confidence: Literal["confirmed", "site", "inferred", "conflict"] = "confirmed"


def _settings() -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute("SELECT settings_json FROM assistant_settings WHERE id = 1").fetchone()
    if not row:
        return json.loads(json.dumps(DEFAULT_SETTINGS))
    try:
        loaded = json.loads(row["settings_json"])
        data = {**DEFAULT_SETTINGS, **loaded}
        if data.get("provider") not in {"builtin", "ollama"}:
            data["provider"] = "ollama"
        data["role_routes"] = {**DEFAULT_SETTINGS["role_routes"], **(loaded.get("role_routes") or {})}
        data["role_routes"] = {k: ("ollama" if v not in {"builtin", "ollama"} else v) for k, v in data["role_routes"].items()}
        data["role_models"] = {**DEFAULT_SETTINGS["role_models"], **(loaded.get("role_models") or {})}
        allowed = {"provider", "ollama_url", "ollama_model", "role_models", "role_routes"}
        data = {k: v for k, v in data.items() if k in allowed}
        return data
    except Exception:
        return json.loads(json.dumps(DEFAULT_SETTINGS))


def _conversation(row) -> dict[str, Any]:
    return dict(row)


def _messages(conversation_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM assistant_messages WHERE conversation_id = ? ORDER BY id", (conversation_id,)).fetchall()
    output = []
    for row in rows:
        item = dict(row)
        try:
            item["tools"] = json.loads(item.pop("tools_json"))
        except Exception:
            item["tools"] = []
        output.append(item)
    return output


def _create_conversation(project_id: int | None, title: str) -> dict[str, Any]:
    with get_connection() as conn:
        cursor = conn.execute("INSERT INTO assistant_conversations(project_id, title) VALUES (?, ?)", (project_id, title[:180]))
        conn.commit()
        row = conn.execute("SELECT * FROM assistant_conversations WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _conversation(row)


@router.get("/settings")
def get_settings():
    return _settings()


@router.put("/settings")
def save_settings(payload: SettingsPayload):
    data = payload.model_dump()
    data["role_routes"] = {**DEFAULT_SETTINGS["role_routes"], **(data.get("role_routes") or {})}
    # Migration safety: unsupported legacy routes become local Ollama routes.
    data["role_routes"] = {k: ("ollama" if v not in {"builtin", "ollama"} else v) for k, v in data["role_routes"].items()}
    data["role_models"] = {**DEFAULT_SETTINGS["role_models"], **(data.get("role_models") or {})}
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO assistant_settings(id, settings_json, updated_at) VALUES (1, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(id) DO UPDATE SET settings_json=excluded.settings_json, updated_at=CURRENT_TIMESTAMP""",
            (json.dumps(data, ensure_ascii=False),),
        )
        conn.commit()
    return data


@router.get("/team")
def team():
    settings = _settings()
    routes = settings.get("role_routes") or {}
    return [{**item, "provider": routes.get(item["id"], "builtin")} for item in list_roles()]


@router.get("/ollama/status")
async def get_ollama_status():
    settings = _settings()
    return await ollama_status(str(settings["ollama_url"]), str(settings.get("ollama_model") or ""))


@router.post("/memory/import-starter")
def import_starter_memory():
    return seed_starter_context()


@router.get("/memory/{project_id}/state")
def get_memory_state(project_id: int):
    return get_project_state(project_id, limit=50)


@router.get("/memory/{project_id}/events")
def get_memory_events(project_id: int, limit: int = 50):
    return get_project_events(project_id, limit=limit)


@router.get("/memory/{project_id}")
def get_memory(project_id: int):
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM ai_project_memory WHERE project_id=? AND is_active=1 ORDER BY id DESC", (project_id,)).fetchall()
    return [dict(row) for row in rows]


@router.post("/memory")
def add_memory(payload: MemoryPayload):
    with get_connection() as conn:
        exists = conn.execute("SELECT id FROM projects WHERE id=?", (payload.project_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Проект не найден")
        cursor = conn.execute(
            "INSERT INTO ai_project_memory(project_id, kind, title, content, source, confidence) VALUES (?, ?, ?, ?, ?, ?)",
            (payload.project_id, payload.kind, payload.title.strip(), payload.content.strip(), payload.source, payload.confidence),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM ai_project_memory WHERE id=?", (cursor.lastrowid,)).fetchone()
    return dict(row)


@router.delete("/memory/{memory_id}", status_code=204)
def delete_memory(memory_id: int):
    with get_connection() as conn:
        result = conn.execute("UPDATE ai_project_memory SET is_active=0, updated_at=CURRENT_TIMESTAMP WHERE id=?", (memory_id,))
        conn.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Запись памяти не найдена")


@router.get("/conversations")
def list_conversations(project_id: int | None = None):
    with get_connection() as conn:
        if project_id is None:
            rows = conn.execute("SELECT * FROM assistant_conversations ORDER BY updated_at DESC, id DESC LIMIT 50").fetchall()
        else:
            rows = conn.execute("SELECT * FROM assistant_conversations WHERE project_id = ? ORDER BY updated_at DESC, id DESC LIMIT 50", (project_id,)).fetchall()
    return [_conversation(row) for row in rows]


@router.post("/conversations")
def create_conversation(payload: ConversationCreate):
    return _create_conversation(payload.project_id, payload.title.strip() or "Новый диалог")


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: int):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM assistant_conversations WHERE id = ?", (conversation_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Диалог не найден")
    return {**_conversation(row), "messages": _messages(conversation_id)}


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: int):
    with get_connection() as conn:
        result = conn.execute("DELETE FROM assistant_conversations WHERE id = ?", (conversation_id,))
        conn.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Диалог не найден")


@router.post("/chat")
async def chat(payload: ChatPayload):
    message = payload.message.strip()
    if payload.conversation_id:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM assistant_conversations WHERE id = ?", (payload.conversation_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Диалог не найден")
        conversation = dict(row)
        project_id = payload.project_id if payload.project_id is not None else conversation["project_id"]
    else:
        project_id = payload.project_id
        title = message[:80] + ("…" if len(message) > 80 else "")
        conversation = _create_conversation(project_id, title)

    with get_connection() as conn:
        conn.execute("INSERT INTO assistant_messages(conversation_id, role, content, tools_json) VALUES (?, 'user', ?, '[]')", (conversation["id"], message))
        conn.commit()

    history_rows = _messages(conversation["id"])
    routing_history = [{"role": x.get("role"), "content": x.get("content", ""), "tools": x.get("tools", [])} for x in history_rows[:-1]]
    fallback, tools, context = await run_tool_first(message, project_id, routing_history)
    settings = _settings()
    history = [{"role": x["role"], "content": x["content"]} for x in history_rows if x["role"] in {"user", "assistant"}][:-1]

    role = payload.force_role if payload.force_role in ROLES else select_role(message)
    provider_used = "builtin"
    model_used = ""
    provider_error = ""
    team_opinions: list[dict[str, Any]] = []
    answer = fallback

    try:
        if wants_consilium(message):
            answer, team_opinions = await consilium_answer(
                settings=settings, user_message=message, context=context, history=history, fallback=fallback
            )
            role = "coordinator"
            providers = sorted({x.get("provider", "") for x in team_opinions if x.get("content")})
            provider_used = "+".join(x for x in providers if x) or "builtin"
        else:
            reply = await role_answer(role=role, settings=settings, user_message=message, context=context, history=history)
            if reply:
                answer = reply.content
                provider_used = reply.provider
                model_used = reply.model
    except Exception as exc:
        provider_error = str(exc)
        answer = fallback + f"\n\nAI-специалист «{ROLES[role]['name']}» сейчас недоступен, поэтому использован встроенный режим ContentDesk."

    role_event = {"name": "ai_role", "label": f"AI-команда · {ROLES[role]['name']}", "status": "done", "data": {"role": role, "provider": provider_used, "model": model_used}}
    tools = [role_event, *tools]
    if team_opinions:
        tools.insert(1, {"name": "ai_consilium", "label": f"Консилиум · {len(team_opinions)} специалиста", "status": "done", "data": team_opinions})

    with get_connection() as conn:
        conn.execute("INSERT INTO assistant_messages(conversation_id, role, content, tools_json) VALUES (?, 'assistant', ?, ?)", (conversation["id"], answer, json.dumps(tools, ensure_ascii=False)))
        conn.execute("UPDATE assistant_conversations SET project_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (project_id, conversation["id"]))
        conn.commit()

    return {
        "conversation_id": conversation["id"], "project_id": project_id, "answer": answer,
        "tools": tools, "provider": provider_used, "model": model_used, "role": role,
        "role_name": ROLES[role]["name"], "provider_error": provider_error, "team_opinions": team_opinions,
    }
