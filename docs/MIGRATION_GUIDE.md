# 模块化重构迁移指南

## 概述

本文档说明如何将 `web_app.py` 中的代码逐步迁移到新的模块化架构。

---

## 新的目录结构

```
ai-generator/
├── app/                           # 新的模块化应用
│   ├── __init__.py               # 应用模块入口
│   ├── config.py                 # 配置管理
│   ├── decorators.py             # 装饰器
│   ├── extensions.py             # 扩展初始化
│   ├── utils/                    # 工具模块
│   │   ├── __init__.py
│   │   └── response.py           # 统一响应格式
│   ├── services/                 # 服务层
│   │   ├── __init__.py
│   │   ├── oss_service.py        # OSS 服务
│   │   └── file_service.py       # 文件服务
│   └── api/                      # API 路由
│       ├── __init__.py
│       ├── auth.py               # 认证
│       ├── projects.py           # 项目管理
│       ├── admin.py              # 管理员
│       ├── image.py              # 图片生成
│       ├── batch.py              # 批量生成
│       ├── video.py              # 视频生成
│       ├── script.py             # 剧本
│       ├── storyboard.py         # 分镜
│       ├── tools.py              # 工具
│       └── content.py            # 内容管理
├── web_app.py                    # 原始文件（逐步迁移）
├── app_new.py                    # 新的应用入口示例
└── database.py                   # 数据库模块
```

---

## 迁移步骤

### 阶段 1: 替换响应格式

**目标**: 将 `jsonify` 替换为 `ApiResponse`

#### 旧代码:
```python
# web_app.py
from flask import jsonify

@app.route('/api/test')
def test():
    data = {'message': 'hello'}
    return jsonify({'success': True, 'data': data})
```

#### 新代码:
```python
# app/api/your_module.py
from app.utils import ApiResponse

@app.route('/api/test')
def test():
    data = {'message': 'hello'}
    return ApiResponse.success(data)
```

**批量替换**:
```bash
# 查找所有使用 jsonify 的地方
grep -n "jsonify" web_app.py

# 常见模式替换:
# jsonify({'success': True, 'data': data}) -> ApiResponse.success(data)
# jsonify({'success': False, 'error': msg}) -> ApiResponse.error(msg)
# jsonify(data) -> ApiResponse.success(data)
```

---

### 阶段 2: 替换 OSS 调用

**目标**: 将 OSS 操作迁移到 `oss_service`

#### 旧代码:
```python
# web_app.py (123-369行)
def upload_to_aliyun_oss(file_path, user_id=None, is_sample=False, is_video=False, project_id=None):
    # ... 50+ 行代码
    pass

def get_oss_bucket():
    # ... 代码
    pass

def list_sample_images_from_oss(user_id=None, project_id=None):
    # ... 代码
    pass

# 使用
oss_url = upload_to_aliyun_oss(file_path, user_id, is_sample, is_video, project_id)
```

#### 新代码:
```python
# 在需要使用的地方
from app.services import oss_service

# 上传文件
oss_url = oss_service.upload_file(
    file_path=file_path,
    user_id=user_id,
    project_id=project_id,
    file_type="sample" if is_sample else "video" if is_video else "image"
)

# 列出示例图片
images = oss_service.list_sample_images(user_id, project_id)
```

---

### 阶段 3: 替换文件上传逻辑

**目标**: 将文件上传迁移到 `file_upload_service`

#### 旧代码:
```python
# web_app.py - 分散在各个路由中
file = request.files.get('file')
if file:
    filename = secure_filename(file.filename)
    file_path = os.path.join(upload_folder, filename)
    file.save(file_path)
    # ... 验证、上传到 OSS 等逻辑
```

#### 新代码:
```python
from app.services import file_upload_service

success, path_or_url, error = file_upload_service.save_uploaded_file(
    file=file,
    user_id=user_id,
    project_id=project_id,
    subfolder="images",
    file_type="image",
    upload_to_oss=True
)

if not success:
    return ApiResponse.bad_request(error)
```

---

### 阶段 4: 迁移路由到模块

#### 认证相关路由 → `app/api/auth.py`

需要迁移的路由:
- `/login` (GET, POST) - 540-565行
- `/register` (GET, POST) - 566-571行
- `/logout` - 572-579行

#### 项目管理路由 → `app/api/projects.py`

需要迁移的路由:
- `/api/projects` (GET) - 580-592行
- `/api/projects/switch` (POST) - 593-613行

#### 管理员路由 → `app/api/admin.py`

需要迁移的路由:
- `/admin` - 624-632行
- `/api/admin/users` (GET, POST) - 633-655行
- `/api/admin/users/<user_id>` (DELETE) - 656-667行
- `/api/admin/users/<user_id>/password` (POST) - 668-678行
- `/api/admin/projects` (GET, POST) - 679-687行
- `/api/admin/projects/<project_id>/assign` (POST) - 700-710行
- `/api/admin/projects/<project_id>/revoke` (POST) - 711-721行
- `/api/stats` - 614-623行
- `/api/stats` (GET) - 722-969行

