from __future__ import annotations

import re
from collections import OrderedDict
from io import BytesIO
from typing import Any

from docx import Document

URL_RE = re.compile(r"https?://[^\s\])}>;,]+", re.I)
RELATIVE_URL_RE = re.compile(r"(?<![\w:/.-])(/[a-zA-Z0-9а-яА-ЯёЁ_%+~.-]+(?:/[a-zA-Z0-9а-яА-ЯёЁ_%+~.-]+)*/?)(?=[\s\]),.;:!?]|$)")
PRIORITY_RE = re.compile(r"\bP[0-3]\b", re.I)
DEADLINE_RE = re.compile(r"(?:срок(?:и)?\s*[:—-]?\s*([^\n.;]+)|до\s+(\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?)|(?:сегодня|завтра|послезавтра)|(?:недел(?:я|и|ю|ь)\s*\d+(?:\s*[–—-]\s*\d+)?))", re.I)

ROLE_PATTERNS = [
    ("Разработчик", ("разработчик", "front-end", "back-end", "frontend", "backend")),
    ("Контент-менеджер", ("контент-менеджер", "контент менеджер")),
    ("SEO-специалист", ("seo-специалист", "seo специалист", "сео-специалист")),
    ("Дизайнер", ("дизайнер",)),
]

TYPE_RULES = [
    ("Перелинковка", ("перелинков", "внутренн", "ссыл", "анкор", "донор")),
    ("Техническое SEO", ("robots", "x-robots", "sitemap", "canonical", "breadcrumb", "хлебн", "schema.org", "индексац", "gsc", "краулинг")),
    ("Контент", ("текст", "тизер", "анонс", "контент", "стать", "описан", "главн", "хаб")),
    ("Изображения", ("изображ", "фото", "картин", "alt", "webp", "avif", "баннер")),
    ("Разработка", ("верст", "dom", "меню", "мега-меню", "код", "frontend", "backend", "cms", "301", "404")),
]

ACTION_WORDS = ("добав", "созда", "подготов", "размест", "замен", "исправ", "провер", "настро", "убер", "удал", "сдел", "перенес", "обнов", "доработ", "встав", "загруз", "опублик", "простав", "переимен", "сверст", "реализ", "напис", "сгенер", "перелинк", "оптимиз", "скоррект", "вывести", "подключ", "убед")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" \t•*-—;,.\n")


def _category(text: str) -> str:
    low = text.lower()
    for name, words in TYPE_RULES:
        if any(word in low for word in words):
            return name
    return "Общее"


def _role_from_heading(text: str) -> str | None:
    low = text.lower()
    for role, words in ROLE_PATTERNS:
        if any(word in low for word in words):
            return role
    return None


def _looks_action(text: str) -> bool:
    low = text.lower().strip()
    first = low.split(" ", 1)[0] if low else ""
    return any(first.startswith(x) for x in ACTION_WORDS)


def _detect_project(text: str, project_names: list[str]) -> str:
    low = text.lower()
    matches = [name for name in project_names if name and name.lower() in low]
    if matches:
        return max(matches, key=len)
    match = re.search(r"(?:проект|сайт|клиент)\s*[:—-]\s*([^\n.;]+)", text, re.I)
    return _clean(match.group(1))[:80] if match else "Не определён"


def _detect_deadline(text: str) -> str:
    match = DEADLINE_RE.search(text)
    if not match:
        return "Не указан"
    return _clean(next((g for g in match.groups() if g), match.group(0)))


def _meta(text: str, project_names: list[str]) -> tuple[str, str, str, list[str], list[str], list[str]]:
    priority_match = PRIORITY_RE.search(text)
    priority = priority_match.group(0).upper() if priority_match else "Не указан"
    deadline = _detect_deadline(text)
    urls = list(dict.fromkeys(URL_RE.findall(text)))
    relative_urls = list(dict.fromkeys(RELATIVE_URL_RE.findall(text)))
    ambiguities = []
    if priority == "Не указан": ambiguities.append("В ТЗ не указан приоритет")
    if deadline == "Не указан": ambiguities.append("В ТЗ не указан срок")
    if relative_urls and not urls:
        ambiguities.append("Найдены относительные URL, но домен проекта не указан — выберите проект, чтобы собрать полные адреса")
    elif not urls and not relative_urls:
        ambiguities.append("В ТЗ не найдены URL страниц — при необходимости их нужно уточнить")
    return _detect_project(text, project_names), priority, deadline, urls, relative_urls, ambiguities


