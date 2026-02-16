# -*- coding: utf-8 -*-

from __future__ import annotations

import math
import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_config
from app.models.llm import RAGChunk, RAGDocument
from app.services.llm.providers import UnifiedLLMClient

project_config = get_config()


class RAGService:
    """RAG 最小可用版：文档入库、切块、向量化、余弦召回。"""

    def __init__(self, llm_client: UnifiedLLMClient | None = None):
        self.llm_client = llm_client or UnifiedLLMClient()

    async def ingest_document(
        self,
        db: AsyncSession,
        *,
        owner_id: int,
        title: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        chunk_size: int = 800,
        chunk_overlap: int = 120,
        embedding_provider: str | None = None,
        embedding_model: str | None = None,
    ) -> dict[str, Any]:
        text = (content or "").strip()
        if not text:
            return {"doc_id": "", "chunk_count": 0}

        metadata = metadata or {}
        chunk_size = max(200, min(chunk_size, 4000))
        chunk_overlap = max(0, min(chunk_overlap, chunk_size - 1))

        chunks = self._split_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        doc_id = f"doc_{uuid.uuid4().hex}"
        doc = RAGDocument(
            doc_id=doc_id,
            owner_id=owner_id,
            title=title,
            content=text,
            meta_info=metadata,
            chunk_count=len(chunks),
            status=1,
        )
        db.add(doc)
        await db.flush()

        for idx, chunk in enumerate(chunks):
            embedding = await self.llm_client.embedding(
                text=chunk,
                provider=embedding_provider or project_config.EMBEDDING_PROVIDER,
                model=embedding_model or project_config.EMBEDDING_MODEL,
            )
            db.add(
                RAGChunk(
                    doc_id=doc_id,
                    owner_id=owner_id,
                    chunk_index=idx,
                    content=chunk,
                    embedding=embedding,
                    meta_info={
                        "title": title,
                        "source": metadata.get("source"),
                        "chunk_size": chunk_size,
                        "chunk_overlap": chunk_overlap,
                    },
                    status=1,
                )
            )

        await db.commit()
        return {
            "doc_id": doc_id,
            "title": title,
            "chunk_count": len(chunks),
        }

    async def list_documents(
        self,
        db: AsyncSession,
        *,
        owner_id: int,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(RAGDocument)
            .where(
                RAGDocument.owner_id == owner_id,
                RAGDocument.is_deleted == 0,
            )
            .order_by(RAGDocument.id.desc())
            .limit(max(1, min(limit, 200)))
        )
        rows = list((await db.execute(stmt)).scalars().all())
        return [
            {
                "doc_id": row.doc_id,
                "title": row.title,
                "chunk_count": row.chunk_count,
                "metadata": row.meta_info or {},
                "create_time": row.create_time,
                "update_time": row.update_time,
            }
            for row in rows
        ]

    async def remove_document(
        self,
        db: AsyncSession,
        *,
        owner_id: int,
        doc_id: str,
    ) -> dict[str, Any]:
        stmt = select(RAGDocument).where(
            RAGDocument.doc_id == doc_id,
            RAGDocument.owner_id == owner_id,
            RAGDocument.is_deleted == 0,
        )
        row = (await db.execute(stmt)).scalars().first()
        if not row:
            return {"deleted": False, "doc_id": doc_id}
        row.is_deleted = 1
        row.touch()
        await db.execute(
            delete(RAGChunk).where(
                RAGChunk.doc_id == doc_id,
                RAGChunk.owner_id == owner_id,
            )
        )
        await db.commit()
        return {"deleted": True, "doc_id": doc_id}

    async def retrieve_context(
        self,
        query: str,
        *,
        db: AsyncSession | None = None,
        owner_id: int | None = None,
        top_k: int = 3,
        embedding_provider: str | None = None,
        embedding_model: str | None = None,
    ) -> list[dict]:
        if not query.strip():
            return []
        if db is None or owner_id is None:
            return []

        query_embedding = await self.llm_client.embedding(
            text=query.strip(),
            provider=embedding_provider or project_config.EMBEDDING_PROVIDER,
            model=embedding_model or project_config.EMBEDDING_MODEL,
        )
        stmt = (
            select(RAGChunk)
            .where(
                RAGChunk.owner_id == owner_id,
                RAGChunk.is_deleted == 0,
            )
            .limit(5000)
        )
        chunks = list((await db.execute(stmt)).scalars().all())
        if not chunks:
            return []

        scored: list[tuple[float, RAGChunk]] = []
        for chunk in chunks:
            score = self._cosine_similarity(query_embedding, chunk.embedding or [])
            if score <= 0:
                continue
            scored.append((score, chunk))
        scored.sort(key=lambda x: x[0], reverse=True)
        selected = scored[: max(1, min(top_k, 20))]

        doc_map: dict[str, str] = {}
        doc_ids = [item.doc_id for _, item in selected]
        if doc_ids:
            doc_stmt = select(RAGDocument).where(
                RAGDocument.doc_id.in_(doc_ids),
                RAGDocument.owner_id == owner_id,
                RAGDocument.is_deleted == 0,
            )
            docs = list((await db.execute(doc_stmt)).scalars().all())
            doc_map = {doc.doc_id: doc.title for doc in docs}

        result: list[dict[str, Any]] = []
        for score, chunk in selected:
            result.append(
                {
                    "doc_id": chunk.doc_id,
                    "title": doc_map.get(chunk.doc_id),
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                    "score": round(score, 6),
                    "metadata": chunk.meta_info or {},
                }
            )
        return result

    @staticmethod
    def _split_text(text: str, *, chunk_size: int, chunk_overlap: int) -> list[str]:
        chunks: list[str] = []
        start = 0
        length = len(text)
        while start < length:
            end = min(start + chunk_size, length)
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= length:
                break
            start = end - chunk_overlap
        return chunks

    @staticmethod
    def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
        if not vec1 or not vec2:
            return 0.0
        size = min(len(vec1), len(vec2))
        if size <= 0:
            return 0.0
        a = vec1[:size]
        b = vec2[:size]
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
