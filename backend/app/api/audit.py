from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.seo_audit import audit_page

router = APIRouter(prefix="/audit", tags=["SEO audit"])


class PageAuditRequest(BaseModel):
    url: str = Field(min_length=3, max_length=2048)


@router.post("/page")
async def page_audit(payload: PageAuditRequest):
    try:
        return await audit_page(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
