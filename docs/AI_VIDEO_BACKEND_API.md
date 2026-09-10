# AI Video Backend 接口文档

> 面向前端、第三方系统和 AI 代码生成工具。本文档以当前 `ai-video-backend` 源码为准，按 Controller 分组描述全部业务接口。

## 1. 接入概览

### 1.1 基础地址

本地默认地址：

```text
http://127.0.0.1:8080/admin
```

部署后请将 `http://127.0.0.1:8080` 替换为实际服务地址，`/admin` 是固定的 Context Path。

### 1.2 接口清单

| Controller | operationId 建议 | 方法 | 路径 | 作用 |
|---|---|---|---|---|
| UserController | `userAuth` | POST | `/user/v1/auth` | 校验 AppKey 并返回当前用户 ID |
| UserController | `userAdd` | POST | `/user/v1/add` | 新增可调用接口的用户 |
| UserController | `userUpdate` | POST | `/user/v1/update` | 修改用户 AppKey、启用状态或删除状态 |
| UserController | `userPage` | POST | `/user/v1/page` | 分页查询未删除用户 |
| ProjectController | `projectAdd` | POST | `/project/v1/add` | 新增 AI 视频项目 |
| ProjectController | `projectUpdate` | POST | `/project/v1/update` | 修改项目名称或状态 |
| ProjectController | `projectPage` | POST | `/project/v1/page` | 分页查询项目 |
| FileController | `fileUpload` | POST | `/file/v1/upload` | 以 multipart 方式上传实体文件到 S3 |
| FileController | `fileUploadByUrl` | POST | `/file/v1/upload/url` | 下载远程文件并上传到 S3 |
| FileController | `fileUpdate` | POST | `/file/v1/update` | 修改文件所属项目、展示文件名或状态 |
| FileController | `filePage` | POST | `/file/v1/page` | 分页查询文件，并生成临时预览地址 |

### 1.3 鉴权

除 Swagger 和框架错误页面外，本文所有接口都必须在请求头中携带 `appkey`：

| Header | 必填 | 类型 | 含义 |
|---|---|---|---|
| `appkey` | 是 | string | 用户的接口调用凭证。只有 `enable = 1` 且 `isDelete = 0` 的用户能通过鉴权 |
| `Content-Type` | JSON 接口是 | string | JSON 接口使用 `application/json`；实体文件上传使用 `multipart/form-data` |

鉴权失败时 HTTP 状态码为 `401`：

```json
{
  "success": false,
  "code": "401",
  "message": "请求头中缺少AppKey",
  "data": null,
  "timestamp": "1788854400000"
}
```

`message` 还可能为 `AppKey无效`。AppKey 不要写入日志、异常信息、URL Query 或公开代码仓库。

### 1.4 统一响应结构

所有接口都返回 `Result<T>`：

| 字段 | JSON 类型 | 含义 |
|---|---|---|
| `success` | boolean | 业务是否成功。调用方应优先使用此字段判断结果 |
| `code` | string | 业务码。`"1"` 成功、`"0"` 一般业务失败、`"401"` 鉴权失败、`"500"` 系统异常 |
| `message` | string | 结果说明或错误原因 |
| `data` | T \| null | 接口业务数据；失败时通常为 `null` |
| `timestamp` | string | 服务端生成响应时的 Unix 毫秒时间戳 |

成功示例：

```json
{
  "success": true,
  "code": "1",
  "message": "成功",
  "data": true,
  "timestamp": "1788854400000"
}
```

业务校验失败通常仍返回 HTTP `200`，必须继续检查 `success`：

```json
{
  "success": false,
  "code": "0",
  "message": "项目名称不能为空",
  "data": null,
  "timestamp": "1788854400000"
}
```

未捕获的系统异常返回 HTTP `500`，响应 `code` 为 `"500"`。

> `code`、`timestamp`、`fileSize` 在 Java 中是 `long/Long`，项目会将其序列化为 JSON 字符串，生成客户端时不要声明为 JavaScript `number`。`createTime`、`updateTime`、`deletedTime` 是 `java.util.Date`，当前未声明固定 JSON 格式，建议客户端兼容 Unix 毫秒数或日期字符串，并统一转换为自身的日期对象。

### 1.5 分页结构

分页请求公共字段：

