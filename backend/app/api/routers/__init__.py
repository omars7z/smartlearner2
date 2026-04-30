from fastapi import APIRouter

from .auth import router as auth_router
from .curriculum import router as curriculum_router
from .exams import router as exams_router
from .lessons import router as lessons_router
from .placement import router as placement_router
from .qa import router as qa_router
from .resources import router as resources_router
from .syllabus import router as syllabus_router
from .usage import router as usage_router


def build_api_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    router.include_router(auth_router)
    router.include_router(placement_router)
    router.include_router(curriculum_router)
    router.include_router(syllabus_router)
    router.include_router(lessons_router)
    router.include_router(qa_router)
    router.include_router(exams_router)
    router.include_router(resources_router)
    router.include_router(usage_router)
    return router
