# -*- coding: utf-8 -*-

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_config
from app.core.exceptions import CustomException
from app.models.admin import Admin
from app.schemas.llm import LLMChatReq
from app.services.llm.chat_service import ChatService
from app.services.llm.contracts import CapabilityMatrix, OrchestratorMode

project_config = get_config()


class LLMOrchestrator:
    """对外统一编排入口。当前支持 legacy 与 langgraph 两种模式。"""

    def __init__(self, chat_service: ChatService):
        self.chat_service = chat_service

    @property
    def mode(self) -> OrchestratorMode:
        raw_mode = (project_config.LLM_ORCHESTRATOR or "legacy").strip().lower()
        if raw_mode == OrchestratorMode.langgraph.value:
            return OrchestratorMode.langgraph
        return OrchestratorMode.legacy

    async def run_chat(
        self,
        db: AsyncSession,
        *,
        owner: Admin,
        request_data: LLMChatReq,
    ) -> dict[str, Any]:
        if self.mode == OrchestratorMode.langgraph:
            return await self._run_with_langgraph(db, owner=owner, request_data=request_data)
        return await self.chat_service.chat(db, owner=owner, request_data=request_data)

    async def stream_chat(
        self,
        db: AsyncSession,
        *,
        owner: Admin,
        request_data: LLMChatReq,
    ) -> AsyncIterator[dict[str, Any]]:
        if self.mode == OrchestratorMode.langgraph:
            # 先复用现有流式通路；后续改为 LangGraph 节点级流式事件。
            async for event in self.chat_service.chat_stream(db, owner=owner, request_data=request_data):
                yield event
            return

        async for event in self.chat_service.chat_stream(db, owner=owner, request_data=request_data):
            yield event

    def capability_matrix(self) -> CapabilityMatrix:
        mode = self.mode
        if mode == OrchestratorMode.langgraph:
            return CapabilityMatrix(
                orchestrator_mode=mode,
                multi_turn=True,
                function_calling=True,
                sse_streaming=True,
                mcp=True,
                rag=True,
                skill=True,
                human_approval=False,
                resumable_execution=False,
                details={
                    "checkpoint_backend": project_config.LLM_AGENT_CHECKPOINT_BACKEND,
                    "approval_mode": project_config.LLM_AGENT_APPROVAL_MODE,
                    "max_steps": project_config.LLM_AGENT_MAX_STEPS,
                    "observability": True,
                    "rate_limit_quota": bool(project_config.LLM_RATE_LIMIT_ENABLE),
                    "memory_summary": bool(project_config.LLM_MEMORY_ENABLE),
                    "auto_fallback": bool(project_config.LLM_AUTO_FALLBACK_ENABLE),
                    "planned_capabilities": [
                        "mcp",
                        "rag",
                        "human_approval",
                        "resumable_execution",
                    ],
                },
            )

        return CapabilityMatrix(
            orchestrator_mode=mode,
            multi_turn=True,
            function_calling=True,
            sse_streaming=True,
            mcp=True,
            rag=True,
            skill=True,
            human_approval=False,
            resumable_execution=False,
            details={
                "checkpoint_backend": "not_enabled",
                "approval_mode": "not_enabled",
                "max_steps": project_config.LLM_MAX_TOOL_STEPS,
                "observability": True,
                "rate_limit_quota": bool(project_config.LLM_RATE_LIMIT_ENABLE),
                "memory_summary": bool(project_config.LLM_MEMORY_ENABLE),
                "auto_fallback": bool(project_config.LLM_AUTO_FALLBACK_ENABLE),
            },
        )

    async def _run_with_langgraph(
        self,
        db: AsyncSession,
        *,
        owner: Admin,
        request_data: LLMChatReq,
    ) -> dict[str, Any]:
        try:
            from langgraph.graph import END, START, StateGraph
        except Exception as exc:
            raise CustomException(
                detail=f"LLM_ORCHESTRATOR=langgraph 但 LangGraph 不可用: {exc}",
                custom_code=10005,
            )

        class GraphState(dict):
            pass

        async def execute_node(state: GraphState):
            result = await self.chat_service.chat(db, owner=owner, request_data=request_data)
            state["result"] = result
            return state

        graph_builder = StateGraph(GraphState)
        graph_builder.add_node("execute", execute_node)
        graph_builder.add_edge(START, "execute")
        graph_builder.add_edge("execute", END)
        graph = graph_builder.compile()

        graph_state = await graph.ainvoke(GraphState())
        result = graph_state.get("result")
        if not isinstance(result, dict):
            raise CustomException(detail="LangGraph执行结果异常", custom_code=10005)
        return result
