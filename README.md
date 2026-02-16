# exile-ai

AI基建集成

## 项目背景

## 核心功能定位

## 未来开发方向

## 环境与依赖管理（uv）

1. 安装依赖

```bash
uv sync
```

2. 启动服务

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 7777 --reload
```

3. 启动 Celery Worker（用于消费测试场景执行任务）

```bash
uv run celery -A app.tasks.celery_app:celery_app worker -Q exile_scenario_tasks --loglevel INFO
```

4. 运行测试

```bash
uv run pytest
```

## 生产部署建议（Gunicorn + Celery）

1. 启动 API 进程（示例）

```bash
gunicorn -w 8 -k uvicorn.workers.UvicornWorker app.main:app -b 0.0.0.0:5001 \
  --access-logfile /srv/access.log --error-logfile /srv/error.log \
  --log-level debug --timeout 300 --capture-output -D
```

2. 启动 Celery Worker（示例）

```bash
uv run celery -A app.tasks.celery_app:celery_app worker \
  -Q exile_scenario_tasks \
  --loglevel=info \
  --concurrency=8 \
  --pool=threads \
  --logfile=/srv/logs/ors_server/celery/worker.log \
  --pidfile=/srv/logs/ors_server/celery/worker.pid \
  --detach
```

## Celery 队列说明

- `task_default_queue` 在 `app/tasks/celery_app.py` 中配置，当前默认值是 `exile_scenario_tasks`。
- `run_scenario_task.delay(...)` 未显式指定 `queue`，会进入 `task_default_queue`。
- Worker 使用 `-Q exile_scenario_tasks` 时，只会消费该队列。
- 若后续引入多种任务，建议使用 `task_routes` 按任务类型分队列，并为不同队列部署不同 worker。

## ORM 说明

项目已从 `tortoise` 迁移为 `SQLAlchemy 2.0 Async`。

默认数据库后端为 `mysql`，可通过环境变量切换：

```env
DB_BACKEND=mysql
```

## 数据迁移（Alembic）

1. 生成迁移文件（基于模型自动对比）

```bash
# 如果`alembic`文件夹不存在或被删除
uv run alembic init alembic
```

```bash
uv run alembic revision --autogenerate -m "init schema"
```

2. 执行迁移到最新版本

```bash
# 如果新增了表模型则需要执行
uv run alembic revision --autogenerate -m "add xxx table"
```

```bash
uv run alembic upgrade head
```

3. 回滚一个版本

```bash
uv run alembic downgrade -1
```

4. 查看当前版本和历史

```bash
uv run alembic current
uv run alembic history --verbose
```