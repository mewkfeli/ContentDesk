from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from app.services.internal_linking import analyze_internal_links, page_key
from app.services.seo_audit import USER_AGENT, normalize_url
from app.services.site_audit import audit_site_page, collect_sitemap_entries, discover_sitemap

STATUS_LABELS = {
    "ok": "🟢 Всё нормально",
    "content": "🟡 Исправить контент-менеджеру",
    "developer": "🔴 Передать разработчику",
    "insufficient": "⚪ Недостаточно данных",
}
EXECUTOR_LABELS = {
    "ok": "Не требуется",
    "content": "Контент-менеджер",
    "developer": "Разработчик",
    "insufficient": "Проверить повторно после полного crawl",
}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _host(value: str) -> str:
    return urlparse(value).netloc.lower().removeprefix("www.")


def _url_key(value: str) -> str:
    return page_key(value)


def _same_page(left: str, right: str) -> bool:
    return bool(left and right and _url_key(left) == _url_key(right))


def _robots_flags(value: str) -> dict[str, bool]:
    low = value.lower()
    none_directive = bool(re.search(r"(?:^|[,\s:])none(?:$|[,\s])", low))
    all_directive = bool(re.search(r"(?:^|[,\s:])all(?:$|[,\s])", low))
    noindex = none_directive or bool(re.search(r"(?:^|[,\s:])noindex(?:$|[,\s])", low))
    nofollow = none_directive or bool(re.search(r"(?:^|[,\s:])nofollow(?:$|[,\s])", low))
    return {
        "noindex": noindex,
        "nofollow": nofollow,
        "index": (all_directive or bool(re.search(r"(?:^|[,\s:])index(?:$|[,\s])", low))) and not noindex,
        "follow": (all_directive or bool(re.search(r"(?:^|[,\s:])follow(?:$|[,\s])", low))) and not nofollow,
    }


def _candidate_hub(target_url: str, page_map: dict[str, dict[str, Any]], incoming_links: list[dict[str, Any]], home_url: str) -> tuple[str, str]:
    """Infer a hub from real donor relationships first, URL ancestry second."""
    # A DOM-classified hub/category donor is the strongest signal.
    typed = []
    for link in incoming_links:
        source = page_map.get(_url_key(link.get("source", "")))
        if not source or _same_page(source.get("url", ""), home_url):
            continue
        types = set(link.get("types") or ([link.get("type")] if link.get("type") else []))
        if "hub" in types:
            typed.append(source)
    if typed:
        typed.sort(key=lambda row: (-(row.get("depth") if row.get("depth") is not None else 999), row.get("outgoing", 0)), reverse=True)
        return typed[0]["url"], "structure"

    # Flat CMS structures have no useful URL parent, so prefer shallow donor pages
    # that link to many internal pages. This uses the graph, not the URL alone.
    donors = []
    for link in incoming_links:
        source = page_map.get(_url_key(link.get("source", "")))
        if not source or _same_page(source.get("url", ""), home_url):
            continue
        depth = source.get("depth")
        outgoing = int(source.get("outgoing", 0) or 0)
        if depth is not None and depth <= 2 and outgoing >= 6:
            donors.append(source)
    if donors:
        donors.sort(key=lambda row: (row.get("outgoing", 0), row.get("incoming", 0)), reverse=True)
        return donors[0]["url"], "inferred"

    # URL ancestry remains a weak fallback only when that ancestor actually exists in the crawled graph.
    parsed = urlparse(target_url)
    segments = [segment for segment in parsed.path.strip("/").split("/") if segment]
    base = f"{parsed.scheme}://{parsed.netloc}"
    for length in range(len(segments) - 1, 0, -1):
        candidate = base + "/" + "/".join(segments[:length]) + "/"
        row = page_map.get(_url_key(candidate))
        if row:
            return row["url"], "ancestor"
    return "", "unknown"


def _technical_issue(code: str, label: str, detail: str = "", *, blocking: bool = True) -> dict[str, Any]:
    return {"code": code, "label": label, "detail": detail, "owner": "developer", "blocking": blocking}


def _content_issue(code: str, label: str, detail: str = "", *, priority: str = "normal") -> dict[str, Any]:
    return {"code": code, "label": label, "detail": detail, "owner": "content", "priority": priority}


