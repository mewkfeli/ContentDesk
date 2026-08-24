from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services.image_audit import audit_images, audit_site_images
from app.services.image_processor import get_job_file, get_job_zip, process_images

router = APIRouter(prefix="/images", tags=["Images"])


class ImageAuditRequest(BaseModel):
    url: str = Field(min_length=3, max_length=2048)


class ImageSiteAuditRequest(BaseModel):
    url: str = Field(min_length=3, max_length=2048)
    sitemap_url: str = Field(default="", max_length=2048)
    limit: int = Field(default=30, ge=1, le=100)


@router.post("/process")
async def image_process(
    files: list[UploadFile] = File(...),
    max_width: int = Form(1920),
    output_format: str = Form("webp"),
    quality: int = Form(82),
    name_template: str = Form("image-{n}"),
):
    try:
        return await process_images(
            files,
            max_width=max_width,
            output_format=output_format,
            quality=quality,
            name_template=name_template,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/download/{job_id}")
def download_images(job_id: str):
    try:
        zip_path = get_job_zip(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Архив не найден") from exc
    return FileResponse(zip_path, filename="contentdesk-images.zip", media_type="application/zip")


@router.get("/download/{job_id}/{filename}")
def download_image(job_id: str, filename: str):
    try:
        path = get_job_file(job_id, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Изображение не найдено") from exc
    return FileResponse(path, filename=path.name)


@router.post("/audit")
async def image_audit(payload: ImageAuditRequest):
    try:
        return await audit_images(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/site-audit")
async def image_site_audit(payload: ImageSiteAuditRequest):
    try:
        return await audit_site_images(payload.url, payload.sitemap_url, payload.limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
