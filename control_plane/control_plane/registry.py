import difflib
import threading
import time

import requests

from control_plane.config import settings
from control_plane.models import AgentProfile, AgentStatus, AgentMetadataIn, DiscoverySource
from control_plane.observability import get_logger, DISCOVERY_RUNS_TOTAL, AGENTS_REGISTERED

logger = get_logger("control_plane.registry")


class AgentRegistry:
    def __init__(self):
        self._agents: dict[str, AgentProfile] = {}
        self._lock = threading.RLock()

    @staticmethod
    def sanitize_name(name: str) -> str:
        return name.lower().strip().replace(" ", "_").replace("-", "_")

    def scan(self, trigger: str = "manual"):
        logger.info("discovery_scan_started", extra={"trigger": trigger})
        DISCOVERY_RUNS_TOTAL.labels(trigger=trigger).inc()
        found = 0

        if settings.SCAN_TARGETS:
            for target in settings.SCAN_TARGETS:
                url = f"http://{target}"
                card = self._fetch_card(url)
                if card is None:
                    continue
                name = self.sanitize_name(card.get("name", target))
                self._upsert(name, url, card, DiscoverySource.SCAN)
                found += 1
                logger.info("discovery_agent_found", extra={"agent": name, "url": url})
        else:
            for port in range(settings.PORT_RANGE_START, settings.PORT_RANGE_END + 1):
                url = f"http://{settings.HOST}:{port}"
                card = self._fetch_card(url)
                if card is None:
                    continue
                name = self.sanitize_name(card.get("name", f"agent_{port}"))
                self._upsert(name, url, card, DiscoverySource.SCAN)
                found += 1
                logger.info("discovery_agent_found", extra={"agent": name, "url": url})

        logger.info("discovery_scan_completed", extra={"trigger": trigger, "found": found})
        self._refresh_gauge()

    def _fetch_card(self, base_url: str) -> dict | None:
        try:
            resp = requests.get(
                f"{base_url}/.well-known/agent-card.json",
                timeout=settings.SCAN_TIMEOUT_SECONDS,
            )
            if resp.status_code != 200:
                return None
            return resp.json()
        except Exception:
            return None

    def register(self, url: str, name: str | None = None, metadata: AgentMetadataIn | None = None) -> AgentProfile:
        url = url.rstrip("/")
        card = self._fetch_card(url)
        if card is None:
            raise ValueError(f"Could not fetch agent card from {url}/.well-known/agent-card.json")

        resolved_name = self.sanitize_name(name or card.get("name", url))
        profile = self._upsert(resolved_name, url, card, DiscoverySource.REGISTRATION, metadata=metadata)
        logger.info("agent_registered", extra={"agent": resolved_name, "url": url})
        self._refresh_gauge()
        return profile

    def deregister(self, name: str) -> bool:
        name = self.sanitize_name(name)
        with self._lock:
            existed = self._agents.pop(name, None) is not None
        if existed:
            logger.info("agent_deregistered", extra={"agent": name})
            self._refresh_gauge()
        return existed

    def _upsert(self, name, url, card, source, metadata: AgentMetadataIn | None = None) -> AgentProfile:
        with self._lock:
            existing = self._agents.get(name)
            if existing is not None:
                existing.url = url
                existing.card = card
                if metadata is not None:
                    existing.metadata = metadata
                return existing

            profile = AgentProfile(name=name, url=url, card=card, source=source, metadata=metadata)
            self._agents[name] = profile
            return profile

    def get(self, name: str) -> AgentProfile | None:
        return self._agents.get(self.sanitize_name(name))

    def find_best_match(self, agent_name: str) -> AgentProfile:
        name = self.sanitize_name(agent_name)
        with self._lock:
            available = list(self._agents.keys())

        if name in available:
            return self._agents[name]

        matches = difflib.get_close_matches(name, available, n=1, cutoff=0.5)
        if matches:
            logger.warning("fuzzy_match_used", extra={"requested": agent_name, "matched": matches[0]})
            return self._agents[matches[0]]

        raise ValueError(f"Agent '{agent_name}' not found")

    def list_all(self, include_unavailable: bool = True) -> list[AgentProfile]:
        with self._lock:
            profiles = list(self._agents.values())
        if include_unavailable:
            return profiles
        return [p for p in profiles if p.status != AgentStatus.UNAVAILABLE]

    def report_success(self, name: str, latency_ms: float):
        profile = self._agents.get(self.sanitize_name(name))
        if profile:
            profile.record_success(latency_ms, settings.FAILURE_THRESHOLD)
            self._refresh_gauge()

    def report_failure(self, name: str, error: str):
        profile = self._agents.get(self.sanitize_name(name))
        if profile:
            prev_status = profile.status
            profile.record_failure(error, settings.FAILURE_THRESHOLD)
            if prev_status != AgentStatus.UNAVAILABLE and profile.status == AgentStatus.UNAVAILABLE:
                logger.warning(
                    "agent_marked_unavailable",
                    extra={"agent": name, "consecutive_failures": profile.health.consecutive_failures},
                )
            self._refresh_gauge()

    def health_check_all(self):
        with self._lock:
            profiles = list(self._agents.values())

        for profile in profiles:
            card = self._fetch_card(profile.url)
            if card is not None:
                profile.card = card
                if profile.status != AgentStatus.AVAILABLE:
                    logger.info("agent_recovered", extra={"agent": profile.name})
                profile.health.consecutive_failures = 0
                profile.health.last_seen = time.time()
                profile.status = AgentStatus.AVAILABLE
            else:
                profile.record_failure("health_check_unreachable", settings.FAILURE_THRESHOLD)

        self._refresh_gauge()

    def _refresh_gauge(self):
        counts: dict[str, int] = {}
        with self._lock:
            for profile in self._agents.values():
                counts[profile.status.value] = counts.get(profile.status.value, 0) + 1
        for status in AgentStatus:
            AGENTS_REGISTERED.labels(status=status.value).set(counts.get(status.value, 0))

    def sync_peers(self):
        if not settings.FEDERATION_PEERS:
            return

        for peer_base_url in settings.FEDERATION_PEERS:
            try:
                resp = requests.get(
                    f"{peer_base_url}/agents",
                    headers={"X-API-Key": settings.API_KEY},
                    timeout=settings.SCAN_TIMEOUT_SECONDS * 4,
                )
                if resp.status_code != 200:
                    logger.warning("federation_peer_error", extra={"peer": peer_base_url, "status": resp.status_code})
                    continue

                for agent in resp.json().get("agents", []):
                    federated_name = f"peer__{self.sanitize_name(peer_base_url)}__{agent['name']}"
                    card = {"name": agent["name"], "description": agent.get("description"), "skills": agent.get("skills")}
                    self._upsert(federated_name, agent["url"], card, DiscoverySource.FEDERATION)

                logger.info("federation_sync_ok", extra={"peer": peer_base_url})
            except Exception as e:
                logger.warning("federation_peer_unreachable", extra={"peer": peer_base_url, "error": str(e)})

        self._refresh_gauge()
