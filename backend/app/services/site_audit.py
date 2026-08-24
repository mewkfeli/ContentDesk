from __future__ import annotations

import asyncio
import fnmatch
import re
import xml.etree.ElementTree as ET
from collections import Counter
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.services.seo_audit import USER_AGENT, build_core_seo_issues, calculate_core_seo_score, normalize_url


SITEMAP_CANDIDATES = ("/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml")

ASSET_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg", ".ico", ".bmp", ".tif", ".tiff",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip", ".rar", ".7z", ".gz",
    ".css", ".js", ".mjs", ".json", ".xml", ".txt", ".csv", ".mp3", ".wav", ".mp4", ".webm", ".avi",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
}


def is_page_candidate(url: str) -> bool:
    """Return True only for URLs that can reasonably be HTML pages.

    This prevents image:image <loc> entries and WordPress uploads from being
    treated as SEO pages when a sitemap contains media metadata.
    """
    parsed = urlparse(url)
    path = (parsed.path or "/").lower()
    if "/wp-content/uploads/" in path or "/wp-content/plugins/" in path or "/wp-content/themes/" in path:
        return False
    last = path.rsplit("/", 1)[-1]
    if "." in last:
        suffix = "." + last.rsplit(".", 1)[-1]
        if suffix in ASSET_EXTENSIONS:
            return False
    return parsed.scheme in {"http", "https"}


def _direct_loc(parent: ET.Element) -> str:
    for child in list(parent):
        if _xml_tag_name(child.tag) == "loc":
            return _clean(child.text)
    return ""


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _host(value: str) -> str:
    return urlparse(value).netloc.lower().removeprefix("www.")


def _xml_tag_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _has_faq(soup: BeautifulSoup) -> bool:
    # FAQ can be represented by headings/text, schema.org markup, accordions or common class names.
    text = _clean((soup.body or soup).get_text(" ", strip=True)).lower()[:50000]
    if any(marker in text for marker in ("часто задаваемые вопросы", "вопросы и ответы", "faq")):
        return True
    if soup.find(attrs={"itemtype": re.compile(r"FAQPage", re.I)}):
        return True
    for tag in soup.find_all(["section", "div", "ul"], limit=600):
        marker = " ".join([str(tag.get("id") or ""), " ".join(tag.get("class") or [])]).lower()
        if any(x in marker for x in ("faq", "question", "accordion")):
            return True
    return False


def _has_cta(soup: BeautifulSoup) -> bool:
    # Best-effort commercial CTA signal. We do not require exact wording.
    patterns = (
        "заказать", "оставить заявку", "получить консультацию", "рассчитать", "узнать цену",
        "связаться", "обратный звонок", "написать нам", "купить", "записаться", "отправить заявку",
    )
    for tag in soup.find_all(["a", "button"], limit=1000):
        text = _clean(tag.get_text(" ", strip=True)).lower()
        if text and any(pattern in text for pattern in patterns):
            return True
    if soup.find("form"):
        return True
    return False


