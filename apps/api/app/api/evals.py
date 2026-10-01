from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.eval import EvalRunDetail, EvalRunSummary
from app.services import evals as eval_service

router = APIRouter(tags=["evals"])


@router.get("/evals", response_model=list[EvalRunSummary])
def list_evals(db: DbSession, current_user: CurrentUser) -> list[EvalRunSummary]:
    """Benchmark runs (newest first) with per-config resolve rates."""
    return eval_service.list_eval_runs(db)


@router.get("/evals/{eval_id}", response_model=EvalRunDetail)
def get_eval(eval_id: int, db: DbSession, current_user: CurrentUser) -> EvalRunDetail:
    """One benchmark run: summary plus every (instance, config) result."""
    run = eval_service.get_eval_run(db, eval_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eval run not found")
    return run
