from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any

import httpx
from bs4 import BeautifulSoup

WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+(?:[/-][A-Za-zА-Яа-яЁё0-9]+)*", re.UNICODE)
SENTENCE_END_RE = re.compile(r"[.!?…]+")


@dataclass
class Token:
    raw: str
    norm: str
    stem: str
    start: int
    end: int
    index: int
    sentence: int


# Russian Porter-style stemmer for SEO word-form matching. Exact tokens are
# still preferred; stemming is only used when the TZ explicitly permits forms.
_RU_VOWELS = "аеиоуыэюя"
_ADJECTIVE = re.compile(r"(ее|ие|ые|ое|ими|ыми|ей|ий|ый|ой|ем|им|ым|ом|его|ого|ему|ому|их|ых|ую|юю|ая|яя|ою|ею)$")
_PARTICIPLE = re.compile(r"(ем|нн|вш|ющ|щ)$")
_PARTICIPLE_A = re.compile(r"(ивш|ывш|ующ)$")
_VERB = re.compile(r"(ила|ыла|ена|ейте|уйте|ите|или|ыли|ей|уй|ил|ыл|им|ым|ен|ило|ыло|ено|ят|ует|уют|ит|ыт|ены|ить|ыть|ишь|ую|ю)$")
_VERB_A = re.compile(r"(ла|на|ете|йте|ли|й|л|ем|н|ло|но|ет|ны|ть|ешь|нно)$")
_NOUN = re.compile(r"(иями|ями|ами|ией|иям|ием|иях|ев|ов|ие|ье|еи|ии|ей|ой|ий|й|иям|ям|ием|ем|ам|ом|о|у|ах|иях|ях|ы|ь|ию|ью|ю|ия|ья|я|а|евы|овы|е|и)$")
_PERF = re.compile(r"(ив|ивши|ившись|ыв|ывши|ывшись)$")
_PERF_A = re.compile(r"(в|вши|вшись)$")


def normalize_word(word: str) -> str:
    return word.lower().replace("ё", "е").strip("-–—_./\\'\"«»()[]{}")


def _rv(word: str) -> tuple[str, str]:
    for i, ch in enumerate(word):
        if ch in _RU_VOWELS:
            return word[: i + 1], word[i + 1 :]
    return word, ""


def stem_word(word: str) -> str:
    w = normalize_word(word)
    if len(w) <= 3 or not re.search(r"[а-я]", w):
        return w
    prefix, rv = _rv(w)
    if not rv:
        return w

    original_rv = rv
    m = _PERF.search(rv)
    if m:
        rv = rv[:m.start()]
    else:
        m = _PERF_A.search(rv)
        if m and m.start() > 0 and rv[m.start()-1] in "ая":
            rv = rv[:m.start()]
        else:
            rv = re.sub(r"(ся|сь)$", "", rv)
            before = rv
            rv = _ADJECTIVE.sub("", rv)
            if rv != before:
                before_part = rv
                rv = _PARTICIPLE_A.sub("", rv)
                if rv == before_part:
                    m2 = _PARTICIPLE.search(rv)
                    if m2 and m2.start() > 0 and rv[m2.start()-1] in "ая":
                        rv = rv[:m2.start()]
            else:
                before = rv
                rv = _VERB.sub("", rv)
                if rv == before:
                    m2 = _VERB_A.search(rv)
                    if m2 and m2.start() > 0 and rv[m2.start()-1] in "ая":
                        rv = rv[:m2.start()]
                    elif rv == before:
                        rv = _NOUN.sub("", rv)

    rv = re.sub(r"и$", "", rv)
    rv = re.sub(r"ость?$", "", rv)
    if rv.endswith("ейше"):
        rv = rv[:-4]
    if rv.endswith("нн"):
        rv = rv[:-1]
    rv = re.sub(r"ь$", "", rv)
    stemmed = prefix + rv
    return stemmed if len(stemmed) >= 3 else (prefix + original_rv)



def normalize_analysis_text(text: str) -> str:
    """Remove only blank/whitespace-only lines before SEO/editorial analysis.

    Non-empty lines are preserved verbatim and remain separated by a single newline.
    This intentionally does not trim, rewrite or join words, punctuation or keyword phrases.
    """
    if not text:
        return ""
    return "\n".join(line for line in text.splitlines() if line.strip())

def tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    sentence = 0
    last_end = 0
    for idx, match in enumerate(WORD_RE.finditer(text)):
        between = text[last_end:match.start()]
        if SENTENCE_END_RE.search(between):
            sentence += len(SENTENCE_END_RE.findall(between))
        raw = match.group(0)
        tokens.append(Token(raw, normalize_word(raw), stem_word(raw), match.start(), match.end(), idx, sentence))
        last_end = match.end()
    return tokens


def _phrase_tokens(phrase: str) -> list[str]:
    return [m.group(0) for m in WORD_RE.finditer(phrase)]


def _matches_phrase(tokens: list[Token], phrase: str, use_wordforms: bool = True) -> list[dict[str, Any]]:
    query = _phrase_tokens(phrase)
    if not query:
        return []
    qnorm = [normalize_word(x) for x in query]
    qstem = [stem_word(x) for x in query]
    size = len(query)
    matches: list[dict[str, Any]] = []
    for start in range(0, len(tokens) - size + 1):
        chunk = tokens[start:start + size]
        # A multi-word key must not cross a sentence boundary.
        if size > 1 and any(tok.sentence != chunk[0].sentence for tok in chunk[1:]):
            continue
        exact = all(tok.norm == qnorm[i] for i, tok in enumerate(chunk))
        morph = use_wordforms and all(tok.stem == qstem[i] for i, tok in enumerate(chunk))
        if not (exact or morph):
            continue
        matches.append({
            "start_token": chunk[0].index,
            "end_token": chunk[-1].index,
            "start_char": chunk[0].start,
            "end_char": chunk[-1].end,
            "sentence": chunk[0].sentence,
            "match_text": " ".join(t.raw for t in chunk),
            "exact": exact,
        })
    return matches


def parse_tz(tz_text: str) -> dict[str, Any]:
    clean = html.unescape(tz_text or "")

    def grab(pattern: str, default: str = "") -> str:
        m = re.search(pattern, clean, re.I | re.S)
        return m.group(1).strip() if m else default

    url = grab(r"\*\*URL:\*\*\s*\[?([^\]\s)]+)")
    if not url:
        m = re.search(r"https?://[^\s)\]]+", clean)
        url = m.group(0) if m else ""

    rec_words = rec_chars = found_words = found_chars = None
    m = re.search(
        r"Рекомендуемое\s+количество\s+слов:\*{0,2}\s*(\d+)\s*слов(?:\s*\((\d+)\s*символов\))?\s*-\s*найдено\s*:?\s*(\d+)\s*слов(?:\s*\((\d+)\s*символов\))?",
        clean, re.I,
    )
    if m:
        rec_words = int(m.group(1)); rec_chars = int(m.group(2)) if m.group(2) else None
        found_words = int(m.group(3)); found_chars = int(m.group(4)) if m.group(4) else None

    keyword_section = grab(r"Добавьте\s+в\s+текст\s+ключевые\s+слова\**\s*(.*?)(?=\n\s*\\?\?\*|\n\s*\*\s*можно|\n\s*\*\*Добавьте\s+в\s+текст\s+LSI|\n\s*Добавьте\s+в\s+текст\s+LSI)")
    if not keyword_section:
        keyword_section = grab(r"Добавьте\s+в\s+текст\s+ключевые\s+слова\s*(.*?)(?=Добавьте\s+в\s+текст\s+LSI)")

    keywords: list[dict[str, Any]] = []
    for line in keyword_section.splitlines():
        line = line.strip().lstrip("-*• ").strip()
        if not line:
            continue
        m = re.match(r"(.+?):\s*(\d+)\s*-\s*(\d+)(?:\s*\(\s*найдено\s*:\s*(\d+)\s*\))?\s*$", line, re.I)
        if m:
            keywords.append({
                "phrase": m.group(1).strip(),
                "min": int(m.group(2)),
                "max": int(m.group(3)),
                "found_in_source": int(m.group(4)) if m.group(4) else None,
            })

    lsi_section = grab(r"Добавьте\s+в\s+текст\s+LSI\**\s*(.*?)(?=\n\s*\\?\?\*|\n\s*\*\s*одного|\n\s*\*\*Структура\s+статьи|\n\s*Структура\s+статьи)")
    if not lsi_section:
        lsi_section = grab(r"Добавьте\s+в\s+текст\s+LSI\s*(.*?)(?=Структура\s+статьи)")
    lsi: list[str] = []
    for line in lsi_section.splitlines():
        raw_line = line.strip()
        if not raw_line or "одного вхождения достаточно" in raw_line.lower():
            continue
        item = raw_line.lstrip("-*• ").strip()
        if item and not item.startswith("\\"):
            lsi.append(item)

    main_keyword = grab(r"Главное\s+ключевое\s+слово:\*\*?\s*([^\n]+)") or grab(r"Главное\s+ключевое\s+слово:\s*([^\n]+)")
    main_keyword = main_keyword.strip("* ")

    extras_section = grab(r"Дополнительные\s+ключевые\s+слова:\*\*?\s*(.*)$") or grab(r"Дополнительные\s+ключевые\s+слова:\s*(.*)$")
    additional: list[str] = []
    for line in extras_section.splitlines():
        item = line.strip().lstrip("-*• ").strip()
        if item:
            additional.append(item)

    competitors: list[str] = []
    comp_section = grab(r"Конкуренты\*\*?\s*(.*?)(?=\n\s*\*\*Пример\s+Н1|\n\s*Пример\s+Н1)")
    for u in re.findall(r"https?://[^\s)\]]+", comp_section):
        competitors.append(u)

    return {
        "url": url,
        "recommended_words": rec_words,
        "recommended_chars": rec_chars,
        "source_found_words": found_words,
        "source_found_chars": found_chars,
        "keywords": keywords,
        "lsi": lsi,
        "main_keyword": main_keyword,
        "additional_keywords": additional,
        "competitors": competitors,
        "rules": {
            "independent_occurrences": True,
            "min_gap_words": 2,
            "multiword_no_sentence_break": True,
            "preserve_word_order": True,
            "wordforms_allowed": True,
        },
    }


