from __future__ import annotations

from tests.log.test_production_runtime import _initialize, _prepare, _proposal


def test_prepare_lineage_work_is_proportional_to_selected_not_history():
    _backend, log = _initialize("p08-lineage-index")
    for index in range(24):
        proposal = _proposal(
            log,
            learner=f"history-{index}",
            sequence=1,
            values=[float(index), float(index + 1)],
        )
        log.commit_prepared(_prepare(log, proposal, [float(index), float(index + 1)]))

    selected = _proposal(
        log,
        learner="selected",
        sequence=1,
        values=[25.0, 26.0],
    )
    _prepare(log, selected, [25.0, 26.0])
    assert log.last_prepare_lineage_checks == 1
