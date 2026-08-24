from __future__ import annotations

import asyncio
import html
import json
import re
from collections import Counter, defaultdict
from typing import Any
from urllib.parse import parse_qsl, urlparse

import httpx
from bs4 import BeautifulSoup

from app.services.seo_audit import USER_AGENT, normalize_url
from app.services.site_audit import collect_sitemap_entries, discover_sitemap, _excluded_url, _host

ENTITY_RE = re.compile(r"&(?:#\d+|#x[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]+);")
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF]")
PHONE_RE = re.compile(r"(?:\+?7|8)[\s\-\(\)]*\d{3}[\s\-\(\)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}")
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
LEGAL_RE = re.compile(r"\b(?:ООО|АО|ПАО|ИП)\b", re.I)
TECHNICAL_NAME_RE = re.compile(r"(?:^|[-_.])(ajax|endpoint|handler|callback|include|inc|api|feed|cron)(?:[-_.]|$)", re.I)
TECHNICAL_QUERY_KEYS = {"ajax", "ajax_action", "action", "callback", "handler", "endpoint", "wc-ajax"}
VERIFICATION_FILE_RE = re.compile(r"^(?:yandex_[a-z0-9_-]+|google[a-z0-9_-]+)\.html$", re.I)
TECHNICAL_DIR_RE = re.compile(r"/(?:includes?|inc|ajax|api|handlers?|endpoints?)(?:/|$)", re.I)

STATUS_LABELS = {
    "ok": "🟢 Всё в порядке",
    "review": "🟡 Проверить",
    "replace": "🔴 Исправить",
    "technical": "⚫ Техническая проблема",
    "broken": "🔴 HTTP-ошибка / битая страница",
    "template": "🟣 Проблема шаблона Description",
}
PAGE_TYPE_LABELS = {
    "product": "Товар",
    "category": "Категория",
    "article": "Статья",
    "info": "Информационная страница",
    "technical": "Техническая страница",
    "unknown": "Не определено",
}
INDEXABLE_LABELS = {"yes": "Да", "no": "Нет", "unknown": "Не определено"}
ISSUE_LABELS = {
    "missing": "Description отсутствует",
    "too_long": "Description слишком длинный",
    "too_short": "Description слишком короткий",
    "html_entities": "HTML-сущности",
    "emoji": "Эмодзи / спецсимволы",
    "duplicate": "Дубликат Description",
    "template": "Шаблонный Description",
    "service_text": "Контактный или служебный текст",
    "html_fragment": "HTML-фрагмент в Description",
    "fetch_error": "Ошибка получения страницы",
    "http_error": "HTTP-ошибка страницы",
    "technical_template": "Возможна техническая проблема шаблона",
    "technical_url": "Технический URL",
    "noindex": "Meta robots запрещает индексацию",
    "x_robots_noindex": "X-Robots-Tag запрещает индексацию",
    "redirect": "URL перенаправляет на другую страницу",
    "canonical_other": "Canonical указывает на другую страницу",
}


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _normalize_desc(value: str) -> str:
    return _clean(html.unescape(html.unescape(value or ""))).lower()


def _norm_compare_url(value: str) -> str:
    if not value:
        return ""
    try:
        u = urlparse(value)
        scheme = (u.scheme or "https").lower()
        host = (u.hostname or "").lower()
        port = f":{u.port}" if u.port and not ((scheme == "https" and u.port == 443) or (scheme == "http" and u.port == 80)) else ""
        path = re.sub(r"/{2,}", "/", u.path or "/")
        if path != "/":
            path = path.rstrip("/")
        return f"{scheme}://{host}{port}{path}"
    except Exception:
        return value.rstrip("/").lower()


def _raw_description(source: str) -> str:
    patterns = [
        r'<meta\b[^>]*\bname\s*=\s*["\']description["\'][^>]*\bcontent\s*=\s*(["\'])(.*?)\1[^>]*>',
        r'<meta\b[^>]*\bcontent\s*=\s*(["\'])(.*?)\1[^>]*\bname\s*=\s*["\']description["\'][^>]*>',
    ]
    for pattern in patterns:
        m = re.search(pattern, source, flags=re.I | re.S)
        if m:
            return _clean(m.group(2))
    return ""


def _section_key(url: str) -> str:
    path = urlparse(url).path.strip("/")
    if not path:
        return "/"
    parts = path.split("/")
    if len(parts) == 1:
        return "/"
    return f"/{parts[0]}/"


def _template_scope_key(url: str) -> str:
    """Group template comparisons inside a meaningful site section, not site-wide."""
    parts = [x for x in urlparse(url).path.strip("/").split("/") if x]
    if not parts:
        return "/"
    lower = [x.lower() for x in parts]
    if lower[0] in {"catalog", "katalog"} and len(parts) >= 2:
        return f"/{parts[0]}/{parts[1]}/"
    if "blog" in lower:
        pos = lower.index("blog")
        return "/" + "/".join(parts[: pos + 1]) + "/"
    if lower[0] in {"news", "novosti", "articles", "article", "stati"}:
        return f"/{parts[0]}/"
    return f"/{parts[0]}/"


