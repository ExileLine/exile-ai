# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_config
from app.models.base import now_tz
from app.models.llm import LLMConversation, LLMMessage
from app.services.llm.providers import UnifiedLLMClient

project_config = get_config()


class ConversationMemoryService:
    """会话摘要与长期记忆服务。"""

    def __init__(self, llm_client: UnifiedLLMClient | None = None):
        self.llm_client = llm_client or UnifiedLLMClient()

    async def maybe_refresh_summary(
        self,
        db: AsyncSession,
        *,
        conversation: LLMConversation,
        history_rows: list[LLMMessage],
        provider: str,
        model: str,
    ) -> tuple[str | None, int]:
        summary_text, summarized_count = self.get_memory_state(conversation)
        if not project_config.LLM_MEMORY_ENABLE:
            return summary_text, summarized_count
        if not history_rows:
            return summary_text, summarized_count

        history_size = len(history_rows)
        summarized_count = max(0, min(summarized_count, history_size))
        trigger = max(6, int(project_config.LLM_MEMORY_SUMMARY_TRIGGER_MESSAGES))
        keep_recent = max(4, min(int(project_config.LLM_MEMORY_KEEP_RECENT_MESSAGES), 100))
        cutoff = max(0, history_size - keep_recent)
        unsummarized = max(0, cutoff - summarized_count)
        if unsummarized < trigger:
            return summary_text, summarized_count

        rows_to_summarize = history_rows[summarized_count:cutoff]
        if not rows_to_summarize:
            return summary_text, summarized_count

        prompt_messages = self._build_summary_prompt(
            existing_summary=summary_text,
            rows=rows_to_summarize,
        )
        try:
            completion = await self.llm_client.chat_completion(
                messages=prompt_messages,
                provider=provider,
                model=model,
                temperature=0.1,
            )
        except Exception:
            logger.exception("生成会话摘要失败，已跳过本次摘要刷新")
            return summary_text, summarized_count

        content = self._to_text((completion.get("message") or {}).get("content")).strip()
        if not content:
            return summary_text, summarized_count

        max_chars = max(500, int(project_config.LLM_MEMORY_SUMMARY_MAX_CHARS))
        if len(content) > max_chars:
            content = content[:max_chars]

        extra_config = dict(conversation.extra_config or {})
        extra_config["memory_summary"] = content
        extra_config["memory_message_count"] = cutoff
        extra_config["memory_updated_at"] = int(now_tz().timestamp())
        conversation.extra_config = extra_config
        conversation.touch()
        await db.flush()
        return content, cutoff

    @staticmethod
    def get_memory_state(conversation: LLMConversation) -> tuple[str | None, int]:
        extra_config = conversation.extra_config or {}
        summary_text = str(extra_config.get("memory_summary") or "").strip() or None
        try:
            summarized_count = int(extra_config.get("memory_message_count") or 0)
        except Exception:
            summarized_count = 0
        return summary_text, max(0, summarized_count)

    @staticmethod
    def apply_memory(
        *,
        messages: list[dict[str, Any]],
        summary_text: str | None,
    ) -> list[dict[str, Any]]:
        if not summary_text:
            return messages
        memory_message = {
            "role": "system",
            "content": (
                "以下是该会话的长期记忆摘要，请优先保持一致性并在必要时引用：\n"
                f"{summary_text}"
            ),
        }
        return messages + [memory_message]

    @staticmethod
    def trim_history_rows(history_rows: list[LLMMessage], summarized_count: int) -> list[LLMMessage]:
        if summarized_count <= 0:
            return history_rows
        index = max(0, min(summarized_count, len(history_rows)))
        return history_rows[index:]

    @staticmethod
    def _build_summary_prompt(
        *,
        existing_summary: str | None,
        rows: list[LLMMessage],
    ) -> list[dict[str, str]]:
        rows = rows[-80:]
        transcript_lines: list[str] = []
        for row in rows:
            role = str(row.role or "").strip().lower()
            if role not in {"user", "assistant", "tool", "system"}:
                continue
            content = str(row.content or "").strip()
            if not content and role != "assistant":
                continue
            if len(content) > 1000:
                content = content[:1000]
            transcript_lines.append(f"{role}: {content}")
        transcript = "\n".join(transcript_lines)

        if existing_summary:
            user_prompt = (
                "请将【已有摘要】与【新增对话】融合为新的长期记忆，输出中文，要求：\n"
                "1) 保留用户偏好/约束/术语约定\n"
                "2) 保留已确定事实与未完成事项\n"
                "3) 删除冗余闲聊\n"
                "4) 输出结构: 偏好、上下文事实、待办、风险\n\n"
                f"【已有摘要】\n{existing_summary}\n\n"
                f"【新增对话】\n{transcript}"
            )
        else:
            user_prompt = (
                "请将下面对话整理成长期记忆摘要，输出中文，要求：\n"
                "1) 保留用户偏好/约束/术语约定\n"
                "2) 保留已确定事实与未完成事项\n"
                "3) 删除冗余闲聊\n"
                "4) 输出结构: 偏好、上下文事实、待办、风险\n\n"
                f"【对话内容】\n{transcript}"
            )

        return [
            {
                "role": "system",
                "content": "你是会话记忆压缩器，只输出可复用的结构化摘要，不输出多余解释。",
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ]

    @staticmethod
    def _to_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False)
