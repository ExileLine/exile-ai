# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum
from typing import Any

import httpx

from app.core.config import get_config
from app.core.exceptions import CustomException

project_config = get_config()


class LLMProvider(str, Enum):
    deepseek = "deepseek"
    openai = "openai"
    gemini = "gemini"


@dataclass
class ProviderConfig:
    provider: str
    api_key: str
    base_url: str
    default_model: str


class UnifiedLLMClient:
    """统一的多厂商 LLM 客户端（OpenAI-compatible 协议）"""

    def __init__(self):
        self.timeout_seconds = project_config.LLM_TIMEOUT_SECONDS
        self._provider_attr_map = {
            LLMProvider.deepseek.value: ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"),
            LLMProvider.openai.value: ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"),
            LLMProvider.gemini.value: ("GEMINI_API_KEY", "GEMINI_BASE_URL", "GEMINI_MODEL"),
        }

    def resolve_provider(
        self,
        provider: str | None = None,
        model: str | None = None,
        require_api_key: bool = True,
    ) -> tuple[ProviderConfig, str]:
        resolved_provider = (provider or project_config.default_llm_provider).strip().lower()
        provider_attrs = self._provider_attr_map.get(resolved_provider)
        if not provider_attrs:
            raise CustomException(
                detail=f"不支持的模型厂商: {resolved_provider}",
                custom_code=10005,
            )

        api_key_attr, base_url_attr, default_model_attr = provider_attrs
        api_key = (getattr(project_config, api_key_attr, "") or "").strip()
        base_url = (getattr(project_config, base_url_attr, "") or "").strip().rstrip("/")
        default_model = (getattr(project_config, default_model_attr, "") or "").strip()

        if not base_url:
            raise CustomException(
                detail=f"{resolved_provider} base_url 未配置",
                custom_code=10005,
            )
        if require_api_key and not api_key:
            raise CustomException(
                detail=f"{resolved_provider} API key 未配置",
                custom_code=10005,
            )

        provider_config = ProviderConfig(
            provider=resolved_provider,
            api_key=api_key,
            base_url=base_url,
            default_model=default_model,
        )
        resolved_model = (model or default_model or project_config.default_llm_model).strip()
        return provider_config, resolved_model

    async def chat_completion(
        self,
        *,
        messages: list[dict[str, Any]],
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
    ) -> dict[str, Any]:
        provider_config, resolved_model = self.resolve_provider(provider=provider, model=model)
        payload: dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "temperature": (
                float(temperature)
                if temperature is not None
                else float(project_config.LLM_DEFAULT_TEMPERATURE)
            ),
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        url = f"{provider_config.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {provider_config.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=payload)

        if response.status_code >= 400:
            raise CustomException(
                detail=f"模型请求失败({response.status_code}): {response.text[:500]}",
                custom_code=10005,
            )

        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise CustomException(detail="模型返回为空", custom_code=10005)

        message = choices[0].get("message") or {}
        return {
            "provider": provider_config.provider,
            "model": data.get("model") or resolved_model,
            "message": message,
            "finish_reason": choices[0].get("finish_reason"),
            "usage": data.get("usage") or {},
            "raw": data,
        }

    async def chat_completion_stream(
        self,
        *,
        messages: list[dict[str, Any]],
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        provider_config, resolved_model = self.resolve_provider(provider=provider, model=model)
        payload: dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "temperature": (
                float(temperature)
                if temperature is not None
                else float(project_config.LLM_DEFAULT_TEMPERATURE)
            ),
            "stream": True,
        }
        url = f"{provider_config.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {provider_config.api_key}",
            "Content-Type": "application/json",
        }
        timeout = httpx.Timeout(
            connect=self.timeout_seconds,
            read=None,
            write=self.timeout_seconds,
            pool=self.timeout_seconds,
        )

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                if response.status_code >= 400:
                    text = await response.aread()
                    raise CustomException(
                        detail=f"模型流式请求失败({response.status_code}): {text.decode('utf-8', errors='replace')[:500]}",
                        custom_code=10005,
                    )

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if not line.startswith("data:"):
                        continue
                    chunk_text = line[5:].strip()
                    if not chunk_text:
                        continue
                    if chunk_text == "[DONE]":
                        yield {"type": "done"}
                        break
                    try:
                        raw = json.loads(chunk_text)
                    except json.JSONDecodeError:
                        continue

                    choices = raw.get("choices") or []
                    delta = {}
                    finish_reason = None
                    if choices:
                        choice = choices[0]
                        delta = choice.get("delta") or choice.get("message") or {}
                        finish_reason = choice.get("finish_reason")

                    yield {
                        "type": "chunk",
                        "provider": provider_config.provider,
                        "model": raw.get("model") or resolved_model,
                        "delta": delta,
                        "finish_reason": finish_reason,
                        "usage": raw.get("usage") or {},
                        "raw": raw,
                    }

    async def embedding(
        self,
        *,
        text: str,
        provider: str | None = None,
        model: str | None = None,
    ) -> list[float]:
        provider_config, resolved_model = self.resolve_provider(provider=provider, model=model)
        url = f"{provider_config.base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {provider_config.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": resolved_model,
            "input": text,
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=payload)

        if response.status_code >= 400:
            raise CustomException(
                detail=f"向量化请求失败({response.status_code}): {response.text[:500]}",
                custom_code=10005,
            )

        data = response.json()
        vectors = data.get("data") or []
        if not vectors:
            raise CustomException(detail="向量化结果为空", custom_code=10005)
        return vectors[0].get("embedding") or []