#### 图片生成路由 → `app/api/image.py`

需要迁移的路由:
- `/api/image-styles` (GET) - 3076-3091行
- `/api/recent-images` (GET) - 3092-3129行
- `/api/sample-images` (GET) - 2989-3075行
- `/api/upload-sample-image` (POST) - 5075-5191行
- `/api/delete-sample-image` (POST) - 5237-5283行
- `/generate` (POST) - 2957-2988行
- `/generate/stream` (GET) - 2957-2988行
- `/api/delete-image-asset` (POST) - 4942-4966行

#### 批量生成路由 → `app/api/batch.py`

需要迁移的路由:
- `/batch` - 3130-3135行
- `/records` - 3136-3141行
- `/api/batch-generate` (POST) - 3278-3514行
- `/api/batch-generate-all` (POST) - 5480-5756行
- `/api/batch-progress/<batch_id>` (GET) - 5757-5789行
- `/api/records` (GET) - 4988-5025行
- `/api/records/<record_id>` (DELETE) - 5026-5043行
- `/api/batch-delete` (POST) - 5044-5074行
- `/api/download-file` (GET) - 5192-5236行

#### 视频生成路由 → `app/api/video.py`

需要迁移的路由:
- `/video-generate` - 3154-3159行
- `/video-tasks` - 3160-3165行
- `/api/video-tasks` (GET) - 3515-4540行
- `/api/video-tasks/<task_id>` (DELETE) - 4541-4598行
- `/api/video-generate` (POST) - 4599-4875行
- `/api/delete-video-asset` (POST) - 4967-4987行

#### 剧本相关路由 → `app/api/script.py`

需要迁移的路由:
- `/script-generate` - 3172-3177行
- `/script-analysis` - 3166-3171行
- `/api/script-generate` (POST) - 970-1168行
- `/api/script-generate-stream` (POST) - 970-1168行
- `/api/script-generate-async` (POST) - 1725-1756行
- `/api/tasks/<task_id>` (GET) - 1779-2956行
- `/api/script-saves` (GET, POST) - 相关路由
- `/api/script-episodes` (GET, POST, DELETE) - 相关路由
- `/api/script-episodes/<episode_id>/content` (GET) - 相关路由
- `/api/script-episodes/import` (POST) - 相关路由
- `/api/script-templates` (GET, POST) - 相关路由
- `/api/script-templates/<template_id>` (DELETE) - 相关路由

#### 分镜相关路由 → `app/api/storyboard.py`

需要迁移的路由:
- `/storyboard` - 3178-3184行
- `/storyboard-studio` - 3185-3190行
- `/api/storyboard-generate` (POST) - 1654-1724行
- `/api/storyboard-generate-async` (POST) - 1757-1778行
- `/api/storyboard-from-script` (POST) - 1243-1425行
- `/api/storyboard-queue` (GET) - 1426-1437行
- `/api/storyboard-queue/upload` (POST) - 1438-1483行
- `/api/storyboard-queue/<task_id>` (DELETE) - 1484-1497行
- `/api/storyboard-queue/process-one` (POST) - 1498-1611行
- `/api/storyboard-saves` (GET, POST) - 相关路由
- `/api/storyboard-series` (GET) - 相关路由
- `/api/storyboard-series/<series_id>/versions` (GET) - 相关路由
- `/api/storyboard-sample-images` (POST) - 相关路由
- `/api/storyboard-episodes` (GET, POST) - 相关路由

#### 工具类路由 → `app/api/tools.py`

需要迁移的路由:
- `/txt2csv` - 3191行
- `/api/txt2csv-stream` (POST) - 1169-1242行
- `/api/config-prompts` (GET, POST, DELETE) - 3214-3277行
- `/api/config-prompts/<filename>` (GET, DELETE) - 相关路由
- `/api/analyze-script` (POST) - 5809-6240行

#### 内容管理路由 → `app/api/content.py`

需要迁移的路由:
- `/content-management` - 3142-3147行
- `/manage-samples` - 3148-3153行
- `/api/content-library` (GET) - 4876-4941行
- `/api/add-to-person-library` (POST) - 5326-5479行
- `/api/add-to-scene-library` (POST) - 5406-5808行
- `/api/delete-library-asset` (POST) - 5284-5325行
- `/output/<user_id>/<project_id>/<filename>` - 5790-5799行
- `/output/<user_id>/<filename>` - 5800-5808行

---

## 迁移模板

### 迁移单个路由的模板

#### 步骤 1: 在对应的 API 模块中创建函数

