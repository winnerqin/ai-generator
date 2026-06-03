# 全能视频外部 API 对接文档

本文档用于外部系统通过 API 批量创建全能视频任务、查询任务状态和查询批次状态。

## 基础信息

- Base URL: `http://127.0.0.1:8090`
- Content-Type: `application/json`
- 认证方式: `X-API-Key` 或 `Authorization: Bearer <JWT>`
- 一个 `tasks[]` 元素会创建一个全能视频任务，也就是生成一个视频。
- 多个视频请放到同一个 `batch_id` 下的多个 `tasks[]` 元素中。

## 上线准备

已有 MySQL 库需要先执行迁移脚本:

```bash
mysql -u root -p ai_generator < scripts/migrate_omni_external_api_mysql.sql
```

新建库可以执行完整 schema:

```bash
mysql -u root -p -e "CREATE DATABASE ai_generator DEFAULT CHARSET utf8mb4;"
mysql -u root -p ai_generator < scripts/schema_mysql.sql
```

## API Key 配置

### 测试环境

可以在 `.env` 中配置:

```env
EXTERNAL_OMNI_API_KEYS=test-key-123:7:9
```

格式:

```text
API_KEY:user_id:project_id
```

多个 Key 使用英文逗号分隔:

```env
EXTERNAL_OMNI_API_KEYS=test-key-123:7:9,partner-key-456:8:10
```

### 正式环境

建议写入 `external_api_keys` 表，数据库只保存 SHA256，不保存明文 API Key。

```sql
INSERT INTO external_api_keys
(user_id, project_id, name, key_hash, status)
VALUES
(7, 9, 'partner api key', SHA2('test-key-123', 256), 'active');
```

外部调用时仍传明文:

```http
X-API-Key: test-key-123
```

## 认证

### API Key

```http
X-API-Key: test-key-123
```

也支持:

```http
Authorization: Bearer test-key-123
```

如果 `Authorization: Bearer ...` 是有效 JWT，会优先按 JWT 解析；解析失败后可作为 API Key 使用。

### JWT

先登录获取 `access_token`:

```bash
curl -X POST http://127.0.0.1:8090/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"your-user","password":"your-password"}'
```

调用外部 API:

```http
Authorization: Bearer <access_token>
```

## 批量创建任务

```http
POST /api/external/omni-video/tasks/batch
```

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `batch_id` | string | 否 | 批次 ID。建议外部系统传订单号或批次号。 |
| `project_id` | integer | 否 | 项目 ID。API Key 绑定了项目时可不传。 |
| `callback_url` | string | 否 | 回调地址，当前仅入库保留，后续 webhook 可使用。 |
| `tasks` | array | 是 | 任务数组，单次最多 50 个。 |

`tasks[]` 参数:

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `client_request_id` | string | 强烈建议 | 幂等键。同一用户下重复提交会返回已有任务，不会重复创建。 |
| `prompt` | string | 是 | 视频生成提示词。 |
| `model` | string | 否 | 模型。不传时按用户角色选择默认模型。 |
| `resolution` | string | 否 | 分辨率，例如 `480p`、`720p`、`1080p`。 |
| `aspect_ratio` | string | 否 | 比例，例如 `16:9`、`9:16`、`1:1`、`4:3`、`3:4`。 |
| `duration` | integer | 否 | 时长，支持 `4-15` 或 `-1`。 |
| `frame_count` | integer | 否 | 帧数，支持 `29-289`。传入后优先于 `duration`。 |
| `seed` | integer | 否 | 随机种子。 |
| `generate_audio` | boolean | 否 | 是否生成音频，默认 `true`。 |
| `reference_urls` | array | 否 | 参考素材 URL 数组。 |
| `filename` | string | 否 | 期望文件名。 |
| `external_meta` | object | 否 | 外部系统自定义元数据。 |

### 参考素材

`reference_urls` 支持多个图片、视频、音频 URL。服务会按 URL 后缀自动识别:

- 图片: `.jpg`、`.jpeg`、`.png`、`.webp`、`.gif`、`.bmp`
- 视频: `.mp4`、`.mov`、`.webm`、`.avi`、`.mkv`
- 音频: `.mp3`、`.wav`、`.m4a`、`.aac`、`.ogg`、`.flac`
- 其他后缀会作为普通文件参考

素材 URL 应使用公网可访问地址。

### curl 示例

Linux/macOS/Git Bash:

```bash
curl -X POST http://127.0.0.1:8090/api/external/omni-video/tasks/batch \
  -H "X-API-Key: test-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "batch_id": "order-10001",
    "tasks": [
      {
        "client_request_id": "order-10001-video-1",
        "prompt": "生成一个手机支架产品展示视频，突出正面外观",
        "model": "doubao-seedance-2-0-fast-260128",
        "resolution": "720p",
        "aspect_ratio": "16:9",
        "duration": 5,
        "reference_urls": [
          "https://example.com/product-front.jpg",
          "https://example.com/demo-video.mp4",
          "https://example.com/voiceover.mp3"
        ]
      },
      {
        "client_request_id": "order-10001-video-2",
        "prompt": "生成一个手机支架产品展示视频，突出桌面使用场景",
        "resolution": "720p",
        "aspect_ratio": "16:9",
        "duration": 5,
        "reference_urls": [
          "https://example.com/product-front.jpg",
          "https://example.com/desk-scene.jpg"
        ]
      }
    ]
  }'
```

PowerShell:

