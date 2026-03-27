# Sample NL2SQL Agent

A test fixture repository used for doc_analyzer tests.

## Architecture

This service converts natural language queries to SQL using an LLM pipeline.
It includes a circuit breaker to protect against LLM provider failures.

## Circuit Breaker

We added the circuit breaker after a production incident in March 2024 where
the OpenAI API became slow under high load. Without the circuit breaker, all
incoming queries blocked for the full 30-second timeout, exhausting the thread
pool and taking down the entire service.

### Why we built it

During the March 2024 incident, OpenAI response times climbed to 45 seconds.
Our retry logic kept hammering the API, which made things worse. Every user
request was occupying a thread for 45 seconds, and within 2 minutes we had
exhausted all 50 threads in the pool. The service became unresponsive to
healthy traffic (health checks, database queries) because it was waiting on
a degraded LLM provider.

### The fix

We added a `CircuitBreaker` class with:
- `failure_threshold = 5` — trips after 5 consecutive failures
- `recovery_timeout = 30.0` — waits 30 seconds before probing recovery

### Trade-offs

- Threshold of 5 was chosen empirically — lower caused false positives during
  brief API hiccups; higher allowed too much degraded traffic through.
- 30-second recovery timeout matches our SLA for query latency.
- We considered using a sliding window (failures per minute) but the counter
  approach was simpler to reason about and sufficient for our traffic pattern.

## Known issues

See bugs.md for a log of production incidents.