def _reserve_independent_matches(tokens: list[Token], requirements: list[dict[str, Any]], use_wordforms: bool) -> tuple[dict[int, list[dict[str, Any]]], list[dict[str, Any]]]:
    # Longer keys are assigned first. Their token spans cannot then satisfy a shorter key.
    ranked = sorted(enumerate(requirements), key=lambda x: (-len(_phrase_tokens(x[1]["phrase"])), x[0]))
    occupied: set[int] = set()
    assigned: dict[int, list[dict[str, Any]]] = {i: [] for i in range(len(requirements))}
    all_assigned: list[dict[str, Any]] = []

    for original_index, req in ranked:
        for match in _matches_phrase(tokens, req["phrase"], use_wordforms):
            span = set(range(match["start_token"], match["end_token"] + 1))
            if span & occupied:
                continue
            enriched = {**match, "phrase": req["phrase"], "requirement_index": original_index}
            assigned[original_index].append(enriched)
            all_assigned.append(enriched)
            occupied |= span
    all_assigned.sort(key=lambda m: (m["start_token"], m["end_token"]))
    return assigned, all_assigned


def _snippet(text: str, start: int, end: int, radius: int = 70) -> str:
    left = max(0, start - radius); right = min(len(text), end + radius)
    value = re.sub(r"\s+", " ", text[left:right]).strip()
    return ("…" if left else "") + value + ("…" if right < len(text) else "")