def _content_fullness(
    *,
    word_count: int,
    h1_count: int,
    h2_count: int,
    h3_count: int,
    paragraphs: int,
    images: int,
    missing_alt: int,
    internal_links: int,
    has_faq: bool,
    has_cta: bool,
) -> tuple[int, list[dict[str, str]]]:
    """Heuristic content completeness score, separate from technical SEO score."""
    score = 0
    issues: list[dict[str, str]] = []

    if h1_count == 1:
        score += 15
    elif h1_count == 0:
        issues.append({"code": "content_missing_h1", "severity": "warning", "label": "Для контента нет H1"})

    if word_count >= 500:
        score += 22
    elif word_count >= 300:
        score += 18
    elif word_count >= 150:
        score += 10
        issues.append({"code": "content_thin", "severity": "recommendation", "label": "Небольшой объём основного текста"})
    else:
        issues.append({"code": "content_thin", "severity": "warning", "label": "Очень мало текстового контента"})

    if h2_count >= 2:
        score += 13
    elif h2_count == 1:
        score += 8
        if word_count >= 500:
            issues.append({"code": "weak_heading_structure", "severity": "recommendation", "label": "Слабая структура H2/H3"})
    elif word_count >= 250:
        issues.append({"code": "weak_heading_structure", "severity": "warning", "label": "Текст не разбит заголовками H2"})

    if h3_count >= 1:
        score += 4
    elif word_count >= 900:
        issues.append({"code": "weak_heading_structure", "severity": "recommendation", "label": "Для большого текста стоит проверить H3"})

    if paragraphs >= 4:
        score += 8
    elif paragraphs >= 2:
        score += 4
    elif word_count >= 200:
        issues.append({"code": "weak_paragraph_structure", "severity": "recommendation", "label": "Мало смысловых абзацев"})

    if images > 0:
        score += 7
        alt_ok = max(0, images - missing_alt)
        score += round(8 * alt_ok / max(1, images))
        if missing_alt:
            issues.append({"code": "content_missing_alt", "severity": "recommendation", "label": f"Без ALT: {missing_alt} из {images} изображений"})
    else:
        if word_count >= 300:
            issues.append({"code": "no_content_images", "severity": "recommendation", "label": "На странице нет изображений"})

    if internal_links >= 3:
        score += 13
    elif internal_links >= 1:
        score += 7
        issues.append({"code": "content_few_links", "severity": "recommendation", "label": "Мало внутренних ссылок в контенте"})
    else:
        issues.append({"code": "content_few_links", "severity": "warning", "label": "Нет внутренних ссылок"})

    if has_cta:
        score += 7
    else:
        issues.append({"code": "missing_cta", "severity": "recommendation", "label": "Не найден явный CTA или форма"})

    if has_faq:
        score += 3
    else:
        issues.append({"code": "missing_faq", "severity": "recommendation", "label": "FAQ не найден"})

    score = max(0, min(100, score))
    if score < 60:
        issues.insert(0, {"code": "low_content_fullness", "severity": "warning", "label": f"Низкая наполненность: {score}/100"})
    return score, issues


async def discover_sitemap(client: httpx.AsyncClient, domain: str, explicit: str = "") -> str:
    if explicit.strip():
        return normalize_url(explicit)
    base = normalize_url(domain).rstrip("/")

    # First respect Sitemap directives from robots.txt. This is useful for sites
    # with non-standard sitemap names and is shared by Site Audit and Meta Description Audit.
    try:
        robots = await client.get(f"{base}/robots.txt")
        if robots.status_code < 400:
            for line in robots.text.splitlines():
                match = re.match(r"^\s*Sitemap\s*:\s*(\S+)", line, flags=re.I)
                if not match:
                    continue
                candidate = match.group(1).strip()
                try:
                    response = await client.get(candidate)
                    if response.status_code < 400 and ("xml" in response.headers.get("content-type", "").lower() or response.text.lstrip().startswith("<")):
                        return str(response.url)
                except httpx.HTTPError:
                    continue
    except httpx.HTTPError:
        pass

    for path in SITEMAP_CANDIDATES:
        candidate = f"{base}{path}"
        try:
            response = await client.get(candidate)
            if response.status_code < 400 and ("xml" in response.headers.get("content-type", "").lower() or response.text.lstrip().startswith("<")):
                return str(response.url)
        except httpx.HTTPError:
            continue
    raise ValueError("Не удалось автоматически найти sitemap.xml через robots.txt или стандартные адреса. Укажите адрес карты сайта вручную.")