def group_urls(urls: list[str]) -> dict[str, int]:
    counts = Counter(_section_key(url) for url in urls)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


async def preview_sitemap(domain: str, sitemap_url: str = "", max_urls: int = 5000, exclude_patterns: list[str] | None = None) -> dict[str, Any]:
    base = normalize_url(domain)
    timeout = httpx.Timeout(20.0, connect=8.0)
    headers = {"User-Agent": USER_AGENT, "Accept": "application/xml,text/xml,text/html;q=0.8,*/*;q=0.5"}
    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
        resolved = await discover_sitemap(client, base, sitemap_url)
        entries, errors = await collect_sitemap_entries(client, resolved, max_urls=max_urls, max_sitemaps=100)
    patterns = exclude_patterns or []
    urls = [e["url"] for e in entries if not _excluded_url(e["url"], patterns)]
    unique = list(dict.fromkeys(urls))
    sitemaps = sorted({resolved} | {e.get("sitemap_url", "") for e in entries if e.get("sitemap_url")})
    return {
        "domain": base.rstrip("/"), "sitemap_url": resolved, "sitemaps": sitemaps,
        "sitemaps_count": len(sitemaps), "found_urls": len(urls), "unique_urls": len(unique),
        "duplicates": len(urls) - len(unique), "sections": group_urls(unique), "urls": unique,
        "errors": errors,
    }


def _jsonld_types(soup: BeautifulSoup) -> set[str]:
    found: set[str] = set()
    for script in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        try:
            data = json.loads(script.string or script.get_text() or "{}")
        except Exception:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                t = item.get("@type")
                if isinstance(t, str): found.add(t.lower())
                elif isinstance(t, list): found.update(str(x).lower() for x in t)
                graph = item.get("@graph")
                if isinstance(graph, list): stack.extend(graph)
            elif isinstance(item, list):
                stack.extend(item)
    return found


