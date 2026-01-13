# 应用日志系统文档

## 概述
本应用已实现了完整的操作日志记录系统，用于追踪用户活动、调试问题和分析应用性能。所有日志均输出到控制台和 `app.log` 文件。

## 日志配置

### 日志文件位置
- **文件位置**: `app.log` (项目根目录)
- **日志级别**: INFO, WARNING, ERROR
- **时间格式**: `YYYY-MM-DD HH:MM:SS`
- **日志输出**: 同时输出到文件和控制台

### 日志函数

#### 1. `log_operation(operation, details=None, level='INFO')`
记录操作类日志，包括业务操作的执行结果。

**参数:**
- `operation`: 操作名称（字符串）
- `details`: 详细信息（可选），可包含用户ID、结果、错误信息
- `level`: 日志级别（'INFO', 'WARNING', 'ERROR'）

**示例输出:**
```
2024-01-15 10:30:45 - [INFO] - [操作] 生成图片成功 | 用户ID: 123, 提示词长度: 156, 生成图片数: 4
2024-01-15 10:32:10 - [ERROR] - [操作] 删除记录失败 | 用户ID: 123, 错误: 数据库连接异常
```

#### 2. `log_request(method, endpoint, user_id=None, params=None)`
记录API请求的入口，包含请求方法、端点和用户信息。

**参数:**
- `method`: HTTP方法（GET, POST, DELETE等）
- `endpoint`: API端点路径
- `user_id`: 用户ID（可选）
- `params`: 请求参数描述（可选）

**示例输出:**
```
2024-01-15 10:30:30 - [INFO] - [请求] POST /api/generate | 用户: 123 | 参数: 提示词长度: 156
2024-01-15 10:32:00 - [INFO] - [请求] DELETE /api/records/456 | 用户: 123
```

#### 3. `log_response(endpoint, status, message=None)`
记录API响应信息（当前使用较少）。

## 已集成的日志操作

### 认证操作
| 操作 | 端点 | 日志内容 |
|-----|------|--------|
| 登录成功 | POST /login | 用户ID, 用户名 |
| 登录失败 | POST /login | 错误原因 |
| 注册 | POST /register | 新用户ID |
| 登出 | GET /logout | 用户ID |

### 图片生成
| 操作 | 端点 | 日志内容 |
|-----|------|--------|
| 单图生成 | POST /api/generate | 提示词长度, 生成数量 |
| 生成成功 | POST /api/generate | 输出目录, 文件数量 |
| 生成失败 | POST /api/generate | 错误信息 |
| 批量生成提交 | POST /api/batch-generate-all | 任务总数, 批次ID |

### 脚本分析
| 操作 | 端点 | 日志内容 |
|-----|------|--------|
| 分析请求 | POST /api/analyze-script | 脚本长度 |
| 分析成功 | POST /api/analyze-script | 生成的场景数 |
| 分析异常 | POST /api/analyze-script | 错误类型, 错误信息 |

### 记录管理
| 操作 | 端点 | 日志内容 |
|-----|------|--------|
| 获取记录列表 | GET /api/records | 页码, 每页数量, 搜索关键词, 返回记录数 |
| 删除单条记录 | DELETE /api/records/{id} | 记录ID |
| 批量删除记录 | POST /api/batch-delete | 成功数, 失败数 |

### 样本图管理
| 操作 | 端点 | 日志内容 |
|-----|------|--------|
| 获取样本列表 | GET /api/sample-images | 类别, 返回图片数 |
| 上传样本图 | POST /api/upload-sample-image | 文件名, 类别, 文件大小 |
| 删除样本图 | POST /api/delete-sample-image | 文件路径 |

### 库资源管理
| 操作 | 端点 | 日志内容 |
|-----|------|--------|
| 添加到人物库 | POST /api/add-to-person-library | 文件名 |
| 添加到场景库 | POST /api/add-to-scene-library | 文件名 |
| 删除库资源 | POST /api/delete-library-asset | 资源ID, 资源类型 |

### 应用启动
| 操作 | 说明 | 日志内容 |
|-----|-----|--------|
| 应用启动 | 启动时记录 | 版本, 环境, 监听地址 |
| 数据库初始化 | 启动时记录 | 初始化状态 |
| OSS配置 | 启动时记录 | 端点信息(已配置)或警告(未配置) |

## 日志示例

### 完整的用户操作流程日志