async def collect_sitemap_entries(
    client: httpx.AsyncClient,
    sitemap_url: str,
    *,
    max_urls: int = 200,
    max_sitemaps: int = 40,
) -> tuple[list[dict[str, str]], list[str]]:
    """Collect page URLs together with the leaf sitemap and optional metadata.

    Existing callers that only need URLs should use collect_sitemap_urls().
    """
    queue = [sitemap_url]
    visited: set[str] = set()
    entries: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    errors: list[str] = []

    while queue and len(entries) < max_urls and len(visited) < max_sitemaps:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        try:
            response = await client.get(current)
            response.raise_for_status()
            root = ET.fromstring(response.content)
        except (httpx.HTTPError, ET.ParseError) as exc:
            errors.append(f"{current}: {exc}")
            continue

        root_name = _xml_tag_name(root.tag)
        if root_name == "sitemapindex":
            locations = [_direct_loc(node) for node in list(root) if _xml_tag_name(node.tag) == "sitemap"]
            for location in locations:
                if location and location not in visited and location not in queue:
                    queue.append(location)
            continue

        for node in list(root):
            if _xml_tag_name(node.tag) != "url":
                continue
            location = _direct_loc(node)
            if not location or not is_page_candidate(location) or location in seen_urls:
                continue
            fields: dict[str, str] = {"url": location, "sitemap_url": current, "priority": "", "changefreq": "", "lastmod": ""}
            for child in list(node):
                tag = _xml_tag_name(child.tag)
                if tag in {"priority", "changefreq", "lastmod"}:
                    fields[tag] = _clean(child.text)
            entries.append(fields)
            seen_urls.add(location)
            if len(entries) >= max_urls:
                break

    if not entries:
        raise ValueError("В sitemap не найдено URL страниц.")
    return entries, errors


async def collect_sitemap_urls(
    client: httpx.AsyncClient,
    sitemap_url: str,
    *,
    max_urls: int = 200,
    max_sitemaps: int = 40,
) -> tuple[list[str], list[str]]:
    entries, errors = await collect_sitemap_entries(
        client, sitemap_url, max_urls=max_urls, max_sitemaps=max_sitemaps
    )
    return [entry["url"] for entry in entries], errors


