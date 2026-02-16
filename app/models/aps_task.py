# -*- coding: utf-8 -*-
# @Time    : 2026/2/13
# @Author  : yangyuexiong
# @File    : aps_task.py

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import CustomBaseModel


class ApsTask(CustomBaseModel):
    """定时任务"""

    __tablename__ = "exile_aps_tasks"

    task_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="任务id")
    trigger_type: Mapped[str] = mapped_column(String(16), nullable=False, comment="触发器类型:date;interval;cron")
    trigger_param: Mapped[dict] = mapped_column(JSON, nullable=False, comment="触发器参数")
    task_function_name: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="任务函数名称")
    task_function_args: Mapped[list] = mapped_column(JSON, nullable=False, default=list, comment="任务参数:args")
    task_function_kwargs: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, comment="任务参数:kwargs")