```powershell
curl.exe -X POST http://127.0.0.1:8090/api/external/omni-video/tasks/batch `
  -H "X-API-Key: test-key-123" `
  -H "Content-Type: application/json" `
  -d '{
    "batch_id": "order-10001",
    "tasks": [
      {
        "client_request_id": "order-10001-video-1",
        "prompt": "生成一个手机支架产品展示视频",
        "resolution": "720p",
        "aspect_ratio": "16:9",
        "duration": 5
      }
    ]
  }'
```

### 成功响应

全部创建成功时 HTTP 状态码为 `201`:

```json
{
  "success": true,
  "batch_id": "order-10001",
  "created": 2,
  "reused": 0,
  "failed": 0,
  "items": [
    {
      "index": 0,
      "client_request_id": "order-10001-video-1",
      "task_id": "task-xxx",
      "status": "queued",
      "status_code": 201,
      "idempotent": false,
      "message": "任务创建成功"
    }
  ]
}
```

部分失败时 HTTP 状态码为 `207`，每条任务看 `items[].status_code` 和 `items[].error`。

## 查询单个任务状态

```http
GET /api/external/omni-video/tasks/{task_id}
```

查询时默认会同步刷新远端任务状态。可传 `sync=false` 只读本地库。

```bash
curl -H "X-API-Key: test-key-123" \
  "http://127.0.0.1:8090/api/external/omni-video/tasks/task-xxx"
```

响应:

```json
{
  "success": true,
  "task": {
    "task_id": "task-xxx",
    "status": "succeeded",
    "batch_id": "order-10001",
    "client_request_id": "order-10001-video-1",
    "video_url": "https://example.com/video.mp4",
    "cover_url": "https://example.com/cover.jpg",
    "fail_reason": null,
    "token_usage": 12345,
    "amount_yuan": 1.23,
    "created_at": "2026-06-03 12:00:00",
    "updated_at": "2026-06-03 12:05:00"
  }
}
```

## 查询批次状态

```http
GET /api/external/omni-video/batches/{batch_id}
```

参数:

| 字段 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `page` | integer | `1` | 页码。 |
| `page_size` | integer | `50` | 每页数量，最大 `100`。 |
| `status` | string | 空 | 按任务状态筛选。 |
| `sync_running` | boolean | `true` | 是否刷新非终态任务。 |
| `project_id` | integer | 空 | 查询指定项目。 |

示例:

```bash
curl -H "X-API-Key: test-key-123" \
  "http://127.0.0.1:8090/api/external/omni-video/batches/order-10001?page=1&page_size=50"
```

响应:

```json
{
  "success": true,
  "batch_id": "order-10001",
  "items": [
    {
      "task_id": "task-xxx",
      "status": "queued",
      "batch_id": "order-10001",
      "client_request_id": "order-10001-video-1"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 50
}
```

## 幂等规则

- 幂等键是 `client_request_id`。
- 当前规则为同一 `user_id` 下相同 `client_request_id` 只创建一次。
- 重复提交时不会再次调用远端生成接口，不会重复扣费。
- 重复提交的单条响应:

```json
{
  "client_request_id": "order-10001-video-1",
  "task_id": "task-existing",
  "status": "queued",
  "status_code": 200,
  "idempotent": true,
  "message": "任务已存在"
}
```

建议外部系统使用稳定唯一值，例如 `订单号-视频序号`。

## 任务状态

常见状态:

| 状态 | 说明 |
| --- | --- |
| `queued` | 已创建，等待处理。 |
| `running` | 生成中。 |
| `succeeded` / `success` / `completed` | 成功。 |
| `failed` | 失败。 |
| `cancelled` / `canceled` | 已取消。 |
| `expired` | 已过期。 |

不同远端模型可能返回不同成功状态，系统会兼容 `succeeded`、`success`、`completed`、`done`、`finished`。

## HTTP 状态码

| 状态码 | 场景 |
| --- | --- |
| `200` | 查询成功，或幂等命中已有任务。 |
| `201` | 批量提交全部成功。 |
| `207` | 批量提交部分成功、部分失败。 |
| `400` | 请求参数错误，例如缺少 `tasks`、提示词为空、模型/分辨率不支持。 |
| `401` | 缺少认证或认证无效。 |
| `402` | 账号余额不足。 |
| `403` | 无权访问指定项目。 |
| `404` | 任务不存在。 |
| `500` | 服务端异常。 |

## 错误响应

整体请求失败:

```json
{
  "success": false,
  "error": "缺少认证凭据"
}
```

批量部分失败:

```json
{
  "success": false,
  "batch_id": "order-10001",
  "created": 1,
  "reused": 0,
  "failed": 1,
  "items": [
    {
      "index": 0,
      "client_request_id": "order-10001-video-1",
      "task_id": "task-xxx",
      "status": "queued",
      "status_code": 201,
      "idempotent": false,
      "message": "任务创建成功"
    },
    {
      "index": 1,
      "client_request_id": "order-10001-video-2",
      "task_id": null,
      "status": "failed",
      "status_code": 400,
      "idempotent": false,
      "error": "提示词不能为空"
    }
  ]
}
```

## 定时同步

服务启动后会自动启动全能视频状态同步 worker，默认每 60 秒刷新一次 `queued` 和 `running` 任务。

`.env` 可配置:

```env
OMNI_VIDEO_WORKER_ENABLED=true
OMNI_VIDEO_WORKER_INTERVAL_SECONDS=60
OMNI_VIDEO_WORKER_BATCH_LIMIT=200
```

如果外部系统希望立即获得最新状态，可在查询接口中使用默认的 `sync=true` 或 `sync_running=true`。
