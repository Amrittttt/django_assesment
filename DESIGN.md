# Section 2 - Rate-Limited Async Job Queue Design

## Candidate architectures and trade-offs

### 1) Celery + Redis
**Pros**
- Mature task lifecycle: retries, dead lettering patterns, worker crash behavior controls.
- Durable broker semantics (Redis list/stream semantics with visibility timeout settings).
- Operationally common in Django ecosystems.

**Cons**
- More moving parts (worker + broker + monitoring).
- Requires deliberate idempotency and ACK configuration.

### 2) Django Q
**Pros**
- Simpler setup for small Django-only deployments.

**Cons**
- Smaller ecosystem and fewer battle-tested production knobs for crash recovery and high-burst behavior.

### 3) Custom queue implementation
**Pros**
- Full control over behavior and data model.

**Cons**
- Reinvents reliability concerns already solved in mature task systems.
- Higher defect risk for retries, poison messages, observability.

## Chosen architecture

I chose **Celery + Redis**, with Celery handling delivery/retry and Redis enforcing the global send rate via an atomic token-bucket Lua script.

## Rate limiter choice

I implemented **Option A: token bucket**.

Why token bucket:
- Natural fit for burst traffic while still respecting sustained throughput limits.
- Lower Redis memory overhead than sliding window for large event volume.
- Better smoothing than fixed window, which can allow boundary spikes.

Atomicity guarantee:
- A single Lua script (`EVAL`) checks/refills/decrements tokens in one atomic server-side operation.
- No race window exists between read and write even under concurrent workers.

Redis failure behavior:
- **Fail closed** in this implementation. If limiter cannot confirm token availability, task retries instead of sending. This protects provider quota compliance.

## Reliability and crash handling

Celery settings:
- `task_acks_late = True`
- `task_reject_on_worker_lost = True`
- `broker_transport_options = {'visibility_timeout': 3600}`

These ensure an in-flight task killed before ACK is re-queued for another worker.

## Dead-letter handling

After max retries, task stores failure metadata into `FailedEmailJob` for operational triage and replay.

## Idempotency note

Production systems should carry a business idempotency key (for example, `message_id`) and de-duplicate sends in the provider request layer. This scaffold shows retry/rate-limit/crash patterns but keeps idempotency minimal for clarity.

## Practical run notes

- Core assessment tests run without external Redis process.
- For live Celery + Redis behavior, run `redis-server` and `celery -A assessment worker -l info`.
- If `redis` Python package is missing locally, settings fall back to in-memory broker/backend to keep baseline project execution usable.
