import re
from urllib.parse import urlparse

CONTENT_TYPES = {
    "service": "Страница услуги",
    "article": "SEO-статья",
    "category": "Категория каталога",
    "case": "Кейс / проект",
    "regional": "Региональный блок",
    "meta": "Title + Description",
    "alt": "ALT",
    "anchors": "Анкоры",
    "annotation": "Краткая аннотация",
}


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _sent(text: str) -> str:
    text = _clean(text)
    if not text:
        return ""
    return text if text[-1] in ".!?" else text + "."


def _slug_words(url: str) -> list[str]:
    path = urlparse(url).path.strip("/")
    words = re.split(r"[-_/]+", path)
    stop = {"catalog", "uslugi", "services", "service", "category", "page"}
    return [w for w in words if len(w) > 2 and w not in stop][:6]


def generate_content(*, content_type: str, subject: str, project: dict, profile: dict, facts: str = "", region: str = "", target_url: str = "", donor_urls: list[str] | None = None) -> dict:
    subject = _clean(subject)
    facts = _clean(facts)
    region = _clean(region)
    donor_urls = donor_urls or []
    name = project.get("name", "Проект")
    ptype = _clean(project.get("project_type", ""))
    tone = _clean(profile.get("tone", "Экспертный, конкретный, без лишней рекламы"))
    rules = [x.strip() for x in profile.get("rules", []) if x.strip()]
    forbidden = [x.strip() for x in profile.get("forbidden", []) if x.strip()]
    structure = profile.get("service_structure", ["H1", "Краткое описание", "Что входит в услугу", "Преимущества", "CTA"])

    context_line = f" для {region}" if region else ""
    fact_line = facts or (f"Материал для проекта «{name}»" + (f" ({ptype})" if ptype else ""))

    h1 = f"{subject}{context_line}".strip()
    title = h1
    if len(title) < 45:
        suffix = f" — {name}"
        if len(title + suffix) <= 65:
            title += suffix
    description = _sent(f"{subject}{context_line}: {fact_line}")[:160].rstrip()
    if description and description[-1] not in ".!?":
        description = description.rsplit(" ", 1)[0] + "."

    sections: list[dict] = []
    if content_type == "service":
        sections = [
            {"title": "H1", "text": h1},
            {"title": "Вводный текст", "text": _sent(f"{subject}{context_line} — комплексное решение с учётом задач заказчика и особенностей объекта. {fact_line}")},
            {"title": "Что входит в услугу", "items": ["Анализ исходных данных и требований", "Подготовка и реализация необходимого решения", "Контроль результата и сопровождение"]},
            {"title": "Текст под преимуществами", "text": _sent(f"Работы по направлению «{subject}» выполняются с учётом требований проекта, условий эксплуатации и согласованного объёма работ")},
            {"title": "CTA", "text": f"Оставьте заявку, чтобы уточнить объём работ по направлению «{subject}»."},
        ]
    elif content_type == "article":
        sections = [
            {"title": "H1", "text": h1},
            {"title": "Введение", "text": _sent(f"В материале разберём тему «{subject}», основные задачи, критерии выбора решения и практические моменты. {fact_line}")},
            {"title": "Структура статьи", "items": [f"Что важно знать про {subject.lower()}", "Когда это решение применяется", "Как выбрать подходящий вариант", "Типовые ошибки и ограничения", "Практические рекомендации"]},
            {"title": "Вывод", "text": _sent(f"При выборе решения по теме «{subject}» важно учитывать реальные условия применения и требования конкретного проекта")},
        ]
    elif content_type == "category":
        sections = [
            {"title": "H1", "text": h1},
            {"title": "Описание категории", "text": _sent(f"В разделе представлены решения по направлению «{subject}». {fact_line}")},
            {"title": "Что учитывать при выборе", "items": ["Назначение и условия эксплуатации", "Технические характеристики", "Совместимость и требования к обслуживанию"]},
        ]
    elif content_type == "case":
        sections = [
            {"title": "Название кейса", "text": h1},
            {"title": "Аннотация", "text": _sent(f"Реализация проекта по направлению «{subject}» с учётом требований заказчика, сроков и условий объекта")},
            {"title": "Что было выполнено", "items": ["Подготовка решения", "Организация работ / поставки", "Контроль сроков и результата"]},
            {"title": "Основной текст", "text": _sent(f"Команда проекта выполнила комплекс работ по направлению «{subject}». {fact_line}")},
        ]
    elif content_type == "regional":
        r = region or "регионе"
        sections = [
            {"title": "Региональный заголовок", "text": f"{subject} в {r}" if region else subject},
            {"title": "Текст", "text": _sent(f"Организуем {subject.lower()} в {r}. Условия, сроки и формат работы уточняются с учётом адреса, объёма и особенностей заказа")},
        ]
    elif content_type == "annotation":
        sections = [{"title": "Аннотация", "text": _sent(f"{subject}{context_line} — {fact_line[:180]}") }]
    elif content_type == "meta":
        sections = []
    elif content_type == "alt":
        base = subject or "Изображение"
        sections = [{"title": "ALT", "items": [base, f"{base} — {name}", f"{base}{context_line}"]}]
    elif content_type == "anchors":
        words = _slug_words(target_url)
        natural = " ".join(words).replace("-", " ") if words else subject.lower()
        variants = [subject.lower(), natural, f"подробнее о {subject.lower()}"]
        variants = list(dict.fromkeys([v for v in variants if v]))
        sections = [{"title": "Варианты анкора", "items": variants}]

    links = []
    for url in donor_urls[:6]:
        links.append({"url": url, "anchor": subject.lower()})

    return {
        "content_type": content_type,
        "content_type_label": CONTENT_TYPES.get(content_type, content_type),
        "project_id": project.get("id"),
        "project_name": name,
        "subject": subject,
        "title": title,
        "description": description,
        "sections": sections,
        "links": links,
        "image_plan": [
            {"role": "Hero", "idea": f"Ключевой визуал по теме «{subject}» без текста"},
            {"role": "Процесс", "idea": f"Реальный процесс или применение по теме «{subject}»"},
            {"role": "Деталь", "idea": f"Крупный план оборудования, материала или результата по теме «{subject}»"},
        ] if content_type in {"service", "article", "case", "category"} else [],
        "profile": {"tone": tone, "rules": rules, "forbidden": forbidden, "service_structure": structure},
        "notice": "Черновик создан локальными шаблонами ContentDesk. Факты и характеристики нужно проверять по материалам проекта; AI-слой будет подключён отдельно.",
    }
