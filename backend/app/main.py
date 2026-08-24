from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.projects import router as projects_router
from app.api.audit import router as audit_router
from app.api.images import router as images_router
from app.api.tasks import router as tasks_router
from app.api.site_audit import router as site_audit_router
from app.api.internal_linking import router as internal_linking_router
from app.api.content import router as content_router
from app.api.assistant import router as assistant_router
from app.api.work_plan import router as work_plan_router
from app.api.system import router as system_router
from app.api.search import router as search_router
from app.api.overview import router as overview_router
from app.api.jobs import router as jobs_router
from app.api.indexing import router as indexing_router
from app.api.meta_descriptions import router as meta_descriptions_router
from app.api.seo_text import router as seo_text_router
from app.db.database import init_db
from app.services.project_memory import seed_starter_context, backfill_current_state
from app.services.background_jobs import mark_interrupted_jobs
from app.logging_setup import logger


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    seed_starter_context()
    backfill_current_state()
    mark_interrupted_jobs()
    yield


app = FastAPI(
    title="ContentDesk API",
    version="2.8.0",
    description="Локальный API для ContentDesk",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects_router, prefix="/api")
app.include_router(audit_router, prefix="/api")
app.include_router(images_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(site_audit_router, prefix="/api")
app.include_router(internal_linking_router, prefix="/api")
app.include_router(content_router, prefix="/api")
app.include_router(assistant_router, prefix="/api")
app.include_router(work_plan_router, prefix="/api")
app.include_router(system_router, prefix="/api")
app.include_router(search_router, prefix="/api")
app.include_router(overview_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
app.include_router(indexing_router, prefix="/api")
app.include_router(meta_descriptions_router, prefix="/api")
app.include_router(seo_text_router, prefix="/api")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Внутренняя ошибка ContentDesk. Открой Настройки → Диагностика."})


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "ContentDesk API", "version": "2.8.0"}
