# AI Generator

基于 Flask 的多用户 AI 内容生产平台，当前主入口为 `app_factory.py`。

项目已经完成从旧单体结构向模块化结构迁移，当前运行核心集中在：

- `app_factory.py`：应用入口
- `app/`：模块化 API、服务层、工具层
- `templates/` + `static/`：前端页面与资源
- `database.py`：MySQL 数据访问层
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
- MySQL 8.0
- 可选接入：
  - 火山方舟 / Seedance
  - 阿里云 OSS

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
- `DB_TYPE`：固定为 `mysql`
- `MYSQL_HOST`、`MYSQL_PORT`：MySQL 8.0 服务地址和端口
- `MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_DATABASE`：MySQL 连接账号、密码和库名
- `MYSQL_CHARSET`：MySQL 字符集，推荐 `utf8mb4`
- `ARK_API_KEY`：Seedance / 方舟接口密钥
- `ARK_API_KEY_POOL`：全能视频国内版上游 Key 池，多个 Key 用英文逗号分隔；配置后创建任务会按稳定哈希分流到不同 Key
- `ARK_INTL_API_KEY_POOL`：全能视频国际版上游 Key 池，多个 Key 用英文逗号分隔
- `PUBLIC_BASE_URL`：对外可访问的服务基础地址，支付中心回调地址会基于它生成
- `PAYMENT_CENTER_ENABLED`：是否启用支付中心充值能力
- `PAYMENT_CENTER_BASE_URL`、`PAYMENT_CENTER_CREATE_ORDER_PATH`：支付中心地址与创建订单路径
- `PAYMENT_CENTER_MERCHANT_ID`、`PAYMENT_CENTER_APP_ID`、`PAYMENT_CENTER_SIGN_SECRET`：支付中心签名与商户配置
- `PAYMENT_CENTER_ALLOWED_AMOUNTS`：用户中心预设充值金额，单位元，逗号分隔
- `PAYMENT_CENTER_MIN_RECHARGE_CENT`、`PAYMENT_CENTER_MAX_RECHARGE_CENT`：自定义充值金额范围，单位分
- `SEEDANCE_OMNI_MODEL_INTERNAL`：内部用户可用全能视频模型列表（逗号分隔，按顺序展示）
- `SEEDANCE_OMNI_MODEL_EXTERNAL`：外部用户可用全能视频模型列表（逗号分隔，按顺序展示）
- `SEEDANCE_OMNI_MODEL_ALIASES`：模型别名映射（逗号分隔，格式 `模型编码:显示别名`）
- `OSS_ENABLED`：是否启用 OSS
- `OSS_ENDPOINT`、`OSS_ACCESS_KEY_ID`、`OSS_ACCESS_KEY_SECRET`

在 `.env` 中设置 MySQL 8.0 连接信息：

```text
DB_TYPE=mysql
MYSQL_HOST=your-mysql-host
MYSQL_PORT=3306
MYSQL_USER=ai_app
MYSQL_PASSWORD=your-password
MYSQL_DATABASE=ai_generator
MYSQL_CHARSET=utf8mb4
```

全能视频如需使用两个上游 API Key 共同承担并发，可以在 `.env` 中这样配置：

```text
ARK_API_KEY_POOL=key_a,key_b
ARK_INTL_API_KEY_POOL=intl_key_a,intl_key_b
```

说明：

- Web 界面创建全能视频任务和外部批量 API 都会走同一套上游 Key 分流逻辑
- 创建任务时会按 `batch_id`、`client_request_id`、`filename`、`prompt`、首个参考素材 URL 生成稳定路由键
- 同一个任务后续的查询、刷新、取消会固定回创建时命中的同一个上游 Key
- 如果未配置 `*_POOL`，系统会回退到原有的单 `ARK_API_KEY` / `ARK_INTL_API_KEY` 行为

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

## 数据库备份

仓库已提供 Linux 备份脚本：

- `scripts/backup_generation_prod.sh`

默认行为：

- 每次将 `generation_prod` 导出到 `/opt/dbbackup`
- 输出文件格式为 `.sql.gz`
- 本地仅保留最近 `7` 天备份
- 默认按低权限账号可用方式导出，不依赖 `PROCESS` / `EVENT` 额外权限

可直接执行：

```bash
chmod +x scripts/backup_generation_prod.sh
DB_HOST=127.0.0.1 \
DB_PORT=3306 \
DB_NAME=generation_prod \
DB_USER=root \
DB_PASSWORD=your-password \
scripts/backup_generation_prod.sh
```

如需每天自动备份，可加入 `crontab`：

```cron
0 3 * * * DB_HOST=127.0.0.1 DB_PORT=3306 DB_NAME=generation_prod DB_USER=root DB_PASSWORD=your-password /opt/ai-generator/scripts/backup_generation_prod.sh >> /var/log/generation_prod_backup.log 2>&1
```

说明：

- `BACKUP_DIR` 默认是 `/opt/dbbackup`
- `RETENTION_DAYS` 默认是 `7`
- 也可通过环境变量覆盖以上参数
- 脚本默认启用 `--no-tablespaces`，且不导出 `events`，适合普通业务库备份账号

## 保留脚本

仓库保留了少量仍有实际用途的辅助文件：

- `manage_users.py`：用户管理脚本
- `config/storyboard.md`
- `config/txt2csv.md`
- `docs/MIGRATE_TO_MYSQL.md`
- `docs/USER_RECHARGE_PAYMENT.md`
- `scripts/schema_mysql.sql`

其余旧单体、迁移报告、调试脚本和重复说明文档已清理。
