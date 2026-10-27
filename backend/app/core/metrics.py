"""Prometheus metrics (served at /metrics), readable by Prometheus, Grafana or Google Cloud Monitoring."""

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest


class Metrics:
    def __init__(self) -> None:
        # One registry per app instance, so tests can build many apps without name clashes.
        self.registry = CollectorRegistry()
        self.http_requests = Counter(
            "sokokali_http_requests_total", "HTTP requests", ["method", "route", "status"], registry=self.registry
        )
        self.http_latency = Histogram(
            "sokokali_http_request_duration_seconds",
            "HTTP request latency",
            ["route"],
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
            registry=self.registry,
        )
        self.chat_replies = Counter(
            "sokokali_chat_replies_total", "Chat replies by engine and intent", ["engine", "intent"], registry=self.registry
        )
        self.live_events = Counter("sokokali_live_events_total", "Live viewer events", ["kind"], registry=self.registry)
        self.live_queue = Gauge("sokokali_live_queue_size", "Comments waiting for an answer", registry=self.registry)
        self.ws_clients = Gauge("sokokali_ws_clients", "Connected live-feed clients", registry=self.registry)
        self.broadcast_running = Gauge("sokokali_broadcast_running", "1 when the broadcast is running", registry=self.registry)
        self.broadcast_errors = Gauge("sokokali_broadcast_errors", "Errors since the broadcast started", registry=self.registry)

    def render(self) -> bytes:
        return generate_latest(self.registry)
