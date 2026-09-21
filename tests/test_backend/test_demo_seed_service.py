"""Shared demo seed service regression tests."""

from app import db
from app.models.task import MonitorTask
from app.models.user import User
from app.services.demo_seed_service import seed_demo_data
from app.services.pipeline_service import PipelineService


def test_seed_demo_data_is_idempotent(app, monkeypatch):
    with app.app_context():
        user = User.query.filter_by(username="admin").first()
        if user is None:
            user = User(username="admin", email="seed@example.com", role="admin")
            user.set_password("test-password")
            db.session.add(user)
            db.session.commit()

    pipeline_calls = []

    def fake_pipeline(current_app, task_id, days, limit):
        pipeline_calls.append((task_id, days, limit))
        with current_app.app_context():
            task = db.session.get(MonitorTask, task_id)
            task.data_count = 42
            task.status = "active"
            db.session.commit()

    monkeypatch.setattr(PipelineService, "run_task_pipeline", fake_pipeline)

    first = seed_demo_data(app)
    second = seed_demo_data(app)

    assert len(first) == len(second) == 1
    assert first[0].created is True
    assert first[0].data_count == 42
    assert second[0].created is False
    assert second[0].task_id == first[0].task_id
    assert pipeline_calls == [(first[0].task_id, 14, 600)]
