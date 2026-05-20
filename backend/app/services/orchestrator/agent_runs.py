from collections.abc import Callable

from app.services.agents import AgentValidationError


async def log_agent_run(
    agent_repo,
    *,
    agent_name: str,
    stage: str,
    input_json: dict,
    output_json: dict,
    is_valid: bool,
    user_id: int,
) -> None:
    await agent_repo.log_run(
        agent_name=agent_name,
        stage=stage,
        input_json=input_json,
        output_json=output_json,
        is_valid=is_valid,
        user_id=user_id,
    )


async def validate_and_log(
    agent_repo,
    *,
    validator_name: str,
    input_json: dict,
    payload: dict,
    user_id: int,
    validate_fn: Callable[[dict], dict],
) -> dict:
    try:
        validated = validate_fn(payload)
    except AgentValidationError as exc:
        await log_agent_run(
            agent_repo,
            agent_name=validator_name,
            stage="validate",
            input_json=input_json,
            output_json={"error": str(exc)},
            is_valid=False,
            user_id=user_id,
        )
        raise
    await log_agent_run(
        agent_repo,
        agent_name=validator_name,
        stage="validate",
        input_json=input_json,
        output_json=validated,
        is_valid=True,
        user_id=user_id,
    )
    return validated
