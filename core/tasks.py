
import json
import os

from celery import shared_task
try:
    import redis
except ImportError:  # pragma: no cover
    redis = None

from .models import FailedEmailJob
from .rate_limiter import RedisTokenBucketRateLimiter


def _redis_client():
    if redis is None:
        raise RuntimeError('redis package is required to create a Redis client')
    return redis.Redis.from_url(os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0'))


def _send_with_provider(recipient, body):
    if 'force-failure' in body:
        raise RuntimeError('simulated provider failure')
    return {'status': 'accepted', 'recipient': recipient}


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=32, retry_jitter=True, max_retries=5)
def send_transactional_email(self, recipient, body, metadata=None):
    metadata = metadata or {}
    limiter = RedisTokenBucketRateLimiter(_redis_client())
    result = limiter.consume()

    if not result.allowed:
        raise self.retry(countdown=1)

    try:
        response = _send_with_provider(recipient, body)
        return {'response': response, 'metadata': metadata}
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            FailedEmailJob.objects.create(
                recipient=recipient,
                payload={'body': body, 'metadata': metadata},
                error=json.dumps({'error': str(exc), 'retries': self.request.retries}),
            )
        raise
