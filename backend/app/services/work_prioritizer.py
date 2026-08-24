from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

from app.db.database import get_connection


def _json(value: str, default: Any):
    try:
        return json.loads(value)
    except Exception:
        return default


def _deadline(value: str) -> date | None:
    raw = (value or '').strip()
    if not raw or raw.lower() in {'не указан', 'не указано', '—'}:
        return None
    for fmt in ('%d.%m.%Y', '%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    m = re.search(r'(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})', raw)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def _task_progress(parsed: dict[str, Any], done_keys: list[str]) -> tuple[int, int]:
    task_keys = [f"task-{i.get('id')}" for g in parsed.get('role_groups', []) for i in g.get('items', [])]
    qa_keys = [f"qa-{i}" for i, _ in enumerate(parsed.get('qa_checklist', []))]
    valid = task_keys + qa_keys
    return len([x for x in valid if x in set(done_keys)]), len(valid)


def build_work_plan(project_id: int | None = None) -> dict[str, Any]:
    today = date.today()
    items: list[dict[str, Any]] = []
    with get_connection() as conn:
        project_where = 'WHERE id = ?' if project_id else ''
        projects = conn.execute(f'SELECT * FROM projects {project_where}', ((project_id,) if project_id else ())).fetchall()
        for project_row in projects:
            p = dict(project_row)
            pid = p['id']
            audit_row = conn.execute('SELECT * FROM site_audits WHERE project_id = ? ORDER BY id DESC LIMIT 1', (pid,)).fetchone()
            audit = dict(audit_row) if audit_row else None
            linking = conn.execute('SELECT * FROM internal_link_audits WHERE project_id = ? ORDER BY id DESC LIMIT 1', (pid,)).fetchone()

            task_rows = conn.execute("SELECT * FROM saved_tasks WHERE project_id = ? AND status != 'done'", (pid,)).fetchall()
            generated_site_task = None
            if audit:
                source = f"AI Assistant / Site Audit #{audit['id']} / critical"
                generated_site_task = next((dict(row) for row in task_rows if (row['source_name'] or '') == source), None)

            # Не дублируем в плане «найденную проблему» и уже созданную из неё
            # задачу. Если задача по этому аудиту есть, она сама представляет
            # работу и получает детали аудита ниже.
            if audit and not generated_site_task:
                if audit['critical']:
                    items.append({
                        'kind': 'seo', 'project_id': pid, 'project_name': p['name'],
                        'title': f"Исправить критические SEO-ошибки — {audit['critical']}",
                        'detail': f"Последний аудит: {audit['score']}/100 · {audit['pages_total']} стр.",
                        'score': 100 + min(audit['critical'], 20), 'priority': 'P1', 'href': f"/site-audit/{audit['id']}",
                        'overdue': False, 'quick': audit['critical'] <= 2,
                    })
                elif audit['warnings']:
                    items.append({
                        'kind': 'seo', 'project_id': pid, 'project_name': p['name'],
                        'title': f"Разобрать SEO-предупреждения — {audit['warnings']}",
                        'detail': f"Последний аудит: {audit['score']}/100", 'score': 52 + min(audit['warnings'], 15),
                        'priority': 'P2', 'href': f"/site-audit/{audit['id']}", 'overdue': False, 'quick': audit['warnings'] <= 3,
                    })

            if linking:
                l = dict(linking)
                result = _json(l['result_json'], {})
                orphans = int(result.get('orphans', l['orphans']) or 0)
                broken = int(result.get('broken_links_count', l['broken_links']) or 0)
                weak = int(result.get('weak_pages', 0) or 0)
                if orphans or broken:
                    items.append({
                        'kind': 'linking', 'project_id': pid, 'project_name': p['name'],
                        'title': f"Исправить перелинковку: сирот {orphans}, битых ссылок {broken}",
                        'detail': f"Оценка перелинковки: {l['score']}/100", 'score': 94 + min(orphans + broken, 15),
                        'priority': 'P1', 'href': f"/linking/{l['id']}", 'overdue': False, 'quick': (orphans + broken) <= 2,
                    })
                elif weak:
                    items.append({
                        'kind': 'linking', 'project_id': pid, 'project_name': p['name'],
                        'title': f"Усилить слабые страницы перелинковкой — {weak}",
                        'detail': f"Оценка перелинковки: {l['score']}/100", 'score': 46 + min(weak // 5, 12),
                        'priority': 'P3', 'href': f"/linking/{l['id']}", 'overdue': False, 'quick': weak <= 3,
                    })

            for row in task_rows:
                t = dict(row)
                parsed = _json(t['parsed_json'], {})
                done = _json(t['done_json'], [])
                completed, total = _task_progress(parsed, done)
                remaining = max(0, total - completed)
                dl = _deadline(t['deadline'])
                overdue = bool(dl and dl < today)
                days = (dl - today).days if dl else None
                base = {'P1': 88, 'P2': 68, 'P3': 48}.get(t['priority'], 42)
                if overdue: base += 30
                elif days is not None and days <= 2: base += 20
                elif days is not None and days <= 7: base += 10
                if remaining <= 2 and remaining > 0: base += 6

                detail = f"Осталось {remaining} из {total}" + (f" · срок {t['deadline']}" if dl else '')
                if audit and (t.get('source_name') or '') == f"AI Assistant / Site Audit #{audit['id']} / critical":
                    detail = f"Критических проблем: {audit['critical']} · задача уже создана · осталось {remaining} из {total}"
                    base = max(base, 100 + min(int(audit['critical'] or 0), 20))

                items.append({
                    'kind': 'task', 'project_id': pid, 'project_name': p['name'], 'title': t['title'],
                    'detail': detail, 'score': base, 'priority': t['priority'], 'href': f"/tasks/manage/{t['id']}",
                    'overdue': overdue, 'quick': 0 < remaining <= 3,
                })
    items.sort(key=lambda x: (-x['score'], x['project_name'], x['title']))
    return {
        'date': today.isoformat(), 'items': items,
        'urgent': [x for x in items if x['score'] >= 85],
        'overdue': [x for x in items if x['overdue']],
        'quick_wins': [x for x in items if x['quick']],
        'top': items[:8],
    }


def render_plan(plan: dict[str, Any], mode: str = 'today') -> str:
    source = plan['top']
    title = 'План работы на сегодня'
    if mode == 'urgent':
        source, title = plan['urgent'][:10], 'Срочные задачи'
    elif mode == 'overdue':
        source, title = plan['overdue'][:10], 'Просроченные задачи'
    elif mode == 'quick':
        source, title = plan['quick_wins'][:10], 'Быстрые задачи'
    if not source:
        return f"{title}: подходящих пунктов сейчас нет."
    lines = [f"{title}:"]
    for i, item in enumerate(source, 1):
        marker = 'P1' if item['score'] >= 85 else item.get('priority', '—')
        lines.append(f"{i}. [{marker}] {item['project_name']} — {item['title']}. {item['detail']}")
    if mode == 'today':
        lines.append(f"\nСрочных: {len(plan['urgent'])} · просроченных: {len(plan['overdue'])} · быстрых: {len(plan['quick_wins'])}.")
    return '\n'.join(lines)