def _finalize(title: str, text: str, project_names: list[str], goals: list[str], expected: list[str], notes: list[str], references: list[str], tasks: list[dict[str, Any]]) -> dict[str, Any]:
    project, priority, deadline, urls, relative_urls, ambiguities = _meta(text, project_names)
    grouped: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for task in tasks:
        grouped.setdefault(task["role"], []).append(task)
    low = text.lower()
    qa = ["Проверить результат на desktop", "Проверить результат на mobile"]
    if any(x in low for x in ("ссыл", "перелинков", "донор", "анкор")):
        qa.append("Проверить все добавленные и изменённые внутренние ссылки")
    if any(x in low for x in ("текст", "контент", "тизер", "анонс", "стать", "описан")):
        qa.append("Проверить орфографию и фактические данные в добавленном контенте")
    if any(x in low for x in ("breadcrumb", "хлебн", "breadcrumblist")):
        qa.append("Проверить BreadcrumbList и соответствие хлебных крошек фактической навигации")
    if "meta robots" in low or "robots" in low:
        qa.append("Проверить meta robots на затронутых страницах")
    if "x-robots" in low:
        qa.append("Проверить X-Robots-Tag на уровне сервера")
    if "sitemap" in low:
        qa.append("Проверить наличие затронутых URL в sitemap.xml и корректность sitemap после изменений")
    if any(x in low for x in ("canonical", "каноникал")):
        qa.append("Проверить canonical на затронутых страницах")
    if any(x in low for x in ("301", "редирект")):
        qa.append("Проверить редиректы и отсутствие цепочек перенаправлений")
    qa = list(dict.fromkeys(qa))
    return {
        "title": title or "Новое ТЗ", "project": project, "priority": priority, "deadline": deadline,
        "urls": urls, "relative_urls": relative_urls, "task_count": len(tasks), "role_groups": [{"role": k, "items": v} for k,v in grouped.items()],
        "goals": goals, "expected_results": expected, "notes": notes, "references": references,
        "qa_checklist": qa, "ambiguities": ambiguities,
    }


def parse_structured_lines(lines: list[dict[str, Any]], project_names: list[str] | None = None) -> dict[str, Any]:
    project_names = project_names or []
    raw_text = "\n".join(x["text"] for x in lines if x.get("text"))
    title = next((x["text"] for x in lines if x.get("text", "").lower().startswith(("тз ", "тз№", "тз №", "техническое задание"))), "")
    goals: list[str] = []; expected: list[str] = []; notes: list[str] = []; references: list[str] = []; tasks: list[dict[str, Any]] = []
    section = "context"; role = "Общее"; current: dict[str, Any] | None = None; tid = 0

    for row in lines:
        text = _clean(row.get("text", "")); level = row.get("level")
        if not text: continue
        low = text.lower()
        detected_role = _role_from_heading(text)
        if low.startswith("цели тз") or low.startswith("цель тз"):
            section = "goals"; current = None; continue
        if low.startswith("ожидаемый результат"):
            section = "expected"; current = None
            rest = text.split(":",1)[1].strip() if ":" in text else ""
            if rest: expected.append(rest)
            continue
        if detected_role and (low.startswith("задач") or "для " in low):
            role = detected_role; section = "tasks"; current = None; continue
        if re.search(r"\.(?:xlsx|xls|pdf|docx)$", text, re.I):
            references.append(text); continue
        if section == "goals":
            goals.append(text); continue
        if section == "expected":
            expected.append(text); continue

        if level == 0 or (level is None and section == "tasks" and text.endswith(":") and not low.startswith(("проблема:", "решение:", "пример:"))):
            tid += 1
            current = {"id": tid, "title": text.rstrip(":"), "role": role, "category": _category(text), "problem": "", "solution": "", "subtasks": [], "notes": [], "done": False}
            tasks.append(current); section = "tasks"; continue

        if current is not None:
            if low.startswith("проблема:"):
                current["problem"] = text.split(":",1)[1].strip(); continue
            if low.startswith("решение:"):
                current["solution"] = text.split(":",1)[1].strip(); continue
            if low.startswith("пример:"):
                current["notes"].append(text); continue
            if level is not None or _looks_action(text):
                current["subtasks"].append(text); continue
            current["notes"].append(text); continue

        if text != title:
            notes.append(text)

    return _finalize(title, raw_text, project_names, goals, expected, notes, references, tasks)


def parse_docx(data: bytes, project_names: list[str] | None = None) -> dict[str, Any]:
    doc = Document(BytesIO(data))
    lines = []
    for p in doc.paragraphs:
        text = p.text.strip()
        if not text: continue
        level = None
        ppr = p._p.pPr
        if ppr is not None and ppr.numPr is not None:
            level = int(ppr.numPr.ilvl.val) if ppr.numPr.ilvl is not None else 0
        lines.append({"text": text, "level": level})
    if not lines: raise ValueError("В DOCX не найден текст")
    return parse_structured_lines(lines, project_names)


def parse_task(text: str, project_names: list[str] | None = None) -> dict[str, Any]:
    text = text.strip()
    if len(text) < 5: raise ValueError("Вставьте текст ТЗ")
    if len(text) > 80000: raise ValueError("ТЗ слишком большое: максимум 80 000 символов")
    lines = []
    for raw in text.replace("\r", "").split("\n"):
        raw = raw.strip()
        if not raw: continue
        m = re.match(r"^(\d+)[.)]\s*(.+)$", raw)
        lines.append({"text": m.group(2) if m else raw, "level": 0 if m else None})
    return parse_structured_lines(lines, project_names)