async def audit_site_page(client: httpx.AsyncClient, raw_url: str, project_host: str) -> dict[str, Any]:
    try:
        response = await client.get(raw_url)
    except httpx.TimeoutException:
        return _failed_page(raw_url, 0, "Timeout")
    except httpx.RequestError as exc:
        return _failed_page(raw_url, 0, f"Ошибка запроса: {exc.__class__.__name__}")

    status_code = response.status_code
    final_url = str(response.url)
    initial_status_code = response.history[0].status_code if response.history else status_code
    redirect_chain = [
        {"url": str(item.url), "status_code": item.status_code, "location": item.headers.get("location", "")}
        for item in response.history
    ]
    content_type = response.headers.get("content-type", "")
    x_robots = _clean(response.headers.get("x-robots-tag"))
    if "html" not in content_type.lower():
        failed = _failed_page(raw_url, status_code, "URL не возвращает HTML", final_url=final_url)
        failed.update({"initial_status_code": initial_status_code, "redirect_chain": redirect_chain, "content_type": content_type, "x_robots": x_robots})
        return failed

    soup = BeautifulSoup(response.text, "html.parser")
    title = _clean(soup.title.string if soup.title and soup.title.string else "")
    description_tag = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    description = _clean(description_tag.get("content")) if description_tag else ""
    robots_tag = soup.find("meta", attrs={"name": re.compile(r"^robots$", re.I)})
    robots = _clean(robots_tag.get("content")) if robots_tag else ""
    canonical_tag = soup.find("link", rel=lambda value: value and "canonical" in value)
    canonical = urljoin(final_url, canonical_tag.get("href")) if canonical_tag and canonical_tag.get("href") else ""
    h1_values = [_clean(tag.get_text(" ", strip=True)) for tag in soup.find_all("h1")]
    h2_count = len(soup.find_all("h2"))
    h3_count = len(soup.find_all("h3"))
    paragraphs = sum(1 for tag in soup.find_all("p") if len(_clean(tag.get_text(" ", strip=True))) >= 20)

    body = soup.body or soup
    body_copy = BeautifulSoup(str(body), "html.parser")
    for tag in body_copy(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()
    words = re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", _clean(body_copy.get_text(" ", strip=True)))

    internal_links: set[str] = set()
    for anchor in soup.find_all("a"):
        href = _clean(anchor.get("href"))
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(final_url, href).split("#", 1)[0]
        parsed = urlparse(absolute)
        if parsed.scheme in {"http", "https"} and _host(absolute) == project_host:
            internal_links.add(absolute)

    images = soup.find_all("img")
    missing_alt = 0
    for image in images:
        alt = image.get("alt")
        # В site audit считаем проблемой отсутствие атрибута или пустой ALT у любого img.
        # Детальный Image Audit позволяет вручную отделить декоративные изображения.
        if alt is None or not _clean(alt if isinstance(alt, str) else ""):
            missing_alt += 1

    issues = build_core_seo_issues(
        status_code=status_code,
        title=title,
        description=description,
        h1_count=len(h1_values),
        canonical=canonical,
        robots=robots,
        word_count=len(words),
        internal_links=len(internal_links),
        missing_alt=missing_alt,
    )
    score = calculate_core_seo_score(issues)
    has_faq = _has_faq(soup)
    has_cta = _has_cta(soup)
    content_score, content_issues = _content_fullness(
        word_count=len(words), h1_count=len(h1_values), h2_count=h2_count, h3_count=h3_count,
        paragraphs=paragraphs, images=len(images), missing_alt=missing_alt, internal_links=len(internal_links),
        has_faq=has_faq, has_cta=has_cta,
    )
    issues.extend(content_issues)

    return {
        "url": raw_url,
        "final_url": final_url,
        "status_code": status_code,
        "initial_status_code": initial_status_code,
        "redirect_chain": redirect_chain,
        "content_type": content_type,
        "x_robots": x_robots,
        "score": score,
        "score_method": "core_v1",
        "title": title,
        "description": description,
        "h1": h1_values[0] if h1_values else "",
        "h1_count": len(h1_values),
        "h2_count": h2_count,
        "h3_count": h3_count,
        "paragraphs": paragraphs,
        "content_score": content_score,
        "has_faq": has_faq,
        "has_cta": has_cta,
        "content_issues": content_issues,
        "canonical": canonical,
        "robots": robots,
        "word_count": len(words),
        "internal_links": len(internal_links),
        "images": len(images),
        "missing_alt": missing_alt,
        "issues": issues,
    }


def _failed_page(url: str, status_code: int, message: str, final_url: str | None = None) -> dict[str, Any]:
    return {
        "url": url,
        "final_url": final_url or url,
        "status_code": status_code,
        "initial_status_code": status_code,
        "redirect_chain": [],
        "content_type": "",
        "x_robots": "",
        "score": 0,
        "title": "",
        "description": "",
        "h1": "",
        "h1_count": 0,
        "h2_count": 0,
        "h3_count": 0,
        "paragraphs": 0,
        "content_score": 0,
        "has_faq": False,
        "has_cta": False,
        "content_issues": [{"code": "low_content_fullness", "severity": "warning", "label": "Наполненность не рассчитана"}],
        "canonical": "",
        "robots": "",
        "word_count": 0,
        "internal_links": 0,
        "images": 0,
        "missing_alt": 0,
        "issues": [{"code": "fetch_error", "severity": "critical", "label": message}],
    }


def _add_duplicate_issues(pages: list[dict[str, Any]], field: str, code: str, label: str) -> int:
    values = Counter(_clean(str(page.get(field, ""))).lower() for page in pages if _clean(str(page.get(field, ""))))
    duplicates = {value for value, count in values.items() if count > 1}
    affected = 0
    for page in pages:
        value = _clean(str(page.get(field, ""))).lower()
        if value and value in duplicates:
            page["issues"].append({"code": code, "severity": "warning", "label": label})
            # Дубли — site-wide сигнал. Он отображается как проблема, но не
            # меняет базовую оценку страницы, чтобы Page Audit и Site Audit
            # показывали одинаковый score для одного URL.
            affected += 1
    return affected



def _excluded_url(url: str, patterns: list[str]) -> bool:
    if not patterns:
        return False
    low = url.lower()
    from urllib.parse import urlparse
    parsed = urlparse(url)
    target = (parsed.path + ("?" + parsed.query if parsed.query else "")).lower()
    for raw in patterns:
        pattern = raw.strip().lower()
        if not pattern:
            continue
        if "*" in pattern or "?" in pattern and not pattern.startswith("?"):
            if fnmatch.fnmatch(target, pattern) or fnmatch.fnmatch(low, pattern):
                return True
        elif pattern.startswith("?"):
            if pattern[1:] in parsed.query.lower():
                return True
        elif pattern in target or pattern in low:
            return True
    return False

async def audit_site(
    domain: str,
    sitemap_url: str = "",
    max_pages: int = 200,
    exclude_patterns: list[str] | None = None,
    progress_callback=None,
    cancel_event=None,
) -> dict[str, Any]:
    base_domain = normalize_url(domain)
    max_pages = max(1, min(max_pages, 500))
    timeout = httpx.Timeout(18.0, connect=8.0)
    limits = httpx.Limits(max_connections=12, max_keepalive_connections=8)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/xml,text/xml;q=0.9,*/*;q=0.8"}

    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True, limits=limits) as client:
        resolved_sitemap = await discover_sitemap(client, base_domain, sitemap_url)
        urls, sitemap_errors = await collect_sitemap_urls(client, resolved_sitemap, max_urls=max_pages * 3)
        exclude_patterns = exclude_patterns or []
        urls = [u for u in urls if not _excluded_url(u, exclude_patterns)][:max_pages]
        project_host = _host(base_domain)

        semaphore = asyncio.Semaphore(8)

        async def run_one(url: str) -> dict[str, Any]:
            async with semaphore:
                return await audit_site_page(client, url, project_host)

        pages: list[dict[str, Any]] = []
        total = len(urls)
        if progress_callback:
            await progress_callback(0, total, "Получен sitemap, начинаю проверку страниц")
        tasks = [asyncio.create_task(run_one(url)) for url in urls]
        try:
            for completed in asyncio.as_completed(tasks):
                if cancel_event is not None and cancel_event.is_set():
                    for task in tasks:
                        task.cancel()
                    raise asyncio.CancelledError
                pages.append(await completed)
                if progress_callback:
                    await progress_callback(len(pages), total, f"Проверено {len(pages)} из {total} страниц")
        finally:
            if cancel_event is not None and cancel_event.is_set():
                for task in tasks:
                    if not task.done():
                        task.cancel()

    duplicate_title_pages = _add_duplicate_issues(pages, "title", "duplicate_title", "Дублирующийся Title")
    duplicate_description_pages = _add_duplicate_issues(pages, "description", "duplicate_description", "Дублирующийся Description")
    duplicate_h1_pages = _add_duplicate_issues(pages, "h1", "duplicate_h1", "Дублирующийся H1")

    issue_counts: Counter[str] = Counter()
    severity_counts: Counter[str] = Counter()
    for page in pages:
        for item in page["issues"]:
            issue_counts[item["code"]] += 1
            severity_counts[item["severity"]] += 1

    successful_pages = [page for page in pages if 200 <= page["status_code"] < 300]
    score = round(sum(page["score"] for page in pages) / len(pages)) if pages else 0
    content_pages = [page for page in successful_pages if page.get("content_type", "").lower().find("html") >= 0]
    content_score = round(sum(page.get("content_score", 0) for page in content_pages) / len(content_pages)) if content_pages else 0
    low_content_pages = sum(1 for page in content_pages if page.get("content_score", 0) < 60)
    missing_faq_pages = sum(1 for page in content_pages if not page.get("has_faq"))
    missing_cta_pages = sum(1 for page in content_pages if not page.get("has_cta"))

    return {
        "domain": base_domain.rstrip("/"),
        "sitemap_url": resolved_sitemap,
        "sitemap_errors": sitemap_errors,
        "pages_total": len(pages),
        "pages_success": len(successful_pages),
        "score": score,
        "content_score": content_score,
        "low_content_pages": low_content_pages,
        "missing_faq_pages": missing_faq_pages,
        "missing_cta_pages": missing_cta_pages,
        "critical": severity_counts["critical"],
        "warnings": severity_counts["warning"],
        "recommendations": severity_counts["recommendation"],
        "issue_counts": dict(issue_counts),
        "duplicate_title_pages": duplicate_title_pages,
        "duplicate_description_pages": duplicate_description_pages,
        "duplicate_h1_pages": duplicate_h1_pages,
        "pages": pages,
        "limited": len(urls) >= max_pages,
        "max_pages": max_pages,
    }