| 字段 | 必填 | 类型 | 默认值 | 含义 |
|---|---|---|---|---|
| `pageNo` | 否 | integer | `1` | 页码，从 1 开始 |
| `pageSize` | 否 | integer | `10` | 每页条数，应大于 0 |

分页响应 `PageInfo<T>`：

```json
{
  "pageParam": {
    "nextPage": 2,
    "previousPage": 0,
    "pageSize": 10,
    "pageNo": 1,
    "pageTotal": 3,
    "totalCount": 25
  },
  "items": []
}
```

| 字段 | 类型 | 含义 |
|---|---|---|
| `pageParam.nextPage` | integer | 下一页页码；没有下一页时为 `0` |
| `pageParam.previousPage` | integer | 上一页页码；没有上一页时为 `0` |
| `pageParam.pageSize` | integer | 当前每页条数 |
| `pageParam.pageNo` | integer | 当前页码 |
| `pageParam.pageTotal` | integer | 总页数 |
| `pageParam.totalCount` | integer | 符合条件的总记录数 |
| `items` | T[] | 当前页数据 |

后端分页接口没有统一校验正数，调用方必须保证 `pageNo >= 1` 且 `pageSize >= 1`。

## 2. UserController

用户代表具有 Backend 调用权限的身份。`appKey` 是鉴权凭证；`enable = 0` 或 `isDelete = 1` 后，该用户的 AppKey 不能再调用任何受保护接口。

### 2.1 校验当前 AppKey

```text
POST /user/v1/auth
operationId: userAuth
```

用途：验证请求头中的 AppKey 是否有效，并取得这个 AppKey 对应的当前用户 ID。服务间接入时可用它做连通性和身份检查。

请求体：无。

请求示例：

```bash
curl -X POST 'http://127.0.0.1:8080/admin/user/v1/auth' \
  -H 'appkey: <YOUR_APP_KEY>'
```

成功响应中的 `data` 是当前用户 ID：

```json
{
  "success": true,
  "code": "1",
  "message": "成功",
  "data": 12,
  "timestamp": "1788854400000"
}
```

### 2.2 新增用户

```text
POST /user/v1/add
operationId: userAdd
Content-Type: application/json
```

用途：创建一个新的接口调用用户，并为其保存唯一 AppKey。创建结果默认启用且未删除。

请求体：

| 字段 | 必填 | 类型 | 约束与含义 |
|---|---|---|---|
| `name` | 是 | string | 用户名，不能是空白字符串；数据库长度上限 64 |
| `appKey` | 是 | string | 接口调用凭证，不能是空白字符串；数据库长度上限 128，且全局唯一 |

`id`、`enable`、`isDelete` 即使传入也不会参与新增逻辑：`id` 由数据库生成，`enable` 固定为 `1`，`isDelete` 使用数据库默认值 `0`。

请求示例：

```json
{
  "name": "video-agent",
  "appKey": "<NEW_UNIQUE_APP_KEY>"
}
```

成功响应的 `data` 为 `true`。

常见失败原因：

- `用户名不能为空`
- `AppKey不能为空`
- AppKey 重复或字段超过数据库长度时会写入失败

### 2.3 修改用户

```text
POST /user/v1/update
operationId: userUpdate
Content-Type: application/json
```

用途：修改指定用户的鉴权凭证、启用状态或软删除状态。用户名不能通过该接口修改。

请求体：

| 字段 | 必填 | 类型 | 约束与含义 |
|---|---|---|---|
| `id` | 业务上必填 | integer | 要修改的用户 ID |
| `appKey` | 否 | string | 新 AppKey；传入时不能是空白字符串，且必须满足数据库唯一约束 |
| `enable` | 否 | integer | `0` 冻结，`1` 启用；冻结后该用户无法鉴权 |
| `isDelete` | 否 | integer | `0` 未删除，`1` 已删除；删除后该用户无法鉴权且不出现在用户列表 |

只发送需要修改的字段，未发送或值为 `null` 的字段不会更新。`name` 即使传入也会被忽略。

请求示例：

```json
{
  "id": 12,
  "enable": 0
}
```

成功响应的 `data` 为 `true`。

> 当前实现未校验 `id` 是否存在，也未检查数据库实际修改行数，因此 `id` 不存在时仍可能返回成功。调用方应始终传入 `id`，需要强一致确认时应在修改后查询验证。

