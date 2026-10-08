# app/cache.py
import os
from typing import Optional

import redis
from dotenv import load_dotenv

load_dotenv()

DEFAULT_REDIS_URL = "redis://localhost:6379/0"


def _resolve_redis_url() -> str:
    """REDIS_URL > REDIS_HOST/REDIS_PORT > localhost 순으로 접속 주소를 결정한다."""
    url = os.getenv("REDIS_URL", "").strip()
    if url:
        return url
    host = os.getenv("REDIS_HOST", "").strip()
    if host:
        port = os.getenv("REDIS_PORT", "6379").strip() or "6379"
        return f"redis://{host}:{port}/0"
    return DEFAULT_REDIS_URL


def create_redis_client() -> Optional["redis.Redis"]:
    """Redis에 한 번만 연결을 시도한다. 실패하면 경고 한 줄만 출력하고 None(캐시 비활성화)을 반환한다."""
    url = _resolve_redis_url()
    safe_target = url.split("@")[-1]  # 비밀번호가 로그에 노출되지 않도록 마스킹
    try:
        client = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        client.ping()
        print(f"✅ Redis 연결 성공 ({safe_target})")
        return client
    except Exception as e:
        print(
            f"⚠️ Redis 연결 실패 ({safe_target}): {e} -> 캐시 없이 실행합니다. "
            f"(REDIS_URL 환경변수를 확인하거나 Redis를 실행하세요)"
        )
        return None