def analyze_text(tz: dict[str, Any], text: str, use_wordforms: bool = True) -> dict[str, Any]:
    text = normalize_analysis_text(text)
    tokens = tokenize(text)
    requirements = tz.get("keywords") or []
    assigned, all_assigned = _reserve_independent_matches(tokens, requirements, use_wordforms)

    keyword_rows: list[dict[str, Any]] = []
    missing_total = excess_total = 0
    for idx, req in enumerate(requirements):
        matches = assigned.get(idx, [])
        count = len(matches)
        min_count, max_count = int(req.get("min", 0)), int(req.get("max", 0))
        if count < min_count:
            status = "missing"; delta = min_count - count; missing_total += delta
        elif count > max_count:
            status = "excess"; delta = count - max_count; excess_total += delta
        else:
            status = "ok"; delta = 0
        keyword_rows.append({
            **req,
            "count": count,
            "status": status,
            "delta": delta,
            "matches": [{**m, "snippet": _snippet(text, m["start_char"], m["end_char"])} for m in matches],
        })

    # Rule 2: assigned key occurrences must have at least two ordinary words between them.
    spacing_violations: list[dict[str, Any]] = []
    for prev, cur in zip(all_assigned, all_assigned[1:]):
        # Separate sentences are explicitly preferred by the source TZ and are safe.
        if prev.get("sentence") != cur.get("sentence"):
            continue
        gap = cur["start_token"] - prev["end_token"] - 1
        if gap < 2:
            spacing_violations.append({
                "first": prev["phrase"], "second": cur["phrase"], "gap_words": max(0, gap),
                "snippet": _snippet(text, prev["start_char"], cur["end_char"], 85),
            })

    lsi_rows = []
    for phrase in tz.get("lsi") or []:
        matches = _matches_phrase(tokens, phrase, use_wordforms)
        lsi_rows.append({"phrase": phrase, "count": len(matches), "found": bool(matches)})

    additional_rows = []
    for phrase in tz.get("additional_keywords") or []:
        matches = _matches_phrase(tokens, phrase, use_wordforms)
        additional_rows.append({"phrase": phrase, "count": len(matches), "found": bool(matches)})

    word_count = len(tokens)
    char_count = len(re.sub(r"\s+", " ", text).strip())
    rec_words = tz.get("recommended_words")
    rec_chars = tz.get("recommended_chars")
    word_delta = (rec_words - word_count) if rec_words is not None else None
    char_delta = (rec_chars - char_count) if rec_chars is not None else None

    missing_lsi = [x["phrase"] for x in lsi_rows if not x["found"]]
    issues: list[str] = []
    if missing_total:
        issues.append(f"Не хватает обязательных независимых вхождений: {missing_total}.")
    if excess_total:
        issues.append(f"Превышен максимум по ключам: {excess_total} лишних вхождений.")
    if spacing_violations:
        issues.append(f"Нарушено расстояние между вхождениями: {len(spacing_violations)} мест.")
    if missing_lsi:
        issues.append(f"Не использовано LSI: {len(missing_lsi)}.")
    if rec_words and word_count < max(1, int(rec_words * 0.85)):
        issues.append(f"Текст заметно короче рекомендации: {word_count} из {rec_words} слов.")

    plan: list[str] = []
    for row in keyword_rows:
        if row["status"] == "missing":
            plan.append(f"Добавить «{row['phrase']}» ещё {row['delta']} раз(а) как самостоятельное вхождение.")
        elif row["status"] == "excess":
            plan.append(f"Убрать/переформулировать «{row['phrase']}» минимум {row['delta']} раз(а).")
    if missing_lsi:
        plan.append("Добавить LSI по одному разу: " + ", ".join(missing_lsi) + ".")
    if spacing_violations:
        plan.append("Разнести отмеченные ключевые вхождения: между соседними должно быть минимум 2 других слова, лучше — разные предложения.")
    if word_delta is not None and word_delta > 0:
        plan.append(f"Увеличить объём примерно на {word_delta} слов до ориентира {rec_words} слов.")
    elif word_delta is not None and word_delta < -max(20, int((rec_words or 0) * .2)):
        plan.append(f"Текст длиннее ориентира примерно на {abs(word_delta)} слов; при сокращении не потерять обязательные вхождения.")

    return {
        "word_count": word_count,
        "char_count": char_count,
        "recommended_words": rec_words,
        "recommended_chars": rec_chars,
        "word_delta": word_delta,
        "char_delta": char_delta,
        "keywords": keyword_rows,
        "lsi": lsi_rows,
        "additional_keywords": additional_rows,
        "spacing_violations": spacing_violations,
        "summary": {
            "keywords_ok": sum(1 for x in keyword_rows if x["status"] == "ok"),
            "keywords_total": len(keyword_rows),
            "missing_occurrences": missing_total,
            "excess_occurrences": excess_total,
            "lsi_found": sum(1 for x in lsi_rows if x["found"]),
            "lsi_total": len(lsi_rows),
            "spacing_violations": len(spacing_violations),
            "ready": not issues,
        },
        "issues": issues,
        "plan": plan,
        "counting_note": "Ключи считаются независимо: совпадение, занятое более длинным ключом из ТЗ, не засчитывается как отдельное вхождение короткого ключа. Словоформы учитываются консервативной нормализацией; порядок слов сохраняется.",
    }


