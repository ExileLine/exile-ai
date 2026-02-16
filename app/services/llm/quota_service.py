# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any

from loguru import logger

from app.core.config import get_config
from app.core.exceptions import CustomException
from app.db.redis_client import get_redis_pool
from app.models.base import now_tz
from app.services.llm.observability_service import LLMObservabilityService

project_config = get_config()


class LLMQuotaService:
    """限流与配额服务（按用户/模型）。"""

    async def enforce_before_request(self, *, owner_id: int, provider: str, model: str):
        if not project_config.LLM_RATE_LIMIT_ENABLE:
            return

        redis = await self._get_redis_or_none()
        if redis is None:
            return

        provider = (provider or "unknown").strip().lower() or "unknown"
        model = (model or "unknown").strip() or "unknown"
        day_str = now_tz().strftime("%Y%m%d")
        minute_key = self._minute_key(owner_id=owner_id, provider=provider, model=model)
        day_req_key = self._day_request_key(owner_id=owner_id, provider=provider, model=model, day_str=day_str)
        day_tok_key = self._day_token_key(owner_id=owner_id, provider=provider, model=model, day_str=day_str)

        minute_limit = max(1, int(project_config.LLM_RATE_LIMIT_REQUESTS_PER_MINUTE))
        minute_count = await redis.incr(minute_key)
        if minute_count == 1:
            await redis.expire(minute_key, 70)
        if minute_count > minute_limit:
            raise CustomException(
                status_code=429,
                detail=f"触发限流：{provider}/{model} 每分钟最多 {minute_limit} 次请求",
                custom_code=10005,
            )

        day_limit = max(0, int(project_config.LLM_RATE_LIMIT_REQUESTS_PER_DAY))
        if day_limit > 0:
            day_count = await redis.incr(day_req_key)
            if day_count == 1:
                await redis.expire(day_req_key, 172800)
            if day_count > day_limit:
                raise CustomException(
                    status_code=429,
                    detail=f"触发限流：{provider}/{model} 每日最多 {day_limit} 次请求",
                    custom_code=10005,
                )

        token_limit = max(0, int(project_config.LLM_TOKEN_QUOTA_PER_DAY))
        if token_limit > 0:
            used_text = await redis.get(day_tok_key)
            used_tokens = self._to_int(used_text)
            if used_tokens >= token_limit:
                raise CustomException(
                    status_code=429,
                    detail=f"触发配额：{provider}/{model} 每日 token 配额 {token_limit} 已用尽",
                    custom_code=10005,
                )

    async def commit_token_usage(
        self,
        *,
        owner_id: int,
        provider: str,
        model: str,
        usage: dict[str, Any] | None,
    ):
        if not project_config.LLM_RATE_LIMIT_ENABLE:
            return
        redis = await self._get_redis_or_none()
        if redis is None:
            return
        usage = usage or {}
        _, _, total_tokens = LLMObservabilityService.extract_token_usage(usage)
        if total_tokens <= 0:
            return
        provider = (provider or "unknown").strip().lower() or "unknown"
        model = (model or "unknown").strip() or "unknown"
        day_str = now_tz().strftime("%Y%m%d")
        day_tok_key = self._day_token_key(owner_id=owner_id, provider=provider, model=model, day_str=day_str)
        new_value = await redis.incrby(day_tok_key, total_tokens)
        if new_value <= total_tokens:
            await redis.expire(day_tok_key, 172800)

    async def snapshot(
        self,
        *,
        owner_id: int,
        provider: str,
        model: str,
    ) -> dict[str, Any]:
        provider = (provider or "unknown").strip().lower() or "unknown"
        model = (model or "unknown").strip() or "unknown"
        day_str = now_tz().strftime("%Y%m%d")

        redis = await self._get_redis_or_none()
        if redis is None:
            return {
                "enabled": bool(project_config.LLM_RATE_LIMIT_ENABLE),
                "provider": provider,
                "model": model,
                "error": "redis_unavailable",
            }

        minute_key = self._minute_key(owner_id=owner_id, provider=provider, model=model)
        day_req_key = self._day_request_key(owner_id=owner_id, provider=provider, model=model, day_str=day_str)
        day_tok_key = self._day_token_key(owner_id=owner_id, provider=provider, model=model, day_str=day_str)

        minute_used = self._to_int(await redis.get(minute_key))
        day_req_used = self._to_int(await redis.get(day_req_key))
        day_tok_used = self._to_int(await redis.get(day_tok_key))

        return {
            "enabled": bool(project_config.LLM_RATE_LIMIT_ENABLE),
            "provider": provider,
            "model": model,
            "limits": {
                "requests_per_minute": int(project_config.LLM_RATE_LIMIT_REQUESTS_PER_MINUTE),
                "requests_per_day": int(project_config.LLM_RATE_LIMIT_REQUESTS_PER_DAY),
                "tokens_per_day": int(project_config.LLM_TOKEN_QUOTA_PER_DAY),
            },
            "usage": {
                "requests_this_minute": minute_used,
                "requests_today": day_req_used,
                "tokens_today": day_tok_used,
            },
        }

    @staticmethod
    def _minute_key(*, owner_id: int, provider: str, model: str) -> str:
        minute_bucket = int(now_tz().timestamp() // 60)
        return f"llm:rate:minute:{owner_id}:{provider}:{model}:{minute_bucket}"

    @staticmethod
    def _day_request_key(*, owner_id: int, provider: str, model: str, day_str: str) -> str:
        return f"llm:rate:day:req:{day_str}:{owner_id}:{provider}:{model}"

    @staticmethod
    def _day_token_key(*, owner_id: int, provider: str, model: str, day_str: str) -> str:
        return f"llm:rate:day:tok:{day_str}:{owner_id}:{provider}:{model}"

    @staticmethod
    async def _get_redis_or_none():
        try:
            return await get_redis_pool()
        except Exception:
            logger.warning("Redis 不可用，已跳过 LLM 限流/配额校验")
            return None

    @staticmethod
    def _to_int(value: Any) -> int:
        if value is None:
            return 0
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        try:
            text = str(value).strip()
            if not text:
                return 0
            return int(float(text))
        except Exception:
            return 0
