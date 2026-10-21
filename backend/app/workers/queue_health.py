"""Expiring worker presence; a broker being reachable is not proof of a consumer."""
import json
from time import monotonic

import redis
from celery import signals

from app.core_config import get_settings

PREFIX = "dashboard:worker-queues:"
_queues: dict[str, list[str]] = {}
_published: dict[str, float] = {}


def _client():
    return redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=1, socket_timeout=1,
                               decode_responses=True)


def _publish(hostname):
    if hostname not in _queues or monotonic() - _published.get(hostname, -100) < 20:
        return
    try:
        with _client() as client:
            client.set(PREFIX + hostname, json.dumps(_queues[hostname]), ex=90)
        _published[hostname] = monotonic()
    except redis.RedisError:
        pass  # A failed heartbeat cannot mark a worker healthy.


def _ready(sender=None, **kwargs):
    if sender is not None:
        _queues[sender.hostname] = [queue.name for queue in sender.task_consumer.queues]
        _publish(sender.hostname)


def _heartbeat(sender=None, **kwargs):
    if sender is not None:
        _publish(sender.eventer.hostname)


def _shutdown(sender=None, **kwargs):
    hostname = getattr(sender, "hostname", None)
    if hostname:
        try:
            with _client() as client:
                client.delete(PREFIX + hostname)
        except redis.RedisError:
            pass
        _queues.pop(hostname, None)
        _published.pop(hostname, None)


def monitor_queue_status():
    try:
        with _client() as client:
            consumers = []
            for key in client.scan_iter(match=PREFIX + "*", count=100):
                queues = client.get(key)
                if queues and "monitor" in json.loads(queues):
                    consumers.append(key.removeprefix(PREFIX))
        return {"status": "available" if consumers else "missing", "consumers": sorted(consumers)}
    except (redis.RedisError, ValueError, TypeError):
        return {"status": "unavailable", "consumers": []}


def install():
    signals.worker_ready.connect(_ready, weak=False, dispatch_uid="dashboard-queue-ready")
    signals.heartbeat_sent.connect(_heartbeat, weak=False, dispatch_uid="dashboard-queue-heartbeat")
    signals.worker_shutdown.connect(_shutdown, weak=False, dispatch_uid="dashboard-queue-shutdown")
