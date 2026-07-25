# Vision Agent 定义（Phase 1 / T08 真实实现）

## 标识

- 名称：Vision Agent
- 版本：`1.0.0-phase1`（由 `0.1.0-phase0` 升级）
- 实现状态：**已实现最小骨架 + LLM 调用**（T08）
- 实现位置：`agents/vision/agent.py`
- 注册：`agents/config.yaml::agents.vision.enabled=true`

## 职责

对用户上传的建筑阳台/窗户照片进行结构化分析，输出可追踪的视觉观察字段，供后续 Design / Environment Agent 使用。

## 输入

- `AgentContext.request_id`
- `input_data` 推荐字段：
  - `image_id` (str) 图片 UUID
  - `image_b64` (str) base64 编码图片
  - `mime_type` (str) 图片 MIME

## 输出（LLM 启用）

`AgentResult.data` 包含：

- `agent`: `"vision"`
- `version`: `"1.0.0-phase1"`
- `stage`: `"vision_analyzed"`
- `image_id`: 上传 UUID
- `provider`: 实际命中的 LLM provider 名
- `scene_type`: 开放阳台 / 封闭阳台 / 落地窗 / 飘窗 / unknown
- `obstructions`: 障碍物列表
- `orientation_hint`: 朝向线索（东南西北 / 不确定）
- `quality`: high / medium / low
- `recommendations`: 视觉相关建议
- `pending_verification`: false（真 LLM 调用成功）或 true（占位）

## 降级

LLM 未启用 / API key 缺失 / 401 / 非 JSON 响应时：

- 返回 `success=true` + `pending_verification=true`；
- `scene_type="unknown"` / `obstructions=[]` / `quality="low"`；
- LLM 抛错时返回 `success=false` + `error.code="VISION_FAILED"`。

## 限制

- 不猜测楼层、面积、材质等不在图像中的信息。
- 不输出结构安全或最终设计结论。
- 不把模型推断冒充人工测量。
- 所有工程数值（图像压缩阈值、像素上限等）保持 `pending_verification`。
- Phase 2 接入真实视觉模型（GPT-4o vision / 通义 qwen-vl）后再细化 prompt。