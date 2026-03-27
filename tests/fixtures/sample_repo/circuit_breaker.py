"""
Sample circuit breaker implementation — used as a test fixture.
This simulates what the code_researcher agent would find in a real repo.
"""

import time
from enum import Enum


class State(Enum):
    CLOSED = "closed"       # normal operation — requests pass through
    OPEN = "open"           # tripped — all requests fail fast
    HALF_OPEN = "half_open" # recovery probe — one test request allowed


class CircuitBreaker:
    """
    Circuit breaker that tracks consecutive failures and opens when
    the threshold is exceeded.
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = State.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None

    @property
    def state(self) -> State:
        if self._state == State.OPEN:
            if self._last_failure_time and (
                time.monotonic() - self._last_failure_time > self.recovery_timeout
            ):
                self._state = State.HALF_OPEN
        return self._state

    def call(self, fn, *args, **kwargs):
        if self.state == State.OPEN:
            raise CircuitOpenError("Circuit is OPEN — request rejected")

        try:
            result = fn(*args, **kwargs)
            self._on_success()
            return result
        except Exception as exc:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        self._failure_count = 0
        self._state = State.CLOSED

    def _on_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            self._state = State.OPEN


class CircuitOpenError(Exception):
    """Raised when a request is rejected because the circuit is OPEN."""
