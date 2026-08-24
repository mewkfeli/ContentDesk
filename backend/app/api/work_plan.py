from fastapi import APIRouter
from app.services.work_prioritizer import build_work_plan

router = APIRouter(prefix='/work-plan', tags=['Work plan'])

@router.get('')
def get_work_plan(project_id: int | None = None):
    return build_work_plan(project_id)
