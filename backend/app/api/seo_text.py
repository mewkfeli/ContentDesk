from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.seo_text_tz import analyze_text, audit_style, fetch_page_text, normalize_analysis_text, parse_tz

router = APIRouter(prefix="/seo-text", tags=["seo-text"])


class ParsePayload(BaseModel):
    tz_text: str = Field(min_length=20)


class AnalyzePayload(BaseModel):
    tz_text: str = Field(min_length=20)
    text: str = ""
    use_wordforms: bool = True


class StyleAuditPayload(BaseModel):
    tz_text: str = Field(min_length=20)
    text: str = ""
    use_wordforms: bool = True


class FetchPayload(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


@router.post("/parse")
def parse(payload: ParsePayload):
    result = parse_tz(payload.tz_text)
    if not result["keywords"]:
        raise HTTPException(status_code=422, detail="Не удалось найти блок «Добавьте в текст ключевые слова». Проверь формат ТЗ.")
    return result


@router.post("/analyze")
def analyze(payload: AnalyzePayload):
    tz = parse_tz(payload.tz_text)
    if not tz["keywords"]:
        raise HTTPException(status_code=422, detail="Не удалось распознать ключевые слова в ТЗ.")
    return {"tz": tz, "analysis": analyze_text(tz, payload.text, payload.use_wordforms)}


@router.post("/style-audit")
def style_audit(payload: StyleAuditPayload):
    tz = parse_tz(payload.tz_text)
    if not tz["keywords"]:
        raise HTTPException(status_code=422, detail="Не удалось распознать ключевые слова в ТЗ.")
    return {"tz": tz, "style": audit_style(tz, payload.text, payload.use_wordforms)}


@router.post("/check")
def check(payload: AnalyzePayload):
    tz = parse_tz(payload.tz_text)
    if not tz["keywords"]:
        raise HTTPException(status_code=422, detail="Не удалось распознать ключевые слова в ТЗ.")
    normalized_text = normalize_analysis_text(payload.text)
    return {
        "tz": tz,
        "normalized_text": normalized_text,
        "analysis": analyze_text(tz, normalized_text, payload.use_wordforms),
        "style": audit_style(tz, normalized_text, payload.use_wordforms),
    }


@router.post("/fetch")
def fetch(payload: FetchPayload):
    try:
        return fetch_page_text(payload.url)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Не удалось получить текст страницы: {exc}")
