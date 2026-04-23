# Section 1 - Incident Investigation Log

## Investigation timeline

1. **Validate symptom and blast radius**  
   Reproduced timeout only for users with large order history (>200 orders). Small accounts remained fast. This ruled out total API outage and pointed to data-size scaling behavior.

2. **Check recent deployment metadata**  
   Confirmed no direct code diff in `orders summary` view. Focus shifted to indirect regressions: serializer fields, model relations, default ordering, and database schema/index drift.

3. **Inspect SQL query volume with django-debug-toolbar**  
   Enabled debug toolbar and hit `/api/orders/summary/broken/`. Query panel showed one base query + hundreds of repeated relation lookups, classic fan-out behavior.

4. **Capture exact ORM access pattern**  
   Found loop-driven access to `order.customer.email` and `order.items.count()` without eager loading, causing repeated `SELECT` calls per row.

5. **Hypothesis validation with query counting test**  
   Added test with Django `CaptureQueriesContext`: broken path produced O(N) query growth; fixed path stayed bounded.

## Root cause category

**Primary cause: N+1 query regression (ORM relationship loading).**

Why this category fits:
- The endpoint did not change, but data volume crossed a threshold where lazy relationship fetching became expensive.
- The SQL profile shows repeated lookups for related tables per order row.
- Latency increased approximately with order count, which is characteristic of N+1 behavior.

## Demonstration and fix

- Broken implementation: `Order.objects.filter(...).order_by(...); for order in queryset: order.customer..., order.items.count()`
- Fixed implementation uses:
  - `select_related('customer')` to join FK rows in one query
  - `prefetch_related('items')` to batch-load reverse relation
  - `annotate(item_count=Count('items'))` to avoid per-row count queries

## Why the fix works (DB + ORM)

- `select_related` converts separate customer lookups into a SQL `JOIN`; Django hydrates `customer` without extra round trips.
- `prefetch_related` executes one additional query for all related items and performs in-Python relation mapping; this replaces many tiny relation queries.
- `annotate(Count(...))` computes counts in SQL `GROUP BY` scope instead of calling `.count()` per object, eliminating repeated aggregate queries.

## Query evidence (captured in tests)

From `core.tests.test_orders_summary_performance`:
- Broken view query count for sample dataset: **445 queries**
- Fixed view query count for same dataset: **3 queries**

This confirms measurable and material reduction.

## Reproduction commands used in this project

1. Run test suite with query-count assertion:

```bash
python manage.py test
```

2. Start server and call both endpoints with tenant header:

```bash
python manage.py runserver 127.0.0.1:8000
curl -H "X-Tenant-ID: 1" http://127.0.0.1:8000/api/orders/summary/broken/
curl -H "X-Tenant-ID: 1" http://127.0.0.1:8000/api/orders/summary/fixed/
```

3. Optional profiling UI:
- `django-debug-toolbar` URLs are enabled when package is installed.
- If package is absent, app still runs; query evidence remains available via tests.
