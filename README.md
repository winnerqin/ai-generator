# AI Generator

基于 Flask 的多用户 AI 内容生产平台，当前主入口为 `app_factory.py`。

项目已经完成从旧单体结构向模块化结构迁移，当前运行核心集中在：

- `app_factory.py`：应用入口
- `app/`：模块化 API、服务层、工具层
- `templates/` + `static/`：前端页面与资源
- `database.py`：SQLite 为主的数据访问层，保留 MySQL 迁移能力
- `tests/`：回归测试

## 功能概览

- 单图生成
- 批量生成
- 生图任务记录
- 视频生成与视频任务
- 全能视频与全能任务
- 剧本生成与剧本分析
- 分镜生成与分镜工作室
- 转换工具
- 内容管理
- 管理员后台与系统统计

## 运行环境

- Python 3.10+
- Windows / PowerShell 已验证
- SQLite 默认开箱可用
- 可选接入：
  - 火山方舟 / Seedance
  - 阿里云 OSS
  - MySQL

## 安装依赖

创建并激活虚拟环境后安装运行依赖：

```powershell
python -m venv .\venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

如需测试与格式化工具，再安装开发依赖：

```powershell
pip install -r requirements.dev.txt
```

## 环境变量

先复制示例配置：

```powershell
Copy-Item .env.example .env
```

常用配置项：

- `SECRET_KEY`：Flask 会话密钥
- `FLASK_HOST`：默认 `0.0.0.0`
- `FLASK_PORT`：默认 `8090`
- `FLASK_DEBUG`：是否开启调试
- `DB_TYPE`：`sqlite` 或 `mysql`
- `DB_PATH`：SQLite 文件路径
- `ARK_API_KEY`：Seedance / 方舟接口密钥
- `OSS_ENABLED`：是否启用 OSS
- `OSS_ENDPOINT`、`OSS_ACCESS_KEY_ID`、`OSS_ACCESS_KEY_SECRET`

## 启动方式

推荐直接使用主入口：

```powershell
.\venv\Scripts\python.exe .\app_factory.py
```

默认访问地址：

```text
http://127.0.0.1:8090
```

也可以通过环境变量覆盖：

```powershell
$env:FLASK_HOST="0.0.0.0"
$env:FLASK_PORT="8090"
$env:FLASK_DEBUG="false"
.\venv\Scripts\python.exe .\app_factory.py
```

## 用户与项目

- 登录后会根据 `user_projects` 自动选择当前项目
- 当前版本已具备“按项目切换”的基础能力
- 绝大多数业务数据仍是“用户 + 项目”双重过滤
- 也就是说：默认更偏向“用户在项目内工作”，不是“项目成员完全共享内容”

## 测试

运行全部测试：

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

## 保留脚本

仓库保留了少量仍有实际用途的辅助文件：

- `manage_users.py`：用户管理脚本
- `config/storyboard.md`
- `config/txt2csv.md`
- `docs/MIGRATE_TO_MYSQL.md`
- `scripts/schema_mysql.sql`

其余旧单体、迁移报告、调试脚本和重复说明文档已清理。
