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
