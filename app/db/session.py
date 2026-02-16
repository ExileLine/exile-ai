# -*- coding: utf-8 -*-
# @Time    : 2026/2/13
# @Author  : yangyuexiong
# @File    : session.py

from collections.abc import AsyncGenerator

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_config

project_config = get_config()

engine = create_async_engine(
    project_config.sqlalchemy_database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=project_config.DEBUG,
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖: 获取异步数据库会话"""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """应用启动时初始化数据库连接"""
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info(">>> 数据库连接池初始化完成")


async def close_db():
    """应用关闭时关闭数据库连接"""
    await engine.dispose()
    logger.info(">>> 数据库连接池已关闭")
