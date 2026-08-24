from __future__ import annotations

import asyncio
import re
from collections import Counter, defaultdict, deque
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup, Tag

from app.services.seo_audit import USER_AGENT, normalize_url
from app.services.site_audit import collect_sitemap_urls, discover_sitemap, is_page_candidate, _excluded_url

STOPWORDS = {
    "и", "в", "во", "на", "для", "с", "со", "по", "из", "к", "ко", "от", "до", "за", "под", "над",
    "при", "или", "как", "что", "это", "а", "но", "не", "the", "of", "and", "for", "to", "in", "on",
    "услуги", "услуга", "страница", "главная", "компания", "сайт",
}

TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"gclid", "yclid", "fbclid", "mc_cid", "mc_eid", "_ga"}
RELATED_HEADINGS = (
    "услуги, которые могут вас заинтересовать", "похожие услуги", "с этим также заказывают",
    "вам может быть интересно", "вас может заинтересовать", "смотрите также", "рекомендуем",
)


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _host(value: str) -> str:
    return urlparse(value).netloc.lower().removeprefix("www.").split(":", 1)[0]


def _normalized_query(query: str) -> str:
    if not query:
        return ""
    kept: list[tuple[str, str]] = []
    for key, value in parse_qsl(query, keep_blank_values=True):
        low = key.lower()
        if low in TRACKING_QUERY_KEYS or any(low.startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES):
            continue
        # Preserve pagination-like query params; other query variants are usually not separate crawl nodes.
        if low in {"page", "paged", "pageno", "page_number"}:
            kept.append((key, value))
    return urlencode(kept, doseq=True)


def page_key(url: str) -> str:
    """Stable graph identity: www/trailing slash/tracking variants collapse to one page."""
    parsed = urlparse(url)
    scheme = (parsed.scheme or "https").lower()
    host = parsed.netloc.lower().removeprefix("www.")
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = _normalized_query(parsed.query)
    return urlunparse((scheme, host, path, "", query, ""))


def _canonical_link(url: str) -> str:
    """Display/request URL with harmless variants normalized, but path semantics retained."""
    parsed = urlparse(url)
    scheme = (parsed.scheme or "https").lower()
    host = parsed.netloc.lower().removeprefix("www.")
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    query = _normalized_query(parsed.query)
    return urlunparse((scheme, host, path, "", query, ""))


def _tokens(*values: str) -> set[str]:
    text = " ".join(values).lower().replace("ё", "е")
    words = re.findall(r"[a-zа-я0-9]{3,}", text)
    return {word for word in words if word not in STOPWORDS and not word.isdigit()}


def _slug_words(url: str) -> str:
    path = urlparse(url).path.strip("/")
    last = path.split("/")[-1] if path else ""
    return re.sub(r"[-_]+", " ", last)


def _normalize_anchor(value: str) -> str:
    return _clean(value)[:180]


def _class_tokens(tag: Tag | None) -> str:
    if not tag:
        return ""
    classes = tag.get("class") or []
    if isinstance(classes, str):
        classes = classes.split()
    return " ".join([str(tag.get("id") or ""), *map(str, classes)]).lower()


def _nearby_heading(anchor: Tag) -> str:
    # Find a heading inside the nearest few structural ancestors. Useful for related-services blocks.
    node: Tag | None = anchor
    for _ in range(5):
        parent = node.parent if isinstance(node, Tag) else None
        if not isinstance(parent, Tag):
            break
        headings = parent.find_all(re.compile(r"^h[2-6]$"), limit=3)
        text = " ".join(_clean(h.get_text(" ", strip=True)).lower() for h in headings)
        if text:
            return text
        node = parent
    return ""