def _technical_url_signals(url: str, soup: BeautifulSoup | None = None, content_type: str = "") -> list[str]:
    parsed = urlparse(url)
    path = parsed.path.lower()
    name = path.rsplit("/", 1)[-1]
    signals: list[str] = []
    query_keys = {k.lower() for k, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    if query_keys & TECHNICAL_QUERY_KEYS:
        signals.append("технические параметры URL")
    if VERIFICATION_FILE_RE.match(name):
        signals.append("файл подтверждения поисковой системы")
    if TECHNICAL_DIR_RE.search(path):
        signals.append("служебный раздел сайта")
    if TECHNICAL_NAME_RE.search(name):
        signals.append("служебное имя файла/endpoint")
    if name.endswith(".php"):
        # .php alone is not enough, but PHP inside a technical directory or with an obvious service name is.
        if TECHNICAL_DIR_RE.search(path) or any(token in name for token in ("_inc", "-inc", "include", "ajax", "handler", "endpoint", "callback", "tab.php")):
            signals.append("служебный PHP-файл")
    if content_type and "html" not in content_type.lower():
        signals.append("ответ не является HTML-документом")
    if soup is not None:
        has_document = bool(soup.find("html") or soup.find("body"))
        meaningful = bool(soup.find("h1") or soup.find("title") or len(_clean(soup.get_text(" ", strip=True))) > 120)
        if not has_document and not meaningful:
            signals.append("нет признаков обычной HTML-страницы")
    return list(dict.fromkeys(signals))


def _page_type_from_url(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    parts = [x for x in parsed.path.strip("/").split("/") if x]
    lowered = [x.lower() for x in parts]
    if "blog" in lowered:
        pos = lowered.index("blog")
        if len(parts) > pos + 1:
            return "article", "структура URL раздела блога"
    if any(x in lowered for x in ("articles", "article", "stati", "novosti", "news")) and len(parts) >= 2:
        return "article", "структура URL раздела публикаций"
    return None


def _detect_page_type(url: str, soup: BeautifulSoup, body_text: str, content_type: str) -> tuple[str, str]:
    tech = _technical_url_signals(url, soup, content_type)
    if tech:
        return "technical", "; ".join(tech)

    url_type = _page_type_from_url(url)
    if url_type:
        return url_type

    types = _jsonld_types(soup)
    if "product" in types:
        return "product", "schema.org Product"
    if types & {"article", "newsarticle", "blogposting"}:
        return "article", "структурированные данные Article"
    if types & {"collectionpage", "itemlist"}:
        return "category", "структурированные данные категории/списка"

    parsed = urlparse(url)
    parts = [x for x in parsed.path.strip("/").split("/") if x]
    lowered = [x.lower() for x in parts]
    if lowered and lowered[0] in {"news", "blog", "articles", "article", "stati", "novosti"} and len(parts) >= 2:
        return "article", "структура URL раздела публикаций"
    if lowered and lowered[0] in {"catalog", "katalog"}:
        if len(parts) <= 2:
            return "category", "структура каталога"
        slug = parts[-1]
        product_signals = 0
        if re.search(r"\d", slug): product_signals += 1
        page_lower = body_text.lower()
        if any(x in page_lower for x in ("характеристики", "технические характеристики", "артикул", "модель")): product_signals += 1
        if soup.find(attrs={"itemtype": re.compile(r"schema\.org/Product", re.I)}): product_signals += 2
        if product_signals >= 2:
            return "product", "структура каталога и признаки товарной страницы"
        return "unknown", "вложенная страница каталога без достаточных признаков товара"

    if len(parts) <= 1 and (parts and parts[0].lower() in {"about", "contacts", "contact", "delivery", "payment", "help", "company"}):
        return "info", "структура информационного раздела"
    return "unknown", "недостаточно надёжных признаков"




def _jsonld_product_data(soup: BeautifulSoup) -> dict[str, Any]:
    """Extract only explicit Product facts from JSON-LD. Never infer missing values."""
    products: list[dict[str, Any]] = []
    for script in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        try:
            data = json.loads(script.string or script.get_text() or "{}")
        except Exception:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                typ = item.get("@type")
                types = {str(typ).lower()} if isinstance(typ, str) else {str(x).lower() for x in typ or []}
                if "product" in types:
                    products.append(item)
                graph = item.get("@graph")
                if isinstance(graph, list):
                    stack.extend(graph)
            elif isinstance(item, list):
                stack.extend(item)
    if not products:
        return {}
    # Prefer the Product object with the most explicit fields.
    product = max(products, key=lambda x: sum(bool(x.get(k)) for k in ("name","model","sku","brand","manufacturer","category","additionalProperty","description")))
    def entity_name(value: Any) -> str:
        if isinstance(value, str): return _clean(value)
        if isinstance(value, dict): return _clean(str(value.get("name") or value.get("@id") or ""))
        return ""
    props: list[dict[str, str]] = []
    raw_props = product.get("additionalProperty")
    if isinstance(raw_props, dict): raw_props = [raw_props]
    if isinstance(raw_props, list):
        for prop in raw_props:
            if not isinstance(prop, dict): continue
            name = _clean(str(prop.get("name") or "")); value = _clean(str(prop.get("value") or ""))
            if name and value and len(name) <= 80 and len(value) <= 160:
                props.append({"label": name, "value": value, "source": "schema.org Product"})
    return {
        "name": _clean(str(product.get("name") or "")),
        "model": _clean(str(product.get("model") or "")),
        "sku": _clean(str(product.get("sku") or product.get("mpn") or "")),
        "brand": entity_name(product.get("brand")),
        "manufacturer": entity_name(product.get("manufacturer")),
        "category": entity_name(product.get("category")),
        "description": _clean(str(product.get("description") or "")),
        "properties": props[:12],
    }


def _dom_product_facts(soup: BeautifulSoup) -> list[dict[str, str]]:
    """Extract label/value characteristics explicitly rendered on the page."""
    facts: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    def add(label: str, value: str, source: str):
        label = _clean(label).strip(":"); value = _clean(value)
        if not label or not value or label.lower() == value.lower(): return
        if len(label) > 90 or len(value) > 180: return
        key=(label.lower(), value.lower())
        if key in seen: return
        seen.add(key); facts.append({"label":label,"value":value,"source":source})
    for tr in soup.find_all("tr"):
        cells=tr.find_all(["th","td"], recursive=False)
        if len(cells)>=2:
            add(cells[0].get_text(" ",strip=True), cells[1].get_text(" ",strip=True), "таблица характеристик")
    for dt in soup.find_all("dt"):
        dd=dt.find_next_sibling("dd")
        if dd: add(dt.get_text(" ",strip=True), dd.get_text(" ",strip=True), "список характеристик")
    # Common characteristic cards: label/value nodes in one small container.
    for node in soup.find_all(class_=re.compile(r"(?:char|spec|property|param|feature)", re.I)):
        text=_clean(node.get_text(" ",strip=True))
        if 4 <= len(text) <= 180:
            m=re.match(r"^([^:]{2,70}):\s*(.{1,100})$", text)
            if m: add(m.group(1),m.group(2),"характеристика на странице")
        if len(facts)>=20: break
    return facts[:20]


def _breadcrumb_category(soup: BeautifulSoup, h1: str) -> str:
    candidates=[]
    for nav in soup.find_all(["nav","ol","ul"], class_=re.compile(r"bread|crumb", re.I)):
        texts=[_clean(a.get_text(" ",strip=True)) for a in nav.find_all("a") if _clean(a.get_text(" ",strip=True))]
        candidates.extend(texts)
    if not candidates:
        for node in soup.find_all(attrs={"itemtype": re.compile(r"BreadcrumbList", re.I)}):
            candidates.extend(_clean(x.get_text(" ",strip=True)) for x in node.find_all("a"))
    ignore={"главная","каталог",_clean(h1).lower()}
    for value in reversed(candidates):
        if value and value.lower() not in ignore and len(value)<=100:
            return value
    return ""


def _purpose_sentence(body_text: str, subject: str) -> str:
    # Keep only an explicit sentence that states purpose/use.
    for part in re.split(r"(?<=[.!?])\s+", body_text):
        clean=_clean(part)
        low=clean.lower()
        if not (35 <= len(clean) <= 240): continue
        if any(token in low for token in ("предназначен", "предназначена", "предназначено", "используется для", "применяется для", "служит для")):
            return clean
    return ""


def _extract_product_data(soup: BeautifulSoup, h1: str, body_text: str) -> dict[str, Any]:
    structured=_jsonld_product_data(soup)
    facts=[]
    seen=set()
    def add(label: str, value: str, source: str):
        label=_clean(label); value=_clean(value)
        if not value: return
        key=(label.lower(),value.lower())
        if key in seen: return
        seen.add(key); facts.append({"label":label,"value":value,"source":source})
    name=structured.get("name") or h1
    if structured.get("model"): add("Модель",structured["model"],"schema.org Product")
    if structured.get("sku"): add("Артикул",structured["sku"],"schema.org Product")
    maker=structured.get("manufacturer") or structured.get("brand")
    if maker: add("Производитель",maker,"schema.org Product")
    category=structured.get("category") or _breadcrumb_category(soup,h1)
    if category: add("Категория",category,"страница / хлебные крошки" if not structured.get("category") else "schema.org Product")
    for fact in structured.get("properties",[]): add(fact["label"],fact["value"],fact["source"] )
    for fact in _dom_product_facts(soup): add(fact["label"],fact["value"],fact["source"] )
    purpose=""
    for node in soup.find_all(["p","li"]):
        text=_clean(node.get_text(" ",strip=True))
        low=text.lower()
        if 30<=len(text)<=240 and any(token in low for token in ("предназначен","предназначена","предназначено","используется для","применяется для","служит для")):
            purpose=text; break
    if not purpose:
        purpose=_purpose_sentence(body_text,name)
    if purpose: add("Назначение",purpose,"текст страницы")
    # Delivery/warranty are allowed only when an explicit phrase is present on the product page.
    for label, pattern in (("Гарантия",r"[^.!?]{0,80}гаранти[^.!?]{0,120}"),("Доставка",r"[^.!?]{0,80}доставк[^.!?]{0,120}")):
        m=re.search(pattern,body_text,re.I)
        if m:
            value=_clean(m.group(0))
            if 15<=len(value)<=180: add(label,value,"текст страницы")
    return {"name":name,"category":category,"facts":facts[:16]}


def _indexability(row: dict[str, Any]) -> tuple[str, str]:
    status = int(row.get("status_code") or 0)
    robots = (row.get("robots") or "").lower()
    xrobots = (row.get("x_robots_tag") or "").lower()
    canonical = row.get("canonical") or ""
    url = row.get("url") or ""
    if row.get("page_type") == "technical":
        return "no", "техническая страница"
    if row.get("error") and not row.get("status_code"):
        return "unknown", "страницу не удалось получить"
    if row.get("redirected"):
        return "no", "URL перенаправляет на другой адрес"
    if status < 200 or status >= 400:
        return "no", f"HTTP {status or 'ошибка'}"
    if "noindex" in robots:
        return "no", "meta robots: noindex"
    if "noindex" in xrobots:
        return "no", "X-Robots-Tag: noindex"
    if canonical and _norm_compare_url(canonical) != _norm_compare_url(url):
        return "no", "canonical указывает на другую страницу"
    if status == 200:
        return "yes", "технических запретов не обнаружено"
    return "unknown", "недостаточно данных"


async def _scan_one(client: httpx.AsyncClient, url: str, project_host: str) -> dict[str, Any]:
    base_result: dict[str, Any] = {
        "url": url, "status_code": 0, "final_url": url, "error": "", "title": "", "h1": "",
        "description_raw": "", "description": "", "description_length": 0, "canonical": "", "robots": "",
        "x_robots_tag": "", "body_excerpt": "", "issues": [], "status": "ok", "status_label": STATUS_LABELS["ok"],
        "suggested_description": "", "suggestion_action": "", "section": _section_key(url), "duplicate_urls": [],
        "duplicate_count": 0, "template_group": "", "template_scope": _template_scope_key(url),
        "template_group_size": 0, "entity_tokens": [], "page_type": "unknown",
        "page_type_label": PAGE_TYPE_LABELS["unknown"], "page_type_reason": "", "indexable": "unknown",
        "indexable_label": INDEXABLE_LABELS["unknown"], "indexability_reason": "", "redirected": False,
        "redirect_chain": [], "technical_signals": [], "product_data": {}, "generation_used_facts": [], "generation_notes": [],
    }
    try:
        response = await client.get(url)
    except httpx.TimeoutException:
        inferred = _page_type_from_url(url)
        if inferred:
            base_result.update(page_type=inferred[0], page_type_label=PAGE_TYPE_LABELS[inferred[0]], page_type_reason=inferred[1])
        base_result.update(error="Тайм-аут", issues=["fetch_error"], indexable="unknown", indexable_label=INDEXABLE_LABELS["unknown"], indexability_reason="страницу не удалось получить")
        return base_result
    except httpx.RequestError as exc:
        inferred = _page_type_from_url(url)
        if inferred:
            base_result.update(page_type=inferred[0], page_type_label=PAGE_TYPE_LABELS[inferred[0]], page_type_reason=inferred[1])
        base_result.update(error=f"Ошибка запроса: {exc.__class__.__name__}", issues=["fetch_error"], indexable="unknown", indexable_label=INDEXABLE_LABELS["unknown"], indexability_reason="страницу не удалось получить")
        return base_result

    history = [{"status": r.status_code, "url": str(r.url)} for r in response.history]
    redirected = bool(response.history and _norm_compare_url(str(response.url)) != _norm_compare_url(url))
    content_type = response.headers.get("content-type", "")
    base_result.update(status_code=response.status_code, final_url=str(response.url), x_robots_tag=_clean(response.headers.get("x-robots-tag", "")), redirected=redirected, redirect_chain=history)

    if "html" not in content_type.lower():
        base_result["error"] = "URL не возвращает HTML"
        base_result["technical_signals"] = _technical_url_signals(url, None, content_type)
        base_result["page_type"] = "technical" if base_result["technical_signals"] else "unknown"
        base_result["page_type_label"] = PAGE_TYPE_LABELS[base_result["page_type"]]
        base_result["page_type_reason"] = "; ".join(base_result["technical_signals"]) or "ответ не является обычной HTML-страницей"
        base_result["indexable"], base_result["indexability_reason"] = _indexability(base_result)
        base_result["indexable_label"] = INDEXABLE_LABELS[base_result["indexable"]]
        return base_result

    source = response.text
    soup = BeautifulSoup(source, "html.parser")
    title = _clean(soup.title.string if soup.title and soup.title.string else "")
    h1_tag = soup.find("h1")
    h1 = _clean(h1_tag.get_text(" ", strip=True)) if h1_tag else ""
    desc_tag = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    decoded = html.unescape(html.unescape(_clean(desc_tag.get("content")))) if desc_tag and desc_tag.get("content") is not None else ""
    raw = _raw_description(source)
    canonical_tag = soup.find("link", rel=lambda value: value and "canonical" in value)
    canonical = str(httpx.URL(str(response.url)).join(canonical_tag.get("href"))) if canonical_tag and canonical_tag.get("href") else ""
    robots_tag = soup.find("meta", attrs={"name": re.compile(r"^robots$", re.I)})
    robots = _clean(robots_tag.get("content")) if robots_tag else ""

    body = soup.body or soup
    copy = BeautifulSoup(str(body), "html.parser")
    for tag in copy(["script", "style", "noscript", "svg", "template", "nav", "footer"]):
        tag.decompose()
    body_text = _clean(copy.get_text(" ", strip=True))
    page_type, page_type_reason = _detect_page_type(url, soup, body_text, content_type)
    tech_signals = _technical_url_signals(url, soup, content_type)

    product_data = _extract_product_data(soup, h1, body_text) if page_type == "product" else {}
    base_result.update({
        "title": title, "h1": h1, "description_raw": raw, "description": decoded,
        "description_length": len(decoded), "canonical": canonical, "robots": robots,
        "body_excerpt": body_text[:4200], "page_type": page_type, "page_type_label": PAGE_TYPE_LABELS[page_type],
        "page_type_reason": page_type_reason, "technical_signals": tech_signals, "product_data": product_data,
    })
    base_result["indexable"], base_result["indexability_reason"] = _indexability(base_result)
    base_result["indexable_label"] = INDEXABLE_LABELS[base_result["indexable"]]
    return base_result


def _detect_base_issues(row: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    desc = row.get("description", "")
    raw = row.get("description_raw", "")
    status = int(row.get("status_code") or 0)
    if status and not (200 <= status < 400): issues.append("http_error")
    elif row.get("error") and row.get("page_type") != "technical": issues.append("fetch_error")
    if row.get("page_type") == "technical": issues.append("technical_url")
    if row.get("redirected"): issues.append("redirect")
    if "noindex" in (row.get("robots") or "").lower(): issues.append("noindex")
    if "noindex" in (row.get("x_robots_tag") or "").lower(): issues.append("x_robots_noindex")
    canonical = row.get("canonical") or ""
    if canonical and _norm_compare_url(canonical) != _norm_compare_url(row.get("url", "")): issues.append("canonical_other")

    # Description diagnostics are still recorded for technical/non-indexable URLs, but they will not become ordinary Replace work.
    if not desc:
        issues.append("missing")
    else:
        if len(desc) > 160: issues.append("too_long")
        if len(desc) < 70: issues.append("too_short")
        entity_tokens = ENTITY_RE.findall(raw)
        if entity_tokens:
            issues.append("html_entities")
            row["entity_tokens"] = sorted(set(entity_tokens))
        if EMOJI_RE.search(desc): issues.append("emoji")
        if PHONE_RE.search(desc) or EMAIL_RE.search(desc) or LEGAL_RE.search(desc): issues.append("service_text")
        if "<" in desc and ">" in desc: issues.append("html_fragment")
    return list(dict.fromkeys(issues))


def _template_signature(desc: str) -> str:
    value = _normalize_desc(desc)
    # Replace model/article-like alphanumeric tokens before plain numbers so
    # ЭТ-500, ЭТ-20111М and 18x5PzS250 collapse to the same product pattern.
    value = re.sub(r"\b[a-zа-я]*\d+[a-zа-я0-9-]*\b", "MODEL", value, flags=re.I)
    value = re.sub(r"\b\d+(?:[.,]\d+)?\b", "#", value)
    value = re.sub(r"[«»\"'()]", "", value)
    return value


def _apply_cross_page_checks(rows: list[dict[str, Any]]) -> dict[str, Any]:
    # Exact duplicates are compared on decoded/normalized text.
    desc_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        normalized = _normalize_desc(row.get("description", ""))
        if normalized:
            desc_groups[normalized].append(row)
    for group in desc_groups.values():
        if len(group) > 1:
            urls = [r["url"] for r in group]
            for row in group:
                row["issues"].append("duplicate")
                row["duplicate_urls"] = [u for u in urls if u != row["url"]]
                row["duplicate_count"] = len(group)

    # Template similarity is local to a site section + page type. This prevents a pattern
    # from /catalog/elektrotelezhki/ from marking unrelated pages across the whole site.
    sig_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        desc = row.get("description", "")
        if not desc or row.get("page_type") == "technical":
            continue
        signature = _template_signature(desc)
        if signature:
            scope = row.get("template_scope") or _template_scope_key(row.get("url", ""))
            sig_groups[(scope, row.get("page_type", "unknown"), signature)].append(row)

    template_groups = 0
    template_rows: set[str] = set()
    for (scope, page_type, signature), group in sig_groups.items():
        # Three pages with the same normalized pattern inside one section are enough
        # to flag a repeated template. This is a signal, not a claim about the CMS cause.
        if len(group) >= 3:
            template_groups += 1
            for row in group:
                if "template" not in row["issues"]:
                    row["issues"].append("template")
                row["template_group"] = signature[:180]
                row["template_scope"] = scope
                row["template_group_size"] = len(group)
                template_rows.add(row.get("url", ""))

    # Repeated HTML entity defects are an additional strong template/CMS signal,
    # but only promote normal, indexable SEO pages; technical URLs remain technical.
    entity_by_scope: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if "html_entities" in row.get("issues", []) and row.get("page_type") != "technical":
            key = (row.get("template_scope") or _template_scope_key(row.get("url", "")), row.get("page_type", "unknown"))
            entity_by_scope[key].append(row)
    mass_entity = False
    for _, group in entity_by_scope.items():
        if len(group) >= 5:
            mass_entity = True
            for row in group:
                if "technical_template" not in row["issues"]:
                    row["issues"].append("technical_template")
                template_rows.add(row.get("url", ""))

    technical_issue_codes = {"technical_url", "noindex", "x_robots_noindex", "redirect", "canonical_other"}
    replace_issue_codes = {"missing", "too_long", "html_entities", "duplicate", "html_fragment"}
    review_issue_codes = {"too_short", "emoji", "service_text"}
    for row in rows:
        row["issues"] = list(dict.fromkeys(row["issues"]))
        issues = set(row["issues"])
        # A real HTTP error is a broken page, not a technical include/endpoint.
        if "http_error" in issues:
            row["status"] = "broken"
        elif row.get("page_type") == "technical" or issues & technical_issue_codes:
            row["status"] = "technical"
        elif "fetch_error" in issues:
            # Network/request failure means the audit could not decide; keep it separate
            # from broken HTTP pages while still routing it to technical review.
            row["status"] = "technical"
        elif row.get("url", "") in template_rows or "technical_template" in issues:
            row["status"] = "template"
        elif issues & replace_issue_codes:
            row["status"] = "replace"
        elif issues & review_issue_codes or "template" in issues:
            row["status"] = "review"
        else:
            row["status"] = "ok"
        row["status_label"] = STATUS_LABELS[row["status"]]
    return {"mass_entity_problem": mass_entity, "template_groups": template_groups, "template_rows": len(template_rows)}


async def run_meta_description_audit(domain: str, urls: list[str], *, source_name: str = "", sitemap_url: str = "", progress_callback=None, cancel_event=None) -> dict[str, Any]:
    base = normalize_url(domain)
    project_host = _host(base)
    unique_urls = list(dict.fromkeys(urls))
    timeout = httpx.Timeout(18.0, connect=8.0)
    limits = httpx.Limits(max_connections=10, max_keepalive_connections=6)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
    sem = asyncio.Semaphore(6)

    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True, limits=limits) as client:
        async def one(url: str):
            async with sem: return await _scan_one(client, url, project_host)
        tasks = [asyncio.create_task(one(url)) for url in unique_urls]
        rows: list[dict[str, Any]] = []
        if progress_callback: await progress_callback(0, len(tasks), "Начинаю аудит Meta Description")
        try:
            for completed in asyncio.as_completed(tasks):
                if cancel_event is not None and cancel_event.is_set():
                    for task in tasks: task.cancel()
                    raise asyncio.CancelledError
                row = await completed
                row["issues"] = _detect_base_issues(row)
                rows.append(row)
                if progress_callback: await progress_callback(len(rows), len(tasks), f"Проверено {len(rows)} из {len(tasks)} страниц")
        finally:
            if cancel_event is not None and cancel_event.is_set():
                for task in tasks:
                    if not task.done(): task.cancel()

    cross = _apply_cross_page_checks(rows)
    status_counts = Counter(row["status"] for row in rows)
    issue_counts = Counter(code for row in rows for code in set(row["issues"]))
    for row in rows:
        row["issue_labels"] = [ISSUE_LABELS.get(code, code) for code in row["issues"]]
    technical_excluded = sum(1 for r in rows if r.get("page_type") == "technical")
    fetch_errors = sum(1 for r in rows if "fetch_error" in r.get("issues", []))
    http_errors = sum(1 for r in rows if "http_error" in r.get("issues", []))
    http_404 = sum(1 for r in rows if int(r.get("status_code") or 0) == 404)
    http_5xx = sum(1 for r in rows if 500 <= int(r.get("status_code") or 0) < 600)
    template_problem_count = sum(1 for r in rows if r.get("status") == "template")
    products_content_fix = sum(1 for r in rows if r.get("page_type") == "product" and r.get("indexable") == "yes" and r.get("status") == "replace")
    products_template_problem = sum(1 for r in rows if r.get("page_type") == "product" and r.get("indexable") == "yes" and r.get("status") == "template")
    return {
        "domain": base.rstrip("/"), "source_name": source_name, "sitemap_url": sitemap_url,
        "urls_total": len(rows), "status_counts": dict(status_counts), "issue_counts": dict(issue_counts),
        "mass_template_warning": cross["mass_entity_problem"], "template_groups": cross["template_groups"],
        "technical_excluded": technical_excluded, "fetch_errors": fetch_errors, "http_errors": http_errors,
        "http_404": http_404, "http_5xx": http_5xx,
        "template_problem_count": template_problem_count, "products_content_fix": products_content_fix,
        "products_template_problem": products_template_problem, "products_to_fix": products_content_fix, "rows": rows,
    }


def _strip_contacts(value: str) -> str:
    value = PHONE_RE.sub("", value)
    value = EMAIL_RE.sub("", value)
    value = re.sub(r"\b(?:ООО|АО|ПАО|ИП)\s+[«\"']?[^,.!?;]{1,80}[»\"']?", "", value, flags=re.I)
    return _clean(value)


def _safe_fact_value(value: str) -> str:
    value=html.unescape(html.unescape(_clean(value)))
    value=EMOJI_RE.sub("",value)
    value=re.sub(r"<[^>]+>","",value)
    value=_strip_contacts(value)
    return _clean(value).strip(" .;,:—–-")


def _fact_priority(label: str) -> int:
    low=label.lower()
    priorities=(
        (("грузопод", "ёмкост", "емкост", "мощност", "напряж", "длина вил", "высота подъ", "масса", "скорост"),0),
        (("назначение",),1),
        (("производитель","бренд"),2),
        (("категория",),3),
        (("модель","артикул"),4),
        (("гарантия","доставка"),5),
    )
    for tokens,p in priorities:
        if any(t in low for t in tokens): return p
    return 6


def _natural_fact_fragment(label: str, value: str) -> str:
    low=label.lower().replace("ё","е")
    mapping=(
        (("грузопод",),"грузоподъёмностью"),
        (("емкост",),"ёмкостью"),
        (("мощност",),"мощностью"),
        (("напряж",),"напряжением"),
        (("скорост",),"скоростью"),
        (("высота подъ", "высота подь"),"высотой подъёма"),
        (("масса", "вес"),"массой"),
    )
    for tokens,word in mapping:
        if any(t in low for t in tokens): return f"{word} {value}"
    if "длина вил" in low: return f"с длиной вил {value}"
    return ""


def suggest_description_details(row: dict[str, Any]) -> dict[str, Any]:
    """Generate an explainable Description from facts already found on this exact page."""
    if row.get("page_type") == "technical" or row.get("indexable") != "yes":
        return {"description":"","used_facts":[],"notes":["Генерация отключена для технической или неиндексируемой страницы"]}
    title=_clean(row.get("title","")); h1=_clean(row.get("h1",""))
    subject=h1 or title
    if not subject:
        return {"description":"","used_facts":[],"notes":["На странице не найден H1 или Title"]}
    subject=re.sub(r"\s*[|—–]\s*[^|—–]{2,55}$","",subject).strip()
    product=row.get("product_data") or {}
    used=[]; notes=[]
    candidate=subject
    if row.get("page_type") == "product" and product:
        facts=[f for f in product.get("facts",[]) if isinstance(f,dict)]
        cleaned=[]; seen=set()
        for f in sorted(facts,key=lambda x:_fact_priority(str(x.get("label","")))):
            label=_clean(str(f.get("label",""))); value=_safe_fact_value(str(f.get("value","")))
            if not value or len(value)>185: continue
            key=(label.lower(),value.lower())
            if key in seen: continue
            seen.add(key); cleaned.append({"label":label,"value":value,"source":f.get("source","")})
        # Build the first sentence from explicit high-value characteristics in natural Russian.
        natural=[]
        for fact in cleaned:
            if fact["label"].lower() in {"модель","артикул","категория","назначение","производитель","бренд","гарантия","доставка"}: continue
            fragment=_natural_fact_fragment(fact["label"],fact["value"])
            if fragment and len(fragment)<=58:
                natural.append((fact,fragment))
            if len(natural)>=3: break
        if natural:
            fragments=[x[1] for x in natural]
            if len(fragments)==1: joined=fragments[0]
            elif len(fragments)==2: joined=f"{fragments[0]} и {fragments[1]}"
            else: joined=f"{fragments[0]}, {fragments[1]} и {fragments[2]}"
            proposal=f"{subject} {joined}"
            if len(proposal)<=158:
                candidate=proposal; used.extend(x[0] for x in natural)
        # An explicit purpose sentence may supplement the characteristics, never inferred by the generator.
        purpose=next((f for f in cleaned if f["label"].lower()=="назначение"),None)
        if purpose:
            purpose_text=purpose["value"]
            purpose_text=re.sub(r"^"+re.escape(subject)+r"\s*[-—–:]?\s*","",purpose_text,flags=re.I)
            proposal=f"{candidate}. {purpose_text}"
            if len(proposal)<=158:
                candidate=proposal; used.append(purpose)
        maker=next((f for f in cleaned if f["label"].lower() in {"производитель","бренд"}),None)
        if maker and maker not in used and len(candidate)<125:
            proposal=f"{candidate}. Производитель — {maker['value']}"
            if len(proposal)<=158:
                candidate=proposal; used.append(maker)
        # If recognized natural facts were unavailable, use one explicit short characteristic rather than inventing copy.
        if not used:
            for fact in cleaned:
                if fact["label"].lower() in {"модель","артикул","категория"}: continue
                fragment=f"{fact['label'].rstrip(':')}: {fact['value']}"
                proposal=f"{subject}. {fragment}"
                if len(fragment)<=72 and len(proposal)<=158:
                    candidate=proposal; used.append(fact); break
        category=next((f for f in cleaned if f["label"].lower()=="категория"),None)
        if len(candidate)<110 and category and category not in used:
            proposal=f"{candidate}. Категория — {category['value']}"
            if len(proposal)<=158:
                candidate=proposal; used.append(category)
    else:
        body=_clean(row.get("body_excerpt",""))
        for part in re.split(r"(?<=[.!?])\s+",body):
            part=_strip_contacts(_clean(part))
            if 35<=len(part)<=180 and subject.lower() not in part.lower() and not EMOJI_RE.search(part):
                proposal=f"{subject}. {part}"
                if len(proposal)<=160:
                    candidate=proposal; used.append({"label":"Текст страницы","value":part,"source":"текст страницы"})
                    break
    candidate=html.unescape(html.unescape(candidate)); candidate=EMOJI_RE.sub("",candidate); candidate=re.sub(r"<[^>]+>","",candidate); candidate=_strip_contacts(candidate); candidate=_clean(candidate)
    candidate=candidate.rstrip(" ,;:")
    if candidate and candidate[-1] not in ".!?": candidate += "."
    if len(candidate)>160:
        candidate=candidate[:157].rsplit(" ",1)[0].rstrip(" ,;:")+"…"
    if len(candidate)<120:
        notes.append("На странице недостаточно коротких подтверждённых фактов, поэтому вариант короче ориентира 120–160 символов")
    if row.get("page_type")=="product" and not used:
        notes.append("Не удалось безопасно добавить характеристики: использовано только название товара")
    return {"description":candidate,"used_facts":used,"notes":notes}


def suggest_description(row: dict[str, Any]) -> str:
    return suggest_description_details(row)["description"]
