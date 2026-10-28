import threading

import pytest

from axibridge.render_work import RenderCancelled, RenderWork, checkpoint


def test_checkpoint_is_noop_outside_scope_and_cancel_reaches_worker():
    work = RenderWork()
    checkpoint()
    entered = threading.Event()
    proceed = threading.Event()
    result = []

    def worker():
        try:
            with work.scope():
                entered.set()
                proceed.wait(2)
                checkpoint()
        except RenderCancelled:
            result.append("cancelled")

    thread = threading.Thread(target=worker)
    thread.start()
    assert entered.wait(2)
    work.cancel()
    proceed.set()
    thread.join(2)
    assert result == ["cancelled"]


def test_scope_started_during_mutation_is_already_cancelled():
    work = RenderWork()
    with work.mutation():
        with pytest.raises(RenderCancelled):
            with work.scope():
                pass
    with work.scope():
        checkpoint()


def test_scope_cleanup_after_exception_and_nested_mutations():
    work = RenderWork()
    with pytest.raises(RuntimeError):
        with work.scope():
            raise RuntimeError("boom")
    work.cancel()
    with work.mutation(), work.mutation():
        with pytest.raises(RenderCancelled):
            with work.scope():
                pass
    with work.scope():
        checkpoint()


def test_replacement_cancels_only_same_lane_and_preserves_current_owner():
    work = RenderWork()
    with work.scope(('client-a', 'fill')) as old:
        with work.scope(('client-b', 'fill')) as other:
            with work.scope() as ordinary:
                with work.scope(('client-a', 'fill')) as current:
                    assert old.is_set()
                    assert not other.is_set() and not ordinary.is_set() and not current.is_set()
                assert not other.is_set() and not ordinary.is_set()


def test_queued_lane_is_replaced_and_old_cleanup_keeps_new_owner():
    work = RenderWork()
    gate = threading.Lock()
    first_registered, second_registered, first_done = (threading.Event() for _ in range(3))
    results = []
    def reader(registered, done=None):
        try:
            with work.scope(('tab', 'fill')):
                registered.set()
                with gate:
                    checkpoint()
                results.append('completed')
        except RenderCancelled:
            results.append('cancelled')
        finally:
            if done: done.set()
    with gate:
        one = threading.Thread(target=reader, args=(first_registered, first_done))
        one.start(); assert first_registered.wait(2)
        two = threading.Thread(target=reader, args=(second_registered,))
        two.start(); assert second_registered.wait(2)
    assert first_done.wait(2)
    one.join(2); two.join(2)
    assert sorted(results) == ['cancelled', 'completed']
    assert not work._events and not work._lanes
