from __future__ import annotations

import pytest

from jarvis.core.config.planning_config import PlanningConfig
from jarvis.core.cowork.models import CoworkTaskResponse
from jarvis.core.events import EventBus
from jarvis.core.planning.engine import PlanningEngine
from jarvis.core.planning.types import TaskStatus


@pytest.fixture
def engine() -> PlanningEngine:
    return PlanningEngine(PlanningConfig(max_retries=1, preview_task_threshold=3))


def test_create_plan_from_semicolon_request(engine: PlanningEngine) -> None:
    plan = engine.create_plan("research pricing; write a summary")
    assert [t.description for t in plan.tasks] == ["research pricing", "write a summary"]
    assert plan.tasks[0].status == TaskStatus.READY
    assert plan.tasks[1].status == TaskStatus.PENDING
    assert plan.tasks[1].depends_on == ("0",)


def test_create_plan_assigns_collaborators_via_keyword_routing(engine: PlanningEngine) -> None:
    plan = engine.create_plan("test this feature")
    assert plan.tasks[0].collaborator.value == "qa_engineer"


def test_create_plan_with_explicit_task_descriptions(engine: PlanningEngine) -> None:
    plan = engine.create_plan("do stuff", task_descriptions=["step one", "step two"])
    assert [t.description for t in plan.tasks] == ["step one", "step two"]


def test_single_task_plan_has_no_dependencies(engine: PlanningEngine) -> None:
    plan = engine.create_plan("say hello")
    assert len(plan.tasks) == 1
    assert plan.tasks[0].status == TaskStatus.READY


def test_plan_from_cowork_response_is_sequential_by_step_order(engine: PlanningEngine) -> None:
    response = CoworkTaskResponse(
        task_id="t1",
        summary="clean up",
        steps=[
            {"step_id": 1, "description": "list files", "action_type": "respond"},
            {"step_id": 2, "description": "delete old files", "action_type": "respond"},
        ],
    )
    plan = engine.plan_from_cowork_response(response)
    assert plan.plan_id == "t1"
    assert plan.tasks[1].depends_on == ("1",)


def test_parallel_groups_reflects_independence(engine: PlanningEngine) -> None:
    plan = engine.create_plan("research pricing; meanwhile check inventory")
    groups = engine.parallel_groups(plan)
    assert groups == [["0", "1"]]


def test_next_ready_tasks_only_returns_ready(engine: PlanningEngine) -> None:
    plan = engine.create_plan("a; then b")
    ready = engine.next_ready_tasks(plan)
    assert [t.id for t in ready] == ["0"]


def test_mark_done_unblocks_dependent_task(engine: PlanningEngine) -> None:
    plan = engine.create_plan("a; then b")
    engine.mark_in_progress(plan, "0")
    engine.mark_done(plan, "0", result="ok")
    assert plan.get_task("1").status == TaskStatus.READY


def test_mark_failed_skips_dependent_task(engine: PlanningEngine) -> None:
    plan = engine.create_plan("a; then b")
    engine.mark_in_progress(plan, "0")
    engine.mark_failed(plan, "0", "boom")
    assert plan.get_task("1").status == TaskStatus.SKIPPED
    assert plan.has_failed_tasks is True


def test_retry_failed_reopens_task_and_its_skipped_dependents(engine: PlanningEngine) -> None:
    plan = engine.create_plan("a; then b")
    engine.mark_in_progress(plan, "0")
    engine.mark_failed(plan, "0", "boom")
    assert plan.get_task("1").status == TaskStatus.SKIPPED

    retried = engine.retry_failed(plan, "0")

    assert retried is True
    assert plan.get_task("0").status == TaskStatus.READY
    assert plan.get_task("1").status == TaskStatus.PENDING  # waiting on 0 again, not stuck


def test_retry_failed_respects_max_attempts(engine: PlanningEngine) -> None:
    # max_retries=1 -> max_attempts=2: one real attempt + one retry
    plan = engine.create_plan("a")
    engine.mark_in_progress(plan, "0")  # attempts=1
    engine.mark_failed(plan, "0", "boom")
    assert engine.retry_failed(plan, "0") is True

    engine.mark_in_progress(plan, "0")  # attempts=2, at max
    engine.mark_failed(plan, "0", "boom again")
    assert engine.retry_failed(plan, "0") is False


def test_retry_non_failed_task_returns_false(engine: PlanningEngine) -> None:
    plan = engine.create_plan("a")
    assert engine.retry_failed(plan, "0") is False  # it's READY, not FAILED


def test_plan_is_not_complete_while_a_task_has_failed(engine: PlanningEngine) -> None:
    plan = engine.create_plan("a; then b")
    engine.mark_in_progress(plan, "0")
    engine.mark_failed(plan, "0", "boom")  # "1" becomes SKIPPED, but "0" itself is FAILED
    assert plan.is_complete is False
    assert plan.has_failed_tasks is True


def test_plan_is_complete_when_every_task_is_done_or_skipped(engine: PlanningEngine) -> None:
    plan = engine.create_plan("a; then b")
    engine.mark_in_progress(plan, "0")
    engine.mark_done(plan, "0", result="ok")
    engine.mark_in_progress(plan, "1")
    engine.mark_done(plan, "1", result="ok")
    assert plan.is_complete is True


def test_should_preview_true_for_large_plans(engine: PlanningEngine) -> None:
    plan = engine.create_plan("a; then b; then c; then d")
    assert engine.should_preview(plan) is True  # 4 tasks > threshold of 3


def test_should_preview_false_for_small_benign_plan(engine: PlanningEngine) -> None:
    plan = engine.create_plan("say hello")
    assert engine.should_preview(plan) is False


def test_should_preview_true_for_risky_keyword(engine: PlanningEngine) -> None:
    plan = engine.create_plan("delete the old backup files")
    assert engine.should_preview(plan) is True


def test_render_plan_includes_wave_and_status_info(engine: PlanningEngine) -> None:
    plan = engine.create_plan("a; then b")
    rendered = engine.render_plan(plan)
    assert "Wave 1" in rendered
    assert "Wave 2" in rendered
    assert "[ready] 0: a" in rendered


def test_events_published_on_plan_and_task_lifecycle() -> None:
    events = EventBus()
    received: list[str] = []
    for name in (
        "planning.plan_created",
        "planning.task_started",
        "planning.task_completed",
        "planning.task_failed",
        "planning.task_retrying",
    ):
        events.subscribe(name, lambda e, n=name: received.append(n))

    engine = PlanningEngine(PlanningConfig(max_retries=1), events=events)
    plan = engine.create_plan("a")
    engine.mark_in_progress(plan, "0")
    engine.mark_failed(plan, "0", "boom")
    engine.retry_failed(plan, "0")
    engine.mark_in_progress(plan, "0")
    engine.mark_done(plan, "0")

    assert received == [
        "planning.plan_created",
        "planning.task_started",
        "planning.task_failed",
        "planning.task_retrying",
        "planning.task_started",
        "planning.task_completed",
    ]
