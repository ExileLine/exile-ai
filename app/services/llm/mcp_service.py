# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_config
from app.core.exceptions import CustomException
from app.models.llm import MCPServer

project_config = get_config()


class MCPService:
    """MCP Server Registry + Tool Adapter 最小版。"""

    async def list_servers(
        self,
        db: AsyncSession | None,
        *,
        owner_id: int | None = None,
    ) -> list[dict]:
        if db is None:
            return []
        stmt = select(MCPServer).where(
            MCPServer.is_deleted == 0,
            or_(MCPServer.status == 1, MCPServer.status.is_(None)),
            or_(MCPServer.owner_id == owner_id, MCPServer.owner_id.is_(None)),
        )
        rows = list((await db.execute(stmt)).scalars().all())
        rows.sort(key=lambda item: (item.owner_id != owner_id, item.name))
        return [self._row_to_dict(item) for item in rows]

    async def upsert_server(
        self,
        db: AsyncSession,
        *,
        owner_id: int,
        request_data: dict[str, Any],
    ) -> dict[str, Any]:
        server_id = str(request_data.get("server_id") or "").strip()
        if not server_id:
            raise CustomException(detail="server_id 不能为空", custom_code=10001)
        stmt = select(MCPServer).where(
            MCPServer.server_id == server_id,
            MCPServer.owner_id == owner_id,
            MCPServer.is_deleted == 0,
        )
        row = (await db.execute(stmt)).scalars().first()
        enabled = 1 if bool(request_data.get("enabled", True)) else 0

        if row:
            row.name = str(request_data.get("name") or row.name)
            row.transport = str(request_data.get("transport") or row.transport)
            row.endpoint = request_data.get("endpoint")
            row.command = request_data.get("command")
            row.args = request_data.get("args") or []
            row.env = request_data.get("env") or {}
            row.timeout_seconds = int(request_data.get("timeout_seconds") or row.timeout_seconds or 30)
            row.enabled = enabled
            row.tool_definitions = request_data.get("tool_definitions") or []
            row.extra_config = request_data.get("extra_config") or {}
            row.status = 1
            row.touch()
        else:
            row = MCPServer(
                server_id=server_id,
                owner_id=owner_id,
                name=str(request_data.get("name") or server_id),
                transport=str(request_data.get("transport") or "http"),
                endpoint=request_data.get("endpoint"),
                command=request_data.get("command"),
                args=request_data.get("args") or [],
                env=request_data.get("env") or {},
                timeout_seconds=int(request_data.get("timeout_seconds") or 30),
                enabled=enabled,
                tool_definitions=request_data.get("tool_definitions") or [],
                extra_config=request_data.get("extra_config") or {},
                status=1,
            )
            db.add(row)

        await db.commit()
        await db.refresh(row)
        return self._row_to_dict(row)

    async def list_openai_tools(
        self,
        db: AsyncSession | None,
        *,
        owner_id: int | None = None,
        tool_names: list[str] | None = None,
        include_meta: bool = False,
    ) -> list[dict[str, Any]]:
        if db is None:
            return []
        tool_filter = set(tool_names or [])
        tools: list[dict[str, Any]] = []
        servers = await self.list_servers(db, owner_id=owner_id)
        for server in servers:
            if not server.get("enabled"):
                continue
            for tool in server.get("tool_definitions") or []:
                name = str(tool.get("name") or "").strip()
                if not name:
                    continue
                if tool_filter and name not in tool_filter:
                    continue
                item = {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": str(tool.get("description") or f"MCP tool from {server.get('name')}"),
                        "parameters": tool.get("parameters") or {
                            "type": "object",
                            "properties": {},
                        },
                    },
                }
                if include_meta:
                    item["_mcp"] = {
                        "server_id": server.get("server_id"),
                        "transport": server.get("transport"),
                        "endpoint": server.get("endpoint"),
                    }
                tools.append(item)
        return tools

    async def execute_tool_call(
        self,
        db: AsyncSession | None,
        *,
        owner_id: int | None,
        tool_call: dict[str, Any],
    ) -> dict[str, Any]:
        if db is None:
            raise CustomException(detail="MCP 执行需要数据库会话", custom_code=10005)

        call_id = tool_call.get("id") or f"mcp_toolcall_{uuid.uuid4().hex}"
        function_block = tool_call.get("function") or {}
        tool_name = str(function_block.get("name") or "").strip()
        if not tool_name:
            raise CustomException(detail="工具调用缺少 name", custom_code=10005)
        arguments_text = function_block.get("arguments") or "{}"
        try:
            arguments = json.loads(arguments_text)
        except json.JSONDecodeError:
            arguments = {"raw": arguments_text}

        server_row = await self._find_server_by_tool_name(db, owner_id=owner_id, tool_name=tool_name)
        if not server_row:
            raise CustomException(detail=f"MCP 工具 {tool_name} 未注册", custom_code=10002)
        if not server_row.enabled:
            raise CustomException(detail=f"MCP 服务器 {server_row.server_id} 已禁用", custom_code=10005)

        transport = (server_row.transport or "http").lower()
        if transport == "mock":
            result = {
                "server_id": server_row.server_id,
                "tool_name": tool_name,
                "arguments": arguments,
                "transport": "mock",
            }
            return self._tool_call_result(call_id, tool_name, arguments, result, ok=True)

        if transport == "http":
            endpoint = (server_row.endpoint or "").strip()
            if not endpoint:
                raise CustomException(
                    detail=f"MCP 服务器 {server_row.server_id} endpoint 未配置",
                    custom_code=10005,
                )
            timeout = max(1, int(server_row.timeout_seconds or 30))
            payload = {
                "tool_name": tool_name,
                "arguments": arguments,
                "server_id": server_row.server_id,
            }
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(endpoint, json=payload)
                if resp.status_code >= 400:
                    return self._tool_call_result(
                        call_id,
                        tool_name,
                        arguments,
                        {
                            "error": f"MCP HTTP 调用失败({resp.status_code})",
                            "body": resp.text[:800],
                        },
                        ok=False,
                    )
                result = resp.json()
                return self._tool_call_result(call_id, tool_name, arguments, result, ok=True)
            except Exception as exc:
                return self._tool_call_result(
                    call_id,
                    tool_name,
                    arguments,
                    {"error": str(exc)},
                    ok=False,
                )

        raise CustomException(detail=f"暂不支持的 MCP transport: {transport}", custom_code=10005)

    async def _find_server_by_tool_name(
        self,
        db: AsyncSession,
        *,
        owner_id: int | None,
        tool_name: str,
    ) -> MCPServer | None:
        stmt = select(MCPServer).where(
            MCPServer.is_deleted == 0,
            or_(MCPServer.status == 1, MCPServer.status.is_(None)),
            or_(MCPServer.owner_id == owner_id, MCPServer.owner_id.is_(None)),
        )
        rows = list((await db.execute(stmt)).scalars().all())
        rows.sort(key=lambda item: (item.owner_id != owner_id, item.name))
        for row in rows:
            for tool in row.tool_definitions or []:
                if str(tool.get("name") or "").strip() == tool_name:
                    return row
        return None

    @staticmethod
    def _tool_call_result(
        call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        result: Any,
        *,
        ok: bool,
    ) -> dict[str, Any]:
        return {
            "ok": ok,
            "tool_call_id": call_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "content": json.dumps({"ok": ok, "result": result}, ensure_ascii=False),
        }

    @staticmethod
    def _row_to_dict(row: MCPServer) -> dict[str, Any]:
        return {
            "server_id": row.server_id,
            "owner_id": row.owner_id,
            "name": row.name,
            "transport": row.transport,
            "endpoint": row.endpoint,
            "command": row.command,
            "args": row.args or [],
            "env": row.env or {},
            "timeout_seconds": row.timeout_seconds,
            "enabled": bool(row.enabled),
            "tool_definitions": row.tool_definitions or [],
            "extra_config": row.extra_config or {},
        }
