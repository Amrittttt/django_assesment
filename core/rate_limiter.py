
from dataclasses import dataclass
import time


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int


class RedisTokenBucketRateLimiter:
    LUA_SCRIPT = """
    local key = KEYS[1]
    local capacity = tonumber(ARGV[1])
    local refill_rate = tonumber(ARGV[2])
    local now = tonumber(ARGV[3])

    local bucket = redis.call('HMGET', key, 'tokens', 'ts')
    local tokens = tonumber(bucket[1])
    local ts = tonumber(bucket[2])

    if tokens == nil then
        tokens = capacity
        ts = now
    end

    local elapsed = math.max(0, now - ts)
    local refill = elapsed * refill_rate
    tokens = math.min(capacity, tokens + refill)

    local allowed = 0
    if tokens >= 1 then
        tokens = tokens - 1
        allowed = 1
    end

    redis.call('HMSET', key, 'tokens', tokens, 'ts', now)
    redis.call('EXPIRE', key, 120)
    return {allowed, math.floor(tokens)}
    """

    def __init__(self, redis_client, key='email:token_bucket', capacity=200, refill_rate_per_sec=200/60):
        self.redis = redis_client
        self.key = key
        self.capacity = capacity
        self.refill_rate_per_sec = refill_rate_per_sec

    def consume(self):
        now = time.time()
        allowed, remaining = self.redis.eval(
            self.LUA_SCRIPT,
            1,
            self.key,
            self.capacity,
            self.refill_rate_per_sec,
            now,
        )
        return RateLimitResult(bool(allowed), int(remaining))
