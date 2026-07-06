import time
import uuid
from contextlib import asynccontextmanager

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from control_plane.auth import require_api_key, require_registration_token, log_effective_auth_config
from control_plane.config import settings
from control_plane.control_plane import ControlPlane
from control_plane.models import CallRequest, RegisterRequest
from control_plane.observability import (
    configure_logging,
    get_logger,
    trace_context,
    HTTP_REQUESTS_TOTAL,
    HTTP_REQUEST_DURATION,
)
from control_plane.scheduler import PeriodicJob

configure_logging()
logger = get_logger("control_plane.main")

cp = ControlPlane(host=settings.HOST)

_jobs: list[PeriodicJob] = []

logger.info(f"API KEY: {settings.API_KEY}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_effective_auth_config()

    _jobs.append(PeriodicJob("periodic_scan", settings.SCAN_INTERVAL_SECONDS, lambda: cp.discover_agents(trigger="periodic")))
    _jobs.append(PeriodicJob("health_check", settings.HEALTH_CHECK_INTERVAL_SECONDS, cp.health_check))
    if settings.FEDERATION_PEERS:
        _jobs.append(PeriodicJob("federation_sync", settings.SCAN_INTERVAL_SECONDS, cp.sync_federation))

    for job in _jobs:
        job.start()

    logger.info("control_plane_lifespan_started")
    yield
    for job in _jobs:
        job.stop()
    logger.info("control_plane_lifespan_stopped")


app = FastAPI(title="A2A Control Plane", version="0.2.0", lifespan=lifespan)


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex[:16]
    with trace_context(trace_id=trace_id, span=f"{request.method} {request.url.path}"):
        start = time.time()
        response = await call_next(request)
        duration = time.time() - start

        HTTP_REQUESTS_TOTAL.labels(
            method=request.method, path=request.url.path, status=response.status_code
        ).inc()
        HTTP_REQUEST_DURATION.labels(method=request.method, path=request.url.path).observe(duration)

        response.headers["X-Trace-Id"] = trace_id
        logger.info(
            "http_request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(duration * 1000, 2),
            },
        )
        return response


@app.get("/health")
def health():
    """Unauthenticated liveness probe -- deliberately excludes any agent
    data so it's safe to expose to infra health checkers without a key."""
    return {"status": "ok", "service": settings.SERVICE_NAME}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/agents", dependencies=[Depends(require_api_key)])
def list_agents(include_unavailable: bool = True):
    return {"agents": cp.get_alive_agents(include_unavailable=include_unavailable)}


@app.post("/agents/register", dependencies=[Depends(require_registration_token)])
def register_agent(req: RegisterRequest):
    try:
        profile = cp.register_agent(url=req.url, name=req.name, metadata=req.metadata)
        return {"status": "registered", "agent": profile.to_public_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/agents/{agent_name}", dependencies=[Depends(require_api_key)])
def deregister_agent(agent_name: str):
    existed = cp.deregister_agent(agent_name)
    if not existed:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    return {"status": "deregistered", "agent": agent_name}


@app.post("/call", dependencies=[Depends(require_api_key)])
def call_agent(req: CallRequest):
    try:
        result = cp.call_agent(req.agent_name, req.input_data, max_retries=req.max_retries)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/refresh", dependencies=[Depends(require_api_key)])
def refresh():
    cp.discover_agents(trigger="manual")
    return {"status": "rescanned"}


@app.post("/health-check", dependencies=[Depends(require_api_key)])
def trigger_health_check():
    cp.health_check()
    return {"status": "health_checked"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7000)