def _classify(row: dict[str, Any]) -> dict[str, Any]:
    tech: list[dict[str, Any]] = []
    content: list[dict[str, Any]] = []
    notes: list[str] = []
    link_data_sufficient = bool(row.get("link_data_sufficient", True))

    initial_status = int(row.get("initial_status_code") or row.get("status_code") or 0)
    final_status = int(row.get("status_code") or 0)
    redirect_chain = row.get("redirect_chain") or []
    if initial_status in {301, 302, 303, 307, 308} or redirect_chain:
        tech.append(_technical_issue("redirect", f"URL отвечает редиректом HTTP {initial_status}", row.get("final_url", "")))
    if final_status == 0:
        tech.append(_technical_issue("unavailable", "Страница технически недоступна", "Запрос не завершился успешно."))
    elif final_status == 404:
        tech.append(_technical_issue("http_404", "HTTP 404", "Страница не найдена."))
    elif final_status >= 500:
        tech.append(_technical_issue("http_5xx", f"HTTP {final_status}", "Серверная ошибка."))
    elif not 200 <= final_status < 300:
        tech.append(_technical_issue("http_status", f"HTTP {final_status}", "Проверьте ожидаемое поведение URL."))

    content_type = (row.get("content_type") or "").lower()
    if final_status and "html" not in content_type:
        tech.append(_technical_issue("not_html", "URL не возвращает HTML", row.get("content_type", "")))

    robots = row.get("robots", "") or ""
    robots_flags = _robots_flags(robots)
    if robots_flags["noindex"]:
        tech.append(_technical_issue("meta_noindex", "Meta robots содержит noindex", robots))

    x_robots = row.get("x_robots", "") or ""
    x_flags = _robots_flags(x_robots)
    if x_flags["noindex"]:
        tech.append(_technical_issue("x_robots_noindex", "X-Robots-Tag содержит noindex", x_robots))

    canonical = row.get("canonical", "") or ""
    final_url = row.get("final_url") or row.get("url") or ""
    if canonical:
        if not _same_page(canonical, final_url):
            tech.append(_technical_issue("canonical_other", "Canonical ведёт на другой URL", canonical))
    else:
        notes.append("Canonical отсутствует. Само по себе это не является блокировкой индексации.")

    sitemap = row.get("sitemap") or {}
    if not sitemap.get("present"):
        tech.append(_technical_issue(
            "missing_sitemap", "URL не найден в sitemap",
            "Проверьте, должен ли этот URL присутствовать в карте сайта и не исключён ли он генератором sitemap.",
            blocking=False,
        ))
    else:
        if not sitemap.get("priority"):
            notes.append("В sitemap не указан priority — это не считается критической ошибкой.")
        if not sitemap.get("changefreq"):
            notes.append("В sitemap не указан changefreq — это не считается критической ошибкой.")

    inlinks = int(row.get("inlinks") or 0)
    hub_status = row.get("hub_status")
    if row.get("self_link"):
        notes.append("На странице обнаружена самоссылка. Она показана отдельно и не учитывается в Inlinks, потому что не является независимой страницей-донором.")
    if link_data_sufficient:
        if inlinks == 0:
            content.append(_content_issue(
                "orphan", "Нет внутренних HTML-ссылок на страницу",
                "Полный crawl не обнаружил уникальных страниц-доноров с обычным <a href>.", priority="high",
            ))
        elif inlinks == 1 and not row.get("home_link") and hub_status != "yes":
            content.append(_content_issue(
                "weak_inlinks", "Обнаружена только 1 уникальная страница-донор",
                "Откройте список доноров и оцените значимость существующей ссылки перед добавлением новых.", priority="normal",
            ))

        if row.get("hub_candidate") and hub_status == "no":
            content.append(_content_issue(
                "missing_hub_link", "Предполагаемая хабовая/родительская страница не ссылается на URL",
                row.get("hub_candidate", ""), priority="normal",
            ))
    else:
        notes.append("Данные внутренней перелинковки не классифицируются: crawl сайта неполный или недостаточно надёжен.")

    if not _clean(row.get("title")):
        content.append(_content_issue("missing_title", "Title отсутствует или пуст", priority="high"))
    if not _clean(row.get("h1")):
        content.append(_content_issue("missing_h1", "H1 отсутствует или пуст", priority="high"))
    elif int(row.get("h1_count") or 0) > 1:
        content.append(_content_issue("multiple_h1", f"На странице несколько H1: {row.get('h1_count')}", priority="normal"))

    word_count = int(row.get("word_count") or 0)
    if final_status and 200 <= final_status < 300:
        if word_count == 0:
            content.append(_content_issue("empty_content", "Содержательный текст не обнаружен", priority="high"))
        elif word_count < 50:
            content.append(_content_issue(
                "very_short_content", f"Очень мало текста: около {word_count} слов",
                "Это предупреждающий сигнал, а не автоматический диагноз: оцените назначение страницы и достаточность содержания.",
            ))
        elif word_count < 150:
            notes.append(f"На странице около {word_count} слов. Для коротких служебных страниц это может быть нормально; проверьте достаточность по смыслу.")

    blocking_tech = [item for item in tech if item.get("blocking")]
    non_link_content = [item for item in content if item.get("code") not in {"orphan", "weak_inlinks", "missing_hub_link"}]
    if blocking_tech:
        status = "developer"
    elif tech:
        status = "developer"
    elif non_link_content:
        status = "content"
    elif not link_data_sufficient:
        status = "insufficient"
    elif content:
        status = "content"
    else:
        status = "ok"

    recommendations: list[str] = []
    if status == "developer":
        for item in tech:
            if item["code"] == "x_robots_noindex":
                recommendations.append("Передать URL разработчику: убрать или скорректировать X-Robots-Tag, если noindex не является намеренным.")
            elif item["code"] == "meta_noindex":
                recommendations.append("Проверить источник meta robots noindex (CMS/SEO-настройки/шаблон) и передать разработчику, если запрет не является намеренным.")
            elif item["code"] == "canonical_other":
                recommendations.append("Передать разработчику/SEO-специалисту проверку canonical: сейчас он указывает на другой URL.")
            elif item["code"] == "missing_sitemap":
                recommendations.append("Проверить генерацию sitemap и необходимость присутствия URL в карте сайта. Отсутствие URL не доказывает причину неиндексации само по себе.")
            elif item["code"] == "redirect":
                recommendations.append("Проверить, должен ли проблемный URL редиректить. Для индексации ориентируйтесь на конечный URL.")
            elif item["code"].startswith("http_") or item["code"] in {"unavailable", "not_html"}:
                recommendations.append("Передать разработчику техническую доступность URL.")
        if content:
            recommendations.append("После устранения технических блокировок можно дополнительно выполнить контентные рекомендации ниже.")
    elif status == "content":
        if any(item["code"] == "orphan" for item in content):
            recommendations.append("Добавить страницу в естественную структуру сайта: прежде всего ссылку с тематического хаба/раздела, если такой раздел существует.")
            recommendations.append("Добавить релевантные контекстные ссылки со смежных страниц. Не наращивать количество ссылок только ради числа.")
        if any(item["code"] == "weak_inlinks" for item in content):
            recommendations.append("Оценить текущую страницу-донор и при необходимости усилить URL релевантными ссылками со смежных услуг/материалов.")
        if any(item["code"] == "missing_hub_link" for item in content):
            recommendations.append("Если определённая ContentDesk страница действительно является тематическим хабом, добавить с неё естественную ссылку на URL.")
        if any(item["code"] in {"missing_title", "missing_h1", "multiple_h1"} for item in content):
            recommendations.append("Исправить Title/H1 с учётом назначения страницы и без искусственного переспама.")
        if any(item["code"] in {"empty_content", "very_short_content"} for item in content):
            recommendations.append("Проверить, достаточно ли страница отвечает на задачу пользователя. Не увеличивать текст механически только ради объёма.")
    elif status == "insufficient":
        recommendations.append("Не делать вывод о качестве перелинковки по этому запуску. Увеличьте лимит crawl или устраните ошибки обхода и повторите проверку.")
    else:
        recommendations.append("Явных технических блокировок и проблем внутренней доступности не найдено. Статус GSC может быть связан с приоритетом обхода, качеством/дублированием контента или другими факторами вне этой проверки.")

    return {
        **row,
        "status": status,
        "status_label": STATUS_LABELS[status],
        "executor": EXECUTOR_LABELS[status],
        "technical_issues": tech,
        "content_issues": content,
        "notes": notes,
        "problems": [item["label"] for item in tech + content],
        "recommendations": recommendations,
        "recommendation": " ".join(recommendations),
        "robots_flags": robots_flags,
        "x_robots_flags": x_flags,
    }


