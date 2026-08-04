from __future__ import annotations

import pytest

from jarvis.core.exceptions import CyclicWorkflowError
from jarvis.core.workflow.dependencies import topological_waves
from jarvis.core.workflow.types import WorkflowStep


def test_sequential_steps_form_one_wave_each() -> None:
    steps = [
        WorkflowStep(id="a", name="A", action="x.y"),
        WorkflowStep(id="b", name="B", action="x.y", depends_on=("a",)),
        WorkflowStep(id="c", name="C", action="x.y", depends_on=("b",)),
    ]
    assert topological_waves(steps) == [["a"], ["b"], ["c"]]


def test_independent_steps_share_a_wave() -> None:
    steps = [
        WorkflowStep(id="a", name="A", action="x.y"),
        WorkflowStep(id="b", name="B", action="x.y"),
        WorkflowStep(id="c", name="C", action="x.y", depends_on=("a", "b")),
    ]
    waves = topological_waves(steps)
    assert waves == [["a", "b"], ["c"]]


def test_cycle_raises() -> None:
    steps = [
        WorkflowStep(id="a", name="A", action="x.y", depends_on=("b",)),
        WorkflowStep(id="b", name="B", action="x.y", depends_on=("a",)),
    ]
    with pytest.raises(CyclicWorkflowError):
        topological_waves(steps)


def test_empty_steps_produce_no_waves() -> None:
    assert topological_waves([]) == []
