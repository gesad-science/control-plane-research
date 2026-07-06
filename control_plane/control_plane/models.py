import statistics
import time
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator


class AgentStatus(str, Enum):
    AVAILABLE = "available"
    DEGRADED = "degraded"      
    UNAVAILABLE = "unavailable" 
    UNKNOWN = "unknown"         


class DiscoverySource(str, Enum):
    SCAN = "scan"
    REGISTRATION = "registration"
    FEDERATION = "federation"


class AgentMetadataIn(BaseModel):
    cost_per_call_usd: Optional[float] = None
    avg_resource_cpu_millicores: Optional[int] = None
    avg_resource_memory_mb: Optional[int] = None
    max_concurrency: Optional[int] = None
    tags: list[str] = Field(default_factory=list)
    owner: Optional[str] = None
    version: Optional[str] = None
    region: Optional[str] = None
    scaling_hint: dict[str, Any] = Field(default_factory=dict)


class RegisterRequest(BaseModel):
    name: Optional[str] = None
    url: str
    metadata: AgentMetadataIn = Field(default_factory=AgentMetadataIn)

    @field_validator("url")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")


class CallRequest(BaseModel):
    agent_name: str
    input_data: dict | str
    max_retries: Optional[int] = None


class LatencyStats(BaseModel):
    count: int = 0
    avg_ms: Optional[float] = None
    p95_ms: Optional[float] = None
    last_ms: Optional[float] = None


class HealthStats(BaseModel):
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    total_successes: int = 0
    total_failures: int = 0
    last_error: Optional[str] = None
    last_seen: Optional[float] = None  # unix timestamp, last successful contact


class AgentProfile:
    LATENCY_WINDOW = 50

    def __init__(
        self,
        name: str,
        url: str,
        card: dict,
        source: DiscoverySource,
        metadata: Optional[AgentMetadataIn] = None,
    ):
        self.name = name
        self.url = url
        self.card = card
        self.source = source
        self.metadata = metadata or AgentMetadataIn()
        self.status = AgentStatus.UNKNOWN
        self.health = HealthStats()
        self._latencies_ms: list[float] = []
        self.registered_at = time.time()

    def record_latency(self, latency_ms: float):
        self._latencies_ms.append(latency_ms)
        if len(self._latencies_ms) > self.LATENCY_WINDOW:
            self._latencies_ms.pop(0)

    def latency_stats(self) -> LatencyStats:
        if not self._latencies_ms:
            return LatencyStats()
        sorted_lat = sorted(self._latencies_ms)
        p95_index = max(0, int(len(sorted_lat) * 0.95) - 1)
        return LatencyStats(
            count=len(self._latencies_ms),
            avg_ms=round(statistics.fmean(self._latencies_ms), 2),
            p95_ms=round(sorted_lat[p95_index], 2),
            last_ms=round(self._latencies_ms[-1], 2),
        )

    def record_success(self, latency_ms: float, failure_threshold: int):
        self.record_latency(latency_ms)
        self.health.consecutive_failures = 0
        self.health.consecutive_successes += 1
        self.health.total_successes += 1
        self.health.last_seen = time.time()
        self.status = AgentStatus.AVAILABLE

    def record_failure(self, error: str, failure_threshold: int):
        self.health.consecutive_successes = 0
        self.health.consecutive_failures += 1
        self.health.total_failures += 1
        self.health.last_error = error
        if self.health.consecutive_failures >= failure_threshold:
            self.status = AgentStatus.UNAVAILABLE
        else:
            self.status = AgentStatus.DEGRADED

    def to_public_dict(self) -> dict:
        return {
            "name": self.name,
            "url": self.url,
            "description": self.card.get("description"),
            "skills": self.card.get("skills"),
            "status": self.status.value,
            "source": self.source.value,
            "health": self.health.model_dump(),
            "latency": self.latency_stats().model_dump(),
            "metadata": self.metadata.model_dump(),
            "registered_at": self.registered_at,
        }
