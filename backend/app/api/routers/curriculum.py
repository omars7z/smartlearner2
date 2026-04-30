from fastapi import APIRouter

from app.core.deep_learning_curriculum import curriculum_payload as deep_learning_curriculum_payload
from app.core.py4e_curriculum import curriculum_payload

router = APIRouter(tags=["curriculum"])


@router.get("/curriculum/py4e")
async def get_py4e_curriculum() -> dict:
    return curriculum_payload()


@router.get("/curriculum/deep-learning")
async def get_deep_learning_curriculum() -> dict:
    return deep_learning_curriculum_payload()
