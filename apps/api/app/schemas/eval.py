from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConfigSummary(BaseModel):
    config: str
    generated: int
    scored: int
    resolved: int
    resolve_rate: float | None
    ci95: list[float] | None
    infra_failures: list[str]
    with_patch: int
    localized: int
    avg_tokens: float
    avg_llm_calls: float
    avg_seconds: float


class EvalResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    instance_id: str
    repo: str
    config: str
    agent_run_id: int | None
    status: str
    target_path: str | None
    gold_path: str | None
    localized: bool | None
    resolved: bool | None
    score_detail: dict | None
    error: str | None
    llm_calls: int
    prompt_tokens: int
    completion_tokens: int
    seconds: float
    patch: str | None


class EvalRunSummary(BaseModel):
    id: int
    name: str
    dataset: str
    model: str
    instance_count: int
    configs: list[str]
    settings: dict
    created_at: datetime
    summary: list[ConfigSummary]


class EvalRunDetail(EvalRunSummary):
    instance_ids: list[str]
    results: list[EvalResultResponse]
