from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import AgentRun


class AgentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_run(
        self,
        agent_name: str,
        stage: str,
        input_json: dict,
        output_json: dict,
        is_valid: bool,
        user_id: int | None = None,
    ) -> AgentRun:
        run = AgentRun(
            user_id=user_id,
            agent_name=agent_name,
            stage=stage,
            input_json=input_json,
            output_json=output_json,
            is_valid=is_valid,
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        return run
