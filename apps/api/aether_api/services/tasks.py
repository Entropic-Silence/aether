from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from croniter import croniter
from sqlalchemy import select

from ..db import SessionLocal
from ..orm import Conversation, Message, MessageBlock, Model, Provider, Task, TaskRun


def parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def compute_next_run(task: Task, now: datetime) -> datetime | None:
    if task.schedule_type == "one_time":
        try:
            target = parse_dt(task.schedule_value)
        except ValueError:
            return None
        return target if target > now else None
    if task.schedule_type == "interval":
        try:
            seconds = int(task.schedule_value)
        except ValueError:
            return None
        base = task.last_run or now
        nxt = base + timedelta(seconds=seconds)
        return nxt if nxt > now else now
    if task.schedule_type == "cron":
        try:
            return croniter(task.schedule_value, now).get_next(datetime).astimezone(timezone.utc)
        except Exception:  # noqa: BLE001
            return None
    return None


async def execute_task(task_id: str) -> None:
    async with SessionLocal() as db:
        task = await db.get(Task, task_id)
        if not task or not task.enabled:
            return
        model = None
        if task.model_id:
            model = await db.get(Model, task.model_id)
        if model is None:
            model = await db.scalar(select(Model).where(Model.enabled.is_(True), Model.is_default.is_(True)).limit(1))
        if model is None:
            model = await db.scalar(select(Model).where(Model.enabled.is_(True)).limit(1))
        provider = await db.get(Provider, model.provider_id) if model else None

        run_row = TaskRun(task_id=task.id, status="running")
        db.add(run_row)
        await db.commit()
        await db.refresh(run_row)

        now = datetime.now(timezone.utc)
        task.last_run = now
        if task.schedule_type == "one_time":
            task.enabled = False
            task.next_run = None
        else:
            task.next_run = compute_next_run(task, now)
        await db.commit()

        if not provider:
            run_row.status = "failed"
            run_row.error = "No model/provider available"
            run_row.finished_at = datetime.now(timezone.utc)
            await db.commit()
            return

        conv = Conversation(workspace_id=task.workspace_id, user_id=task.user_id,
                            project_id=task.project_id, title=f"Task: {task.name or task.prompt[:40]}",
                            mode="chat")
        db.add(conv)
        await db.flush()
        user_msg = Message(conversation_id=conv.id, role="user")
        db.add(user_msg)
        await db.flush()
        db.add(MessageBlock(message_id=user_msg.id, seq=0, type="text", data={"text": task.prompt}))

        from ..adapters import build_adapter

        adapter = build_adapter(provider)
        try:
            resp = await asyncio.wait_for(adapter.chat(
                [
                    {"role": "system", "content": "You are running a scheduled task. Complete it fully and concisely."},
                    {"role": "user", "content": task.prompt},
                ],
                model_id=model.model_id,
                generation=model.generation_defaults or None,
                extra_body=model.extra_body or None,
            ), timeout=600)
            text = ((resp.get("choices") or [{}])[0].get("message") or {}).get("content", "")
        except Exception as e:  # noqa: BLE001
            text = ""
            run_row.status = "failed"
            run_row.error = str(e)[:500]
        else:
            run_row.status = "completed"
        finally:
            await adapter.aclose()

        if text:
            assistant_msg = Message(conversation_id=conv.id, parent_id=user_msg.id, role="assistant",
                                    model_id=model.id, status="completed")
            db.add(assistant_msg)
            await db.flush()
            db.add(MessageBlock(message_id=assistant_msg.id, seq=0, type="markdown", data={"text": text}))
            conv.current_leaf_id = assistant_msg.id

        run_row.conversation_id = conv.id
        run_row.result_summary = text[:500]
        run_row.finished_at = datetime.now(timezone.utc)
        await db.commit()


async def scheduler_loop(interval_s: float = 30.0) -> None:
    """Background loop that fires due tasks."""
    while True:
        try:
            now = datetime.now(timezone.utc)
            async with SessionLocal() as db:
                rows = await db.execute(
                    select(Task).where(Task.enabled.is_(True), Task.next_run.is_not(None))
                )
                due = [t.id for t in rows.scalars().all()
                       if t.next_run and t.next_run <= now]
            for task_id in due:
                asyncio.create_task(execute_task(task_id))
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(interval_s)