### 2.4 分页查询用户

```text
POST /user/v1/page
operationId: userPage
Content-Type: application/json
```

用途：分页查询未删除用户。响应不会返回 AppKey，避免在用户列表中泄露凭证。

请求体：

| 字段 | 必填 | 类型 | 约束与含义 |
|---|---|---|---|
| `name` | 否 | string | 用户名精确匹配；空字符串等同不筛选 |
| `enable` | 否 | integer | `0` 冻结，`1` 启用 |
| `pageNo` | 否 | integer | 页码，从 1 开始，默认 1 |
| `pageSize` | 否 | integer | 每页条数，默认 10 |

无筛选请求示例：

```json
{
  "pageNo": 1,
  "pageSize": 10
}
```

筛选请求示例：

```json
{
  "name": "video-agent",
  "enable": 1,
  "pageNo": 1,
  "pageSize": 20
}
```

响应 `data` 类型为 `PageInfo<UserDTO>`。`UserDTO` 字段：

| 字段 | 类型 | 含义 |
|---|---|---|
| `id` | integer | 用户 ID |
| `name` | string | 用户名 |
| `headImg` | string \| null | 头像 URL；当前用户表没有对应字段，通常为 `null` |
| `enable` | integer | `0` 冻结，`1` 启用 |
| `isDelete` | integer | `0` 未删除，`1` 已删除；本接口固定筛掉已删除记录 |

> 当前源码存在已知实现限制：服务只统计 `totalCount`，没有查询并组装用户数据，因此 `items` 当前始终为空数组，即使 `totalCount > 0`。在该实现修复前，不要用 `items` 判断用户是否存在。

## 3. ProjectController

项目是文件的业务归属容器。项目状态 `status` 表示项目是否启用，但当前文件接口不会因为项目停用而拒绝上传或查询。

### 3.1 新增项目

```text
POST /project/v1/add
operationId: projectAdd
Content-Type: application/json
```

请求体：

| 字段 | 必填 | 类型 | 约束与含义 |
|---|---|---|---|
| `projectName` | 是 | string | 项目名称，不能是空白字符串；数据库长度上限 128 |
| `status` | 否 | integer | `0` 停用，`1` 启用；不传时默认 `1` |

请求示例：

```json
{
  "projectName": "2026 秋季新品宣传片",
  "status": 1
}
```

响应 `data` 类型为 `ProjectDTO`：

```json
{
  "success": true,
  "code": "1",
  "message": "成功",
  "data": {
    "id": 101,
    "projectName": "2026 秋季新品宣传片",
    "status": 1,
    "createTime": null,
    "createId": 12,
    "updateTime": null,
    "updateId": 12
  },
  "timestamp": "1788854400000"
}
```

新增响应直接使用内存中的插入对象，数据库自动生成的 `createTime`、`updateTime` 可能为 `null`；分页查询时会返回数据库中的实际时间。

### 3.2 修改项目

```text
POST /project/v1/update
operationId: projectUpdate
Content-Type: application/json
```

用途：按项目 ID 修改名称和/或状态，并返回实际请求修改的字段和值。

请求体：

| 字段 | 必填 | 类型 | 约束与含义 |
|---|---|---|---|
| `id` | 是 | integer | 项目 ID |
| `projectName` | 否 | string | 新项目名称；传入时不能是空白字符串 |
| `status` | 否 | integer | `0` 停用，`1` 启用 |

`projectName`、`status` 至少传一个。只发送需要修改的字段，未发送或值为 `null` 的字段不会更新。

请求示例：

```json
{
  "id": 101,
  "projectName": "2026 秋季新品短视频",
  "status": 1
}
```

成功响应：

```json
{
  "success": true,
  "code": "1",
  "message": "项目修改成功",
  "data": {
    "id": 101,
    "updatedContent": {
      "projectName": "2026 秋季新品短视频",
      "status": 1
    }
  },
  "timestamp": "1788854400000"
}
```

常见失败原因：

- `项目id不能为空`
- `项目名称不能为空`
- `没有需要修改的项目内容`
- `项目不存在或修改失败`

### 3.3 分页查询项目

```text
POST /project/v1/page
operationId: projectPage
Content-Type: application/json
```

请求体：

