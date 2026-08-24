from __future__ import annotations

import asyncio
import re
from collections import Counter
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/151.0 Safari/537.36 ContentDesk/0.2"
)

CORE_SEVERITY_PENALTY = {"critical": 16, "warning": 7, "recommendation": 3}


def build_core_seo_issues(*, status_code: int, title: str, description: str, h1_count: int, canonical: str, robots: str, word_count: int, internal_links: int, missing_alt: int) -> list[dict[str, str]]:
    """Shared page-level scoring signals used by Page Audit and Site Audit.

    Keep this deliberately compact and deterministic so the same page receives
    the same base SEO score in both modules. Site-wide duplicate checks are
    reported separately and do not mutate the page's base score.
    """
    issues: list[dict[str, str]] = []

    def issue(code: str, severity: str, label: str) -> None:
        issues.append({"code": code, "severity": severity, "label": label})

    if not 200 <= status_code < 300:
        issue("http_status", "critical", f"HTTP {status_code}")
    if not title:
        issue("missing_title", "critical", "Отсутствует Title")
    elif len(title) < 30 or len(title) > 65:
        issue("title_length", "warning", f"Title: {len(title)} симв.")
    if not description:
        issue("missing_description", "warning", "Отсутствует Description")
    elif len(description) < 70 or len(description) > 170:
        issue("description_length", "recommendation", f"Description: {len(description)} симв.")
    if h1_count == 0:
        issue("missing_h1", "critical", "Отсутствует H1")
    elif h1_count > 1:
        issue("multiple_h1", "warning", f"Несколько H1: {h1_count}")
    if not canonical:
        issue("missing_canonical", "warning", "Отсутствует canonical")
    if "noindex" in robots.lower():
        issue("noindex", "critical", "Страница закрыта noindex")
    if word_count < 200:
        issue("thin_content", "recommendation", f"Мало текста: ≈{word_count} слов")
    if internal_links < 3:
        issue("few_internal_links", "recommendation", f"Мало внутренних ссылок: {internal_links}")
    if missing_alt:
        issue("missing_alt", "warning", f"Изображений без ALT: {missing_alt}")
    return issues


def calculate_core_seo_score(issues: list[dict[str, str]]) -> int:
    penalty = sum(CORE_SEVERITY_PENALTY.get(item.get("severity", "recommendation"), 3) for item in issues)
    return max(0, min(100, 100 - penalty))



def normalize_url(url: str) -> str:
    value = url.strip()
    if not value:
        raise ValueError("Укажите URL страницы")
    if not re.match(r"^https?://", value, flags=re.IGNORECASE):
        value = f"https://{value}"
    parsed = urlparse(value)
    if not parsed.netloc:
        raise ValueError("Некорректный URL")
    return value


def _clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _meta_content(soup: BeautifulSoup, *, name: str | None = None, prop: str | None = None) -> str:
    attrs: dict[str, str] = {}
    if name:
        attrs["name"] = name
    if prop:
        attrs["property"] = prop
    tag = soup.find("meta", attrs=attrs)
    return _clean_text(tag.get("content")) if tag and tag.get("content") else ""


def _score_status(ok: bool, warning: bool = False) -> str:
    if ok:
        return "good"
    return "warning" if warning else "error"


async def _fetch_image_size(client: httpx.AsyncClient, url: str) -> int | None:
    try:
        response = await client.head(url, follow_redirects=True)
        if response.status_code < 400:
            length = response.headers.get("content-length")
            if length and length.isdigit():
                return int(length)
    except httpx.HTTPError:
        return None
    return None


