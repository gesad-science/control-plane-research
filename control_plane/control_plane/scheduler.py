import threading
import time

from control_plane.observability import get_logger

logger = get_logger("control_plane.scheduler")


class PeriodicJob:
    def __init__(self, name: str, interval_seconds: float, fn):
        self.name = name
        self.interval_seconds = interval_seconds
        self.fn = fn
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self.interval_seconds <= 0:
            logger.info("periodic_job_disabled", extra={"job": self.name})
            return
        self._thread = threading.Thread(target=self._run, name=f"job-{self.name}", daemon=True)
        self._thread.start()
        logger.info("periodic_job_started", extra={"job": self.name, "interval_seconds": self.interval_seconds})

    def _run(self):
        while not self._stop.wait(self.interval_seconds):
            try:
                self.fn()
            except Exception:
                logger.exception("periodic_job_failed", extra={"job": self.name})

    def stop(self):
        self._stop.set()
