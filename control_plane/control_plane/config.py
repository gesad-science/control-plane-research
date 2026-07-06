import os
import secrets


def _bool(env_var: str, default: bool) -> bool:
    val = os.getenv(env_var)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


class Settings:
    HOST = os.getenv("CP_SCAN_HOST", "localhost")
    PORT_RANGE_START = int(os.getenv("CP_PORT_RANGE_START", "9000"))
    PORT_RANGE_END = int(os.getenv("CP_PORT_RANGE_END", "9010"))
    SCAN_TIMEOUT_SECONDS = float(os.getenv("CP_SCAN_TIMEOUT", "0.5"))

    SCAN_TARGETS = [t.strip() for t in os.getenv("CP_SCAN_TARGETS", "").split(",") if t.strip()]

    SCAN_INTERVAL_SECONDS = float(os.getenv("CP_SCAN_INTERVAL_SECONDS", "30"))
    HEALTH_CHECK_INTERVAL_SECONDS = float(os.getenv("CP_HEALTH_CHECK_INTERVAL_SECONDS", "10"))

    AUTH_ENABLED = _bool("CP_AUTH_ENABLED", True)
    API_KEY = os.getenv("CP_API_KEY") or secrets.token_urlsafe(24)
    REGISTRATION_TOKEN = os.getenv("CP_REGISTRATION_TOKEN") or secrets.token_urlsafe(24)
    _API_KEY_WAS_GENERATED = os.getenv("CP_API_KEY") is None
    _REGISTRATION_TOKEN_WAS_GENERATED = os.getenv("CP_REGISTRATION_TOKEN") is None

    MAX_RETRIES = int(os.getenv("CP_MAX_RETRIES", "3"))
    RETRY_BACKOFF_BASE_SECONDS = float(os.getenv("CP_RETRY_BACKOFF_BASE", "0.5"))
    RETRY_BACKOFF_MAX_SECONDS = float(os.getenv("CP_RETRY_BACKOFF_MAX", "8"))
    CALL_TIMEOUT_SECONDS = float(os.getenv("CP_CALL_TIMEOUT_SECONDS", "30"))

    FAILURE_THRESHOLD = int(os.getenv("CP_FAILURE_THRESHOLD", "3"))
    RECOVERY_THRESHOLD = int(os.getenv("CP_RECOVERY_THRESHOLD", "1"))

    LOG_LEVEL = os.getenv("CP_LOG_LEVEL", "INFO")
    JSON_LOGS = _bool("CP_JSON_LOGS", True)
    SERVICE_NAME = os.getenv("CP_SERVICE_NAME", "control-plane")
    ENABLE_TRACING = _bool("CP_ENABLE_TRACING", True)

    FEDERATION_PEERS = [p.strip() for p in os.getenv("CP_FEDERATION_PEERS", "").split(",") if p.strip()]
    FEDERATION_ID = os.getenv("CP_FEDERATION_ID", "local")


settings = Settings()