async def audit_page(raw_url: str) -> dict[str, Any]:
    requested_url = normalize_url(raw_url)

    timeout = httpx.Timeout(15.0, connect=8.0)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}

    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
        try:
            response = await client.get(requested_url)
        except httpx.TimeoutException as exc:
            raise ValueError("Сайт не ответил вовремя") from exc
        except httpx.RequestError as exc:
            raise ValueError(f"Не удалось открыть страницу: {exc}") from exc

        final_url = str(response.url)
        content_type = response.headers.get("content-type", "")
        if "html" not in content_type.lower():
            raise ValueError("URL не возвращает HTML-страницу")

        soup = BeautifulSoup(response.text, "html.parser")

        title = _clean_text(soup.title.string if soup.title and soup.title.string else "")
        description = _meta_content(soup, name="description")
        robots = _meta_content(soup, name="robots")
        canonical_tag = soup.find("link", rel=lambda value: value and "canonical" in value)
        canonical = urljoin(final_url, canonical_tag.get("href")) if canonical_tag and canonical_tag.get("href") else ""

        h1 = [_clean_text(tag.get_text(" ", strip=True)) for tag in soup.find_all("h1")]
        h2 = [_clean_text(tag.get_text(" ", strip=True)) for tag in soup.find_all("h2")]
        h3 = [_clean_text(tag.get_text(" ", strip=True)) for tag in soup.find_all("h3")]

        body = soup.body or soup
        body_copy = BeautifulSoup(str(body), "html.parser")
        for tag in body_copy(["script", "style", "noscript", "svg", "template"]):
            tag.decompose()
        visible_text = _clean_text(body_copy.get_text(" ", strip=True))
        words = re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", visible_text)
        word_count = len(words)

        page_host = urlparse(final_url).netloc.lower().removeprefix("www.")
        internal_links: set[str] = set()
        external_links: set[str] = set()
        empty_links = 0

        for anchor in soup.find_all("a"):
            href = _clean_text(anchor.get("href"))
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                if not href:
                    empty_links += 1
                continue
            absolute = urljoin(final_url, href)
            parsed = urlparse(absolute)
            if parsed.scheme not in {"http", "https"}:
                continue
            host = parsed.netloc.lower().removeprefix("www.")
            clean = absolute.split("#", 1)[0]
            if host == page_host:
                internal_links.add(clean)
            else:
                external_links.add(clean)

        image_rows: list[dict[str, Any]] = []
        alt_counter: Counter[str] = Counter()
        image_urls_for_size: list[str] = []

        for index, img in enumerate(soup.find_all("img"), start=1):
            src = _clean_text(img.get("src") or img.get("data-src") or img.get("data-lazy-src"))
            alt_attr = img.get("alt")
            alt = _clean_text(alt_attr if isinstance(alt_attr, str) else "")
            absolute_src = urljoin(final_url, src) if src else ""
            if alt:
                alt_counter[alt.lower()] += 1
            if absolute_src.startswith(("http://", "https://")):
                image_urls_for_size.append(absolute_src)
            image_rows.append(
                {
                    "index": index,
                    "src": absolute_src or src,
                    "alt": alt,
                    "has_alt_attribute": alt_attr is not None,
                    "size_bytes": None,
                }
            )

        # Размеры запрашиваем только для первых 40 уникальных изображений,
        # чтобы аудит одной страницы не превращался в долгий crawler.
        unique_size_urls = list(dict.fromkeys(image_urls_for_size))[:40]
        if unique_size_urls:
            sizes = await asyncio.gather(*[_fetch_image_size(client, item) for item in unique_size_urls])
            size_map = dict(zip(unique_size_urls, sizes))
            for item in image_rows:
                item["size_bytes"] = size_map.get(item["src"])

        missing_alt = sum(1 for item in image_rows if not item["alt"])
        missing_alt_attribute = sum(1 for item in image_rows if not item["has_alt_attribute"])
        duplicate_alt_values = sorted([alt for alt, count in alt_counter.items() if count > 1])
        large_images = sum(1 for item in image_rows if (item["size_bytes"] or 0) > 1_000_000)

        og_title = _meta_content(soup, prop="og:title")
        og_description = _meta_content(soup, prop="og:description")
        og_image = _meta_content(soup, prop="og:image")

        checks: list[dict[str, Any]] = []

        def add_check(category: str, label: str, status: str, value: str, recommendation: str = "") -> None:
            checks.append(
                {
                    "category": category,
                    "label": label,
                    "status": status,
                    "value": value,
                    "recommendation": recommendation,
                }
            )

        add_check(
            "technical",
            "HTTP-статус",
            "good" if 200 <= response.status_code < 300 else "error",
            str(response.status_code),
            "Страница должна отдавать успешный HTTP-код 200." if not 200 <= response.status_code < 300 else "",
        )
        add_check(
            "technical",
            "HTTPS",
            _score_status(urlparse(final_url).scheme == "https"),
            "Используется" if urlparse(final_url).scheme == "https" else "Не используется",
            "Переведите страницу на HTTPS." if urlparse(final_url).scheme != "https" else "",
        )
        add_check(
            "technical",
            "Canonical",
            _score_status(bool(canonical)),
            canonical or "Не найден",
            "Добавьте link rel=canonical для основной версии страницы." if not canonical else "",
        )
        add_check(
            "technical",
            "Meta robots",
            "warning" if "noindex" in robots.lower() else "good",
            robots or "Не задан",
            "На странице указан noindex — проверьте, должна ли она индексироваться." if "noindex" in robots.lower() else "",
        )

        title_ok = 30 <= len(title) <= 65
        add_check(
            "metadata",
            "Title",
            "good" if title_ok else ("error" if not title else "warning"),
            f"{len(title)} симв. — {title}" if title else "Не найден",
            "Добавьте Title." if not title else "Ориентир для Title — примерно 30–65 символов; проверьте смысл и читаемость.",
        )
        desc_ok = 70 <= len(description) <= 170
        add_check(
            "metadata",
            "Description",
            "good" if desc_ok else ("error" if not description else "warning"),
            f"{len(description)} симв. — {description}" if description else "Не найден",
            "Добавьте meta description." if not description else "Проверьте длину и информативность description.",
        )
        add_check(
            "metadata",
            "Open Graph",
            "good" if og_title and og_description else "warning",
            f"title: {'✓' if og_title else '—'}, description: {'✓' if og_description else '—'}, image: {'✓' if og_image else '—'}",
            "Добавьте основные Open Graph-теги для корректных превью при публикации ссылок." if not (og_title and og_description) else "",
        )

        h1_status = "good" if len(h1) == 1 else "error"
        add_check(
            "content",
            "H1",
            h1_status,
            h1[0] if len(h1) == 1 else f"Найдено: {len(h1)}",
            "На странице желательно оставить один основной H1." if len(h1) != 1 else "",
        )
        add_check(
            "content",
            "Подзаголовки",
            "good" if h2 else "warning",
            f"H2: {len(h2)}, H3: {len(h3)}",
            "Для содержательной страницы стоит разбить текст на логические разделы H2/H3." if not h2 else "",
        )
        add_check(
            "content",
            "Объём текста",
            "good" if word_count >= 200 else "warning",
            f"≈ {word_count} слов",
            "На странице мало видимого текста; оцените, достаточно ли его для раскрытия темы." if word_count < 200 else "",
        )

        add_check(
            "links",
            "Внутренние ссылки",
            "good" if len(internal_links) >= 3 else "warning",
            str(len(internal_links)),
            "Проверьте возможность добавить релевантные внутренние ссылки." if len(internal_links) < 3 else "",
        )
        add_check("links", "Внешние ссылки", "good", str(len(external_links)))
        add_check(
            "links",
            "Пустые ссылки",
            "good" if empty_links == 0 else "warning",
            str(empty_links),
            "Есть теги <a> без href — проверьте, нужны ли они." if empty_links else "",
        )

        if image_rows:
            add_check(
                "images",
                "ALT изображений",
                "good" if missing_alt == 0 else "error",
                f"Без ALT: {missing_alt} из {len(image_rows)}",
                "Добавьте осмысленные ALT для контентных изображений; декоративные изображения можно оставлять с пустым alt=\"\"." if missing_alt else "",
            )
            add_check(
                "images",
                "Дубли ALT",
                "good" if not duplicate_alt_values else "warning",
                str(len(duplicate_alt_values)),
                "Проверьте повторяющиеся ALT: для разных содержательных изображений они обычно должны отличаться." if duplicate_alt_values else "",
            )
            add_check(
                "images",
                "Тяжёлые изображения",
                "good" if large_images == 0 else "warning",
                f"> 1 МБ: {large_images}",
                "Оптимизируйте крупные изображения и используйте современные форматы, когда это уместно." if large_images else "",
            )
        else:
            add_check("images", "Изображения", "good", "На странице не найдены")

        category_weights = {
            "technical": 25,
            "metadata": 20,
            "content": 20,
            "links": 15,
            "images": 20,
        }
        status_points = {"good": 1.0, "warning": 0.55, "error": 0.0}
        breakdown: dict[str, int] = {}
        for category in category_weights:
            group = [item for item in checks if item["category"] == category]
            ratio = sum(status_points[item["status"]] for item in group) / len(group) if group else 1.0
            breakdown[category] = round(ratio * 100)

        # Единая базовая оценка для Page Audit и Site Audit. Детальные проверки
        # (Open Graph, пустые ссылки, дубли ALT и т. п.) остаются в breakdown и
        # рекомендациях, но не меняют общий score — иначе одна и та же страница
        # получала бы разные оценки в двух модулях.
        core_issues = build_core_seo_issues(
            status_code=response.status_code,
            title=title,
            description=description,
            h1_count=len(h1),
            canonical=canonical,
            robots=robots,
            word_count=word_count,
            internal_links=len(internal_links),
            missing_alt=missing_alt,
        )
        score = calculate_core_seo_score(core_issues)

        issues = [item for item in checks if item["status"] != "good"]

        return {
            "requested_url": requested_url,
            "final_url": final_url,
            "status_code": response.status_code,
            "score": score,
            "score_method": "core_v1",
            "breakdown": breakdown,
            "checks": checks,
            "issues_count": len(issues),
            "summary": {
                "title": title,
                "description": description,
                "canonical": canonical,
                "robots": robots,
                "h1": h1,
                "h2_count": len(h2),
                "h3_count": len(h3),
                "word_count": word_count,
                "internal_links": len(internal_links),
                "external_links": len(external_links),
                "images": len(image_rows),
                "missing_alt": missing_alt,
                "missing_alt_attribute": missing_alt_attribute,
                "duplicate_alt_values": duplicate_alt_values,
                "large_images": large_images,
            },
            "images": image_rows,
        }