def _link_type(anchor: Tag) -> str:
    """Best-effort DOM source type. Values are stable API labels."""
    for ancestor in [anchor, *list(anchor.parents)[:7]]:
        if not isinstance(ancestor, Tag):
            continue
        name = ancestor.name.lower() if ancestor.name else ""
        marker = _class_tokens(ancestor)
        if name == "footer" or "footer" in marker:
            return "footer"
        if "breadcrumb" in marker or "breadcrumbs" in marker or "bread-crumb" in marker:
            return "breadcrumbs"
        if name == "nav" or any(word in marker for word in ("menu", "navbar", "navigation", "header-nav", "main-nav")):
            return "menu"
    nearby = _nearby_heading(anchor)
    if any(phrase in nearby for phrase in RELATED_HEADINGS):
        return "related"
    for ancestor in [anchor, *list(anchor.parents)[:6]]:
        if not isinstance(ancestor, Tag):
            continue
        marker = _class_tokens(ancestor)
        if any(word in marker for word in ("related", "similar", "recommend", "interest", "also-order")):
            return "related"
        if any(word in marker for word in ("service-card", "services-grid", "service_item", "service-item", "category", "catalog", "hub")):
            return "hub"
    if anchor.find_parent("main") is not None or any("content" in _class_tokens(x) for x in list(anchor.parents)[:5] if isinstance(x, Tag)):
        return "content"
    return "other"


def _extract_outgoing(soup: BeautifulSoup, final_url: str, project_host: str, exclude_patterns: list[str]) -> list[dict[str, str]]:
    outgoing: list[dict[str, str]] = []
    # Deduplicate identical target+anchor+type while preserving different anchors/types from the same page.
    seen: set[tuple[str, str, str]] = set()
    for anchor in soup.find_all("a"):
        href = _clean(anchor.get("href"))
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
            continue
        absolute = _canonical_link(urljoin(final_url, href).split("#", 1)[0])
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"} or _host(absolute) != project_host:
            continue
        if not is_page_candidate(absolute) or _excluded_url(absolute, exclude_patterns):
            continue
        anchor_text = _normalize_anchor(anchor.get_text(" ", strip=True))
        link_type = _link_type(anchor)
        key = (page_key(absolute), anchor_text, link_type)
        if key in seen:
            continue
        seen.add(key)
        outgoing.append({"target": absolute, "anchor": anchor_text, "type": link_type})
    return outgoing


