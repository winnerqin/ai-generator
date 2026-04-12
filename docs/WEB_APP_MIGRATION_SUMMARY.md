# web_app.py 迁移总结

## 概述

本次迁移采用渐进式方法，在保持原有代码兼容的同时，逐步引入新模块的功能。

---

## 迁移策略

采用"兼容性优先"策略：
- 所有旧函数都保留为回退选项
- 新模块优先使用，失败时回退到旧实现
- 通过 `NEW_MODULES_AVAILABLE` 标志控制行为

---

## 已完成的迁移

### 1. 模块导入 ✅

在文件开头添加了新模块的兼容性导入：

```python
# 尝试导入新的模块，如果失败则继续使用旧代码
try:
    from app.utils import ApiResponse
    from app.services import oss_service, file_upload_service
    from app.decorators import login_required as new_login_required, admin_required as new_admin_required
    NEW_MODULES_AVAILABLE = True
except ImportError:
    NEW_MODULES_AVAILABLE = False
```

### 2. OSS 函数迁移 ✅

三个核心 OSS 函数已迁移到新模块：

#### upload_to_aliyun_oss()
- 优先使用 `oss_service.upload_file()`
- 参数映射：`is_sample` → `file_type='sample'`，`is_video` → `file_type='video'`
- 失败时回退到旧实现

#### get_oss_bucket()
- 优先使用 `oss_service.get_bucket()`
- 失败时回退到旧实现

#### list_sample_images_from_oss()
- 优先使用 `oss_service.list_sample_images()`
- 失败时回退到旧实现

### 3. API 响应格式迁移 ✅ (持续进行中)

已更新的 API 路由（约150+处）：

#### 项目管理 API
- `/api/projects` (GET) - 使用新模块
- `/api/projects/switch` (POST) - 使用新模块

#### 管理员 API
- `/api/admin/users` (GET, POST) - 使用新模块
- `/api/admin/users/<id>` (DELETE) - 使用新模块
- `/api/admin/users/<id>/password` (POST) - 使用新模块
- `/api/admin/projects` (GET, POST) - 使用新模块
- `/api/admin/projects/<id>/assign` (POST) - 使用新模块
- `/api/admin/projects/<id>/revoke` (POST) - 使用新模块

#### 分镜队列 API
- `/api/storyboard-queue` (GET) - 使用新模块
- `/api/storyboard-queue/upload` (POST) - 使用新模块
- `/api/storyboard-queue/<task_id>` (DELETE) - 使用新模块
- `/api/storyboard-queue/process-one` (POST) - 使用新模块

#### 剧本 API
- `/api/script-generate` (POST) - 使用新模块
- `/api/script-generate-async` (POST) - 使用新模块
- `/api/script-saves` (GET, POST) - 使用新模块
- `/api/script-saves/<record_id>` (GET) - 使用新模块
- `/api/script-episodes` (GET) - 使用新模块
- `/api/script-episodes/<episode_id>` (POST) - 使用新模块
- `/api/script-episodes/<episode_id>/content` (GET) - 使用新模块
- `/api/script-episodes/<episode_id>` (DELETE) - 使用新模块
- `/api/script-episodes/import` (POST) - 使用新模块
- `/api/script-templates` (GET) - 使用新模块
- `/api/script-templates` (POST) - 使用新模块
- `/api/script-templates/<template_id>` (DELETE) - 使用新模块

#### 分镜 API
- `/api/storyboard-generate` (POST) - 使用新模块
- `/api/storyboard-generate-async` (POST) - 使用新模块
- `/api/storyboard-saves` (GET, POST) - 使用新模块
- `/api/storyboard-saves/<record_id>` (GET) - 使用新模块
- `/api/storyboard-series` (GET) - 使用新模块
- `/api/storyboard-series/<series_id>/versions` (GET) - 使用新模块
- `/api/storyboard-sample-images` (POST) - 使用新模块
- `/api/storyboard-episodes` (GET, POST) - 使用新模块

#### 图片 API
- `/api/sample-images` (GET) - 使用新模块
- `/api/image-styles` (GET) - 使用新模块
- `/api/recent-images` (GET) - 使用新模块

#### 任务 API
- `/api/tasks/<task_id>` (GET) - 使用新模块

#### 视频 API
- `/api/video-tasks/<task_id>` (DELETE) - 使用新模块

#### 通用错误响应（批量替换）
- 所有 `return jsonify({'success': True})` - 使用新模块
- 所有 `if not project_id` 错误 - 使用新模块（多处）
- 所有 `if not prompt` 错误 - 使用新模块（多处）
- 所有 `if not api_key` 错误 - 使用新模块（多处）
- 所有 `if not generation_id` 错误 - 使用新模块（多处）
- 所有 `if not channel` 错误 - 使用新模块（多处）
- 所有 `if 'file' not in request.files` 错误 - 使用新模块（多处）
- 所有 `if not bucket` 错误 - 使用新模块（多处）
- 所有错误消息使用 ApiResponse 方法 - 使用新模块（多处）

---

## 代码变更统计

```
web_app.py | 约500+ 行修改
```

---

## 迁移模式

### 响应格式迁移模式

**旧代码：**
```python
return jsonify({'success': False, 'error': '错误信息'}), 400
```

**新代码：**
```python
if NEW_MODULES_AVAILABLE:
    from app.utils import ApiResponse
    return ApiResponse.bad_request("错误信息")
# 旧实现（保持兼容）
return jsonify({'success': False, 'error': '错误信息'}), 400
```

---

## 待完成的迁移

### 1. API 响应格式（剩余约 100 处）

优先级高的 API：
- 图片生成相关（约 20 处）
- 视频生成相关（约 15 处）
- 批量生成相关（约 10 处）
- 内容管理相关（约 20 处）

### 2. 文件上传逻辑

需要迁移的函数：
- 文件验证
- 文件保存
- 文件删除

### 3. 路由迁移到模块

将路由迁移到对应的 API 蓝图：
- `app/api/image.py` - 图片相关
- `app/api/batch.py` - 批量生成
- `app/api/video.py` - 视频生成
- `app/api/script.py` - 剧本相关
- `app/api/storyboard.py` - 分镜相关
- `app/api/tools.py` - 工具类

---

## 测试建议

### 兼容性测试
1. 测试新模块未安装时的行为
2. 测试 OSS 配置缺失时的行为
3. 测试响应格式是否一致

### 功能测试
1. 用户登录/登出
2. 项目切换
3. 用户管理（CRUD）
4. 项目管理（CRUD）
5. 图片上传到 OSS
6. 剧本生成
7. 分镜生成
8. 视频生成

---

## 迁移后的优势

### 即时优势（已完成）
- OSS 代码复用，减少维护
- 统一的 OSS 错误处理
- 更好的 OSS 功能（如更好的文件分类）
- 统一的响应格式（约60%已完成）
- 更好的错误处理

### 长期优势（待完成）
- 完全统一的响应格式
- 更好的错误处理
- 代码更易测试
- 更容易添加新功能

---

## 回滚方案

如果新模块出现问题：
1. 删除或注释掉模块导入
2. 设置 `NEW_MODULES_AVAILABLE = False`
3. 所有代码将回退到旧实现

---

## 下一步计划

1. 继续迁移高优先级 API 的响应格式
2. 创建批量替换脚本加速迁移
3. 逐步将路由迁移到 API 模块
4. 完成所有迁移后，清理旧代码