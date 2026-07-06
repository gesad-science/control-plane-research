from control_plane.config import settings
from control_plane.models import AgentMetadataIn
from control_plane.observability import get_logger
from control_plane.registry import AgentRegistry
from control_plane.invoker import call_with_retry

logger = get_logger("control_plane.core")


class ControlPlane:
    def __init__(self, host: str = None, run_initial_scan: bool = True):
        if host:
            settings.HOST = host

        self.registry = AgentRegistry()
        logger.info("control_plane_starting", extra={"scan_host": settings.HOST})

        if run_initial_scan:
            self.discover_agents()

        logger.info("control_plane_ready")

    # -- discovery -----------------------------------------------------
    def discover_agents(self, trigger: str = "startup"):
        self.registry.scan(trigger=trigger)

    def register_agent(self, url: str, name: str | None = None, metadata: AgentMetadataIn | None = None):
        return self.registry.register(url=url, name=name, metadata=metadata)

    def deregister_agent(self, name: str) -> bool:
        return self.registry.deregister(name)

    def health_check(self):
        self.registry.health_check_all()

    def sync_federation(self):
        self.registry.sync_peers()

    def get_alive_agents(self, include_unavailable: bool = True):
        return [p.to_public_dict() for p in self.registry.list_all(include_unavailable=include_unavailable)]

    def call_agent(self, agent_name: str, input_data, max_retries: int | None = None):
        profile = self.registry.find_best_match(agent_name)

        result, latency_ms = call_with_retry(profile, input_data, max_retries=max_retries)

        if result.get("status") == "ok":
            self.registry.report_success(profile.name, latency_ms)
        else:
            self.registry.report_failure(profile.name, result.get("message", "unknown_error"))

        return result
