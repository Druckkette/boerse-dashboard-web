from types import SimpleNamespace

import fakeredis

from app.workers import queue_health


def test_monitor_presence_requires_live_monitor_queue(monkeypatch):
    client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(queue_health, "_client", lambda: client)
    monkeypatch.setattr(queue_health, "_queues", {})
    monkeypatch.setattr(queue_health, "_published", {})
    assert queue_health.monitor_queue_status()["status"] == "missing"
    queue_health._ready(SimpleNamespace(hostname="main@audit", task_consumer=SimpleNamespace(queues=[SimpleNamespace(name="default")])))
    assert queue_health.monitor_queue_status()["status"] == "missing"
    queue_health._ready(SimpleNamespace(hostname="monitor@audit", task_consumer=SimpleNamespace(queues=[SimpleNamespace(name="monitor")])))
    assert queue_health.monitor_queue_status() == {"status": "available", "consumers": ["monitor@audit"]}
    client.expire(queue_health.PREFIX + "monitor@audit", -1)
    assert queue_health.monitor_queue_status()["status"] == "missing"


def test_broker_failure_is_not_reported_as_available(monkeypatch):
    import redis
    def unavailable():
        raise redis.ConnectionError("synthetic outage")
    monkeypatch.setattr(queue_health, "_client", unavailable)
    assert queue_health.monitor_queue_status() == {"status": "unavailable", "consumers": []}