async def run_indexing_check(
    *,
    domain: str,
    urls: list[str],
    sitemap_url: str = "",
    max_pages: int = 500,
    exclude_patterns: list[str] | None = None,
    progress_callback=None,
    cancel_event=None,
) -> dict[str, Any]:
    if not urls:
        raise ValueError("В импортированном списке нет URL для проверки.")
    base_domain = normalize_url(domain).rstrip("/")
    max_pages = max(1, min(max_pages, 1000))
    exclude_patterns = exclude_patterns or []

    if progress_callback:
        await progress_callback(0, max_pages, "Строю один граф внутренних ссылок сайта")

    # Reuse the existing crawler once for the whole imported list. This is the
    # expensive operation; never repeat it per GSC URL.
    linking = await analyze_internal_links(
        base_domain,
        sitemap_url,
        max_pages,
        exclude_patterns,
        progress_callback=progress_callback,
        cancel_event=cancel_event,
    )

    if cancel_event is not None and cancel_event.is_set():
        raise asyncio.CancelledError

    page_map = {_url_key(page["url"]): page for page in linking.get("pages", [])}
    project_host = _host(base_domain)

    timeout = httpx.Timeout(18.0, connect=8.0)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/xml,text/xml;q=0.9,*/*;q=0.8"}
    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
        resolved_sitemap = await discover_sitemap(client, base_domain, sitemap_url or linking.get("sitemap_url", ""))
        try:
            sitemap_entries, sitemap_errors = await collect_sitemap_entries(client, resolved_sitemap, max_urls=max(max_pages * 4, len(urls) * 4), max_sitemaps=80)
        except ValueError:
            sitemap_entries, sitemap_errors = [], ["Не удалось получить список URL из sitemap."]
        sitemap_map = {_url_key(item["url"]): item for item in sitemap_entries}

        # Technical signals must describe the exact imported URL variant. The graph may have
        # discovered the same page through /path (301) while GSC contains /path/ (200), so
        # reusing the crawl response here would produce a false redirect diagnosis.
        semaphore = asyncio.Semaphore(8)

        async def fetch_imported(url: str) -> tuple[str, dict[str, Any]]:
            async with semaphore:
                return url, await audit_site_page(client, url, project_host)

        fetched_imported = dict(await asyncio.gather(*(fetch_imported(url) for url in urls)))

    home_url = linking.get("home_url", "")
    rows: list[dict[str, Any]] = []
    for imported_url in urls:
        key = _url_key(imported_url)
        crawl_page = page_map.get(key)
        page_data = dict(fetched_imported.get(imported_url) or {})
        page_data.setdefault("url", imported_url)
        # Merge graph-only fields from the normalized crawl node.
        if crawl_page:
            page_data["incoming"] = crawl_page.get("incoming", 0)
            page_data["incoming_links"] = crawl_page.get("incoming_links", [])
            page_data["depth"] = crawl_page.get("depth")
            page_data["depth_reason"] = crawl_page.get("depth_reason", "")
            page_data["outgoing"] = crawl_page.get("outgoing", 0)
            page_data["found_in_crawl"] = crawl_page.get("found_in_crawl", True)
            page_data["self_link"] = crawl_page.get("self_link", False)
            page_data["self_link_anchors"] = crawl_page.get("self_link_anchors", [])
            page_data["self_link_types"] = crawl_page.get("self_link_types", [])
        else:
            page_data.setdefault("incoming", 0)
            page_data.setdefault("incoming_links", [])
            page_data.setdefault("depth", None)
            page_data.setdefault("depth_reason", "URL не найден в графе crawl")
            page_data.setdefault("outgoing", 0)
            page_data.setdefault("found_in_crawl", False)
            page_data.setdefault("self_link", False)
            page_data.setdefault("self_link_anchors", [])
            page_data.setdefault("self_link_types", [])

        # If the imported variant redirects, sitemap can legitimately contain the
        # final URL instead. Record which form matched.
        final_key = _url_key(page_data.get("final_url") or imported_url)
        sitemap_entry = sitemap_map.get(key) or sitemap_map.get(final_key)
        sitemap_info = {
            "present": bool(sitemap_entry),
            "sitemap_url": sitemap_entry.get("sitemap_url", "") if sitemap_entry else "",
            "priority": sitemap_entry.get("priority", "") if sitemap_entry else "",
            "changefreq": sitemap_entry.get("changefreq", "") if sitemap_entry else "",
            "lastmod": sitemap_entry.get("lastmod", "") if sitemap_entry else "",
        }

        incoming_links = page_data.get("incoming_links") or []
        home_link = any(_same_page(item.get("source", ""), home_url) for item in incoming_links)
        hub_candidate, hub_kind = _candidate_hub(imported_url, page_map, incoming_links, home_url)
        if hub_candidate:
            hub_link = any(_same_page(item.get("source", ""), hub_candidate) for item in incoming_links)
            hub_status = "yes" if hub_link else "no"
        else:
            hub_link = None
            hub_status = "unknown"

        donors = []
        for item in incoming_links[:80]:
            source = item.get("source", "")
            source_row = page_map.get(_url_key(source)) or {}
            donor_type = item.get("type", "other")
            if hub_candidate and _same_page(source, hub_candidate):
                donor_type = "hub"
            donors.append({
                "source": source,
                "anchor": item.get("anchor", ""),
                "anchors": item.get("anchors", []),
                "type": donor_type,
                "types": item.get("types", [donor_type]),
                "title": source_row.get("h1") or source_row.get("title") or "",
                "depth": source_row.get("depth"),
                "outgoing": source_row.get("outgoing", 0),
                "source_discovered_via": item.get("source_discovered_via", ""),
            })

        raw_row = {
            "url": imported_url,
            "final_url": page_data.get("final_url") or imported_url,
            "initial_status_code": page_data.get("initial_status_code", page_data.get("status_code", 0)),
            "status_code": page_data.get("status_code", 0),
            "redirect_chain": page_data.get("redirect_chain", []),
            "content_type": page_data.get("content_type", ""),
            "robots": page_data.get("robots", ""),
            "x_robots": page_data.get("x_robots", ""),
            "canonical": page_data.get("canonical", ""),
            "title": page_data.get("title", ""),
            "h1": page_data.get("h1", ""),
            "h1_count": page_data.get("h1_count", 1 if page_data.get("h1") else 0),
            "word_count": page_data.get("word_count", 0),
            "sitemap": sitemap_info,
            "inlinks": int(page_data.get("incoming", 0)),
            "incoming_links": donors,
            "self_link": bool(page_data.get("self_link", False)),
            "self_link_anchors": page_data.get("self_link_anchors", []),
            "self_link_types": page_data.get("self_link_types", []),
            "home_link": home_link,
            "found_in_crawl": bool(page_data.get("found_in_crawl", crawl_page is not None)),
            "link_data_sufficient": bool(linking.get("crawl_sufficient", False)),
            "depth": page_data.get("depth"),
            "depth_reason": page_data.get("depth_reason", "") if page_data.get("depth") is None else "",
            "hub_candidate": hub_candidate,
            "hub_kind": hub_kind,
            "hub_status": hub_status,
        }
        rows.append(_classify(raw_row))

    counts = {"ok": 0, "content": 0, "developer": 0, "insufficient": 0}
    issue_counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] += 1
        for issue in row["technical_issues"] + row["content_issues"]:
            issue_counts[issue["code"]] = issue_counts.get(issue["code"], 0) + 1

    if progress_callback:
        await progress_callback(len(urls), len(urls), "Проверка списка GSC завершена")

    return {
        "domain": base_domain,
        "sitemap_url": linking.get("sitemap_url") or sitemap_url,
        "sitemap_errors": list(dict.fromkeys((linking.get("sitemap_errors") or []) + sitemap_errors)),
        "urls_total": len(urls),
        "status_counts": counts,
        "issue_counts": issue_counts,
        "crawl": {
            "pages_total": linking.get("pages_total", 0),
            "pages_crawled": linking.get("pages_crawled", linking.get("pages_total", 0)),
            "links_total": linking.get("links_total", 0),
            "html_links_seen": linking.get("html_links_seen", linking.get("links_total", 0)),
            "unique_urls_found": linking.get("unique_urls_found", linking.get("pages_total", 0)),
            "errors_count": linking.get("crawl_errors_count", 0),
            "errors": linking.get("crawl_errors", []),
            "home_url": home_url,
            "home_crawled": linking.get("home_crawled", False),
            "sufficient": linking.get("crawl_sufficient", False),
            "sufficient_reason": linking.get("crawl_sufficient_reason", ""),
            "limited": linking.get("limited", False),
            "max_pages": linking.get("max_pages", max_pages),
            "sitemap_urls_total": linking.get("sitemap_urls_total", 0),
            "sitemap_not_crawled": linking.get("sitemap_not_crawled", 0),
        },
        "rows": rows,
    }