def fetch_page_text(url: str) -> dict[str, Any]:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ContentDesk/2.2; +local SEO audit)"}
    with httpx.Client(timeout=25.0, follow_redirects=True, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    # H1 входит в проверяемый SEO-текст по умолчанию. Забираем его отдельно,
    # затем удаляем h1 из тела, чтобы не получить двойное вхождение, если он
    # расположен внутри <main>/<article>.
    h1_tag = soup.find("h1")
    h1 = " ".join(h1_tag.stripped_strings).strip() if h1_tag else ""

    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
        tag.decompose()
    for tag in soup.find_all("h1"):
        tag.decompose()

    container = soup.find("main") or soup.find("article") or soup.body or soup
    body_text = "\n".join(x.strip() for x in container.stripped_strings if x.strip())
    text = "\n\n".join(x for x in (h1, body_text) if x)
    return {
        "requested_url": url,
        "final_url": str(response.url),
        "status_code": response.status_code,
        "h1": h1,
        "body_text": body_text,
        "text": text,
        "h1_included": bool(h1),
    }

# --- Editorial naturalness audit -----------------------------------------------
# Heuristic only: this does NOT decide whether AI wrote the text. It highlights
# patterns that make commercial/SEO copy feel mechanical, repetitive or unnatural.
_STYLE_MARKERS: list[tuple[str, str, str, str]] = [
    (r"\bв современном мире\b", "Клише", "high", "Убрать универсальную вводную и начать с конкретики по товару, услуге или задаче."),
    (r"\bне секрет, что\b", "Клише", "high", "Убрать стереотипную вводную и сразу сформулировать тезис."),
    (r"\bважно отметить\b", "Клише", "high", "Убрать вводную формулу и сразу дать факт."),
    (r"\bследует отметить\b", "Клише", "medium", "Убрать вводную формулу и сразу дать факт."),
    (r"\bподводя итоги\b", "Клише", "high", "Заменить конкретным выводом или убрать, если вывод уже очевиден."),
    (r"\bтаким образом\b", "Шаблонный вывод", "medium", "Заменить конкретным выводом или удалить связку."),
    (r"\bна сегодняшний день\b", "Канцелярская связка", "medium", "Если дата не важна, убрать эту конструкцию."),
    (r"\bисходя из вышеизложенного\b", "Чрезмерная формальность", "high", "Сказать вывод прямо, без канцелярской связки."),
    (r"\bв данном контексте\b", "Чрезмерная формальность", "medium", "Назвать конкретный контекст или убрать вводную конструкцию."),
    (r"\bв рамках (?:данного|настоящего)\b", "Чрезмерная формальность", "medium", "Сделать формулировку короче и конкретнее."),
    (r"\bдля удобства\b", "Шаблонная вводная", "medium", "Начать сразу с условия, возможности или действия без общей вводной."),
    (r"\bдля таких (?:позиций|случаев|задач) важно\b", "Шаблонная конструкция", "medium", "Убрать «важно» и сразу назвать требование или условие."),
    (r"\bэто помогает\b", "Шаблонная связка", "medium", "Назвать конкретный результат действия вместо общей связки."),
    (r"\bпроцесс .{0,45} включает\b", "Канцелярская конструкция", "medium", "По возможности заменить существительное действием: «при восстановлении очищают, проверяют…»."),
    (r"\bне только[^.!?]{0,90}\bно и\b", "Шаблонная конструкция", "low", "Проверить, можно ли сказать проще и короче."),
    (r"\bпозволяет\b", "Абстрактный глагол", "low", "По возможности назвать конкретный результат или действие."),
    (r"\bобеспечивает\b", "Абстрактный глагол", "low", "По возможности заменить конкретным действием или результатом."),
    (r"\bосуществляется\b", "Канцелярит", "medium", "Перестроить фразу в активный залог."),
    (r"\bпроизводится\b", "Канцелярит", "medium", "Перестроить фразу в активный залог, если смысл не пострадает."),
    (r"\bиспользуются\b", "Пассивная конструкция", "low", "Если возможно, назвать действующее лицо и использовать активный залог."),
    (r"\bявляется\b", "Связочный глагол", "low", "Проверить, можно ли сделать формулировку прямее."),
    (r"\bданн(?:ый|ая|ое|ые|ого|ому|ой|ых|ыми)\b", "Канцелярит", "medium", "Чаще всего заменить конкретным существительным или убрать."),
]
_GENERIC_OPENERS = {"также", "кроме", "при", "для", "это", "такая", "такой", "данный", "данная", "компания", "специалисты", "поставщики"}
_SEMANTIC_STOP = {
    "и", "в", "во", "на", "с", "со", "для", "по", "из", "а", "но", "к", "ко", "что", "как", "или", "при", "это",
    "также", "же", "то", "до", "от", "за", "под", "над", "у", "о", "об", "не", "ни", "бы", "ли", "который", "которая",
    "которые", "такой", "такая", "такие", "этот", "эта", "эти", "его", "ее", "их", "можно", "нужно", "важно",
}


def _sentences_for_style(text: str) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for match in re.finditer(r"[^.!?…]+(?:[.!?…]+|$)", text, re.S):
        raw = re.sub(r"\s+", " ", match.group(0)).strip()
        if not raw:
            continue
        words = WORD_RE.findall(raw)
        if words:
            values.append({"text": raw, "words": len(words), "start": match.start(), "end": match.end()})
    return values


def _paragraphs_for_style(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]


def _content_stems(sentence: str) -> set[str]:
    result: set[str] = set()
    for raw in WORD_RE.findall(sentence):
        norm = normalize_word(raw)
        if len(norm) <= 2 or norm in _SEMANTIC_STOP or norm.isdigit():
            continue
        stem = stem_word(norm)
        if len(stem) >= 3:
            result.add(stem)
    return result


def _semantic_similarity(a: str, b: str) -> float:
    sa, sb = _content_stems(a), _content_stems(b)
    if len(sa) < 3 or len(sb) < 3:
        return 0.0
    intersection = len(sa & sb)
    union = len(sa | sb)
    jaccard = intersection / union if union else 0.0
    containment = intersection / min(len(sa), len(sb))
    # Containment catches a short sentence that simply restates the longer one.
    return max(jaccard, containment * 0.86)


def audit_style(tz: dict[str, Any], text: str, use_wordforms: bool = True) -> dict[str, Any]:
    text = normalize_analysis_text(text)
    sentences = _sentences_for_style(text)
    paragraphs = _paragraphs_for_style(text)
    findings: list[dict[str, Any]] = []

    def add(kind: str, severity: str, title: str, snippet: str, recommendation: str, count: int = 1):
        findings.append({
            "kind": kind, "severity": severity, "title": title, "snippet": snippet,
            "recommendation": recommendation, "count": count,
        })

    lowered = normalize_word(text)
    for pattern, title, base_severity, recommendation in _STYLE_MARKERS:
        matches = list(re.finditer(pattern, lowered, re.I))
        if not matches:
            continue
        common = title in {"Абстрактный глагол", "Связочный глагол", "Пассивная конструкция"}
        if common and len(matches) < 2:
            continue
        severity = base_severity
        if len(matches) >= 3 and severity == "low":
            severity = "medium"
        elif len(matches) >= 3 and severity == "medium":
            severity = "high"
        first = matches[0]
        add("marker", severity, title, _snippet(text, first.start(), first.end(), 80), recommendation, len(matches))

    # Repeated first words / phrases at sentence starts.
    starts: dict[str, list[str]] = {}
    for sentence in sentences:
        ws = [normalize_word(x) for x in WORD_RE.findall(sentence["text"])[:2]]
        if not ws:
            continue
        key = " ".join(ws[:2]) if len(ws) > 1 else ws[0]
        starts.setdefault(key, []).append(sentence["text"])
    for key, vals in starts.items():
        if len(vals) >= 3 or (len(vals) >= 2 and key.split()[0] in _GENERIC_OPENERS):
            add("repetition", "medium", "Повтор начала предложений",
                " / ".join(v[:110] for v in vals[:3]),
                f"Разнообразить начало предложений; конструкция «{key}…» повторяется {len(vals)} раз(а).", len(vals))

    # Semantic repetition in neighboring sentences. This is lexical-semantic heuristic,
    # not an LLM judgment: high overlap of content stems suggests a restatement.
    semantic_pairs: list[tuple[int, float]] = []
    for i in range(len(sentences) - 1):
        score = _semantic_similarity(sentences[i]["text"], sentences[i + 1]["text"])
        if score >= 0.56:
            semantic_pairs.append((i, score))
    if semantic_pairs:
        i, similarity = max(semantic_pairs, key=lambda x: x[1])
        add("semantic_repetition", "high" if similarity >= 0.72 else "medium", "Семантический повтор",
            sentences[i]["text"][:180] + " / " + sentences[i + 1]["text"][:180],
            "Соседние предложения заметно пересекаются по смысловым словам. Проверить, несёт ли второе новую информацию; если нет — объединить или удалить повтор.",
            len(semantic_pairs))

    lengths = [s["words"] for s in sentences]
    if len(lengths) >= 5:
        avg = sum(lengths) / len(lengths)
        variance = sum((x - avg) ** 2 for x in lengths) / len(lengths)
        sd = variance ** 0.5
        if sd < 4.0:
            add("rhythm", "medium", "Слишком ровный ритм",
                f"Средняя длина предложения {avg:.1f} слова; разброс всего {sd:.1f}.",
                "Смешать короткие и более развёрнутые предложения, чтобы текст не звучал шаблонно.")
    long_sentences = [s for s in sentences if s["words"] >= 30]
    if long_sentences:
        add("readability", "medium", "Длинные предложения", long_sentences[0]["text"][:220],
            "Разделить самые длинные предложения, если это не ломает обязательное ключевое вхождение.", len(long_sentences))

    # Frequent connector words that can make generated prose repetitive.
    for connector in ("также", "при этом", "кроме того", "поэтому", "таким образом"):
        c = len(re.findall(rf"\b{re.escape(connector)}\b", lowered, re.I))
        if c >= 3:
            add("repetition", "medium", "Повтор связки", f"«{connector}» — {c} раз(а)",
                "Часть повторов убрать или заменить конкретной логической связью.", c)

    # Artificial liveliness: emojis/excessive exclamation marks in neutral B2B/SEO copy.
    emoji_matches = re.findall(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", text)
    exclamations = text.count("!")
    if emoji_matches:
        add("tone", "high" if len(emoji_matches) >= 3 else "medium", "Искусственная живость: эмодзи",
            f"Эмодзи в тексте: {len(emoji_matches)}.",
            "Для нейтрального коммерческого/SEO-текста убрать декоративные эмодзи, если они не предусмотрены стилем проекта.", len(emoji_matches))
    if exclamations >= 3:
        add("tone", "medium" if exclamations < 6 else "high", "Искусственная живость: восклицания",
            f"Восклицательных знаков: {exclamations}.",
            "Оставить восклицания только там, где эмоциональный тон действительно нужен.", exclamations)

    # Participial / adverbial-participial overload. Conservative suffix patterns to reduce false positives.
    participles = re.findall(r"\b[А-Яа-яЁё-]{4,}(?:ющ(?:ий|ая|ее|ие|его|ему|им|ими|их)|ащ(?:ий|ая|ее|ие|его|ему|им|ими|их)|ящ(?:ий|ая|ее|ие|его|ему|им|ими|их)|вш(?:ий|ая|ее|ие|его|ему|им|ими|их)|ем(?:ый|ая|ое|ые|ого|ому|ым|ыми|ых)|им(?:ый|ая|ое|ые|ого|ому|ым|ыми|ых))\b", text, re.I)
    gerunds = re.findall(r"\b[А-Яа-яЁё-]{4,}(?:вши|вшись|ившись|ывшись|учи|ючи)\b", text, re.I)
    # Also catch common -я gerunds only when preceded by a comma/start and followed by a dependent phrase.
    gerund_y = re.findall(r"(?:^|[,;])\s*([А-Яа-яЁё-]{5,}(?:ая|яя))\s+[А-Яа-яЁё]", text, re.I | re.M)
    gerunds.extend(gerund_y)
    complex_forms = participles + gerunds
    if len(complex_forms) >= 3:
        sample = ", ".join(complex_forms[:6])
        add("syntax", "medium" if len(complex_forms) < 6 else "high", "Много причастных и деепричастных оборотов",
            f"Найдено сложных глагольных форм: {len(complex_forms)}. Примеры: {sample}.",
            "Часть оборотов заменить простыми глагольными конструкциями. Особенно проверить предложения, где несколько оборотов идут подряд.", len(complex_forms))

    # Long em dash is fine in Russian, but frequent use can become a visible generative mannerism.
    em_dash_count = text.count("—")
    word_count = max(1, len(tokenize(text)))
    dashes_per_100 = em_dash_count * 100 / word_count
    if em_dash_count >= 3 and dashes_per_100 >= 1.0:
        add("punctuation", "low" if em_dash_count < 6 else "medium", "Много длинных тире",
            f"Длинное тире «—» встречается {em_dash_count} раз(а), примерно {dashes_per_100:.1f} на 100 слов.",
            "Тире само по себе нормально. Проверить только повторяющийся приём: часть конструкций можно заменить точкой, двоеточием, запятой или перестроить.", em_dash_count)

    # Repeated 3-word sequences outside SEO keyword phrases.
    tokens = [normalize_word(x) for x in WORD_RE.findall(text)]
    stop = {"и", "в", "на", "с", "для", "по", "из", "а", "к", "что", "как", "или", "при", "это", "также"}
    ngrams: dict[str, int] = {}
    for i in range(len(tokens) - 2):
        gram_tokens = tokens[i:i+3]
        if sum(1 for x in gram_tokens if x in stop) >= 2:
            continue
        gram = " ".join(gram_tokens)
        ngrams[gram] = ngrams.get(gram, 0) + 1
    protected_norms = {" ".join(normalize_word(x) for x in WORD_RE.findall(k.get("phrase", ""))) for k in tz.get("keywords", [])}
    repeats = [(g, c) for g, c in ngrams.items() if c >= 2 and g not in protected_norms]
    repeats.sort(key=lambda x: (-x[1], x[0]))
    if repeats:
        gram, count = repeats[0]
        add("repetition", "low", "Повтор словосочетания", f"«{gram}» — {count} раз(а)",
            "Проверить, нужен ли повтор по смыслу. SEO-ключи модуль в эту рекомендацию не включает.", count)

    # Paragraph regularity: many paragraphs with almost same word count often feels templated.
    para_lengths = [len(WORD_RE.findall(p)) for p in paragraphs]
    if len(para_lengths) >= 4:
        spread = max(para_lengths) - min(para_lengths)
        if spread <= 12:
            add("rhythm", "low", "Похожие по объёму абзацы",
                "Длины абзацев: " + ", ".join(map(str, para_lengths[:8])) + " слов.",
                "Если структура выглядит слишком механической, объединить или разбить часть абзацев по смыслу.")

    # Protect the actual keyword occurrences found by the same independent-counting engine.
    requirements = tz.get("keywords") or []
    assigned, _ = _reserve_independent_matches(tokenize(text), requirements, use_wordforms)
    protected: list[dict[str, Any]] = []
    for idx, req in enumerate(requirements):
        for m in assigned.get(idx, []):
            protected.append({
                "phrase": req["phrase"], "match_text": m["match_text"], "exact": m["exact"],
                "snippet": _snippet(text, m["start_char"], m["end_char"], 65),
            })

    # De-duplicate exact same title/snippet, then order by editorial priority.
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for f in findings:
        key = (f["title"], f["snippet"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(f)
    priority = {"high": 0, "medium": 1, "low": 2}
    findings = sorted(deduped, key=lambda x: (priority.get(x["severity"], 3), x["title"]))

    severity_weight = {"high": 11, "medium": 7, "low": 3}
    penalty = sum(severity_weight.get(x["severity"], 0) for x in findings)
    score = max(0, min(100, 100 - penalty))
    high = sum(1 for x in findings if x["severity"] == "high")
    medium = sum(1 for x in findings if x["severity"] == "medium")
    low = sum(1 for x in findings if x["severity"] == "low")

    top_rewrite = [x for x in findings if x["severity"] in {"high", "medium"}][:8]
    brief = [
        "Переработать черновик как редактор, а не механический перефразатор.",
        "Сохранить факты и смысл; не добавлять неподтверждённые характеристики, цены или обещания.",
        "Убрать клише, канцелярит, семантические повторы, одинаковые начала и монотонный ритм.",
        "Не перегружать текст причастными/деепричастными оборотами, длинными тире, эмодзи и восклицаниями.",
        "Не ломать обязательные SEO-вхождения и после правки обязательно повторно запустить проверку по ТЗ.",
    ]
    if findings:
        brief.append("Сначала исправить: " + "; ".join(x["title"] for x in findings[:6]) + ".")

    return {
        "score": score,
        "word_count": len(tokenize(text)),
        "sentence_count": len(sentences),
        "paragraph_count": len(paragraphs),
        "findings": findings,
        "rewrite_first": top_rewrite,
        "protected_keywords": protected,
        "brief": brief,
        "summary": {"high": high, "medium": medium, "low": low, "total": len(findings)},
        "note": "Это редакторская эвристика, а не детектор происхождения текста. Она оценивает естественность: клише, канцелярит, повторы, тон, синтаксис, ритм и пунктуационные привычки. Семантические повторы определяются приближённо по пересечению смысловых слов и требуют проверки редактором.",
    }
