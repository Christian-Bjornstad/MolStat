from molstat.modules import DEFAULT_UNITS, UnitRegistry
from molstat.progress import RunProgress, progress_context
from molstat.system import MolStatSystem


def test_all_emits_one_plan_and_finishes_each_capability_before_next_unit():
    events = []
    system = MolStatSystem.__new__(MolStatSystem)
    system.units = UnitRegistry((DEFAULT_UNITS.require('hemato'), DEFAULT_UNITS.require('solide')))
    calls = []
    def run(unit, kind):
        calls.append((unit, kind))
        if kind == 'backlog':
            raise ValueError('PRIVATE sample text must never appear')
        return {'rows': 3}
    system._run_capability = run
    with progress_context(events.append):
        results = system.run_all(('hemato', 'solide'))
    assert events[0] == RunProgress(stage='planned', total=4)
    assert [e.stage for e in events] == ['planned', 'started', 'finished', 'started', 'failed', 'started', 'finished', 'started', 'failed']
    assert [(e.unit_key, e.job_kind) for e in events if e.stage == 'started'] == calls
    assert results[1].error is not None and results[2].error is None
    assert 'PRIVATE' not in repr(events)


def test_bad_progress_observer_cannot_break_the_run():
    from molstat.progress import emit_progress
    def broken(event):
        raise RuntimeError('UI unavailable')
    with progress_context(broken):
        emit_progress('hemato', 'statistics', 'processing')