async def _fetch_page(
    client: httpx.AsyncClient,
    url: str,
    project_host: str,
    exclude_patterns: list[str] | None = None,
    *,
    discovered_via: str = "crawl",
) -> dict[str, Any]:
    exclude_patterns = exclude_patterns or []
    try:
        response = await client.get(url)
    except httpx.HTTPError as exc:
        return {
            "url": _canonical_link(url), "final_url": _canonical_link(url), "status_code": 0, "initial_status_code": 0,
            "redirect_chain": [], "content_type": "", "title": "", "h1": "", "h1_count": 0,
            "robots": "", "x_robots": "", "canonical": "", "word_count": 0,
            "outgoing": [], "keywords": [], "error": exc.__class__.__name__, "discovered_via": discovered_via,
        }

    final_url = str(response.url)
    initial_status = response.history[0].status_code if response.history else response.status_code
    redirect_chain = [
        {"url": str(item.url), "status_code": item.status_code, "location": item.headers.get("location", "")}
        for item in response.history
    ]
    content_type = response.headers.get("content-type", "")
    if "html" not in content_type.lower():
        return {
            "url": _canonical_link(url), "final_url": _canonical_link(final_url), "status_code": response.status_code,
            "initial_status_code": initial_status, "redirect_chain": redirect_chain,
            "content_type": content_type, "title": "", "h1": "", "h1_count": 0,
            "robots": "", "x_robots": _clean(response.headers.get("x-robots-tag")), "canonical": "",
            "word_count": 0, "outgoing": [], "keywords": [], "error": "not_html", "discovered_via": discovered_via,
        }

    soup = BeautifulSoup(response.text, "html.parser")
    title = _clean(soup.title.string if soup.title and soup.title.string else "")
    h1_tags = soup.find_all("h1")
    h1 = _clean(h1_tags[0].get_text(" ", strip=True)) if h1_tags else ""
    robots_tag = soup.find("meta", attrs={"name": re.compile(r"^robots$", re.I)})
    robots = _clean(robots_tag.get("content")) if robots_tag else ""
    canonical_tag = soup.find("link", rel=lambda value: value and "canonical" in value)
    canonical = urljoin(final_url, canonical_tag.get("href")) if canonical_tag and canonical_tag.get("href") else ""
    x_robots = _clean(response.headers.get("x-robots-tag"))

    body = soup.body or soup
    body_copy = BeautifulSoup(str(body), "html.parser")
    for tag in body_copy(["script", "style", "noscript", "svg", "template", "nav", "footer"]):
        tag.decompose()
    body_text = _clean(body_copy.get_text(" ", strip=True))
    word_count = len(re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", body_text))
    keyword_counts = Counter(re.findall(r"[A-Za-zА-Яа-яЁё0-9]{3,}", body_text[:12000].lower().replace("ё", "е")))
    keywords = [word for word, _ in keyword_counts.most_common(80) if word not in STOPWORDS and not word.isdigit()][:35]

    outgoing = _extract_outgoing(soup, final_url, project_host, exclude_patterns)

    return {
        "url": _canonical_link(url), "final_url": _canonical_link(final_url),
        "status_code": response.status_code, "initial_status_code": initial_status,
        "redirect_chain": redirect_chain, "content_type": content_type,
        "title": title, "h1": h1, "h1_count": len(h1_tags),
        "robots": robots, "x_robots": x_robots, "canonical": canonical,
        "word_count": word_count, "outgoing": outgoing, "keywords": keywords, "error": "",
        "discovered_via": discovered_via,
    }


async def _check_targets(client: httpx.AsyncClient, targets: list[str]) -> dict[str, dict[str, Any]]:
    semaphore = asyncio.Semaphore(12)

    async def check(url: str) -> tuple[str, dict[str, Any]]:
        async with semaphore:
            try:
                response = await client.get(url, follow_redirects=False)
                location = response.headers.get("location", "")
                redirect_to = _canonical_link(urljoin(url, location)) if 300 <= response.status_code < 400 and location else ""
                return page_key(url), {"status_code": response.status_code, "redirect_to": redirect_to}
            except httpx.HTTPError:
                return page_key(url), {"status_code": 0, "redirect_to": ""}

    pairs = await asyncio.gather(*(check(url) for url in targets)) if targets else []
    return dict(pairs)


def _home_url(domain: str) -> str:
    parsed = urlparse(normalize_url(domain))
    return _canonical_link(f"{parsed.scheme}://{parsed.netloc}/")


def _depths(home_key: str, adjacency: dict[str, set[str]], page_keys: set[str]) -> dict[str, int | None]:
    result: dict[str, int | None] = {key: None for key in page_keys}
    if not home_key or home_key not in page_keys:
        return result
    result[home_key] = 0
    queue: deque[str] = deque([home_key])
    while queue:
        source = queue.popleft()
        depth = result[source] or 0
        for target in adjacency.get(source, set()):
            if target in page_keys and result[target] is None:
                result[target] = depth + 1
                queue.append(target)
    return result


def _suggest_donors(target: dict[str, Any], pages: list[dict[str, Any]], existing_source_keys: set[str]) -> list[dict[str, Any]]:
    target_tokens = _tokens(target.get("title", ""), target.get("h1", ""), _slug_words(target["url"]), *target.get("keywords", []))
    candidates: list[tuple[float, dict[str, Any], list[str]]] = []
    target_path = urlparse(target["url"]).path.strip("/").split("/")

    for donor in pages:
        donor_key = page_key(donor["url"])
        if donor_key == page_key(target["url"]) or donor_key in existing_source_keys or not 200 <= donor.get("status_code", 0) < 300:
            continue
        donor_tokens = _tokens(donor.get("title", ""), donor.get("h1", ""), _slug_words(donor["url"]), *donor.get("keywords", []))
        overlap = target_tokens & donor_tokens
        union = target_tokens | donor_tokens
        similarity = len(overlap) / max(1, len(union))
        donor_path = urlparse(donor["url"]).path.strip("/").split("/")
        common_prefix = 0
        for left, right in zip(target_path, donor_path):
            if left != right:
                break
            common_prefix += 1
        score = similarity * 100 + common_prefix * 8 + min(len(donor.get("outgoing", [])), 20) * 0.15
        if overlap or common_prefix:
            candidates.append((score, donor, sorted(overlap)[:6]))

    candidates.sort(key=lambda item: item[0], reverse=True)
    output = []
    for score, donor, overlap in candidates[:3]:
        reasons = ["общие темы: " + ", ".join(overlap[:4])] if overlap else ["близкая ветка структуры сайта"]
        output.append({
            "url": donor["url"], "title": donor.get("h1") or donor.get("title") or donor["url"],
            "score": round(score, 1), "reason": "; ".join(reasons),
        })
    return output


def _anchor_suggestions(page: dict[str, Any]) -> list[str]:
    variants: list[str] = []
    for value in (page.get("h1", ""), page.get("title", ""), _slug_words(page["url"])):
        clean = _clean(value)
        clean = re.split(r"\s+[|—–-]\s+", clean)[0].strip()
        if clean and clean.lower() not in {item.lower() for item in variants}:
            variants.append(clean[:110])
    return variants[:3]


async def analyze_internal_links(
    domain: str,
    sitemap_url: str = "",
    max_pages: int = 200,
    exclude_patterns: list[str] | None = None,
    progress_callback=None,
    cancel_event=None,
) -> dict[str, Any]:
    """Build a real site graph.

    Phase 1 is BFS from the actual home page following crawlable <a href> links.
    Phase 2 uses remaining capacity to inspect sitemap-only URLs, so orphan pages can still
    be audited without pretending they were reachable from Home.
    """
    base_domain = normalize_url(domain).rstrip("/")
    max_pages = max(1, min(max_pages, 1000))
    exclude_patterns = exclude_patterns or []
    timeout = httpx.Timeout(18.0, connect=8.0)
    limits = httpx.Limits(max_connections=16, max_keepalive_connections=10)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/xml,text/xml;q=0.9,*/*;q=0.8"}

    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True, limits=limits) as client:
        resolved_sitemap = await discover_sitemap(client, base_domain, sitemap_url)
        try:
            sitemap_urls, sitemap_errors = await collect_sitemap_urls(client, resolved_sitemap, max_urls=max_pages * 5)
        except ValueError:
            sitemap_urls, sitemap_errors = [], ["Не удалось получить URL из sitemap."]
        sitemap_urls = [u for u in sitemap_urls if not _excluded_url(u, exclude_patterns) and is_page_candidate(u)]
        sitemap_by_key = {page_key(u): _canonical_link(u) for u in sitemap_urls}

        project_host = _host(base_domain)
        home = _home_url(base_domain)
        home_key = page_key(home)
        fetched: dict[str, dict[str, Any]] = {}
        failed: list[dict[str, str]] = []
        discovered_urls: dict[str, str] = {home_key: home}
        discovered_from_home: set[str] = {home_key}
        queue: deque[tuple[str, int]] = deque([(home, 0)])
        queued: set[str] = {home_key}
        bfs_exhausted = True
        total_links_seen = 0

        if progress_callback:
            await progress_callback(0, max_pages, "Краул от Главной: собираю HTML-ссылки")

        # Deliberately sequential BFS by levels for deterministic minimal depth; requests are still modest for <=1000 pages.
        while queue and len(fetched) < max_pages:
            if cancel_event is not None and cancel_event.is_set():
                raise asyncio.CancelledError
            url, depth = queue.popleft()
            key = page_key(url)
            if key in fetched:
                continue
            page = await _fetch_page(client, url, project_host, exclude_patterns, discovered_via="home")
            page["crawl_depth"] = depth
            fetched[key] = page
            if page.get("error") and page.get("error") != "not_html":
                failed.append({"url": url, "error": page.get("error", "")})
            for link in page.get("outgoing", []):
                total_links_seen += 1
                target = link["target"]
                target_key = page_key(target)
                discovered_urls.setdefault(target_key, target)
                if target_key not in discovered_from_home:
                    discovered_from_home.add(target_key)
                if target_key not in queued and target_key not in fetched and len(queued) + len(fetched) < max_pages * 3:
                    queued.add(target_key)
                    queue.append((target, depth + 1))
            if progress_callback:
                await progress_callback(len(fetched), max_pages, f"Краул от Главной: обработано {len(fetched)} страниц")

        if queue:
            bfs_exhausted = False

        # Inspect sitemap-only pages with remaining capacity. They do not receive crawl depth.
        for skey, surl in sitemap_by_key.items():
            if len(fetched) >= max_pages:
                break
            if skey in fetched:
                continue
            if cancel_event is not None and cancel_event.is_set():
                raise asyncio.CancelledError
            page = await _fetch_page(client, surl, project_host, exclude_patterns, discovered_via="sitemap")
            page["crawl_depth"] = None
            fetched[skey] = page
            discovered_urls.setdefault(skey, surl)
            if page.get("error") and page.get("error") != "not_html":
                failed.append({"url": surl, "error": page.get("error", "")})
            total_links_seen += len(page.get("outgoing", []))
            if progress_callback:
                await progress_callback(len(fetched), max_pages, f"Дополняю граф sitemap-страницами: {len(fetched)}")

        pages = [page for page in fetched.values() if page.get("error") != "not_html" and is_page_candidate(page.get("url", ""))]
        page_keys = {page_key(page["url"]) for page in pages}
        page_by_key = {page_key(page["url"]): page for page in pages}

        adjacency: dict[str, set[str]] = defaultdict(set)
        incoming_sources: dict[str, set[str]] = defaultdict(set)
        incoming_details: dict[str, list[dict[str, str]]] = defaultdict(list)
        # Self-links are useful diagnostics, but they are not independent donor pages and
        # therefore must never inflate Inlinks/orphan calculations.
        self_link_details: dict[str, list[dict[str, str]]] = defaultdict(list)
        all_targets: dict[str, str] = {}

        for page in pages:
            source_key = page_key(page["url"])
            for link in page.get("outgoing", []):
                target_key = page_key(link["target"])
                if target_key == source_key:
                    self_link_details[source_key].append({
                        "source": page["url"], "anchor": link.get("anchor", ""), "type": link.get("type", "other")
                    })
                    continue
                adjacency[source_key].add(target_key)
                all_targets.setdefault(target_key, link["target"])
                # Count one unique donor page even if it contains several links to the target.
                incoming_sources[target_key].add(source_key)
                incoming_details[target_key].append({
                    "source": page["url"], "anchor": link.get("anchor", ""), "type": link.get("type", "other")
                })

        if progress_callback:
            await progress_callback(len(fetched), max_pages, "Проверяю статусы внутренних ссылок")
        target_status = await _check_targets(client, sorted(all_targets.values()))

    depths = _depths(home_key, adjacency, page_keys)
    # Prefer BFS depth captured during crawl; graph recalculation serves as consistency check.
    for key, page in page_by_key.items():
        if page.get("discovered_via") == "home":
            depths[key] = page.get("crawl_depth") if page.get("crawl_depth") is not None else depths.get(key)

    broken_links: list[dict[str, Any]] = []
    redirect_links: list[dict[str, Any]] = []
    for source_key, targets in adjacency.items():
        source_url = page_by_key.get(source_key, {}).get("url", source_key)
        for target_key in targets:
            target_url = all_targets.get(target_key, target_key)
            status = target_status.get(target_key, {"status_code": 0, "redirect_to": ""})
            code = status["status_code"]
            if code == 0 or code >= 400:
                broken_links.append({"source": source_url, "target": target_url, "status_code": code})
            elif 300 <= code < 400:
                redirect_links.append({"source": source_url, "target": target_url, "status_code": code, "redirect_to": status["redirect_to"]})

    orphan_keys = [key for key in page_keys if key != home_key and len(incoming_sources.get(key, set())) == 0]
    weak_keys = [key for key in page_keys if key != home_key and len(incoming_sources.get(key, set())) == 1]
    no_outgoing_keys = [key for key in page_keys if len({target for target in adjacency.get(key, set()) if target in page_keys}) == 0]
    unreachable_keys = [key for key in page_keys if key != home_key and depths.get(key) is None]
    deep_keys = [key for key in page_keys if depths.get(key) is not None and int(depths[key]) >= 4]

    page_rows: list[dict[str, Any]] = []
    for key, page in page_by_key.items():
        internal_targets = {target for target in adjacency.get(key, set()) if target in page_keys}
        # One donor page = one inlink, even if multiple anchors on that donor point to target.
        donor_keys = incoming_sources.get(key, set())
        details = incoming_details.get(key, [])
        # Collapse multiple links from same donor into one row while retaining all anchor texts/types.
        grouped: dict[str, dict[str, Any]] = {}
        for detail in details:
            skey = page_key(detail["source"])
            item = grouped.setdefault(skey, {"source": detail["source"], "anchors": [], "types": []})
            if detail.get("anchor") and detail["anchor"] not in item["anchors"]:
                item["anchors"].append(detail["anchor"])
            if detail.get("type") and detail["type"] not in item["types"]:
                item["types"].append(detail["type"])
        incoming_links = []
        for skey, item in grouped.items():
            source_row = page_by_key.get(skey, {})
            incoming_links.append({
                "source": item["source"],
                "anchor": " · ".join(item["anchors"][:4]),
                "anchors": item["anchors"][:10],
                "type": item["types"][0] if len(item["types"]) == 1 else ("mixed" if item["types"] else "other"),
                "types": item["types"],
                "source_depth": depths.get(skey),
                "source_discovered_via": source_row.get("discovered_via", ""),
            })
        incoming_links.sort(key=lambda x: (x["source_depth"] is None, x["source_depth"] or 999, x["source"]))

        self_details = self_link_details.get(key, [])
        self_anchors: list[str] = []
        self_types: list[str] = []
        for detail in self_details:
            anchor = detail.get("anchor", "")
            link_type = detail.get("type", "other")
            if anchor and anchor not in self_anchors:
                self_anchors.append(anchor)
            if link_type and link_type not in self_types:
                self_types.append(link_type)

        page_rows.append({
            "url": page["url"], "final_url": page.get("final_url", page["url"]),
            "title": page.get("title", ""), "h1": page.get("h1", ""), "h1_count": page.get("h1_count", 0),
            "status_code": page.get("status_code", 0), "initial_status_code": page.get("initial_status_code", page.get("status_code", 0)),
            "redirect_chain": page.get("redirect_chain", []), "content_type": page.get("content_type", ""),
            "robots": page.get("robots", ""), "x_robots": page.get("x_robots", ""), "canonical": page.get("canonical", ""),
            "word_count": page.get("word_count", 0), "incoming": len(donor_keys), "outgoing": len(internal_targets),
            "depth": depths.get(key), "depth_reason": "" if depths.get(key) is not None else (
                "URL не достигнут переходами от Главной" if page.get("discovered_via") == "sitemap" else "Не удалось построить путь от Главной"
            ),
            "found_in_crawl": key in discovered_from_home,
            "discovered_via": page.get("discovered_via", ""),
            "is_orphan": key in orphan_keys, "is_weak": key in weak_keys, "no_outgoing": key in no_outgoing_keys,
            "unreachable": key in unreachable_keys, "deep": key in deep_keys, "incoming_links": incoming_links[:80],
            "self_link": bool(self_details), "self_link_anchors": self_anchors[:10], "self_link_types": self_types,
        })

    page_map = {page_key(page["url"]): page for page in pages}
    recommendation_targets = orphan_keys + [key for key in weak_keys if key not in orphan_keys]
    recommendations: list[dict[str, Any]] = []
    for key in recommendation_targets[:40]:
        target = page_map.get(key)
        if not target:
            continue
        donors = _suggest_donors(target, pages, incoming_sources.get(key, set()))
        if donors:
            recommendations.append({
                "target_url": target["url"], "target_title": target.get("h1") or target.get("title") or target["url"],
                "incoming": len(incoming_sources.get(key, set())), "donors": donors, "anchors": _anchor_suggestions(target),
            })

    hubs = sorted(page_rows, key=lambda row: (row["incoming"], row["outgoing"]), reverse=True)[:20]
    hub_keys = {page_key(row["url"]) for row in hubs}
    graph_edges = []
    for source_key in hub_keys:
        for target_key in adjacency.get(source_key, set()):
            if target_key in hub_keys:
                graph_edges.append({"source": page_by_key[source_key]["url"], "target": page_by_key[target_key]["url"]})

    issue_score = len(orphan_keys) * 8 + len(weak_keys) * 2 + len(broken_links) * 8 + len(redirect_links) * 2 + len(deep_keys) * 2 + len(no_outgoing_keys) * 2
    denominator = max(1, len(page_keys) * 20)
    score = max(0, min(100, round(100 - (issue_score / denominator) * 100)))

    sitemap_missing = max(0, len(sitemap_by_key) - len({key for key in page_keys if key in sitemap_by_key}))
    crawl_limited = (not bfs_exhausted) or len(fetched) >= max_pages and (len(sitemap_by_key) > len(fetched) or bool(queue))
    home_crawled = home_key in page_by_key and 200 <= int(page_by_key[home_key].get("status_code", 0)) < 400
    crawl_sufficient = home_crawled and not crawl_limited and len(failed) <= max(2, round(max(1, len(fetched)) * 0.05))

    return {
        "domain": base_domain, "sitemap_url": resolved_sitemap, "sitemap_errors": sitemap_errors,
        "score": score,
        "pages_total": len(page_rows), "pages_crawled": len(fetched), "links_total": sum(len(targets) for targets in adjacency.values()),
        "html_links_seen": total_links_seen, "unique_urls_found": len(discovered_urls), "crawl_errors_count": len(failed),
        "crawl_errors": failed[:100], "home_url": home, "home_crawled": home_crawled,
        "crawl_sufficient": crawl_sufficient, "crawl_sufficient_reason": (
            "Краул от Главной завершён без ограничения." if crawl_sufficient else
            "Достигнут лимит страниц — граф может быть неполным." if crawl_limited else
            "Главная не была успешно обработана." if not home_crawled else
            "Во время обхода слишком много страниц не удалось обработать."
        ),
        "orphans": len(orphan_keys), "weak_pages": len(weak_keys), "no_outgoing": len(no_outgoing_keys),
        "unreachable": len(unreachable_keys), "deep_pages": len(deep_keys), "broken_links_count": len(broken_links),
        "redirect_links_count": len(redirect_links), "broken_links": broken_links[:300], "redirect_links": redirect_links[:300],
        "pages": sorted(page_rows, key=lambda row: (row["is_orphan"], row["is_weak"], -(row["incoming"])), reverse=True),
        "recommendations": recommendations, "graph": {"nodes": hubs, "edges": graph_edges[:180]},
        "limited": crawl_limited, "max_pages": max_pages, "sitemap_urls_total": len(sitemap_by_key), "sitemap_not_crawled": sitemap_missing,
    }
