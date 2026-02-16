# -*- coding: utf-8 -*-

from __future__ import annotations

from datetime import timedelta
from typing import Any

from loguru import logger
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.base import now_tz
from app.models.llm import LLMRequestMetric


class LLMObservabilityService:
    """观测服务：记录请求指标并提供聚合查询。"""

    async def safe_record(
        self,
        *,
        request_id: str,
        owner_id: int,
        conversation_id: str | None,
        provider: str,
        model: str,
        is_stream: bool,
        success: bool,
        latency_ms: int,
        usage: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        fallback_from: str | None = None,
        fallback_chain: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ):
        try:
            await self.record(
                request_id=request_id,
                owner_id=owner_id,
                conversation_id=conversation_id,
                provider=provider,
                model=model,
                is_stream=is_stream,
                success=success,
                latency_ms=latency_ms,
                usage=usage,
                error_code=error_code,
                error_message=error_message,
                fallback_from=fallback_from,
                fallback_chain=fallback_chain,
                extra=extra,
            )
        except Exception:
            logger.exception("写入 LLM 观测指标失败")

    async def record(
        self,
        *,
        request_id: str,
        owner_id: int,
        conversation_id: str | None,
        provider: str,
        model: str,
        is_stream: bool,
        success: bool,
        latency_ms: int,
        usage: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        fallback_from: str | None = None,
        fallback_chain: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ):
        usage = usage or {}
        prompt_tokens, completion_tokens, total_tokens = self.extract_token_usage(usage)
        async with AsyncSessionLocal() as db:
            row = LLMRequestMetric(
                request_id=request_id,
                conversation_id=conversation_id,
                owner_id=owner_id,
                provider=provider,
                model=model,
                is_stream=1 if is_stream else 0,
                success=1 if success else 0,
                latency_ms=max(0, int(latency_ms)),
                error_code=error_code,
                error_message=(error_message or "")[:2000] or None,
                fallback_from=fallback_from,
                fallback_chain=fallback_chain or [],
                usage_prompt_tokens=prompt_tokens,
                usage_completion_tokens=completion_tokens,
                usage_total_tokens=total_tokens,
                usage_raw=usage,
                extra=extra or {},
                status=1,
            )
            db.add(row)
            await db.commit()

    async def summary(
        self,
        db: AsyncSession,
        *,
        owner_id: int,
        days: int = 7,
    ) -> dict[str, Any]:
        days = max(1, min(days, 60))
        since = now_tz() - timedelta(days=days)

        total_stmt = select(
            func.count(LLMRequestMetric.id),
            func.sum(LLMRequestMetric.success),
            func.avg(LLMRequestMetric.latency_ms),
            func.sum(LLMRequestMetric.usage_total_tokens),
            func.sum(LLMRequestMetric.usage_prompt_tokens),
            func.sum(LLMRequestMetric.usage_completion_tokens),
        ).where(
            LLMRequestMetric.owner_id == owner_id,
            LLMRequestMetric.is_deleted == 0,
            LLMRequestMetric.create_time >= since,
        )
        total_row = (await db.execute(total_stmt)).first()
        total_requests = int(total_row[0] or 0)
        success_requests = int(total_row[1] or 0)
        error_requests = max(0, total_requests - success_requests)
        avg_latency_ms = float(total_row[2] or 0.0)
        total_tokens = int(total_row[3] or 0)
        prompt_tokens = int(total_row[4] or 0)
        completion_tokens = int(total_row[5] or 0)

        group_stmt = (
            select(
                LLMRequestMetric.provider,
                LLMRequestMetric.model,
                func.count(LLMRequestMetric.id),
                func.sum(LLMRequestMetric.success),
                func.avg(LLMRequestMetric.latency_ms),
                func.sum(LLMRequestMetric.usage_total_tokens),
            )
            .where(
                LLMRequestMetric.owner_id == owner_id,
                LLMRequestMetric.is_deleted == 0,
                LLMRequestMetric.create_time >= since,
            )
            .group_by(LLMRequestMetric.provider, LLMRequestMetric.model)
            .order_by(desc(func.count(LLMRequestMetric.id)))
            .limit(50)
        )
        group_rows = list((await db.execute(group_stmt)).all())
        by_provider_model: list[dict[str, Any]] = []
        for provider, model, req_count, success_count, avg_latency, group_tokens in group_rows:
            req_count = int(req_count or 0)
            success_count = int(success_count or 0)
            error_count = max(0, req_count - success_count)
            by_provider_model.append(
                {
                    "provider": provider,
                    "model": model,
                    "requests": req_count,
                    "success": success_count,
                    "errors": error_count,
                    "error_rate": round((error_count / req_count), 4) if req_count else 0.0,
                    "avg_latency_ms": round(float(avg_latency or 0.0), 2),
                    "tokens": int(group_tokens or 0),
                }
            )

        return {
            "window_days": days,
            "total_requests": total_requests,
            "success_requests": success_requests,
            "error_requests": error_requests,
            "error_rate": round((error_requests / total_requests), 4) if total_requests else 0.0,
            "avg_latency_ms": round(avg_latency_ms, 2),
            "token_usage": {
                "total_tokens": total_tokens,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
            "by_provider_model": by_provider_model,
        }

    async def recent(
        self,
        db: AsyncSession,
        *,
        owner_id: int,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(LLMRequestMetric)
            .where(
                LLMRequestMetric.owner_id == owner_id,
                LLMRequestMetric.is_deleted == 0,
            )
            .order_by(desc(LLMRequestMetric.id))
            .limit(max(1, min(limit, 200)))
        )
        rows = list((await db.execute(stmt)).scalars().all())
        return [
            {
                "request_id": row.request_id,
                "conversation_id": row.conversation_id,
                "provider": row.provider,
                "model": row.model,
                "is_stream": bool(row.is_stream),
                "success": bool(row.success),
                "latency_ms": row.latency_ms,
                "error_code": row.error_code,
                "error_message": row.error_message,
                "fallback_from": row.fallback_from,
                "fallback_chain": row.fallback_chain or [],
                "usage": {
                    "prompt_tokens": row.usage_prompt_tokens,
                    "completion_tokens": row.usage_completion_tokens,
                    "total_tokens": row.usage_total_tokens,
                },
                "create_time": row.create_time,
            }
            for row in rows
        ]

    @staticmethod
    def extract_token_usage(usage: dict[str, Any]) -> tuple[int, int, int]:
        prompt_tokens = LLMObservabilityService._to_int(
            usage.get("prompt_tokens", usage.get("input_tokens", 0))
        )
        completion_tokens = LLMObservabilityService._to_int(
            usage.get("completion_tokens", usage.get("output_tokens", 0))
        )
        total_tokens = LLMObservabilityService._to_int(usage.get("total_tokens", 0))
        if total_tokens <= 0:
            total_tokens = max(0, prompt_tokens + completion_tokens)
        return prompt_tokens, completion_tokens, total_tokens

    @staticmethod
    def _to_int(value: Any) -> int:
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
