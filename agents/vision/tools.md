# Vision Agent 工具契约（Phase 1 / T08 真实实现）

## 当前工具

| 标识 | 类型 | 状态 |
|------|------|------|
| `vision_model` | LLM provider | 已实现（DualTrackRouter，OpenAI 兼容 / Mock 降级） |
| `file_storage` | 文件存储 | 已实现（本地 `backend/storage/uploads/{tenant_id}/{sha256}.{ext}`，Phase 2 切到 MinIO） |

## 接入规则

- LLM 调用走 `agents/llm/router.py::build_router_from_config`；
- `llm.enabled=false` 或 API key 缺失时自动回退 `MockProvider`；
- 图片元数据走 `agents/vision/image_processor.py::process_image`，统一校验 MIME / size / sha256。

## 失败兜底

- 401 / 超时 / 解析失败 → Agent 返回 `pending_verification=true` 占位；
- 上层 `backend/app/api/vision.py` 收到失败时把 `images.vision_status` 设为 `Failed` 并保留原始 `error` 字段。

## 待办

- Phase 2 接入真实视觉模型（GPT-4o vision / qwen-vl-max），把 prompt 切换到 OpenAI `image_url` 格式；
- 文件存储后端切到 MinIO（TD-015）。