# -*- coding: utf-8 -*-

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class OrchestratorMode(str, Enum):
    legacy = "legacy"
    langgraph = "langgraph"


class AgentRunStatus(str, Enum):
    running = "running"
    waiting_approval = "waiting_approval"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class SSEEventType(str, Enum):
    meta = "meta"
    delta = "delta"
    done = "done"
    error = "error"


class CapabilityMatrix(BaseModel):
    orchestrator_mode: OrchestratorMode
    multi_turn: bool = True
    function_calling: bool = True
    sse_streaming: bool = True
    mcp: bool = False
    rag: bool = False
    skill: bool = True
    human_approval: bool = False
    resumable_execution: bool = False

    details: dict[str, Any] = Field(default_factory=dict)


class AgentStateEnvelope(BaseModel):
    """统一状态载体，作为 Agent 编排输入/输出契约。"""

    conversation_id: str
    owner_id: int
    provider: str
    model: str
    step: int = 0
    max_steps: int = 8
    status: AgentRunStatus = AgentRunStatus.running
    waiting_approval: bool = False
    approval_reason: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