| 字段 | 必填 | 类型 | 约束与含义 |
|---|---|---|---|
| `id` | 否 | integer | 项目 ID 精确匹配 |
| `projectName` | 否 | string | 项目名称精确匹配；当前 Backend 不支持模糊查询 |
| `status` | 否 | integer | `0` 停用，`1` 启用 |
| `pageNo` | 否 | integer | 页码，从 1 开始，默认 1 |
| `pageSize` | 否 | integer | 每页条数，默认 10 |

请求示例：

```json
{
  "status": 1,
  "pageNo": 1,
  "pageSize": 10
}
```

结果按 `updateTime` 倒序、相同更新时间下按 `id` 倒序排列。响应 `data` 类型为 `PageInfo<ProjectDTO>`。

`ProjectDTO` 字段：

| 字段 | 类型 | 含义 |
|---|---|---|
| `id` | integer | 项目 ID |
| `projectName` | string | 项目名称 |
| `status` | integer | `0` 停用，`1` 启用 |
| `createTime` | date \| null | 创建时间 |
| `createId` | integer \| null | 创建人 ID，即新增项目时使用的 AppKey 所属用户 ID |
| `updateTime` | date \| null | 最后更新时间 |
| `updateId` | integer \| null | 最后更新人 ID |

## 4. FileController

文件接口把文件内容存入 AWS S3，把元数据存入数据库。文件类型完全根据原始文件名扩展名判断，不会识别实际二进制内容。

类型判断规则：

| `fileType` | 扩展名，不区分大小写 |
|---|---|
| `VIDEO` | `mp4`、`avi`、`mov`、`mkv`、`flv`、`wmv` |
| `IMAGE` | `png`、`jpg`、`bmp` |
| `OTHER` | 其他扩展名或无扩展名 |

### 4.1 上传实体文件

```text
POST /file/v1/upload
operationId: fileUpload
Content-Type: multipart/form-data
```

用途：直接把调用方提供的二进制文件上传到 S3，并保存文件元数据。适合 Backend 能直接接收文件内容的场景。

multipart 字段：

| 字段 | 必填 | 类型 | 约束与含义 |
|---|---|---|---|
| `projectId` | 是 | integer/form field | 文件所属项目 ID |
| `originalFileName` | 是 | string/form field | 原始文件名，不能为空；用于确定展示文件名、文件类型和扩展名 |
| `file` | 是 | binary/file part | 原始文件，不能为空；文件名用于判断类型和扩展名 |

请求大小上限为 500 MB。当前代码不主动校验 `projectId` 对应的项目是否存在。

请求示例：

```bash
curl -X POST 'http://127.0.0.1:8080/admin/file/v1/upload' \
  -H 'appkey: <YOUR_APP_KEY>' \
  -F 'projectId=101' \
  -F 'originalFileName=demo.mp4' \
  -F 'file=@/absolute/path/demo.mp4;type=video/mp4'
```

处理结果：

- 原始文件名会去掉调用方可能携带的目录部分。
- 扩展名统一保存为小写且不包含点。
- S3 Key 格式为 `project/{projectId}/file/{yyyyMMdd}/{uuid}.{extension}`。
- 视频文件会尝试通过 FFmpeg 计算时长，单位为秒。
- 上传后返回有效期 1 小时的 `previewUrl`。

