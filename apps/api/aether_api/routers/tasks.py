from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import get_current_user
from ..errors import NotFoundError, ValidationError_
from ..orm import Task, TaskRun, User
from ..services.tasks import compute_next_run, execute_task
from .deps_helper import workspace_id_for
from ..services.features import feature_dependency

router = APIRouter(prefix="/tasks", tags=["tasks"], dependencies=[Depends(feature_dependency("tasks"))])

SCHEDULE_TYPES = {"one_time", "interval", "cron"}


class TaskIn(BaseModel):
    name: str = ""
    prompt: str = Field(min_length=1, max_length=8000)
    schedule_type: str = "one_time"
    schedule_value: str = Field(min_length=1, max_length=200)
    timezone: str = "UTC"
    model_id: str | None = None
    project_id: str | None = None
    enabled: bool = True


class TaskPatch(BaseModel):
    name: str | None = None
    prompt: str | None = None
    schedule_type: str | None = None
    schedule_value: str | None = None
    timezone: str | None = None
    model_id: str | None = None
    project_id: str | None = None
    enabled: bool | None = None


def _to_out(t: Task) -> dict:
    return {
        "id": t.id, "name": t.name, "prompt": t.prompt,
        "schedule_type": t.schedule_type, "schedule_value": t.schedule_value,
        "timezone": t.timezone, "model_id": t.model_id, "project_id": t.project_id,
        "enabled": t.enabled, "last_run": t.last_run, "next_run": t.next_run,
        "created_at": t.created_at,
    }


def _validate_schedule(schedule_type: str, schedule_value: str) -> None:
    if schedule_type not in SCHEDULE_TYPES:
        raise ValidationError_(f"schedule_type must be one of {sorted(SCHEDULE_TYPES)}")
    if schedule_type == "interval":
        try:
            if int(schedule_value) <= 0:
                raise ValueError
        except ValueError:
            raise ValidationError_("interval schedule_value must be positive seconds")
    elif schedule_type == "cron":
        from croniter import croniter

        if not croniter.is_valid(schedule_value):
            raise ValidationError_("invalid cron expression")
    elif schedule_type == "one_time":
        try:
            datetime.fromisoformat(schedule_value)
        except ValueError:
            raise ValidationError_("one_time schedule_value must be an ISO datetime")


@router.get("")
async def list_tasks(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = await db.execute(select(Task).where(Task.user_id == user.id).order_by(Task.created_at.desc()))
    return [_to_out(t) for t in rows.scalars().all()]


@router.post("", status_code=201)
async def create_task(body: TaskIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    _validate_schedule(body.schedule_type, body.schedule_value)
    now = datetime.now(timezone.utc)
    t = Task(
        workspace_id=await workspace_id_for(db),
        user_id=user.id,
        name=body.name, prompt=body.prompt,
        schedule_type=body.schedule_type, schedule_value=body.schedule_value,
        timezone=body.timezone, model_id=body.model_id, project_id=body.project_id,
        enabled=body.enabled,
    )
    t.next_run = compute_next_run(t, now) if t.enabled else None
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return _to_out(t)


@router.patch("/{task_id}")
async def update_task(task_id: str, body: TaskPatch,
                      db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    t = await db.get(Task, task_id)
    if not t or t.user_id != user.id:
        raise NotFoundError("Task not found")
    data = body.model_dump(exclude_unset=True)
    st = data.get("schedule_type", t.schedule_type)
    sv = data.get("schedule_value", t.schedule_value)
    if "schedule_type" in data or "schedule_value" in data:
        _validate_schedule(st, sv)
    for k, v in data.items():
        setattr(t, k, v)
    t.next_run = compute_next_run(t, datetime.now(timezone.utc)) if t.enabled else None
    await db.commit()
    await db.refresh(t)
    return _to_out(t)


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    t = await db.get(Task, task_id)
    if not t or t.user_id != user.id:
        raise NotFoundError("Task not found")
    await db.delete(t)
    await db.commit()


@router.post("/{task_id}/run", status_code=202)
async def run_task_now(task_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    import asyncio

    t = await db.get(Task, task_id)
    if not t or t.user_id != user.id:
        raise NotFoundError("Task not found")
    asyncio.create_task(execute_task(task_id))
    return {"ok": True}


@router.get("/{task_id}/runs")
async def task_runs(task_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    t = await db.get(Task, task_id)
    if not t or t.user_id != user.id:
        raise NotFoundError("Task not found")
    rows = await db.execute(select(TaskRun).where(TaskRun.task_id == task_id).order_by(TaskRun.started_at.desc()).limit(50))
    return [
        {"id": r.id, "status": r.status, "conversation_id": r.conversation_id,
         "result_summary": r.result_summary, "error": r.error,
         "started_at": r.started_at, "finished_at": r.finished_at}
        for r in rows.scalars().all()
    ]
