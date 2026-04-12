# 快速重构完成指南

## 新增文件概览

本次重构新增了以下文件，用于统一响应格式、配置管理和服务层封装：

```
app/
├── __init__.py                 # 应用模块入口
├── config.py                   # 配置管理
├── utils/
│   ├── __init__.py            # 工具模块入口
│   └── response.py            # 统一响应格式
└── services/
    ├── __init__.py            # 服务模块入口
    ├── oss_service.py         # 阿里云 OSS 服务
    └── file_service.py        # 文件上传服务

requirements.dev.txt            # 开发依赖
```

---

## 使用指南

### 1. 配置管理 (app/config.py)

```python
from app.config import config

# 读取配置
print(config.SECRET_KEY)
print(config.DB_TYPE)

# 检查配置状态
if config.is_oss_enabled():
    print("OSS 已启用")
if config.is_volcengine_configured():
    print("火山引擎已配置")
```

**环境变量配置** (.env):
```env
# Flask 配置
SECRET_KEY=your-secret-key
FLASK_DEBUG=false

# 数据库配置
DB_TYPE=sqlite
DB_PATH=generation_records.db

# MySQL 配置（可选）
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=ai_app
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=ai_generator

# 火山引擎配置
VOLCENGINE_AK=your-access-key
VOLCENGINE_SK=your-secret-key

# OSS 配置
OSS_ENABLED=true
OSS_ENDPOINT=bucket.oss-region.aliyuncs.com
OSS_ACCESS_KEY_ID=your-access-key
OSS_ACCESS_KEY_SECRET=your-secret-key
```

---

### 2. 统一响应格式 (app/utils/response.py)

```python
from flask import Flask, request
from app.utils import ApiResponse

app = Flask(__name__)

# 成功响应
@app.route('/api/users')
def get_users():
    data = [{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Bob'}]
    return ApiResponse.success(data, "获取成功")

# 错误响应
@app.route('/api/users/<int:user_id>')
def get_user(user_id):
    user = database.get_user(user_id)
    if not user:
        return ApiResponse.not_found("用户不存在")
    return ApiResponse.success(user)

# 分页响应
@app.route('/api/users')
def list_users():
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 10))
    users, total = database.list_users(page, page_size)
    return ApiResponse.paginated(users, total, page, page_size)

# 创建成功 (201)
@app.route('/api/users', methods=['POST'])
def create_user():
    data = request.json
    user_id = database.create_user(data)
    return ApiResponse.created({'id': user_id}, "用户创建成功")

# 无内容 (204)
@app.route('/api/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    database.delete_user(user_id)
    return ApiResponse.no_content()
```

**快捷方法**:
- `ApiResponse.success(data, message, code)` - 成功响应
- `ApiResponse.error(message, code, details)` - 错误响应
- `ApiResponse.created(data, message)` - 创建成功 (201)
- `ApiResponse.no_content(message)` - 无内容 (204)
- `ApiResponse.bad_request(message, details)` - 错误请求 (400)
- `ApiResponse.unauthorized(message)` - 未授权 (401)
- `ApiResponse.forbidden(message)` - 禁止访问 (403)
- `ApiResponse.not_found(message)` - 资源不存在 (404)
- `ApiResponse.conflict(message)` - 资源冲突 (409)
- `ApiResponse.server_error(message)` - 服务器错误 (500)

---

### 3. OSS 服务 (app/services/oss_service.py)

```python
from app.services import oss_service

# 检查 OSS 是否可用
if oss_service.is_available():
    print("OSS 可用")

# 上传文件
oss_url = oss_service.upload_file(
    file_path="/path/to/image.jpg",
    user_id=1,
    project_id=1,
    file_type="image"  # image, video, sample, person, scene, document
)
print(oss_url)  # https://bucket.oss-region.aliyuncs.com/...

# 列出示例图片
images = oss_service.list_sample_images(user_id=1, project_id=1)
for img in images:
    print(img['url'], img['filename'])

# 删除文件
oss_service.delete_file("sample/user_1/image.jpg")

# 检查文件是否存在
exists = oss_service.file_exists("sample/user_1/image.jpg")
```

---

### 4. 文件上传服务 (app/services/file_service.py)

```python
from flask import request
from app.services import file_upload_service
from app.utils import ApiResponse

@app.route('/api/upload', methods=['POST'])
def upload_file():
    file = request.files.get('file')
    user_id = session.get('user_id')
    project_id = request.form.get('project_id')

    # 保存上传的文件
    success, path_or_url, error = file_upload_service.save_uploaded_file(
        file=file,
        user_id=user_id,
        project_id=project_id,
        subfolder="images",
        file_type="image",
        upload_to_oss=True  # 如果 OSS 可用，上传到 OSS
    )

    if not success:
        return ApiResponse.bad_request(error)

    return ApiResponse.success({'url': path_or_url}, "上传成功")
```

---

## 迁移 web_app.py

### 迁移前（旧代码）:

```python
# web_app.py
from flask import jsonify

@app.route('/api/test')
def test():
    data = {'message': 'hello'}
    return jsonify({'success': True, 'data': data})
```

### 迁移后（新代码）:

```python
# web_app.py
from app.utils import ApiResponse

@app.route('/api/test')
def test():
    data = {'message': 'hello'}
    return ApiResponse.success(data)
```

### OSS 使用迁移:

**迁移前**:
```python
# web_app.py
def upload_to_aliyun_oss(file_path, user_id=None, is_sample=False, is_video=False, project_id=None):
    # ... 50+ 行代码
    pass
```

**迁移后**:
```python
# web_app.py
from app.services import oss_service

oss_url = oss_service.upload_file(
    file_path=file_path,
    user_id=user_id,
    project_id=project_id,
    file_type="sample" if is_sample else "video" if is_video else "image"
)
```

---

## 安装开发依赖

```bash
pip install -r requirements.dev.txt
```

开发工具说明:
- `black` - 代码格式化: `black .`
- `isort` - import 排序: `isort .`
- `flake8` - 代码检查: `flake8 .`
- `pytest` - 运行测试: `pytest`
- `mypy` - 类型检查: `mypy .`

---

## 下一步建议

1. **逐步迁移 web_app.py**
   - 先替换简单的响应格式
   - 再替换 OSS 相关调用
   - 最后替换文件上传逻辑

2. **添加类型注解**
   ```python
   def my_view(user_id: int) -> tuple[Response, int]:
       return ApiResponse.success({'id': user_id})
   ```

3. **编写测试**
   ```python
   # tests/test_utils.py
   from app.utils import ApiResponse

   def test_success_response():
       response, status = ApiResponse.success({'test': 'data'})
       assert status == 200
       # ...
   ```

4. **继续模块化**
   - 将路由按功能分组到 `app/api/` 目录
   - 提取业务逻辑到 `app/services/`
   - 引入 ORM 替代原生 SQL