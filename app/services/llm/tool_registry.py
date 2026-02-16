# -*- coding: utf-8 -*-

from __future__ import annotations

import ast
import inspect
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable

import pytz

from app.core.exceptions import CustomException

ToolExecutor = Callable[[dict[str, Any]], Any | Awaitable[Any]]


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    executor: ToolExecutor


class ToolRegistry:
    """Function Calling 工具注册中心"""

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition):
        if tool.name in self._tools:
            raise CustomException(detail=f"工具 {tool.name} 已存在", custom_code=10005)
        self._tools[tool.name] = tool

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in self._tools.values()
        ]

    def list_openai_tools(self, tool_names: list[str] | None = None) -> list[dict[str, Any]]:
        selected_names = tool_names or list(self._tools.keys())
        tools: list[dict[str, Any]] = []
        for name in selected_names:
            tool = self._tools.get(name)
            if not tool:
                raise CustomException(detail=f"工具 {name} 未注册", custom_code=10002)
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
            )
        return tools

    async def execute_tool_call(self, tool_call: dict[str, Any]) -> dict[str, Any]:
        call_id = tool_call.get("id") or f"toolcall_{uuid.uuid4().hex}"
        function_block = tool_call.get("function") or {}
        tool_name = function_block.get("name")
        arguments_text = function_block.get("arguments") or "{}"

        if not tool_name:
            raise CustomException(detail="工具调用缺少 name", custom_code=10005)
        tool = self._tools.get(tool_name)
        if not tool:
            raise CustomException(detail=f"工具 {tool_name} 未注册", custom_code=10002)

        try:
            arguments = json.loads(arguments_text)
        except json.JSONDecodeError:
            arguments = {"raw": arguments_text}

        try:
            result = tool.executor(arguments)
            if inspect.isawaitable(result):
                result = await result  # type: ignore[assignment]
            content = json.dumps({"ok": True, "result": result}, ensure_ascii=False)
            ok = True
        except Exception as exc:
            content = json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
            ok = False

        return {
            "ok": ok,
            "tool_call_id": call_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "content": content,
        }


def register_builtin_tools(registry: ToolRegistry):
    registry.register(
        ToolDefinition(
            name="get_current_time",
            description="获取指定时区的当前时间",
            parameters={
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "时区名称，例如 Asia/Shanghai, UTC",
                        "default": "Asia/Shanghai",
                    },
                    "format": {
                        "type": "string",
                        "description": "时间格式，默认 %Y-%m-%d %H:%M:%S",
                        "default": "%Y-%m-%d %H:%M:%S",
                    },
                },
            },
            executor=_tool_get_current_time,
        )
    )
    registry.register(
        ToolDefinition(
            name="calculate",
            description="执行基础数学表达式计算，仅支持 + - * / // % ** 与括号",
            parameters={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式，例如 (3+5)*2",
                    }
                },
                "required": ["expression"],
            },
            executor=_tool_calculate,
        )
    )
    registry.register(
        ToolDefinition(
            name="echo",
            description="回显输入文本",
            parameters={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "需要原样返回的文本",
                    }
                },
                "required": ["text"],
            },
            executor=_tool_echo,
        )
    )


def _tool_get_current_time(args: dict[str, Any]) -> dict[str, str]:
    tz_name = str(args.get("timezone") or "Asia/Shanghai")
    fmt = str(args.get("format") or "%Y-%m-%d %H:%M:%S")
    tz = pytz.timezone(tz_name)
    now = datetime.now(tz)
    return {
        "timezone": tz_name,
        "value": now.strftime(fmt),
    }


def _tool_calculate(args: dict[str, Any]) -> dict[str, Any]:
    expression = str(args.get("expression") or "").strip()
    if not expression:
        raise ValueError("expression 不能为空")
    value = _safe_eval_expression(expression)
    return {
        "expression": expression,
        "result": value,
    }


def _tool_echo(args: dict[str, Any]) -> dict[str, Any]:
    return {"text": str(args.get("text") or "")}


def _safe_eval_expression(expression: str) -> float:
    allowed_nodes = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Constant,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.FloorDiv,
        ast.Mod,
        ast.Pow,
        ast.UAdd,
        ast.USub,
    )
    tree = ast.parse(expression, mode="eval")

    for node in ast.walk(tree):
        if not isinstance(node, allowed_nodes):
            raise ValueError("表达式包含不允许的操作")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            raise ValueError("仅支持数字常量")

    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant):
            return float(node.value)
        if isinstance(node, ast.UnaryOp):
            operand = _eval(node.operand)
            if isinstance(node.op, ast.UAdd):
                return operand
            if isinstance(node.op, ast.USub):
                return -operand
            raise ValueError("不支持的一元操作")
        if isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.FloorDiv):
                return left // right
            if isinstance(node.op, ast.Mod):
                return left % right
            if isinstance(node.op, ast.Pow):
                return left ** right
        raise ValueError("不支持的表达式")

    return _eval(tree)
