from __future__ import annotations

import asyncio
import re
from collections import Counter
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.services.seo_audit import USER_AGENT, normalize_url


MODERN_FORMATS = {"webp", "avif"}


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _extension(url: str) -> str:
    path = urlparse(url).path.lower()
    if "." not in path.rsplit("/", 1)[-1]:
        return ""
    return path.rsplit(".", 1)[-1].split("?", 1)[0]


async def _inspect_image(client: httpx.AsyncClient, item: dict[str, Any]) -> dict[str, Any]:
    url = item["src"]
    if not url.startswith(("http://", "https://")):
        return item
    try:
        response = await client.head(url, follow_redirects=True)
        if response.status_code in {405, 501}:
            response = await client.get(url, headers={"Range": "bytes=0-0"}, follow_redirects=True)
        item["status_code"] = response.status_code
        length = response.headers.get("content-length")
        item["size_bytes"] = int(length) if length and length.isdigit() else None
        item["content_type"] = response.headers.get("content-type", "")
    except httpx.HTTPError:
        item["status_code"] = None
    return item


async def audit_images(raw_url: str) -> dict[str, Any]:
    requested_url = normalize_url(raw_url)
    timeout = httpx.Timeout(15.0, connect=8.0)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}

    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
        try:
            page = await client.get(requested_url)
        except httpx.TimeoutException as exc:
            raise ValueError("Сайт не ответил вовремя") from exc
        except httpx.RequestError as exc:
            raise ValueError(f"Не удалось открыть страницу: {exc}") from exc

        if "html" not in page.headers.get("content-type", "").lower():
            raise ValueError("URL не возвращает HTML-страницу")

        final_url = str(page.url)
        soup = BeautifulSoup(page.text, "html.parser")
        rows: list[dict[str, Any]] = []
        alt_counter: Counter[str] = Counter()

        for index, img in enumerate(soup.find_all("img"), start=1):
            src = _clean(img.get("src") or img.get("data-src") or img.get("data-lazy-src"))
            if not src:
                continue
            absolute = urljoin(final_url, src)
            alt_attr = img.get("alt")
            alt = _clean(alt_attr if isinstance(alt_attr, str) else "")
            if alt:
                alt_counter[alt.lower()] += 1

            width_raw = str(img.get("width") or "")
            height_raw = str(img.get("height") or "")
            rows.append(
                {
                    "index": index,
                    "src": absolute,
                    "alt": alt,
                    "has_alt_attribute": alt_attr is not None,
                    "width": int(width_raw) if width_raw.isdigit() else None,
                    "height": int(height_raw) if height_raw.isdigit() else None,
                    "extension": _extension(absolute),
                    "status_code": None,
                    "size_bytes": None,
                    "content_type": "",
                }
            )

        # Keep a page-level audit fast enough for interactive use.
        inspected = await asyncio.gather(*[_inspect_image(client, dict(item)) for item in rows[:60]])
        inspected_map = {item["index"]: item for item in inspected}
        rows = [inspected_map.get(item["index"], item) for item in rows]

        duplicate_alts = {alt for alt, count in alt_counter.items() if count > 1}
        for item in rows:
            problems: list[str] = []
            if not item["has_alt_attribute"]:
                problems.append("нет атрибута ALT")
            elif not item["alt"]:
                problems.append("пустой ALT")
            if item["alt"] and item["alt"].lower() in duplicate_alts:
                problems.append("повторяющийся ALT")
            if item["status_code"] is not None and item["status_code"] >= 400:
                problems.append(f"HTTP {item['status_code']}")
            if (item["size_bytes"] or 0) > 1_000_000:
                problems.append("больше 1 МБ")
            if item["extension"] and item["extension"] not in MODERN_FORMATS:
                problems.append("можно рассмотреть WebP/AVIF")
            if not item["width"] or not item["height"]:
                problems.append("нет width/height в HTML")
            item["problems"] = problems

        return {
            "requested_url": requested_url,
            "final_url": final_url,
            "count": len(rows),
            "summary": {
                "missing_alt": sum(1 for item in rows if not item["alt"]),
                "missing_alt_attribute": sum(1 for item in rows if not item["has_alt_attribute"]),
                "duplicate_alt": sum(1 for item in rows if item["alt"] and item["alt"].lower() in duplicate_alts),
                "large_images": sum(1 for item in rows if (item["size_bytes"] or 0) > 1_000_000),
                "broken_images": sum(1 for item in rows if item["status_code"] is not None and item["status_code"] >= 400),
                "legacy_format": sum(1 for item in rows if item["extension"] and item["extension"] not in MODERN_FORMATS),
                "missing_dimensions": sum(1 for item in rows if not item["width"] or not item["height"]),
            },
            "images": rows,
        }