```python
# app/api/example.py
from flask import Blueprint, request, session
from app.utils import ApiResponse
from app.decorators import login_required
import database

# 创建蓝图
example_bp = Blueprint('example', __name__)

@example_bp.route('/api/example', methods=['GET'])
@login_required
def example_route():
    # 1. 从 session 获取用户信息
    user_id = session.get('user_id')
    project_id = session.get('current_project_id')

    # 2. 从 request 获取参数
    param = request.args.get('param')

    # 3. 调用数据库函数
    result = database.get_example_data(user_id, project_id, param)

    # 4. 返回响应
    return ApiResponse.success(result)
```

#### 步骤 2: 在 web_app.py 中删除旧路由

```python
# 删除或注释掉旧路由
# @app.route('/api/example', methods=['GET'])
# def example_route():
#     # ... 旧代码
```

#### 步骤 3: 在 app_new.py 中注册蓝图

```python
from app.api.example import example_bp

def register_blueprints(app):
    app.register_blueprint(example_bp)
```

---

## 数据库适配

新模块依赖于以下 `database.py` 中的函数（可能需要添加）：

```python
# 项目相关
def get_user_projects(user_id)
def get_user_current_project(user_id)
def set_user_current_project(user_id, project_id)
def has_project_access(user_id, project_id)
def create_project(name, owner_id)
def delete_project(project_id)

# 用户相关
def get_all_users()
def create_user(username, password)
def delete_user(user_id)
def update_user_password(user_id, password)

# 统计相关
def get_system_stats(start_date, end_date)

# 图片相关
def get_image_styles()
def get_recent_images(user_id, project_id, limit)
def get_sample_images(user_id, project_id, category)
def add_sample_image(user_id, project_id, record)
def get_sample_image(image_id)
def delete_sample_image(image_id)
def generate_image(user_id, project_id, params)
def get_task_progress(user_id, task_id)
def get_generation_record(record_id)
def delete_generation_record(record_id)

# 批量生成相关
def create_batch_task(user_id, project_id, tasks)
def execute_batch_tasks(user_id, batch_id)
def get_batch_progress(user_id, batch_id)
def get_generation_records(user_id, project_id, page, page_size)
def batch_delete_records(user_id, record_ids)

# 视频相关
def generate_video(user_id, project_id, params)
def get_video_tasks(user_id, project_id, status, limit)
def get_video_task(task_id)
def delete_video_task(task_id)
def update_video_task_asset(task_id, field, value)

# 剧本相关
def generate_script(user_id, project_id, params)
def generate_script_stream(user_id, project_id, params)
def create_script_generation_task(user_id, project_id, params)
def get_generation_task(user_id, task_id)
def get_script_saves(user_id, project_id)
def save_script(user_id, project_id, data)
def get_script_episodes(user_id, script_id)
def create_script_episode(user_id, project_id, data)
def get_script_episode(user_id, episode_id)
def update_script_episode(episode_id, data)
def delete_script_episode(episode_id)
def import_script_episodes(user_id, project_id, script_id, episodes)
def get_script_templates(user_id, project_id)
def save_script_template(user_id, project_id, data)
def delete_script_template(user_id, template_id)

# 分镜相关
def generate_storyboard(user_id, project_id, params)
def create_storyboard_generation_task(user_id, project_id, params)
def get_storyboard_saves(user_id, project_id)
def save_storyboard(user_id, project_id, data)
def get_storyboard_series(user_id, project_id)
def get_storyboard_versions(user_id, series_id)
def save_storyboard_sample_images(user_id, project_id, images)
def get_storyboard_episodes(user_id, series_id)
def create_storyboard_episode(user_id, project_id, data)
def generate_storyboard_from_script(user_id, project_id, params)
def get_storyboard_queue_tasks(user_id)
def upload_storyboard_queue(user_id, project_id, files, prompt_file)
def delete_storyboard_queue_task(user_id, task_id)
def process_one_storyboard_queue_task(user_id)

# 内容库相关
def get_content_library(user_id, project_id, library_type)
def add_to_library(user_id, project_id, table_name, data)
def get_library_asset(user_id, asset_type, asset_id)
def delete_library_asset(user_id, asset_type, asset_id)
def create_image_style(user_id, project_id, data)
def delete_image_style(user_id, style_id)

# 工具相关
def txt2csv_stream(text)
def analyze_script(user_id, project_id, script_text)
```

---

## 测试迁移

迁移完成后，测试以下功能：

1. **基础功能**
   - 用户登录/登出
   - 项目切换
   - 页面访问

2. **核心功能**
   - 图片生成
   - 批量生成
   - 视频生成
   - 剧本生成
   - 分镜生成

3. **管理功能**
   - 用户管理
   - 项目管理
   - 统计查看

---

## 回滚方案

如果迁移出现问题，可以快速回滚：

1. 保留 `web_app.py` 作为备份
2. 使用 `python web_app.py` 启动旧版本
3. 新版本使用 `python app_new.py` 启动

迁移确认无误后：
1. 将 `app_new.py` 重命名为 `web_app.py`
2. 备份旧 `web_app.py` 为 `web_app.py.bak`