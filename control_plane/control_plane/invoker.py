import json
import random
import time
import uuid

import requests

from control_plane.config import settings
from control_plane.models import AgentProfile
from control_plane.observability import (
    get_logger,
    AGENT_INVOCATIONS_TOTAL,
    AGENT_INVOCATION_DURATION,
    AGENT_INVOCATION_RETRIES,
    trace_context,
)

logger = get_logger("control_plane.invoker")


class TransientError(Exception):
    """Raised for errors worth retrying (timeouts, connection errors, 5xx)."""


class PermanentError(Exception):
    """Raised for errors that a retry cannot fix (4xx, malformed response)."""


def _build_payload(input_data) -> dict:
    input_text = json.dumps(input_data) if isinstance(input_data, dict) else str(input_data)
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": input_text}],
                "messageId": str(uuid.uuid4()),
            },
            "metadata": {},
        },
    }


def _single_attempt(profile: AgentProfile, payload: dict) -> dict:
    try:
        response = requests.post(profile.url, json=payload, timeout=settings.CALL_TIMEOUT_SECONDS)
    except requests.exceptions.Timeout as e:
        raise TransientError(f"timeout: {e}")
    except requests.exceptions.ConnectionError as e:
        raise TransientError(f"connection_error: {e}")
    except Exception as e:
        raise TransientError(f"request_failed: {e}")

    if 500 <= response.status_code < 600:
        raise TransientError(f"http_{response.status_code}")
    if 400 <= response.status_code < 500:
        raise PermanentError(f"http_{response.status_code}: {response.text[:200]}")

    raw = response.text.strip()
    if not raw:
        raise TransientError("empty_response")

    try:
        data = response.json()
    except Exception:
        raise PermanentError(f"invalid_json: {raw[:200]}")

    if "error" in data:
        raise PermanentError(f"jsonrpc_error: {data['error']}")

    result = data.get("result")
    try:
        text = result["message"]["parts"][0]["text"]
    except Exception:
        text = result

    return {"status": "ok", "result": text}


def call_with_retry(profile: AgentProfile, input_data, max_retries: int | None = None) -> dict:
    max_retries = settings.MAX_RETRIES if max_retries is None else max_retries
    payload = _build_payload(input_data)

    with trace_context(span=f"call_agent:{profile.name}") as trace_id:
        logger.info("agent_call_started", extra={"agent": profile.name, "max_retries": max_retries})
        start = time.time()
        attempt = 0
        last_error = None

        while attempt <= max_retries:
            attempt_start = time.time()
            try:
                result = _single_attempt(profile, payload)
                latency_ms = (time.time() - attempt_start) * 1000
                total_latency_ms = (time.time() - start) * 1000

                AGENT_INVOCATIONS_TOTAL.labels(agent=profile.name, outcome="success").inc()
                AGENT_INVOCATION_DURATION.labels(agent=profile.name).observe(total_latency_ms / 1000)
                logger.info(
                    "agent_call_succeeded",
                    extra={"agent": profile.name, "attempt": attempt + 1, "latency_ms": round(latency_ms, 2)},
                )
                result["trace_id"] = trace_id
                result["attempts"] = attempt + 1
                return result, latency_ms

            except PermanentError as e:
                last_error = str(e)
                logger.warning("agent_call_permanent_error", extra={"agent": profile.name, "error": last_error})
                break

            except TransientError as e:
                last_error = str(e)
                attempt += 1
                if attempt > max_retries:
                    logger.warning(
                        "agent_call_exhausted_retries",
                        extra={"agent": profile.name, "attempts": attempt, "error": last_error},
                    )
                    break

                AGENT_INVOCATION_RETRIES.labels(agent=profile.name).inc()
                backoff = min(
                    settings.RETRY_BACKOFF_MAX_SECONDS,
                    settings.RETRY_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)),
                )
                backoff += random.uniform(0, backoff * 0.25)  # jitter
                logger.info(
                    "agent_call_retrying",
                    extra={"agent": profile.name, "attempt": attempt, "backoff_seconds": round(backoff, 2), "error": last_error},
                )
                time.sleep(backoff)

        total_latency_ms = (time.time() - start) * 1000
        AGENT_INVOCATIONS_TOTAL.labels(agent=profile.name, outcome="failure").inc()
        AGENT_INVOCATION_DURATION.labels(agent=profile.name).observe(total_latency_ms / 1000)
        attempts_made = attempt if attempt > 0 else 1
        return {
            "status": "error",
            "message": last_error,
            "attempts": attempts_made,
            "trace_id": trace_id,
        }, total_latency_ms
