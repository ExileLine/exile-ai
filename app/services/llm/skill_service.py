# -*- coding: utf-8 -*-

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CustomException
from app.models.llm import LLMSkill


@dataclass
class SkillProfile:
    name: str
    description: str
    system_prompt: str
    tool_names: list[str] = field(default_factory=list)
    rag_enabled: bool = False
    mcp_servers: list[str] = field(default_factory=list)


class SkillService:
    """Skill 服务：支持内置 + 数据库存储配置。"""

    def __init__(self):
        self._skills: dict[str, SkillProfile] = {}
        self._register_builtin_skills()

    def _register_builtin_skills(self):
        self._skills["default_assistant"] = SkillProfile(
            name="default_assistant",
            description="通用助理",
            system_prompt="你是一个专业、严谨、简洁的 AI 助理，优先给出可执行建议。",
            tool_names=["get_current_time", "calculate", "echo"],
        )
        self._skills["coder"] = SkillProfile(
            name="coder",
            description="代码工程师助手",
            system_prompt="你是资深后端工程师，输出以可运行、可维护代码为第一优先级。",
            tool_names=["calculate", "echo"],
        )

    async def get_skill(
        self,
        db: AsyncSession | None,
        name: str | None,
        owner_id: int | None = None,
    ) -> SkillProfile | None:
        if not name:
            return None
        skill_name = name.strip()
        if not skill_name:
            return None

        if db is not None:
            stmt = select(LLMSkill).where(
                LLMSkill.skill_name == skill_name,
                LLMSkill.is_deleted == 0,
                or_(LLMSkill.status == 1, LLMSkill.status.is_(None)),
                or_(LLMSkill.owner_id == owner_id, LLMSkill.owner_id.is_(None)),
            )
            rows = list((await db.execute(stmt)).scalars().all())
            selected = self._pick_skill_by_owner(rows, owner_id=owner_id)
            if selected:
                return self._row_to_profile(selected)

        return self._skills.get(skill_name)

    async def list_skills(
        self,
        db: AsyncSession | None,
        owner_id: int | None = None,
    ) -> list[dict[str, Any]]:
        merged: dict[str, SkillProfile] = dict(self._skills)
        if db is not None:
            stmt = select(LLMSkill).where(
                LLMSkill.is_deleted == 0,
                or_(LLMSkill.status == 1, LLMSkill.status.is_(None)),
                or_(LLMSkill.owner_id == owner_id, LLMSkill.owner_id.is_(None)),
            )
            rows = list((await db.execute(stmt)).scalars().all())
            for row in rows:
                merged[row.skill_name] = self._row_to_profile(row)

        return [
            {
                "name": item.name,
                "description": item.description,
                "system_prompt": item.system_prompt,
                "tool_names": item.tool_names,
                "rag_enabled": item.rag_enabled,
                "mcp_servers": item.mcp_servers,
            }
            for item in merged.values()
        ]

    async def upsert_skill(
        self,
        db: AsyncSession,
        *,
        owner_id: int,
        skill_name: str,
        description: str | None,
        system_prompt: str,
        tool_names: list[str],
        rag_enabled: bool,
        mcp_server_ids: list[str],
        extra_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        skill_name = skill_name.strip()
        if not skill_name:
            raise CustomException(detail="skill_name 不能为空", custom_code=10001)
        clean_tool_names = self._normalize_str_list(tool_names)
        clean_server_ids = self._normalize_str_list(mcp_server_ids)
        stmt = select(LLMSkill).where(
            LLMSkill.owner_id == owner_id,
            LLMSkill.skill_name == skill_name,
            LLMSkill.is_deleted == 0,
        )
        row = (await db.execute(stmt)).scalars().first()

        if row:
            row.description = description
            row.system_prompt = system_prompt
            row.tool_names = clean_tool_names
            row.rag_enabled = 1 if rag_enabled else 0
            row.mcp_server_ids = clean_server_ids
            row.extra_config = extra_config or {}
            row.status = 1
            row.touch()
        else:
            row = LLMSkill(
                owner_id=owner_id,
                skill_name=skill_name,
                description=description,
                system_prompt=system_prompt,
                tool_names=clean_tool_names,
                rag_enabled=1 if rag_enabled else 0,
                mcp_server_ids=clean_server_ids,
                is_builtin=0,
                extra_config=extra_config or {},
                status=1,
            )
            db.add(row)

        await db.commit()
        await db.refresh(row)
        profile = self._row_to_profile(row)
        return {
            "name": profile.name,
            "description": profile.description,
            "system_prompt": profile.system_prompt,
            "tool_names": profile.tool_names,
            "rag_enabled": profile.rag_enabled,
            "mcp_servers": profile.mcp_servers,
        }

    @staticmethod
    def _normalize_str_list(items: list[str]) -> list[str]:
        result: list[str] = []
        seen = set()
        for item in items:
            value = str(item).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    @staticmethod
    def _pick_skill_by_owner(rows: list[LLMSkill], owner_id: int | None) -> LLMSkill | None:
        if not rows:
            return None
        if owner_id is not None:
            for row in rows:
                if row.owner_id == owner_id:
                    return row
        for row in rows:
            if row.owner_id is None:
                return row
        return rows[0]

    @staticmethod
    def _row_to_profile(row: LLMSkill) -> SkillProfile:
        return SkillProfile(
            name=row.skill_name,
            description=row.description or "",
            system_prompt=row.system_prompt,
            tool_names=[str(x) for x in (row.tool_names or [])],
            rag_enabled=bool(row.rag_enabled),
            mcp_servers=[str(x) for x in (row.mcp_server_ids or [])],
        )
