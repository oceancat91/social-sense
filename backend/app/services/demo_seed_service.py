"""Shared demo-data seeding used by local and container entry points."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app import db
from app.models.task import MonitorTask
from app.models.user import User
from app.services.pipeline_service import PipelineService


@dataclass(frozen=True)
class DemoEvent:
    """Configuration for one reproducible demo monitoring task."""

    keyword: str
    platform: str = "all"
    days: int = 14
    limit: int = 600


@dataclass(frozen=True)
class DemoSeedResult:
    """Outcome returned to command-line wrappers for display."""

    task_id: int
    keyword: str
    data_count: int
    created: bool


DEFAULT_DEMO_EVENTS = (
    DemoEvent(keyword="校园食品安全"),
)


def seed_demo_data(
    app,
    events: Iterable[DemoEvent] = DEFAULT_DEMO_EVENTS,
    *,
    username: str = "admin",
) -> list[DemoSeedResult]:
    """Create missing demo tasks and run the data pipeline exactly once per task."""
    results: list[DemoSeedResult] = []
    with app.app_context():
        db.create_all()
        user = User.query.filter_by(username=username).first()
        if user is None:
            raise RuntimeError(f"管理员账户不存在：{username}")

        for event in events:
            task = MonitorTask.query.filter_by(
                user_id=user.id,
                keywords=event.keyword,
                platform=event.platform,
            ).first()
            created = task is None
            if created:
                task = MonitorTask(
                    user_id=user.id,
                    keywords=event.keyword,
                    platform=event.platform,
                    status="collecting",
                )
                db.session.add(task)
                db.session.commit()
                PipelineService.run_task_pipeline(
                    app,
                    task.id,
                    days=event.days,
                    limit=event.limit,
                )

            db.session.expire_all()
            task = db.session.get(MonitorTask, task.id)
            results.append(
                DemoSeedResult(
                    task_id=task.id,
                    keyword=event.keyword,
                    data_count=task.data_count or 0,
                    created=created,
                )
            )
    return results
