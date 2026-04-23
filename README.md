# Django Backend Technical Assessment

This repository contains all required sections from the assessment:

- Section 1: broken endpoint diagnosis and ORM fix
- Section 2: Celery + Redis async queue with Redis atomic rate limiter
- Section 3: automatic multi-tenant ORM isolation
- Section 4: written architecture review answers

## 1) Local setup

Run from `django_assessment`:

```bash
cd /home/piyush/repo/django_assessment
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py test
```

## 2) Start API server

```bash
python manage.py runserver 127.0.0.1:8000
```

## 3) Seed demo data (tenant-aware)

Because `Order.objects` is auto-scoped by tenant manager, create seed data with tenant context:

```bash
python manage.py shell -c "from core.models import Tenant,Customer,Order; from core.tenant_context import set_current_tenant,reset_current_tenant; t,_=Tenant.objects.get_or_create(slug='acme',defaults={'name':'Acme'}); c,_=Customer.objects.get_or_create(tenant=t,email='demo@example.com'); tok=set_current_tenant(t); o=Order.objects.create(tenant=t,customer=c,total_cents=1000); print('tenant_id', t.id, 'order_id', o.id); reset_current_tenant(tok)"
```

## 4) See endpoint output

These APIs require a tenant header. Calling them directly in browser URL without headers returns `Tenant not provided or invalid.`

```bash
curl -H "X-Tenant-ID: 1" http://127.0.0.1:8000/api/orders/summary/broken/
curl -H "X-Tenant-ID: 1" http://127.0.0.1:8000/api/orders/summary/fixed/
```

Expected shape:

```json
{"count": 1, "total_revenue": 1000, "orders": [{"order_id": 1, "customer_email": "demo@example.com", "item_count": 0, "total_cents": 1000}]}
```

## 5) Optional: Redis + Celery run (Section 2)

```bash
# terminal 1
redis-server

# terminal 2
celery -A assessment worker -l info

# terminal 3
python manage.py shell -c "from core.tasks import send_transactional_email; print(send_transactional_email.delay('user@example.com','hello').id)"
```

## Troubleshooting

- `UNIQUE constraint failed: core_tenant.slug`
  - `acme` already exists. Use `get_or_create`, not `create`.
- `Tenant context is not set for this request`
  - You are using `Order.objects` without setting tenant context in shell.
- `Tenant not provided or invalid.`
  - Missing/invalid `X-Tenant-ID` header (or unknown subdomain).
- `curl: (7) Failed to connect ...`
  - Django server is not running on `127.0.0.1:8000`.

## Assessment documents

- `INCIDENT_LOG.md` - Section 1 investigation log + measurable query improvement evidence
- `DESIGN.md` - Section 2 architecture, trade-offs, and failure handling
- `ANSWERS.md` - Section 2 SIGKILL answer + Section 4 written answers
