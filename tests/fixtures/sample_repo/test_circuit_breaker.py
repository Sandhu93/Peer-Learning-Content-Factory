"""Tests for circuit breaker — sample fixture."""

import pytest
from circuit_breaker import CircuitBreaker, CircuitOpenError, State


def failing_fn():
    raise ValueError("downstream failure")


def success_fn():
    return "ok"


def test_starts_closed():
    cb = CircuitBreaker(failure_threshold=3)
    assert cb.state == State.CLOSED


def test_opens_after_threshold():
    cb = CircuitBreaker(failure_threshold=3)
    for _ in range(3):
        with pytest.raises(ValueError):
            cb.call(failing_fn)
    assert cb.state == State.OPEN


def test_rejects_when_open():
    cb = CircuitBreaker(failure_threshold=1)
    with pytest.raises(ValueError):
        cb.call(failing_fn)
    with pytest.raises(CircuitOpenError):
        cb.call(success_fn)


def test_resets_on_success():
    cb = CircuitBreaker(failure_threshold=5)
    cb.call(success_fn)
    assert cb._failure_count == 0
    assert cb.state == State.CLOSED
