# Section 2 Written Answer - SIGKILL Behavior

With Celery default early-ack behavior, a SIGKILL can lose in-flight work because the broker believes the message was already consumed. I configured `task_acks_late=True` so ACK happens only after task completion. I also set `task_reject_on_worker_lost=True`; when a worker process is killed abruptly, Celery tells the broker to requeue instead of treating the task as done. Combined with Redis broker `visibility_timeout`, a claimed-but-unacked task becomes visible again for another worker after timeout. In this implementation, a worker crash mid-send causes task redelivery and retry semantics to continue.

This improves durability but introduces duplicate-delivery risk if crash occurs after external side effect (email provider accepted send) and before ACK. To mitigate that in production, each task should include an idempotency key persisted in application DB or provider metadata; retries check key before sending.

# Section 4 - Written Architecture Review

## Question B - Pagination Trade-offs

Offset pagination (`LIMIT/OFFSET`) is easy to implement and human-friendly (`?page=4`), but degrades at scale because databases still scan/skip rows up to the offset. On large tables this increases IO and latency, especially with deep scroll. It is also unstable under concurrent writes: new inserts or deletes can shift row positions, causing duplicates or missing records across pages. For a mobile infinite-scroll feed, this leads to confusing UX where items reappear or vanish.

Cursor pagination uses a stable ordering key (for example `created_at, id`) and fetches records “after” a cursor (`WHERE (created_at, id) < (...) LIMIT N`). This is typically index-friendly and avoids deep-scan penalties. It is resilient to mutation because navigation is anchored to values, not row counts. Trade-off: implementation complexity is higher, cursors are opaque, and jumping directly to arbitrary page numbers is not natural.

I choose cursor pagination for high-volume, append-heavy timelines and mobile infinite scroll. I choose offset pagination for small/admin datasets where random page access matters more than write consistency, and where table size keeps offset cost acceptable.

## Question C - File Upload Security

1. **Extension spoofing / MIME confusion**  
   Attackers upload executable payloads renamed as images. Mitigation: validate both extension and actual content signature (magic bytes) in Django form/serializer validation, rejecting mismatches.

2. **Path traversal in filenames**  
   Filenames like `../../app.py` can target unsafe paths if used directly. Mitigation: never trust client filename for storage path; generate UUID-based names via custom `upload_to` callable.

3. **Malicious oversized files (resource exhaustion)**  
   Huge payloads can exhaust memory/disk. Mitigation: enforce `DATA_UPLOAD_MAX_MEMORY_SIZE`, request size limits at Django level, and per-field validator max size checks.

4. **Stored XSS through active content**  
   SVG/HTML uploads may execute scripts when rendered inline. Mitigation: restrict allowed file types to safe subset; serve with forced download headers for untrusted formats; never inline-render user HTML/SVG.

5. **Zip bombs / decompression bombs**  
   Compressed archives can expand massively during processing. Mitigation: inspect archive metadata before extraction, cap file count and total uncompressed size, and reject nested/compressed recursion patterns in processing pipeline.

# Demo Verification Commands

These are the exact commands used to verify live output:

```bash
python manage.py runserver 127.0.0.1:8000
python manage.py shell -c "from core.models import Tenant,Customer,Order; from core.tenant_context import set_current_tenant,reset_current_tenant; t,_=Tenant.objects.get_or_create(slug='acme',defaults={'name':'Acme'}); c,_=Customer.objects.get_or_create(tenant=t,email='demo@example.com'); tok=set_current_tenant(t); o=Order.objects.create(tenant=t,customer=c,total_cents=1000); print('tenant_id', t.id, 'order_id', o.id); reset_current_tenant(tok)"
curl -H "X-Tenant-ID: 1" http://127.0.0.1:8000/api/orders/summary/fixed/
```

If the browser URL is opened directly without headers, tenant middleware correctly rejects request with `Tenant not provided or invalid.`