async def _sitemap_urls(client: httpx.AsyncClient, sitemap_url: str, limit: int) -> list[str]:
    """Read a sitemap or sitemap index recursively and return page URLs."""
    seen_maps: set[str] = set()
    pages: list[str] = []

    async def read_map(url: str, depth: int = 0) -> None:
        if url in seen_maps or depth > 3 or len(pages) >= limit:
            return
        seen_maps.add(url)
        try:
            response = await client.get(url)
            response.raise_for_status()
        except httpx.HTTPError:
            return
        soup = BeautifulSoup(response.text, "xml")
        sitemap_locs = [_clean(x.get_text()) for x in soup.find_all("sitemap") for x in x.find_all("loc")]
        if sitemap_locs:
            for child in sitemap_locs:
                if len(pages) >= limit:
                    break
                await read_map(child, depth + 1)
            return
        for loc in soup.find_all("loc"):
            value = _clean(loc.get_text())
            if value and value not in pages:
                pages.append(value)
                if len(pages) >= limit:
                    break

    await read_map(sitemap_url)
    return pages[:limit]


async def _extract_page_image_rows(client: httpx.AsyncClient, page_url: str) -> dict[str, Any]:
    try:
        response = await client.get(page_url)
    except httpx.HTTPError as exc:
        return {"url": page_url, "status_code": None, "error": str(exc), "images": []}
    content_type = response.headers.get("content-type", "").lower()
    if response.status_code >= 400 or "html" not in content_type:
        return {"url": page_url, "status_code": response.status_code, "error": "Страница недоступна или не HTML", "images": []}
    final_url = str(response.url)
    soup = BeautifulSoup(response.text, "html.parser")
    rows: list[dict[str, Any]] = []
    for index, img in enumerate(soup.find_all("img"), start=1):
        src = _clean(img.get("src") or img.get("data-src") or img.get("data-lazy-src"))
        if not src:
            continue
        absolute = urljoin(final_url, src)
        alt_attr = img.get("alt")
        alt = _clean(alt_attr if isinstance(alt_attr, str) else "")
        width_raw = str(img.get("width") or "")
        height_raw = str(img.get("height") or "")
        rows.append({
            "index": index,
            "page_url": final_url,
            "src": absolute,
            "alt": alt,
            "has_alt_attribute": alt_attr is not None,
            "width": int(width_raw) if width_raw.isdigit() else None,
            "height": int(height_raw) if height_raw.isdigit() else None,
            "extension": _extension(absolute),
            "status_code": None,
            "size_bytes": None,
            "content_type": "",
        })
    return {"url": final_url, "status_code": response.status_code, "error": "", "images": rows}


