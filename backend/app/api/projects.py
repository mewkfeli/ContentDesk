from typing import Literal
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, HttpUrl
from app.db.database import get_connection
from app.services.project_memory import seed_starter_context, record_event

router = APIRouter(prefix="/projects", tags=["projects"])

class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    domain: HttpUrl
    cms: str = Field(default="", max_length=60)
    project_type: str = Field(default="", max_length=120)
    content_style: str = Field(default="", max_length=160)

class ProjectUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    domain: HttpUrl
    cms: str = Field(default="", max_length=60)
    project_type: str = Field(default="", max_length=120)
    content_style: str = Field(default="", max_length=160)
    status: Literal["active","paused","archived"] = "active"
    notes: str = ""
    sitemap_url: str = ""
    exclude_patterns: str = ""


def rowdict(r):
    d=dict(r); d.setdefault("notes",""); d.setdefault("sitemap_url",""); d.setdefault("exclude_patterns",""); return d

@router.get("")
def list_projects():
    with get_connection() as conn: rows=conn.execute("SELECT * FROM projects ORDER BY CASE status WHEN 'active' THEN 0 WHEN 'paused' THEN 1 ELSE 2 END,id DESC").fetchall()
    return [rowdict(r) for r in rows]

@router.get("/{project_id}")
def get_project(project_id:int):
    with get_connection() as conn: r=conn.execute("SELECT * FROM projects WHERE id=?",(project_id,)).fetchone()
    if not r: raise HTTPException(404,"Проект не найден")
    return rowdict(r)

@router.post("", status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate):
    try:
        with get_connection() as conn:
            c=conn.execute("INSERT INTO projects(name,domain,cms,project_type,content_style) VALUES(?,?,?,?,?)",(payload.name.strip(),str(payload.domain).rstrip('/'),payload.cms.strip(),payload.project_type.strip(),payload.content_style.strip()))
            conn.commit(); r=conn.execute("SELECT * FROM projects WHERE id=?",(c.lastrowid,)).fetchone()
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc): raise HTTPException(409,"Проект с таким доменом уже существует") from exc
        raise
    result = rowdict(r)
    seed_starter_context()
    return result

@router.put("/{project_id}")
def update_project(project_id:int,payload:ProjectUpdate):
    with get_connection() as conn:
        try:
            c=conn.execute("""UPDATE projects SET name=?,domain=?,cms=?,project_type=?,content_style=?,status=?,notes=?,sitemap_url=?,exclude_patterns=? WHERE id=?""",(payload.name.strip(),str(payload.domain).rstrip('/'),payload.cms.strip(),payload.project_type.strip(),payload.content_style.strip(),payload.status,payload.notes,payload.sitemap_url.strip(),payload.exclude_patterns,project_id))
            conn.commit()
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc): raise HTTPException(409,"Проект с таким доменом уже существует") from exc
            raise
        if c.rowcount==0: raise HTTPException(404,"Проект не найден")
        r=conn.execute("SELECT * FROM projects WHERE id=?",(project_id,)).fetchone()
    result = rowdict(r)
    record_event(project_id, "project", "Обновлены настройки проекта", "Изменены основные настройки/метаданные проекта.", {"name":result.get("name"),"domain":result.get("domain"),"status":result.get("status")}, "Настройки проекта")
    seed_starter_context()
    return result

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id:int):
    with get_connection() as conn:
        result=conn.execute("DELETE FROM projects WHERE id=?",(project_id,)); conn.commit()
    if result.rowcount==0: raise HTTPException(404,"Проект не найден")
