from __future__ import annotations

import pytest

from jarvis.core.cowork.collaborators import CollaboratorRole
from jarvis.core.exceptions import CyclicDependencyError
from jarvis.core.planning.dependencies import (
    estimate_sequential_dependencies,
    topological_waves,
)
from jarvis.core.planning.types import PlanTask


def _task(task_id: str, depends_on: tuple[str, ...] = ()) -> PlanTask:
    return PlanTask(
        id=task_id, description="x", collaborator=CollaboratorRole.PLANNER, depends_on=depends_on
    )


def test_estimate_sequential_dependencies_chains_by_default() -> None:
    result = estimate_sequential_dependencies(["a", "b", "c"])
    assert result == [(), ("0",), ("1",)]


def test_estimate_sequential_dependencies_breaks_on_independence_marker() -> None:
    result = estimate_sequential_dependencies(["a", "meanwhile do b", "c"])
    assert result == [(), (), ("1",)]


def test_topological_waves_single_chain() -> None:
    tasks = [_task("0"), _task("1", ("0",)), _task("2", ("1",))]
    assert topological_waves(tasks) == [["0"], ["1"], ["2"]]


def test_topological_waves_detects_independent_tasks() -> None:
    tasks = [_task("0"), _task("1"), _task("2", ("0", "1"))]
    assert topological_waves(tasks) == [["0", "1"], ["2"]]


def test_topological_waves_raises_on_cycle() -> None:
    tasks = [_task("0", ("1",)), _task("1", ("0",))]
    with pytest.raises(CyclicDependencyError):
        topological_waves(tasks)


def test_topological_waves_empty_plan() -> None:
    assert topological_waves([]) == []
