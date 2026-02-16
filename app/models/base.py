# -*- coding: utf-8 -*-
# @Time    : 2026/2/13
# @Author  : yangyuexiong
# @File    : base.py

import time
from datetime import datetime
from decimal import Decimal
from typing import Any

import pytz
from sqlalchemy import BigInteger, DateTime, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

TZ = pytz.timezone("Asia/Shanghai")


def now_tz() -> datetime:
    return datetime.now(TZ)


def to_tz(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return TZ.localize(dt)
    return dt.astimezone(TZ)


class Base(DeclarativeBase):
    pass


class CustomBaseModel(Base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="id")
    create_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_tz,
        nullable=False,
        comment="创建时间(结构化时间)",
    )
    create_timestamp: Mapped[int] = mapped_column(
        BigInteger,
        default=lambda: int(time.time()),
        nullable=False,
        comment="创建时间(时间戳)",
    )
    update_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_tz,
        onupdate=now_tz,
        nullable=False,
        comment="更新时间(结构化时间)",
    )
    update_timestamp: Mapped[int | None] = mapped_column(
        BigInteger,
        default=lambda: int(time.time()),
        onupdate=lambda: int(time.time()),
        nullable=True,
        comment="更新时间(时间戳)",
    )
    is_deleted: Mapped[int | None] = mapped_column(
        BigInteger,
        default=0,
        nullable=True,
        comment="0正常;其他:已删除",
    )
    status: Mapped[int | None] = mapped_column(
        Integer,
        default=1,
        nullable=True,
        comment="状态",
    )

    async def inject_save(self):
        """兼容旧接口，默认不做额外处理"""

    def touch(self):
        now = now_tz()
        self.update_time = now
        self.update_timestamp = int(now.timestamp())

    def to_dict(self, exclude: set[str] | None = None) -> dict[str, Any]:
        exclude = exclude or set()
        data: dict[str, Any] = {}
        for column in self.__table__.columns:  # type: ignore[attr-defined]
            name = column.name
            if name in exclude:
                continue
            value = getattr(self, name)
            if isinstance(value, datetime):
                value = to_tz(value)
            elif isinstance(value, Decimal):
                value = float(value)
            data[name] = value
        return data
