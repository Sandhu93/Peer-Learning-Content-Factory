# Sample Concepts (Test Fixture)

## Category: Reliability, Failure Isolation, and Production Hardening

### Circuit Breaker for Provider Failure
- **Concept**: Circuit breaker for provider failure
- **Category**: Reliability, Failure Isolation, and Production Hardening
- **Why it matters**: Prevents cascading failures when an upstream provider becomes unavailable.
- **Repo anchors**: circuit_breaker, CircuitBreaker, open_state, half_open

### Retry with Exponential Backoff and Jitter
- **Concept**: Retry with exponential backoff and jitter
- **Category**: Reliability, Failure Isolation, and Production Hardening
- **Why it matters**: Avoids thundering-herd retry storms by distributing retry timing.
- **Repo anchors**: retry, backoff, jitter, exponential

## Category: Observability and Debugging

### Structured Logging with Correlation IDs
- **Concept**: Structured logging with correlation IDs
- **Category**: Observability and Debugging
- **Why it matters**: Enables end-to-end request tracing across services.
- **Repo anchors**: correlation_id, request_id, structlog
