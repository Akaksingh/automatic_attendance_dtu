"""Redis client factory. Connections are made only when a command is issued."""
import redis

from .config import settings

redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