```
2024-01-15 10:30:00 - [INFO] - [操作] 应用启动 | 版本: 1.0 | 环境: 开发 | 监听地址: 0.0.0.0:5000
2024-01-15 10:30:01 - [INFO] - [操作] 数据库初始化 | 状态: 已初始化
2024-01-15 10:30:02 - [INFO] - [操作] OSS配置 | 端点: shor-file.oss-cn-wulanchabu.aliyuncs.com

2024-01-15 10:31:00 - [INFO] - [请求] POST /login | 用户: admin
2024-01-15 10:31:01 - [INFO] - [操作] 用户登录 | 用户ID: 1, 用户名: admin

2024-01-15 10:31:15 - [INFO] - [请求] GET /api/records | 用户: 1 | 参数: 页码: 1, 每页: 20
2024-01-15 10:31:16 - [INFO] - [操作] 获取记录 | 用户ID: 1, 分页: 1/5, 返回: 20条

2024-01-15 10:32:00 - [INFO] - [请求] POST /api/generate | 用户: 1 | 参数: 提示词长度: 256
2024-01-15 10:32:15 - [INFO] - [操作] 生成图片成功 | 用户ID: 1, 输出目录: output/1, 生成图片: 4

2024-01-15 10:33:00 - [INFO] - [请求] POST /api/add-to-person-library | 用户: 1 | 文件: avatar.png
2024-01-15 10:33:02 - [INFO] - [操作] 添加人物库资源 | 用户ID: 1, 文件: avatar.png

2024-01-15 10:34:00 - [INFO] - [请求] POST /api/analyze-script | 用户: 1 | 参数: 脚本长度: 512
2024-01-15 10:34:30 - [INFO] - [操作] 分析脚本成功 | 用户ID: 1, 生成场景数: 5

2024-01-15 10:35:00 - [INFO] - [请求] GET /logout | 用户: 1
2024-01-15 10:35:01 - [INFO] - [操作] 用户登出 | 用户ID: 1, 用户名: admin
```

## 日志分析建议

### 性能监控
- 查看日志中操作的时间间隔，识别缓慢的操作
- 监控API响应时间（请求时间到操作时间）

### 错误追踪
- 查看所有 ERROR 级别的日志
- 关键字搜索：`失败`, `异常`, `错误`

### 用户行为分析
- 统计特定用户的操作频率
- 跟踪用户的完整操作路径
- 分析功能使用情况

### 系统健康检查
- 检查启动日志中的初始化状态
- 监控OSS配置和数据库连接状态

## 日志查看命令

### 实时查看日志
```bash
# Windows PowerShell
Get-Content app.log -Wait

# Linux/Mac
tail -f app.log
```

### 查找特定用户的日志
```bash
# Windows PowerShell
Select-String "用户ID: 123" app.log

# Linux/Mac
grep "用户ID: 123" app.log
```

### 查找错误日志
```bash
# Windows PowerShell
Select-String "\[ERROR\]" app.log

# Linux/Mac
grep "\[ERROR\]" app.log
```

### 统计操作次数
```bash
# 统计生成图片的次数
grep "生成图片成功" app.log | Measure-Object -Line
```

## 配置说明

### 修改日志级别
在 `web_app.py` 第17行修改：
```python
logging.basicConfig(
    level=logging.INFO,  # 改为 DEBUG 获取更详细的日志
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    ...
)
```

### 日志保留策略
当前所有日志追加到 `app.log`。建议定期备份或实现日志轮转：
```python
from logging.handlers import RotatingFileHandler

handler = RotatingFileHandler(
    'app.log', 
    maxBytes=10485760,  # 10MB
    backupCount=5       # 保留5个备份
)
```

## 注意事项

1. **敏感信息**: 日志中不记录密码或API密钥
2. **性能**: 日志记录对性能的影响很小
3. **存储**: 定期检查 `app.log` 文件大小，必要时实施日志轮转
4. **隐私**: 遵守数据隐私法规，定期清理旧日志

## 故障排查

### 日志文件不更新
- 检查 `app.log` 文件权限
- 确保应用有写入权限
- 检查磁盘空间是否充足

### 日志内容不完整
- 确保应用正常运行
- 检查异常处理代码中的日志记录
- 验证 `log_operation()` 调用是否正确

### 文件过大
- 实施日志轮转策略
- 使用脚本定期清理旧日志
- 考虑使用外部日志服务
