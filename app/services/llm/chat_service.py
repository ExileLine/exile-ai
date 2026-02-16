# -*- coding: utf-8 -*-

from __future__ import annotations

from collections.abc import AsyncIterator
import json
import time
import uuid
from typing import Any

from loguru import logger
from sqlalchemy import asc, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_config
from app.core.exceptions import CustomException
from app.models.admin import Admin
from app.models.llm import LLMConversation, LLMMessage
from app.schemas.llm import LLMChatReq, LLMConversationCreateReq
from app.services.llm.mcp_service import MCPService
from app.services.llm.memory_service import ConversationMemoryService
from app.services.llm.observability_service import LLMObservabilityService
from app.services.llm.providers import UnifiedLLMClient
from app.services.llm.quota_service import LLMQuotaService
from app.services.llm.rag_service import RAGService
from app.services.llm.skill_service import SkillService
from app.services.llm.tool_registry import ToolRegistry, register_builtin_tools

project_config = get_config()


def build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_builtin_tools(registry)
    return registry


class ChatService:
    def __init__(
        self,
        *,
        llm_client: UnifiedLLMClient | None = None,
        tool_registry: ToolRegistry | None = None,
        rag_service: RAGService | None = None,
        skill_service: SkillService | None = None,
        mcp_service: MCPService | None = None,
        memory_service: ConversationMemoryService | None = None,
        quota_service: LLMQuotaService | None = None,
        observability_service: LLMObservabilityService | None = None,
    ):
        self.llm_client = llm_client or UnifiedLLMClient()
        self.tool_registry = tool_registry or build_default_tool_registry()
        self.rag_service = rag_service or RAGService()
        self.skill_service = skill_service or SkillService()
        self.mcp_service = mcp_service or MCPService()
        self.memory_service = memory_service or ConversationMemoryService(self.llm_client)
        self.quota_service = quota_service or LLMQuotaService()
        self.observability_service = observability_service or LLMObservabilityService()

    async def create_conversation(
        self,
        db: AsyncSession,
        *,
        owner_id: int,
        request_data: LLMConversationCreateReq | None = None,
    ) -> LLMConversation:
        data = request_data or LLMConversationCreateReq()
        provider_config, resolved_model = self.llm_client.resolve_provider(
            provider=data.provider,
            model=data.model,
            require_api_key=False,
        )
        conversation = LLMConversation(
            conversation_id=f"conv_{uuid.uuid4().hex}",
            owner_id=owner_id,
            title=(data.title or "").strip() or None,
            provider=provider_config.provider,
            model=resolved_model,
            system_prompt=(data.system_prompt or "").strip() or None,
            skill_name=(data.skill_name or "").strip() or None,
            extra_config=data.extra_config or {},
        )
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)
        return conversation

    async def get_conversation_or_raise(
        self,
        db: AsyncSession,
        *,
        owner_id: int,
        conversation_id: str,
    ) -> LLMConversation:
        stmt = select(LLMConversation).where(
            LLMConversation.conversation_id == conversation_id,
            LLMConversation.owner_id == owner_id,
            LLMConversation.is_deleted == 0,
        )
        conversation = (await db.execute(stmt)).scalars().first()
        if not conversation:
            raise CustomException(detail=f"会话 {conversation_id} 不存在", custom_code=10002)
        return conversation

    async def list_messages(
        self,
        db: AsyncSession,
        *,
        owner_id: int,
        conversation_id: str,
        limit: int = 200,
    ) -> list[LLMMessage]:
        stmt = (
            select(LLMMessage)
            .where(
                LLMMessage.conversation_id == conversation_id,
                LLMMessage.owner_id == owner_id,
                LLMMessage.is_deleted == 0,
            )
            .order_by(asc(LLMMessage.id))
            .limit(max(1, min(limit, 500)))
        )
        return list((await db.execute(stmt)).scalars().all())

    async def list_conversations(
        self,
        db: AsyncSession,
        *,
        owner_id: int,
        limit: int = 100,
    ) -> list[LLMConversation]:
        stmt = (
            select(LLMConversation)
            .where(
                LLMConversation.owner_id == owner_id,
                LLMConversation.is_deleted == 0,
            )
            .order_by(desc(LLMConversation.update_time), desc(LLMConversation.id))
            .limit(max(1, min(limit, 300)))
        )
        return list((await db.execute(stmt)).scalars().all())

    async def chat(
        self,
        db: AsyncSession,
        *,
        owner: Admin,
        request_data: LLMChatReq,
    ) -> dict[str, Any]:
        request_id = f"llmreq_{uuid.uuid4().hex}"
        started = time.perf_counter()

        conversation: LLMConversation | None = None
        primary_provider = ""
        primary_model = ""
        metric_provider = ""
        metric_model = ""
        metric_usage: dict[str, Any] = {}
        metric_success = False
        metric_error_code: str | None = None
        metric_error_message: str | None = None
        fallback_from: str | None = None
        fallback_chain: list[str] = []

        try:
            if request_data.conversation_id:
                conversation = await self.get_conversation_or_raise(
                    db,
                    owner_id=owner.id,
                    conversation_id=request_data.conversation_id,
                )
            else:
                conversation = await self.create_conversation(
                    db,
                    owner_id=owner.id,
                    request_data=LLMConversationCreateReq(
                        title=(request_data.message[:30] if request_data.message else None),
                        provider=request_data.provider,
                        model=request_data.model,
                        system_prompt=request_data.system_prompt,
                        skill_name=request_data.skill_name,
                    ),
                )

            skill_name = (request_data.skill_name or conversation.skill_name or "").strip() or None
            skill = await self.skill_service.get_skill(db, skill_name, owner_id=owner.id)
            if skill_name and not skill:
                raise CustomException(detail=f"Skill {skill_name} 不存在", custom_code=10002)

            system_prompt = (
                (request_data.system_prompt or "").strip()
                or (conversation.system_prompt or "").strip()
                or (skill.system_prompt if skill else "")
                or None
            )
            provider = (
                (request_data.provider or "").strip().lower()
                or (conversation.provider or "").strip().lower()
                or project_config.default_llm_provider
            )
            model = (request_data.model or "").strip() or (conversation.model or "").strip() or None
            provider_config, resolved_model = self.llm_client.resolve_provider(
                provider=provider,
                model=model,
                require_api_key=True,
            )
            primary_provider = provider_config.provider
            primary_model = resolved_model
            metric_provider = primary_provider
            metric_model = primary_model

            await self.quota_service.enforce_before_request(
                owner_id=owner.id,
                provider=primary_provider,
                model=primary_model,
            )

            history_rows = await self.list_messages(
                db,
                owner_id=owner.id,
                conversation_id=conversation.conversation_id,
                limit=project_config.LLM_MAX_HISTORY_MESSAGES,
            )

            summary_text, summarized_count = await self.memory_service.maybe_refresh_summary(
                db,
                conversation=conversation,
                history_rows=history_rows,
                provider=primary_provider,
                model=primary_model,
            )
            trimmed_rows = self.memory_service.trim_history_rows(history_rows, summarized_count)
            llm_messages = self._build_llm_messages(
                history_rows=trimmed_rows,
                system_prompt=system_prompt,
                summary_text=summary_text,
            )

            rag_contexts: list[dict[str, Any]] = []
            enable_rag = request_data.use_rag or (bool(skill and skill.rag_enabled))
            if enable_rag:
                rag_contexts = await self.rag_service.retrieve_context(
                    query=request_data.message,
                    db=db,
                    owner_id=owner.id,
                    top_k=request_data.rag_top_k,
                )
                if rag_contexts:
                    llm_messages.append(
                        {
                            "role": "system",
                            "content": self._format_rag_contexts(rag_contexts),
                        }
                    )

            user_text = request_data.message.strip()
            llm_messages.append({"role": "user", "content": user_text})

            selected_tool_names = []
            if request_data.use_tools:
                if request_data.tool_names:
                    selected_tool_names = request_data.tool_names
                elif skill and skill.tool_names:
                    selected_tool_names = skill.tool_names
            local_tools = (
                self.tool_registry.list_openai_tools(selected_tool_names or None)
                if request_data.use_tools
                else []
            )
            mcp_tools = (
                await self.mcp_service.list_openai_tools(
                    db,
                    owner_id=owner.id,
                    tool_names=selected_tool_names or None,
                )
                if request_data.use_tools
                else []
            )
            tools = self._merge_tool_definitions(local_tools, mcp_tools)

            (
                assistant_message,
                generated_records,
                tool_runs,
                usage_total,
                actual_provider,
                actual_model,
                fallback_from,
                fallback_chain,
            ) = await self._run_completion_with_fallback(
                llm_messages=llm_messages,
                primary_provider=primary_provider,
                primary_model=primary_model,
                temperature=request_data.temperature,
                tools=tools,
                max_tool_steps=request_data.max_tool_steps or project_config.LLM_MAX_TOOL_STEPS,
                db=db,
                owner_id=owner.id,
            )
            metric_usage = usage_total
            metric_provider = actual_provider
            metric_model = actual_model

            db.add(
                LLMMessage(
                    conversation_id=conversation.conversation_id,
                    owner_id=owner.id,
                    role="user",
                    content=user_text,
                    provider=actual_provider,
                    model=actual_model,
                    token_usage=None,
                    extra={},
                )
            )

            for item in generated_records:
                db.add(
                    LLMMessage(
                        conversation_id=conversation.conversation_id,
                        owner_id=owner.id,
                        role=item["role"],
                        content=item.get("content"),
                        tool_name=item.get("tool_name"),
                        tool_call_id=item.get("tool_call_id"),
                        tool_calls=item.get("tool_calls"),
                        provider=item.get("provider"),
                        model=item.get("model"),
                        token_usage=item.get("token_usage"),
                        extra=item.get("extra") or {},
                    )
                )

            if not conversation.title:
                conversation.title = user_text[:30]
            conversation.provider = actual_provider
            conversation.model = actual_model
            if request_data.system_prompt:
                conversation.system_prompt = request_data.system_prompt
            if request_data.skill_name:
                conversation.skill_name = request_data.skill_name
            conversation.touch()
            await db.commit()

            await self.quota_service.commit_token_usage(
                owner_id=owner.id,
                provider=actual_provider,
                model=actual_model,
                usage=usage_total,
            )

            metric_success = True
            result = {
                "conversation_id": conversation.conversation_id,
                "provider": actual_provider,
                "model": actual_model,
                "assistant_message": assistant_message,
                "tool_runs": tool_runs,
                "usage": usage_total,
                "rag_contexts": rag_contexts,
            }
            if fallback_from:
                result["fallback"] = {
                    "from": fallback_from,
                    "to": actual_provider,
                    "chain": fallback_chain,
                }
            return result
        except Exception as exc:
            metric_error_code = self._extract_error_code(exc)
            metric_error_message = str(exc)
            raise
        finally:
            latency_ms = int((time.perf_counter() - started) * 1000)
            await self.observability_service.safe_record(
                request_id=request_id,
                owner_id=owner.id,
                conversation_id=(conversation.conversation_id if conversation else request_data.conversation_id),
                provider=metric_provider or primary_provider or project_config.default_llm_provider,
                model=metric_model or primary_model or project_config.default_llm_model,
                is_stream=False,
                success=metric_success,
                latency_ms=latency_ms,
                usage=metric_usage,
                error_code=metric_error_code,
                error_message=metric_error_message,
                fallback_from=fallback_from,
                fallback_chain=fallback_chain,
                extra={"entry": "chat"},
            )

    async def chat_stream(
        self,
        db: AsyncSession,
        *,
        owner: Admin,
        request_data: LLMChatReq,
    ) -> AsyncIterator[dict[str, Any]]:
        request_id = f"llmreq_{uuid.uuid4().hex}"
        started = time.perf_counter()

        conversation: LLMConversation | None = None
        primary_provider = ""
        primary_model = ""
        selected_provider = ""
        selected_model = ""
        metric_usage: dict[str, Any] = {}
        metric_success = False
        metric_error_code: str | None = None
        metric_error_message: str | None = None
        fallback_from: str | None = None
        fallback_chain: list[str] = []
        assistant_parts: list[str] = []
        usage_total: dict[str, Any] = {}
        finish_reason: str | None = None

        try:
            if request_data.conversation_id:
                conversation = await self.get_conversation_or_raise(
                    db,
                    owner_id=owner.id,
                    conversation_id=request_data.conversation_id,
                )
            else:
                conversation = await self.create_conversation(
                    db,
                    owner_id=owner.id,
                    request_data=LLMConversationCreateReq(
                        title=(request_data.message[:30] if request_data.message else None),
                        provider=request_data.provider,
                        model=request_data.model,
                        system_prompt=request_data.system_prompt,
                        skill_name=request_data.skill_name,
                    ),
                )

            skill_name = (request_data.skill_name or conversation.skill_name or "").strip() or None
            skill = await self.skill_service.get_skill(db, skill_name, owner_id=owner.id)
            if skill_name and not skill:
                raise CustomException(detail=f"Skill {skill_name} 不存在", custom_code=10002)

            system_prompt = (
                (request_data.system_prompt or "").strip()
                or (conversation.system_prompt or "").strip()
                or (skill.system_prompt if skill else "")
                or None
            )
            provider = (
                (request_data.provider or "").strip().lower()
                or (conversation.provider or "").strip().lower()
                or project_config.default_llm_provider
            )
            model = (request_data.model or "").strip() or (conversation.model or "").strip() or None
            provider_config, resolved_model = self.llm_client.resolve_provider(
                provider=provider,
                model=model,
                require_api_key=True,
            )
            primary_provider = provider_config.provider
            primary_model = resolved_model
            selected_provider = primary_provider
            selected_model = primary_model

            await self.quota_service.enforce_before_request(
                owner_id=owner.id,
                provider=primary_provider,
                model=primary_model,
            )

            history_rows = await self.list_messages(
                db,
                owner_id=owner.id,
                conversation_id=conversation.conversation_id,
                limit=project_config.LLM_MAX_HISTORY_MESSAGES,
            )
            summary_text, summarized_count = await self.memory_service.maybe_refresh_summary(
                db,
                conversation=conversation,
                history_rows=history_rows,
                provider=primary_provider,
                model=primary_model,
            )
            trimmed_rows = self.memory_service.trim_history_rows(history_rows, summarized_count)
            llm_messages = self._build_llm_messages(
                history_rows=trimmed_rows,
                system_prompt=system_prompt,
                summary_text=summary_text,
            )

            rag_contexts: list[dict[str, Any]] = []
            enable_rag = request_data.use_rag or (bool(skill and skill.rag_enabled))
            if enable_rag:
                rag_contexts = await self.rag_service.retrieve_context(
                    query=request_data.message,
                    db=db,
                    owner_id=owner.id,
                    top_k=request_data.rag_top_k,
                )
                if rag_contexts:
                    llm_messages.append(
                        {
                            "role": "system",
                            "content": self._format_rag_contexts(rag_contexts),
                        }
                    )

            user_text = request_data.message.strip()
            llm_messages.append({"role": "user", "content": user_text})

            warning = None
            if request_data.use_tools:
                warning = "流式模式暂不支持 Function Calling，已自动关闭工具调用。"

            db.add(
                LLMMessage(
                    conversation_id=conversation.conversation_id,
                    owner_id=owner.id,
                    role="user",
                    content=user_text,
                    provider=primary_provider,
                    model=primary_model,
                    token_usage=None,
                    extra={"stream": True},
                )
            )
            if not conversation.title:
                conversation.title = user_text[:30]
            conversation.provider = primary_provider
            conversation.model = primary_model
            if request_data.system_prompt:
                conversation.system_prompt = request_data.system_prompt
            if request_data.skill_name:
                conversation.skill_name = request_data.skill_name
            conversation.touch()
            await db.commit()

            yielded_meta = False
            stream_error: Exception | None = None
            provider_candidates = self._provider_candidates(primary_provider)

            for idx, candidate_provider in enumerate(provider_candidates):
                model_for_candidate = primary_model if candidate_provider == primary_provider else None
                try:
                    candidate_cfg, candidate_model = self.llm_client.resolve_provider(
                        provider=candidate_provider,
                        model=model_for_candidate,
                        require_api_key=True,
                    )
                except Exception as exc:
                    stream_error = exc
                    fallback_chain.append(candidate_provider)
                    if not self._is_fallback_candidate_error(exc):
                        raise
                    continue

                fallback_chain.append(candidate_cfg.provider)
                candidate_warning = warning
                if idx > 0:
                    candidate_warning = (
                        f"主模型 {primary_provider}/{primary_model} 调用失败，已切换到 "
                        f"{candidate_cfg.provider}/{candidate_model}"
                    )

                if not yielded_meta or idx > 0:
                    yield {
                        "event": "meta",
                        "conversation_id": conversation.conversation_id,
                        "provider": candidate_cfg.provider,
                        "model": candidate_model,
                        "warning": candidate_warning,
                    }
                    yielded_meta = True

                got_chunk = False
                try:
                    async for chunk in self.llm_client.chat_completion_stream(
                        messages=llm_messages,
                        provider=candidate_cfg.provider,
                        model=candidate_model,
                        temperature=request_data.temperature,
                    ):
                        if chunk.get("type") != "chunk":
                            continue
                        if not got_chunk:
                            got_chunk = True
                            selected_provider = chunk.get("provider") or candidate_cfg.provider
                            selected_model = chunk.get("model") or candidate_model
                            if idx > 0:
                                fallback_from = primary_provider

                        usage_total = self._merge_usage(usage_total, chunk.get("usage") or {})
                        finish_reason = chunk.get("finish_reason") or finish_reason
                        delta_text = self._extract_delta_text(chunk.get("delta") or {})
                        if delta_text:
                            assistant_parts.append(delta_text)
                            yield {
                                "event": "delta",
                                "conversation_id": conversation.conversation_id,
                                "delta": delta_text,
                            }

                    if not got_chunk:
                        selected_provider = candidate_cfg.provider
                        selected_model = candidate_model
                        if idx > 0:
                            fallback_from = primary_provider
                    stream_error = None
                    break
                except Exception as exc:
                    stream_error = exc
                    if got_chunk:
                        raise
                    if not self._is_fallback_candidate_error(exc):
                        raise
                    continue

            if stream_error:
                raise stream_error

            assistant_text = "".join(assistant_parts).strip()
            db.add(
                LLMMessage(
                    conversation_id=conversation.conversation_id,
                    owner_id=owner.id,
                    role="assistant",
                    content=assistant_text,
                    provider=selected_provider,
                    model=selected_model,
                    token_usage=usage_total,
                    extra={"stream": True, "finish_reason": finish_reason},
                )
            )
            conversation.provider = selected_provider
            conversation.model = selected_model
            conversation.touch()
            await db.commit()

            await self.quota_service.commit_token_usage(
                owner_id=owner.id,
                provider=selected_provider,
                model=selected_model,
                usage=usage_total,
            )

            metric_usage = usage_total
            metric_success = True
            yield {
                "event": "done",
                "conversation_id": conversation.conversation_id,
                "provider": selected_provider,
                "model": selected_model,
                "assistant_message": assistant_text,
                "usage": usage_total,
                "finish_reason": finish_reason,
                "fallback": (
                    {
                        "from": fallback_from,
                        "to": selected_provider,
                        "chain": fallback_chain,
                    }
                    if fallback_from
                    else None
                ),
            }
            return
        except Exception as exc:
            metric_error_code = self._extract_error_code(exc)
            metric_error_message = str(exc)
            assistant_text = "".join(assistant_parts).strip()
            if conversation and assistant_text:
                try:
                    db.add(
                        LLMMessage(
                            conversation_id=conversation.conversation_id,
                            owner_id=owner.id,
                            role="assistant",
                            content=assistant_text,
                            provider=selected_provider or primary_provider,
                            model=selected_model or primary_model,
                            token_usage=usage_total,
                            extra={"stream": True, "partial": True, "error": str(exc)},
                        )
                    )
                    conversation.touch()
                    await db.commit()
                except Exception:
                    logger.exception("写入流式部分响应失败")

            yield {
                "event": "error",
                "conversation_id": conversation.conversation_id if conversation else request_data.conversation_id,
                "message": str(exc),
            }
            return
        finally:
            latency_ms = int((time.perf_counter() - started) * 1000)
            await self.observability_service.safe_record(
                request_id=request_id,
                owner_id=owner.id,
                conversation_id=(conversation.conversation_id if conversation else request_data.conversation_id),
                provider=selected_provider or primary_provider or project_config.default_llm_provider,
                model=selected_model or primary_model or project_config.default_llm_model,
                is_stream=True,
                success=metric_success,
                latency_ms=latency_ms,
                usage=metric_usage or usage_total,
                error_code=metric_error_code,
                error_message=metric_error_message,
                fallback_from=fallback_from,
                fallback_chain=fallback_chain,
                extra={"entry": "chat_stream"},
            )

    async def _run_completion_with_fallback(
        self,
        *,
        llm_messages: list[dict[str, Any]],
        primary_provider: str,
        primary_model: str,
        temperature: float | None,
        tools: list[dict[str, Any]],
        max_tool_steps: int,
        db: AsyncSession,
        owner_id: int,
    ) -> tuple[str | None, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], str, str, str | None, list[str]]:
        fallback_from: str | None = None
        fallback_chain: list[str] = []
        last_error: Exception | None = None

        candidates = self._provider_candidates(primary_provider)
        for idx, candidate_provider in enumerate(candidates):
            model_for_candidate = primary_model if candidate_provider == primary_provider else None
            try:
                candidate_config, candidate_model = self.llm_client.resolve_provider(
                    provider=candidate_provider,
                    model=model_for_candidate,
                    require_api_key=True,
                )
            except Exception as exc:
                fallback_chain.append(candidate_provider)
                last_error = exc
                if not self._is_fallback_candidate_error(exc):
                    raise
                continue

            fallback_chain.append(candidate_config.provider)
            try:
                (
                    assistant_message,
                    generated_records,
                    tool_runs,
                    usage_total,
                    actual_provider,
                    actual_model,
                ) = await self._run_completion_with_tools(
                    llm_messages=llm_messages,
                    provider=candidate_config.provider,
                    model=candidate_model,
                    temperature=temperature,
                    tools=tools,
                    max_tool_steps=max_tool_steps,
                    db=db,
                    owner_id=owner_id,
                )
                if idx > 0:
                    fallback_from = primary_provider
                return (
                    assistant_message,
                    generated_records,
                    tool_runs,
                    usage_total,
                    actual_provider,
                    actual_model,
                    fallback_from,
                    fallback_chain,
                )
            except Exception as exc:
                last_error = exc
                if not self._is_fallback_candidate_error(exc):
                    raise
                continue

        if last_error:
            raise last_error
        raise CustomException(detail="模型调用失败，且无可用回退厂商", custom_code=10005)

    async def _run_completion_with_tools(
        self,
        *,
        llm_messages: list[dict[str, Any]],
        provider: str,
        model: str,
        temperature: float | None,
        tools: list[dict[str, Any]],
        max_tool_steps: int,
        db: AsyncSession,
        owner_id: int,
    ) -> tuple[str | None, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], str, str]:
        working_messages = list(llm_messages)
        generated_records: list[dict[str, Any]] = []
        tool_runs: list[dict[str, Any]] = []
        usage_total: dict[str, Any] = {}
        assistant_text: str | None = None
        actual_provider = provider
        actual_model = model
        tool_call_pending = False

        for _ in range(max(1, max_tool_steps)):
            completion = await self.llm_client.chat_completion(
                messages=working_messages,
                provider=actual_provider,
                model=actual_model,
                temperature=temperature,
                tools=tools,
                tool_choice="auto",
            )
            actual_provider = completion["provider"]
            actual_model = completion["model"]
            usage_total = self._merge_usage(usage_total, completion.get("usage") or {})

            message = completion.get("message") or {}
            tool_calls = message.get("tool_calls") or []
            assistant_text = self._to_text(message.get("content"))
            assistant_llm_message = {
                "role": "assistant",
                "content": assistant_text or "",
            }
            if tool_calls:
                assistant_llm_message["tool_calls"] = tool_calls
            working_messages.append(assistant_llm_message)

            generated_records.append(
                {
                    "role": "assistant",
                    "content": assistant_text,
                    "tool_calls": tool_calls if tool_calls else None,
                    "provider": actual_provider,
                    "model": actual_model,
                    "token_usage": completion.get("usage") or {},
                    "extra": {},
                }
            )

            if not tool_calls:
                tool_call_pending = False
                break

            tool_call_pending = True
            for tool_call in tool_calls:
                try:
                    tool_result = await self.tool_registry.execute_tool_call(tool_call)
                except CustomException as exc:
                    if exc.custom_code != 10002:
                        raise
                    tool_result = await self.mcp_service.execute_tool_call(
                        db,
                        owner_id=owner_id,
                        tool_call=tool_call,
                    )
                tool_runs.append(tool_result)
                tool_message = {
                    "role": "tool",
                    "tool_call_id": tool_result.get("tool_call_id"),
                    "content": tool_result.get("content") or "",
                }
                working_messages.append(tool_message)

                generated_records.append(
                    {
                        "role": "tool",
                        "content": tool_result.get("content"),
                        "tool_name": tool_result.get("tool_name"),
                        "tool_call_id": tool_result.get("tool_call_id"),
                        "provider": None,
                        "model": None,
                        "token_usage": None,
                        "extra": {
                            "ok": tool_result.get("ok"),
                            "arguments": tool_result.get("arguments"),
                        },
                    }
                )

        if tool_call_pending:
            assistant_text = "工具调用达到上限，请缩小问题范围后重试。"
            generated_records.append(
                {
                    "role": "assistant",
                    "content": assistant_text,
                    "tool_calls": None,
                    "provider": actual_provider,
                    "model": actual_model,
                    "token_usage": None,
                    "extra": {"reason": "max_tool_steps_exceeded"},
                }
            )

        return assistant_text, generated_records, tool_runs, usage_total, actual_provider, actual_model

    async def list_metrics_summary(
        self,
        db: AsyncSession,
        *,
        owner_id: int,
        days: int = 7,
    ) -> dict[str, Any]:
        return await self.observability_service.summary(db, owner_id=owner_id, days=days)

    async def list_recent_metrics(
        self,
        db: AsyncSession,
        *,
        owner_id: int,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return await self.observability_service.recent(db, owner_id=owner_id, limit=limit)

    async def get_quota_snapshot(
        self,
        *,
        owner_id: int,
        provider: str,
        model: str,
    ) -> dict[str, Any]:
        return await self.quota_service.snapshot(
            owner_id=owner_id,
            provider=provider,
            model=model,
        )

    @staticmethod
    def _to_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _extract_delta_text(delta: dict[str, Any]) -> str:
        value = delta.get("content")
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            text = value.get("text") or value.get("content")
            if isinstance(text, str):
                return text
            parts = value.get("parts")
            if isinstance(parts, list):
                text_parts: list[str] = []
                for item in parts:
                    if isinstance(item, str):
                        text_parts.append(item)
                    elif isinstance(item, dict):
                        t = item.get("text")
                        if isinstance(t, str):
                            text_parts.append(t)
                return "".join(text_parts)
        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "".join(parts)
        return ""

    @staticmethod
    def _merge_usage(current: dict[str, Any], new_usage: dict[str, Any]) -> dict[str, Any]:
        merged = dict(current)
        for key, value in new_usage.items():
            if isinstance(value, (int, float)) and isinstance(merged.get(key), (int, float)):
                merged[key] = merged[key] + value
            elif isinstance(value, (int, float)) and key not in merged:
                merged[key] = value
            elif key not in merged:
                merged[key] = value
        return merged

    def _build_llm_messages(
        self,
        *,
        history_rows: list[LLMMessage],
        system_prompt: str | None,
        summary_text: str | None = None,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if summary_text:
            messages = self.memory_service.apply_memory(messages=messages, summary_text=summary_text)

        for row in history_rows:
            if row.role not in {"user", "assistant", "tool", "system"}:
                continue
            message = {
                "role": row.role,
                "content": row.content or "",
            }
            if row.role == "assistant" and row.tool_calls:
                message["tool_calls"] = row.tool_calls
            if row.role == "tool" and row.tool_call_id:
                message["tool_call_id"] = row.tool_call_id
            messages.append(message)
        return messages

    @staticmethod
    def _format_rag_contexts(items: list[dict[str, Any]]) -> str:
        lines = ["以下是检索到的上下文，请在回答中优先参考："]
        for idx, item in enumerate(items, start=1):
            text = str(item.get("content") or "").strip()
            if not text:
                continue
            lines.append(f"[{idx}] {text}")
        return "\n".join(lines)

    def _provider_candidates(self, primary_provider: str) -> list[str]:
        primary = (primary_provider or project_config.default_llm_provider).strip().lower()
        if not project_config.LLM_AUTO_FALLBACK_ENABLE:
            return [primary]

        fallback_list = [x.strip().lower() for x in (project_config.LLM_FALLBACK_PROVIDERS or "").split(",") if x.strip()]
        candidates: list[str] = []
        for name in [primary] + fallback_list:
            if not name or name in candidates:
                continue
            candidates.append(name)
        return candidates or [primary]

    @staticmethod
    def _extract_error_code(exc: Exception) -> str | None:
        if isinstance(exc, CustomException):
            return str(exc.custom_code)
        return exc.__class__.__name__

    @staticmethod
    def _is_fallback_candidate_error(exc: Exception) -> bool:
        if not isinstance(exc, CustomException):
            return True
        detail = str(exc.detail)
        markers = [
            "模型请求失败",
            "模型流式请求失败",
            "模型返回为空",
            "API key 未配置",
            "base_url 未配置",
            "不支持的模型厂商",
        ]
        return any(marker in detail for marker in markers)

    def list_tool_definitions(self) -> list[dict[str, Any]]:
        return self.tool_registry.list_tools()

    async def list_all_tool_definitions(
        self,
        db: AsyncSession | None,
        *,
        owner_id: int | None = None,
    ) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = list(self.tool_registry.list_tools())
        mcp_tools = await self.mcp_service.list_openai_tools(db, owner_id=owner_id, include_meta=True)
        for item in mcp_tools:
            fn = item.get("function") or {}
            tools.append(
                {
                    "name": fn.get("name"),
                    "description": fn.get("description"),
                    "parameters": fn.get("parameters"),
                    "source": "mcp",
                    "mcp": item.get("_mcp"),
                }
            )
        return tools

    async def list_skills(
        self,
        db: AsyncSession | None,
        *,
        owner_id: int | None = None,
    ) -> list[dict]:
        return await self.skill_service.list_skills(db, owner_id=owner_id)

    async def list_mcp_servers(
        self,
        db: AsyncSession | None,
        *,
        owner_id: int | None = None,
    ) -> list[dict]:
        return await self.mcp_service.list_servers(db, owner_id=owner_id)

    @staticmethod
    def conversation_to_dict(conversation: LLMConversation) -> dict[str, Any]:
        return {
            "conversation_id": conversation.conversation_id,
            "title": conversation.title,
            "provider": conversation.provider,
            "model": conversation.model,
            "system_prompt": conversation.system_prompt,
            "skill_name": conversation.skill_name,
            "extra_config": conversation.extra_config or {},
            "create_time": conversation.create_time,
            "update_time": conversation.update_time,
        }

    @staticmethod
    def message_to_dict(message: LLMMessage) -> dict[str, Any]:
        return {
            "role": message.role,
            "content": message.content,
            "tool_name": message.tool_name,
            "tool_call_id": message.tool_call_id,
            "tool_calls": message.tool_calls,
            "provider": message.provider,
            "model": message.model,
            "token_usage": message.token_usage,
            "extra": message.extra,
            "create_time": message.create_time,
        }

    @staticmethod
    def _merge_tool_definitions(local_tools: list[dict[str, Any]], mcp_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen = set()
        for item in local_tools + mcp_tools:
            fn = item.get("function") if isinstance(item, dict) else None
            name = (fn or {}).get("name")
            if not name or name in seen:
                continue
            seen.add(name)
            merged.append(item)
        return merged
