from fastapi import APIRouter, Query
from app.db.database import get_connection
router = APIRouter(prefix="/search", tags=["search"])

@router.get("")
def search(q: str = Query(min_length=2, max_length=120)):
    term = f"%{q.strip()}%"
    out = []
    with get_connection() as conn:
        for r in conn.execute("SELECT id,name,domain FROM projects WHERE name LIKE ? OR domain LIKE ? OR notes LIKE ? LIMIT 10", (term,term,term)):
            out.append({"type":"project","title":r["name"],"subtitle":r["domain"],"href":f'/projects/{r["id"]}'})
        for r in conn.execute("SELECT id,title,project_name,status FROM saved_tasks WHERE title LIKE ? OR parsed_json LIKE ? LIMIT 15", (term,term)):
            out.append({"type":"task","title":r["title"],"subtitle":f'{r["project_name"]} · {r["status"]}',"href":f'/tasks/manage/{r["id"]}'})
        for r in conn.execute("SELECT c.id,c.title,p.name project_name FROM assistant_conversations c LEFT JOIN projects p ON p.id=c.project_id WHERE c.title LIKE ? LIMIT 10", (term,)):
            out.append({"type":"chat","title":r["title"],"subtitle":r["project_name"] or "Без проекта","href":f'/assistant?conversation={r["id"]}'})
        for r in conn.execute("SELECT a.id,p.name,a.result_json FROM site_audits a JOIN projects p ON p.id=a.project_id WHERE a.result_json LIKE ? ORDER BY a.id DESC LIMIT 5", (term,)):
            out.append({"type":"audit","title":f'SEO-аудит · {r["name"]}',"subtitle":"Совпадение найдено в отчёте","href":f'/site-audit/{r["id"]}'})
        for r in conn.execute("SELECT c.id,p.name,c.source_name FROM indexing_checks c JOIN projects p ON p.id=c.project_id WHERE c.result_json LIKE ? OR c.source_name LIKE ? ORDER BY c.id DESC LIMIT 5", (term,term)):
            out.append({"type":"indexing","title":f'Проверка индексации · {r["name"]}',"subtitle":r["source_name"] or "Список GSC","href":f'/audit/indexing/{r["id"]}'})
    return out[:30]
