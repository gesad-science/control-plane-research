import contextvars
import json
import logging
import time
import uuid
from contextlib import contextmanager

from prometheus_client import Counter, Histogram, Gauge

from control_plane.config import settings

_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="-")
_span_var: contextvars.ContextVar[str] = contextvars.ContextVar("span", default="-")


def new_trace_id() -> str:
    return uuid.uuid4().hex[:16]


def get_trace_id() -> str:
    return _trace_id_var.get()


@contextmanager
def trace_context(trace_id: str = None, span: str = "-"):
    token_t = _trace_id_var.set(trace_id or new_trace_id())
    token_s = _span_var.set(span)
    start = time.time()
    try:
        yield _trace_id_var.get()
    finally:
        duration_ms = (time.time() - start) * 1000
        logging.getLogger("control_plane.trace").debug(
            "span_end", extra={"span_duration_ms": round(duration_ms, 2)}
        )
        _trace_id_var.reset(token_t)
        _span_var.reset(token_s)

class JSONFormatter(logging.Formatter):
    RESERVED = {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "service": settings.SERVICE_NAME,
            "message": record.getMessage(),
            "trace_id": _trace_id_var.get(),
            "span": _span_var.get(),
        }
        for key, value in record.__dict__.items():
            if key not in self.RESERVED and not key.startswith("_"):
                try:
                    json.dumps(value)
                    payload[key] = value
                except TypeError:
                    payload[key] = str(value)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


class PlainFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        return f"[trace={_trace_id_var.get()}] {base}"


def configure_logging():
    root = logging.getLogger()
    root.setLevel(settings.LOG_LEVEL)

    handler = logging.StreamHandler()
    if settings.JSON_LOGS:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(PlainFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    root.handlers = [handler]

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers = [handler]
        logging.getLogger(name).propagate = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


HTTP_REQUESTS_TOTAL = Counter(
    "control_plane_http_requests_total",
    "Total HTTP requests received by the control plane",
    ["method", "path", "status"],
)

HTTP_REQUEST_DURATION = Histogram(
    "control_plane_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
)

AGENT_INVOCATIONS_TOTAL = Counter(
    "control_plane_agent_invocations_total",
    "Total agent invocations, labeled by outcome",
    ["agent", "outcome"],
)

AGENT_INVOCATION_DURATION = Histogram(
    "control_plane_agent_invocation_duration_seconds",
    "Latency of agent invocations (including retries)",
    ["agent"],
)

AGENT_INVOCATION_RETRIES = Counter(
    "control_plane_agent_invocation_retries_total",
    "Number of retry attempts performed against an agent",
    ["agent"],
)

DISCOVERY_RUNS_TOTAL = Counter(
    "control_plane_discovery_runs_total",
    "Number of discovery scans executed",
    ["trigger"],  
)

AGENTS_REGISTERED = Gauge(
    "control_plane_agents_registered",
    "Current number of agents known to the control plane, by status",
    ["status"],
)
