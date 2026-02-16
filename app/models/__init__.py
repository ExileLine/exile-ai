# 新增模型后，请在这里导入，供 Alembic 自动发现
from app.models.admin import Admin
from app.models.aps_task import ApsTask

__all__ = [
    "Admin",
    "ApsTask",
]
