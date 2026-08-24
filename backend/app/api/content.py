import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db.database import get_connection
from app.services.content_assistant import generate_content
from app.services.project_memory import record_event, update_state

router = APIRouter(prefix="/content", tags=["content"])

DEFAULT_PROFILE = {
    "tone": "Экспертный, конкретный, без лишней рекламы",
    "rules": ["Не придумывать неподтверждённые факты", "Использовать понятные формулировки"],
    "forbidden": ["маркетинговые клише", "неподтверждённые цифры"],
    "service_structure": ["H1", "Краткое описание", "Что входит в услугу", "Текст под преимуществами", "CTA"],
}

class ProfilePayload(BaseModel):
    tone: str = ""
    rules: list[str] = []
    forbidden: list[str] = []
    service_structure: list[str] = []

class GeneratePayload(BaseModel):
    project_id: int
    content_type: str
    subject: str = Field(min_length=2, max_length=240)
    facts: str = ""
    region: str = ""
    target_url: str = ""
    donor_urls: list[str] = []


def _get_project(project_id: int):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Проект не найден")
    return dict(row)

@router.get("/profiles/{project_id}")
def get_profile(project_id: int):
    _get_project(project_id)
    with get_connection() as conn:
        row = conn.execute("SELECT profile_json FROM project_content_profiles WHERE project_id = ?", (project_id,)).fetchone()
    if not row:
        return DEFAULT_PROFILE
    try:
        data = json.loads(row["profile_json"])
    except Exception:
        data = {}
    return {**DEFAULT_PROFILE, **data}

@router.put("/profiles/{project_id}")
def save_profile(project_id: int, payload: ProfilePayload):
    _get_project(project_id)
    data = payload.model_dump()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO project_content_profiles(project_id, profile_json, updated_at)
               VALUES (?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(project_id) DO UPDATE SET profile_json=excluded.profile_json, updated_at=CURRENT_TIMESTAMP""",
            (project_id, json.dumps(data, ensure_ascii=False)),
        )
        conn.commit()
    summary = f"Обновлён контент-профиль: тон — {data.get('tone','')}; правил — {len(data.get('rules') or [])}; запрещённых формулировок — {len(data.get('forbidden') or [])}."
    update_state(project_id, "content_profile", "Контент-профиль проекта", summary, data, "Контент-профиль")
    record_event(project_id, "content_profile", "Обновлён контент-профиль", summary, data, "Контент-профиль")
    return data

@router.post("/generate")
def generate(payload: GeneratePayload):
    project = _get_project(payload.project_id)
    with get_connection() as conn:
        row = conn.execute("SELECT profile_json FROM project_content_profiles WHERE project_id = ?", (payload.project_id,)).fetchone()
    profile = DEFAULT_PROFILE
    if row:
        try:
            profile = {**DEFAULT_PROFILE, **json.loads(row["profile_json"])}
        except Exception:
            pass
    return generate_content(
        content_type=payload.content_type,
        subject=payload.subject,
        project=project,
        profile=profile,
        facts=payload.facts,
        region=payload.region,
        target_url=payload.target_url,
        donor_urls=payload.donor_urls,
    )
