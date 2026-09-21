import pytest
from app.worker import Worker
from app.providers import demo_providers
from tests.conftest import SimulatedCrash

def test_demo_scenarios(store, db):
    provs = demo_providers()
    thread1 = store.create_thread("22CS045")
    run1 = store.enqueue(thread1, "I need to raise a plumbing complaint in my room and please text me.", "mock")
    Worker(store, db, provs).run_once()
    assert store.get_run(run1)["status"] == "succeeded"
    assert db.count("complaint") == 2
    assert db.count("notification") == 1

    thread2 = store.create_thread("22IT017")
    run2 = store.enqueue(thread2, "Can I raise a fan complaint?", "mock")
    Worker(store, db, provs).run_once()
    assert store.get_run(run2)["status"] == "succeeded"
    assert db.count("complaint") == 2 # Did not raise due to warnings limit

def test_crash_recovery(store, db, clock):
    provs = demo_providers()
    thread = store.create_thread("22CS045")
    run = store.enqueue(thread, "I need to raise a plumbing complaint in my room and please text me.", "mock")

    real_once = db.once
    def crash_after_raise(key, tool_name, effect):
        result = real_once(key, tool_name, effect)
        if tool_name == "raise_complaint":
            raise SimulatedCrash()
        return result
    db.once = crash_after_raise

    with pytest.raises(SimulatedCrash):
        Worker(store, db, provs, worker_id="A", lease_seconds=10).run_once()

    assert db.count("complaint") == 2 # 1 seed + 1 new
    assert db.count("notification") == 0 # crashed before notify

    db.once = real_once
    clock.advance(20) # lease expires

    Worker(store, db, provs, worker_id="B").run_once()
    assert store.get_run(run)["status"] == "succeeded"
    assert db.count("complaint") == 2 # Idempotent, no new complaint
    assert db.count("notification") == 1 # Now notified
