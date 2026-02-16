# -*- coding: utf-8 -*-

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_config
from app.core.response import api_response
from app.core.security import check_admin_existence
from app.db.session import get_db_session
from app.models.admin import Admin
from app.schemas.llm import (
    LLMChatReq,
    LLMConversationCreateReq,
    LLMSkillUpsertReq,
    MCPServerUpsertReq,
    RAGDocumentIngestReq,
    RAGRetrieveReq,
)
from app.services.llm.chat_service import ChatService
from app.services.llm.orchestrator import LLMOrchestrator

router = APIRouter()
chat_service = ChatService()
orchestrator = LLMOrchestrator(chat_service)
project_config = get_config()


@router.post("/conversations", summary="创建LLM会话")
async def create_llm_conversation(
    request_data: LLMConversationCreateReq,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    conversation = await chat_service.create_conversation(
        db,
        owner_id=admin.id,
        request_data=request_data,
    )
    data = jsonable_encoder(chat_service.conversation_to_dict(conversation))
    return api_response(data=data)


@router.get("/conversations", summary="会话列表")
async def list_llm_conversations(
    limit: int = Query(default=100, ge=1, le=300),
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    rows = await chat_service.list_conversations(
        db,
        owner_id=admin.id,
        limit=limit,
    )
    data = [chat_service.conversation_to_dict(item) for item in rows]
    return api_response(data=jsonable_encoder(data))


@router.get("/conversations/{conversation_id}", summary="会话详情")
async def llm_conversation_detail(
    conversation_id: str,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    conversation = await chat_service.get_conversation_or_raise(
        db,
        owner_id=admin.id,
        conversation_id=conversation_id,
    )
    data = jsonable_encoder(chat_service.conversation_to_dict(conversation))
    return api_response(data=data)


@router.get("/conversations/{conversation_id}/messages", summary="会话消息列表")
async def llm_conversation_messages(
    conversation_id: str,
    limit: int = Query(default=200, ge=1, le=500),
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    await chat_service.get_conversation_or_raise(
        db,
        owner_id=admin.id,
        conversation_id=conversation_id,
    )
    messages = await chat_service.list_messages(
        db,
        owner_id=admin.id,
        conversation_id=conversation_id,
        limit=limit,
    )
    data = [chat_service.message_to_dict(item) for item in messages]
    return api_response(data=jsonable_encoder(data))


@router.post("/chat", summary="LLM对话")
async def llm_chat(
    request_data: LLMChatReq,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    result = await orchestrator.run_chat(
        db,
        owner=admin,
        request_data=request_data,
    )
    return api_response(data=jsonable_encoder(result))


@router.post("/chat/stream", summary="LLM流式对话")
async def llm_chat_stream(
    request_data: LLMChatReq,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    async def event_generator():
        try:
            async for event in orchestrator.stream_chat(
                db,
                owner=admin,
                request_data=request_data,
            ):
                event_name = event.get("event", "message")
                payload = json.dumps(event, ensure_ascii=False)
                yield f"event: {event_name}\ndata: {payload}\n\n"
        except Exception as exc:
            payload = json.dumps({"event": "error", "message": str(exc)}, ensure_ascii=False)
            yield f"event: error\ndata: {payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/capabilities", summary="LLM编排能力矩阵")
async def llm_capabilities(
    _: Admin = Depends(check_admin_existence),
):
    return api_response(data=orchestrator.capability_matrix().model_dump())


@router.get("/tools", summary="可用工具列表")
async def llm_tools(
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    data = await chat_service.list_all_tool_definitions(db, owner_id=admin.id)
    return api_response(data=data)


@router.get("/skills", summary="可用Skill列表")
async def llm_skills(
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    data = await chat_service.list_skills(db, owner_id=admin.id)
    return api_response(data=data)


@router.post("/skills", summary="新增/更新Skill")
async def llm_skill_upsert(
    request_data: LLMSkillUpsertReq,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    data = await chat_service.skill_service.upsert_skill(
        db,
        owner_id=admin.id,
        skill_name=request_data.skill_name,
        description=request_data.description,
        system_prompt=request_data.system_prompt,
        tool_names=request_data.tool_names,
        rag_enabled=request_data.rag_enabled,
        mcp_server_ids=request_data.mcp_server_ids,
        extra_config=request_data.extra_config,
    )
    return api_response(data=data)


@router.get("/mcp/servers", summary="MCP服务器列表")
async def llm_mcp_servers(
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    data = await chat_service.list_mcp_servers(db, owner_id=admin.id)
    return api_response(data=data)


@router.post("/mcp/servers", summary="新增/更新MCP服务器")
async def llm_mcp_server_upsert(
    request_data: MCPServerUpsertReq,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    data = await chat_service.mcp_service.upsert_server(
        db,
        owner_id=admin.id,
        request_data=request_data.model_dump(),
    )
    return api_response(data=data)


@router.post("/rag/documents", summary="RAG文档入库")
async def llm_rag_document_ingest(
    request_data: RAGDocumentIngestReq,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    data = await chat_service.rag_service.ingest_document(
        db,
        owner_id=admin.id,
        title=request_data.title,
        content=request_data.content,
        metadata=request_data.metadata,
        chunk_size=request_data.chunk_size,
        chunk_overlap=request_data.chunk_overlap,
        embedding_provider=request_data.embedding_provider,
        embedding_model=request_data.embedding_model,
    )
    return api_response(data=data)


@router.get("/rag/documents", summary="RAG文档列表")
async def llm_rag_document_list(
    limit: int = Query(default=50, ge=1, le=200),
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    data = await chat_service.rag_service.list_documents(
        db,
        owner_id=admin.id,
        limit=limit,
    )
    return api_response(data=jsonable_encoder(data))


@router.delete("/rag/documents/{doc_id}", summary="删除RAG文档")
async def llm_rag_document_delete(
    doc_id: str,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    data = await chat_service.rag_service.remove_document(
        db,
        owner_id=admin.id,
        doc_id=doc_id,
    )
    return api_response(data=data)


@router.post("/rag/retrieve", summary="RAG检索测试")
async def llm_rag_retrieve(
    request_data: RAGRetrieveReq,
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    data = await chat_service.rag_service.retrieve_context(
        request_data.query,
        db=db,
        owner_id=admin.id,
        top_k=request_data.top_k,
        embedding_provider=request_data.embedding_provider,
        embedding_model=request_data.embedding_model,
    )
    return api_response(data=data)


@router.get("/metrics/summary", summary="LLM观测汇总")
async def llm_metrics_summary(
    days: int = Query(default=7, ge=1, le=60),
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    data = await chat_service.list_metrics_summary(
        db,
        owner_id=admin.id,
        days=days,
    )
    return api_response(data=jsonable_encoder(data))


@router.get("/metrics/recent", summary="LLM最近请求观测")
async def llm_metrics_recent(
    limit: int = Query(default=50, ge=1, le=200),
    admin: Admin = Depends(check_admin_existence),
    db: AsyncSession = Depends(get_db_session),
):
    data = await chat_service.list_recent_metrics(
        db,
        owner_id=admin.id,
        limit=limit,
    )
    return api_response(data=jsonable_encoder(data))


@router.get("/quota", summary="LLM限流与配额快照")
async def llm_quota_snapshot(
    provider: str | None = Query(default=None, description="模型厂商"),
    model: str | None = Query(default=None, description="模型名称"),
    admin: Admin = Depends(check_admin_existence),
):
    final_provider = (provider or project_config.default_llm_provider).strip().lower()
    _, default_model = chat_service.llm_client.resolve_provider(
        provider=final_provider,
        model=None,
        require_api_key=False,
    )
    final_model = (model or default_model).strip()
    data = await chat_service.get_quota_snapshot(
        owner_id=admin.id,
        provider=final_provider,
        model=final_model,
    )
    return api_response(data=data)
