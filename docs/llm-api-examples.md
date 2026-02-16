# LLM API 示例

以下示例默认服务地址为 `http://127.0.0.1:7777`，并使用登录后的 `token` 头。

## 1. 创建会话

```bash
curl -X POST "http://127.0.0.1:7777/api/llm/conversations" \
  -H "Content-Type: application/json" \
  -H "token: <YOUR_TOKEN>" \
  -d '{
    "title": "Demo",
    "provider": "deepseek",
    "model": "deepseek-chat"
  }'
```

## 2. 多轮对话（非流式）

```bash
curl -X POST "http://127.0.0.1:7777/api/llm/chat" \
  -H "Content-Type: application/json" \
  -H "token: <YOUR_TOKEN>" \
  -d '{
    "conversation_id": "conv_xxx",
    "message": "请总结我们到目前为止的讨论",
    "use_tools": true,
    "use_rag": false
  }'
```

## 3. 流式对话（SSE）

```bash
curl -N "http://127.0.0.1:7777/api/llm/chat/stream" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -H "token: <YOUR_TOKEN>" \
  -d '{
    "conversation_id": "conv_xxx",
    "message": "用三点说明这个项目当前能力",
    "use_tools": false
  }'
```

常见事件：

- `meta`: 会话ID、provider/model、warning
- `delta`: 增量文本
- `done`: 完整结果、usage、finish_reason
- `error`: 错误信息

## 4. 能力矩阵与工具

```bash
curl "http://127.0.0.1:7777/api/llm/capabilities" -H "token: <YOUR_TOKEN>"
curl "http://127.0.0.1:7777/api/llm/tools" -H "token: <YOUR_TOKEN>"
```

## 5. Skill / MCP / RAG

```bash
curl "http://127.0.0.1:7777/api/llm/skills" -H "token: <YOUR_TOKEN>"
curl "http://127.0.0.1:7777/api/llm/mcp/servers" -H "token: <YOUR_TOKEN>"
curl "http://127.0.0.1:7777/api/llm/rag/documents?limit=20" -H "token: <YOUR_TOKEN>"
```

## 6. 观测与配额

```bash
curl "http://127.0.0.1:7777/api/llm/metrics/summary?days=7" -H "token: <YOUR_TOKEN>"
curl "http://127.0.0.1:7777/api/llm/metrics/recent?limit=50" -H "token: <YOUR_TOKEN>"
curl "http://127.0.0.1:7777/api/llm/quota?provider=deepseek&model=deepseek-chat" -H "token: <YOUR_TOKEN>"
```