响应 `data` 类型为 `FileDTO`，见 [4.5 FileDTO](#45-filedto)。

### 4.2 根据链接上传文件

```text
POST /file/v1/upload/url
operationId: fileUploadByUrl
Content-Type: application/json
```

用途：让 Backend 从远程 HTTP/HTTPS 地址下载文件，再上传到 S3。适合已有服务端可访问文件 URL 的场景。

请求体：

| 字段 | 必填 | 类型 | 约束与含义 |
|---|---|---|---|
| `projectId` | 是 | integer | 文件所属项目 ID |
| `fileUrl` | 是 | string/URI | 服务端可访问的 `http://` 或 `https://` 文件地址 |
| `originalFileName` | 条件必填 | string | 希望保存的原始文件名。URL 路径中无法识别文件名时必须传入；也可主动传入以覆盖 URL 中的文件名 |

请求示例：

```json
{
  "projectId": 101,
  "fileUrl": "https://cdn.example.com/assets/demo.mp4?token=temporary-token",
  "originalFileName": "新品宣传片.mp4"
}
```

远程下载约束：

- 仅支持 HTTP 和 HTTPS。
- 文件最大 500 MB；无 `Content-Length` 时也会在流式读取过程中限制大小。
- 连接超时 10 秒，读取超时 60 秒。
- 未传 `originalFileName` 时，从 URL path 的最后一段提取文件名，不使用 Query 参数命名。
- 文件类型和扩展名以最终确定的 `originalFileName` 为准。

响应 `data` 类型为 `FileDTO`，见 [4.5 FileDTO](#45-filedto)。

常见失败原因：

- `项目id不能为空`
- `文件链接不能为空`
- `原始文件名不能为空`
- `文件链接格式不正确`
- `文件链接仅支持HTTP或HTTPS协议`
- `远程文件大小不能超过500MB`
- `远程文件上传失败`

### 4.3 修改文件

```text
POST /file/v1/update
operationId: fileUpdate
Content-Type: application/json
```

用途：修改文件记录的业务归属、展示文件名或启用状态，不会重新上传或移动 S3 对象。

请求体：

| 字段 | 必填 | 类型 | 约束与含义 |
|---|---|---|---|
| `id` | 是 | integer | 文件 ID |
| `projectId` | 否 | integer | 新的所属项目 ID |
| `originalFileName` | 否 | string | 新的展示文件名；传入时不能是空白字符串 |
| `status` | 否 | integer | `0` 停用，`1` 启用 |

只发送需要修改的字段，未发送或值为 `null` 的字段不会更新。

请求示例：

```json
{
  "id": 501,
  "originalFileName": "新品宣传片-终版.mp4",
  "status": 1
}
```

成功响应的 `data` 为 `true`。

重要语义：

- 修改 `projectId` 只更新数据库归属，不会移动或重命名 `fileKey` 指向的 S3 对象。
- 修改 `originalFileName` 只修改展示文件名，不会同步修改 `extensionName`、`fileType` 或 `fileKey`。
- 当前实现不要求至少修改一个可选字段。
- 当前实现不检查实际更新行数，`id` 不存在时仍可能返回成功。

### 4.4 分页查询文件

```text
POST /file/v1/page
operationId: filePage
Content-Type: application/json
```

请求体：

| 字段 | 必填 | 类型 | 约束与含义 |
|---|---|---|---|
| `projectId` | 否 | integer | 所属项目 ID 精确匹配 |
| `originalFileName` | 否 | string | 原始文件名包含匹配，支持模糊查询 |
| `fileType` | 否 | string | `VIDEO`、`IMAGE`、`OTHER` 之一 |
| `status` | 否 | integer | `0` 停用，`1` 启用 |
| `pageNo` | 否 | integer | 页码，从 1 开始，默认 1 |
| `pageSize` | 否 | integer | 每页条数，默认 10 |

请求示例：

```json
{
  "projectId": 101,
  "fileType": "VIDEO",
  "status": 1,
  "pageNo": 1,
  "pageSize": 20
}
```

结果按 `updateTime` 倒序、相同更新时间下按 `id` 倒序排列。响应 `data` 类型为 `PageInfo<FileDTO>`。

每次查询都会为每个存在 `fileKey` 的文件生成新的 S3 临时访问链接，`previewUrl` 有效期为 1 小时，不应持久化后长期复用。当前查询没有按 `deletedTime` 自动排除记录。

### 4.5 FileDTO

| 字段 | 类型 | 含义 |
|---|---|---|
| `id` | integer | 文件 ID |
| `projectId` | integer | 文件当前所属项目 ID |
| `originalFileName` | string | 面向用户显示的原始文件名 |
| `fileType` | string | `VIDEO`、`IMAGE` 或 `OTHER`，上传时按文件名扩展名确定 |
| `fileKey` | string | S3 内部对象 Key，不是可直接访问的公共 URL |
| `previewUrl` | string \| null | S3 预签名临时访问 URL，有效期 1 小时 |
| `extensionName` | string | 小写扩展名，不含点；无扩展名时为空字符串 |
| `videoTime` | integer \| null | 视频时长，单位秒；非视频通常为 `null` |
| `fileSize` | string | 文件大小，单位字节；因为 Long 序列化规则，以字符串返回 |
| `etag` | string \| null | S3 对象 ETag；它不应被当作通用 SHA-256 |
| `uploadType` | string | `FILE` 表示实体文件上传，`URL` 表示链接上传 |
| `status` | integer | `0` 停用，`1` 启用 |
| `deletedTime` | date \| null | 删除时间；当前 Controller 没有删除接口 |
| `createTime` | date \| null | 创建时间；新增响应中可能为 `null`，分页结果来自数据库 |
| `createId` | integer \| null | 上传人 ID |
| `updateTime` | date \| null | 最后更新时间 |
| `updateId` | integer \| null | 最后更新人 ID |

响应示例：

```json
{
  "id": 501,
  "projectId": 101,
  "originalFileName": "新品宣传片.mp4",
  "fileType": "VIDEO",
  "fileKey": "project/101/file/20260908/7a948d5e51634b8d85b47daaf41d3dad.mp4",
  "previewUrl": "https://example-bucket.s3.example.com/project/101/file/...?signature=...",
  "extensionName": "mp4",
  "videoTime": 38,
  "fileSize": "28490123",
  "etag": "9b2cf535f27731c974343645a3985328",
  "uploadType": "FILE",
  "status": 1,
  "deletedTime": null,
  "createTime": 1788854400000,
  "createId": 12,
  "updateTime": 1788854400000,
  "updateId": 12
}
```

## 5. AI/客户端代码生成约束

将本文档交给 AI 生成客户端时，应同时遵循以下规则：

1. 所有路径都拼接在 `{baseUrl}/admin` 后，避免重复或遗漏 `/admin`。
2. 所有请求都使用 POST；除 `/file/v1/upload` 外，请求体都是 JSON。
3. 每个请求必须注入 `appkey` Header，不要把 AppKey 作为 JSON 字段或 URL 参数。
4. HTTP `2xx` 不等于业务成功，必须判断 `response.success === true`。
5. 将 `Result.code`、`Result.timestamp`、`FileDTO.fileSize` 声明为字符串，避免 64 位整数精度丢失。
6. 更新接口只发送调用方明确要求修改的字段，不要用 `null` 代表“不修改”之外的业务含义。
7. 分页调用保证 `pageNo >= 1`、`pageSize >= 1`。
8. 枚举按文档中的大写字符串和数字值原样发送，不要自行翻译。
9. `previewUrl` 是短期链接；需要访问文件时应重新查询，不要把它当永久地址保存。
10. 对文件上传保留原始二进制内容和原始文件名，不要在未被要求时压缩、转码或重编码。

可供 TypeScript 客户端直接参考的公共类型：

```ts
export type Int64String = string;
export type BackendDate = number | string;

export interface ApiResult<T> {
  success: boolean;
  code: Int64String;
  message: string;
  data: T | null;
  timestamp: Int64String;
}

export interface PageParam {
  nextPage: number;
  previousPage: number;
  pageSize: number;
  pageNo: number;
  pageTotal: number;
  totalCount: number;
}

export interface PageInfo<T> {
  pageParam: PageParam;
  items: T[];
}

export type EnableStatus = 0 | 1;
export type FileType = "VIDEO" | "IMAGE" | "OTHER";
export type FileUploadType = "FILE" | "URL";
```

推荐的通用错误处理伪代码：

```ts
const response = await http.post<ApiResult<T>>(path, body, {
  headers: { appkey }
});

if (!response.data.success) {
  throw new BackendApiError(
    response.data.code,
    response.data.message,
    response.status
  );
}

return response.data.data;
```

## 6. 当前实现注意事项汇总

这些行为来自当前源码，生成调用代码时不能假定 Backend 已做额外保护：

- 用户分页当前只返回正确的统计数，`items` 始终为空。
- 用户更新和文件更新不校验目标记录是否存在，可能在零行更新时仍返回成功。
- 项目名称分页筛选是精确匹配，不是模糊匹配。
- 状态字段没有强制枚举校验，调用方应只传 `0` 或 `1`。
- 项目与文件的关联没有在 Controller/Service 中校验；上传文件前应由调用方确认项目 ID 有效。
- 修改文件名不会重新计算文件类型或扩展名，修改文件项目不会移动 S3 对象。
- 项目停用不会自动阻止其文件上传或查询。
- 文件列表不会自动过滤 `deletedTime` 非空的记录。
- 新增项目、上传文件的响应没有重新查询数据库，数据库默认生成的时间字段可能暂时为 `null`。