async def audit_site_images(raw_url: str, sitemap_url: str = "", limit: int = 30) -> dict[str, Any]:
    base_url = normalize_url(raw_url)
    limit = max(1, min(int(limit or 30), 100))
    parsed = urlparse(base_url)
    default_sitemap = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
    sitemap = normalize_url(sitemap_url) if sitemap_url.strip() else default_sitemap
    timeout = httpx.Timeout(20.0, connect=8.0)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/xml,text/xml"}

    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
        urls = await _sitemap_urls(client, sitemap, limit)
        if not urls:
            # Fallback keeps the feature useful when sitemap.xml is absent.
            urls = [base_url]
            try:
                home = await client.get(base_url)
                if "html" in home.headers.get("content-type", "").lower():
                    soup = BeautifulSoup(home.text, "html.parser")
                    host = urlparse(str(home.url)).netloc
                    for a in soup.find_all("a", href=True):
                        candidate = urljoin(str(home.url), str(a.get("href")))
                        cp = urlparse(candidate)
                        candidate = candidate.split("#", 1)[0]
                        if cp.scheme in {"http", "https"} and cp.netloc == host and candidate not in urls:
                            urls.append(candidate)
                            if len(urls) >= limit:
                                break
            except httpx.HTTPError:
                pass

        semaphore = asyncio.Semaphore(5)
        async def guarded(url: str):
            async with semaphore:
                return await _extract_page_image_rows(client, url)
        page_results = await asyncio.gather(*(guarded(url) for url in urls[:limit]))

        all_rows = [row for page in page_results for row in page["images"]]
        unique_by_src: dict[str, dict[str, Any]] = {}
        for row in all_rows:
            unique_by_src.setdefault(row["src"], dict(row))

        # Inspect each unique image once. Cap keeps site audit bounded on image-heavy sites.
        inspect_items = list(unique_by_src.values())[:500]
        inspected = await asyncio.gather(*[_inspect_image(client, dict(item)) for item in inspect_items])
        meta = {item["src"]: item for item in inspected}

        alt_sources: dict[str, set[str]] = {}
        for row in all_rows:
            if row["alt"]:
                alt_sources.setdefault(row["alt"].lower(), set()).add(row["src"])
        duplicate_alts = {alt for alt, sources in alt_sources.items() if len(sources) > 1}

        for row in all_rows:
            inspected_item = meta.get(row["src"])
            if inspected_item:
                for key in ("status_code", "size_bytes", "content_type"):
                    row[key] = inspected_item.get(key)
            problems: list[str] = []
            if not row["has_alt_attribute"]:
                problems.append("нет атрибута ALT")
            elif not row["alt"]:
                problems.append("пустой ALT")
            if row["alt"] and row["alt"].lower() in duplicate_alts:
                problems.append("одинаковый ALT у разных изображений")
            if row["status_code"] is not None and row["status_code"] >= 400:
                problems.append(f"HTTP {row['status_code']}")
            if (row["size_bytes"] or 0) > 1_000_000:
                problems.append("больше 1 МБ")
            if row["extension"] and row["extension"] not in MODERN_FORMATS:
                problems.append("можно рассмотреть WebP/AVIF")
            if not row["width"] or not row["height"]:
                problems.append("нет width/height в HTML")
            row["problems"] = problems

        page_summaries = []
        for page in page_results:
            rows = page["images"]
            # rows are the same dict objects as in all_rows and now include problems.
            page_summaries.append({
                "url": page["url"],
                "status_code": page["status_code"],
                "error": page["error"],
                "images": len(rows),
                "problem_images": sum(1 for row in rows if row.get("problems")),
                "missing_alt": sum(1 for row in rows if not row.get("alt")),
            })

        return {
            "base_url": base_url,
            "sitemap_url": sitemap,
            "pages_scanned": len(page_results),
            "pages_with_errors": sum(1 for page in page_results if page["error"]),
            "image_occurrences": len(all_rows),
            "unique_images": len(unique_by_src),
            "inspected_unique_images": len(inspected),
            "summary": {
                "missing_alt": sum(1 for row in all_rows if not row["alt"]),
                "missing_alt_attribute": sum(1 for row in all_rows if not row["has_alt_attribute"]),
                "duplicate_alt": sum(1 for row in all_rows if row["alt"] and row["alt"].lower() in duplicate_alts),
                "large_images": sum(1 for row in all_rows if (row["size_bytes"] or 0) > 1_000_000),
                "broken_images": sum(1 for row in all_rows if row["status_code"] is not None and row["status_code"] >= 400),
                "legacy_format": sum(1 for row in all_rows if row["extension"] and row["extension"] not in MODERN_FORMATS),
                "missing_dimensions": sum(1 for row in all_rows if not row["width"] or not row["height"]),
                "problem_occurrences": sum(1 for row in all_rows if row["problems"]),
            },
            "pages": page_summaries,
            "images": all_rows,
        }
