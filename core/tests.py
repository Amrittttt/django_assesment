from unittest.mock import patch

from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext

from .middleware import TenantContextMiddleware
from .models import Customer, Order, OrderItem, Tenant
from .rate_limiter import RedisTokenBucketRateLimiter
from .tasks import send_transactional_email
from .tenant_context import set_current_tenant, reset_current_tenant
from .views import order_summary_broken, order_summary_fixed


class InMemoryRedis:
    def __init__(self):
        self.store = {}

    def eval(self, _script, _keys_count, key, capacity, refill_rate, now):
        capacity = float(capacity)
        refill_rate = float(refill_rate)
        now = float(now)

        bucket = self.store.get(key, {'tokens': capacity, 'ts': now})
        elapsed = max(0.0, now - bucket['ts'])
        tokens = min(capacity, bucket['tokens'] + elapsed * refill_rate)

        allowed = 0
        if tokens >= 1:
            tokens -= 1
            allowed = 1

        self.store[key] = {'tokens': tokens, 'ts': now}
        return [allowed, int(tokens)]


class OrdersSummaryPerformanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name='Acme', slug='acme')
        cls.customer = Customer.objects.create(tenant=cls.tenant, email='u@example.com')
        token = set_current_tenant(cls.tenant)
        for i in range(220):
            order = Order.objects.create(tenant=cls.tenant, customer=cls.customer, total_cents=100 + i)
            OrderItem.objects.create(order=order, name='Item', quantity=1)
        reset_current_tenant(token)

    def test_fixed_view_has_significantly_fewer_queries(self):
        request = RequestFactory().get('/api/orders/summary/fixed/', HTTP_X_TENANT_ID=str(self.tenant.id))
        token = set_current_tenant(self.tenant)
        try:
            with CaptureQueriesContext(connection) as broken_ctx:
                order_summary_broken(request)
            with CaptureQueriesContext(connection) as fixed_ctx:
                order_summary_fixed(request)
        finally:
            reset_current_tenant(token)

        self.assertGreater(len(broken_ctx.captured_queries), 200)
        self.assertLess(len(fixed_ctx.captured_queries), 10)


class TenantIsolationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Tenant.objects.create(name='Tenant A', slug='ta')
        cls.tenant_b = Tenant.objects.create(name='Tenant B', slug='tb')

        customer_a = Customer.objects.create(tenant=cls.tenant_a, email='a@example.com')
        customer_b = Customer.objects.create(tenant=cls.tenant_b, email='b@example.com')

        token = set_current_tenant(cls.tenant_a)
        Order.objects.create(tenant=cls.tenant_a, customer=customer_a, total_cents=120)
        reset_current_tenant(token)

        token = set_current_tenant(cls.tenant_b)
        Order.objects.create(tenant=cls.tenant_b, customer=customer_b, total_cents=130)
        reset_current_tenant(token)

    def test_objects_all_is_scoped(self):
        token = set_current_tenant(self.tenant_a)
        try:
            order_ids = list(Order.objects.all().values_list('tenant_id', flat=True))
        finally:
            reset_current_tenant(token)

        self.assertEqual(order_ids, [self.tenant_a.id])

    def test_tenant_a_cannot_access_tenant_b_data(self):
        token = set_current_tenant(self.tenant_a)
        try:
            count = Order.objects.filter(tenant=self.tenant_b).count()
        finally:
            reset_current_tenant(token)

        self.assertEqual(count, 0)

    def test_middleware_sets_and_cleans_tenant_context(self):
        factory = RequestFactory()
        request = factory.get('/', HTTP_X_TENANT_ID=str(self.tenant_a.id))

        def view(req):
            return order_summary_fixed(req)

        middleware = TenantContextMiddleware(view)
        response = middleware(request)
        self.assertEqual(response.status_code, 200)


class QueueAndRateLimitTests(TestCase):
    def test_token_bucket_never_allows_more_than_capacity_instantly(self):
        r = InMemoryRedis()
        limiter = RedisTokenBucketRateLimiter(r, key='test-bucket', capacity=200, refill_rate_per_sec=200 / 60)
        allowed = 0
        for _ in range(500):
            if limiter.consume().allowed:
                allowed += 1
        self.assertLessEqual(allowed, 201)

    @patch('core.tasks._redis_client')
    @patch('core.tasks._send_with_provider')
    def test_500_jobs_processed_no_loss_and_retry_observed(self, mock_send, mock_redis_client):
        mock_redis_client.return_value = InMemoryRedis()

        call_count = {'n': 0}

        def side_effect(recipient, body):
            call_count['n'] += 1
            if call_count['n'] == 1:
                raise RuntimeError('intentional failure for retry check')
            return {'status': 'accepted', 'recipient': recipient}

        mock_send.side_effect = side_effect

        retry_result = send_transactional_email.apply(args=('user@example.com', 'force-failure-once'))
        self.assertTrue(retry_result.successful())
        self.assertGreaterEqual(call_count['n'], 2)

        with patch('core.tasks._send_with_provider', return_value={'status': 'accepted'}):
            with patch('core.tasks.RedisTokenBucketRateLimiter.consume') as mock_consume:
                mock_consume.return_value = type('Result', (), {'allowed': True, 'remaining': 999})()
                results = []
                for i in range(500):
                    res = send_transactional_email.apply(args=(f'user{i}@example.com', 'ok'))
                    results.append(res)

        successful = [r for r in results if r.successful()]
        self.assertEqual(len(successful), 500)
