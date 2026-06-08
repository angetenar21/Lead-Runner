import os
import json
import redis
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Initialize Redis client. We use decode_responses=True to get strings instead of bytes
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
except Exception as e:
    print(f"Failed to connect to Redis: {e}")
    redis_client = None

def get_json(key: str) -> dict | list | None:
    """Retrieve and parse JSON data from Redis."""
    if not redis_client:
        return None
    try:
        data = redis_client.get(key)
        if data:
            return json.loads(data)
    except Exception as e:
        print(f"Redis get error for {key}: {e}")
    return None

def set_json(key: str, value: dict | list, expiry_seconds: int = 86400) -> bool:
    """Store JSON data in Redis with an expiration time (default 24 hours)."""
    if not redis_client:
        return False
    try:
        return redis_client.setex(key, expiry_seconds, json.dumps(value))
    except Exception as e:
        print(f"Redis set error for {key}: {e}")
    return False
