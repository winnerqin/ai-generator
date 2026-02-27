# 将数据库从 SQLite 切换为 MySQL 操作指南

当前项目使用 SQLite（`database.py` + `generation_records.db`）。若要改为使用 MySQL，需完成以下操作。

---

## 一、环境与依赖

### 1. 安装 MySQL 驱动

任选其一（推荐 PyMySQL，纯 Python、易部署）：

```bash
# 推荐
pip install PyMySQL

# 或
pip install mysql-connector-python
```

在 `requirements.txt` 中增加一行：`PyMySQL>=1.0.0`（或你使用的驱动及版本）。

### 2. 准备 MySQL 服务

- 安装并启动 MySQL 5.7+ / MariaDB 10.2+。
- 创建专用数据库与用户，例如：

```sql
CREATE DATABASE ai_generator CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'ai_app'@'%' IDENTIFIED BY '你的密码';
GRANT ALL ON ai_generator.* TO 'ai_app'@'%';
FLUSH PRIVILEGES;
```

---

## 二、配置

通过环境变量或配置文件指定 MySQL 连接信息，例如：

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `DB_TYPE` | 数据库类型 | `mysql`（为 mysql 时用 MySQL，否则用 SQLite） |
| `MYSQL_HOST` | 主机 | `127.0.0.1` 或 `localhost` |
| `MYSQL_PORT` | 端口 | `3306` |
| `MYSQL_USER` | 用户名 | `ai_app` |
| `MYSQL_PASSWORD` | 密码 | 你的密码 |
| `MYSQL_DATABASE` | 数据库名 | `ai_generator` |
| `MYSQL_CHARSET` | 字符集 | `utf8mb4`（推荐） |

保留原有 `DB_PATH` 或仅在使用 SQLite 时生效即可。

---

## 三、代码层面需要改动的要点

`database.py` 当前大量使用 SQLite 专用写法，切换 MySQL 时需统一处理。

### 1. 连接方式

- **当前**：`conn = sqlite3.connect(DB_PATH)`
- **MySQL（PyMySQL）**：  
  `conn = pymysql.connect(host=..., port=..., user=..., password=..., database=..., charset=...)`  
  建议根据 `DB_TYPE` 在单独模块中封装 `get_conn()`，`database.py` 只调 `get_conn()`。

### 2. 占位符

- **当前**：所有 SQL 使用 `?` 占位，例如 `WHERE id = ?`。
- **MySQL（PyMySQL）**：使用 `%s`，例如 `WHERE id = %s`。  
  要么在封装层把 `?` 统一替换为 `%s` 再执行，要么在 `database.py` 中全局把 `?` 改为 `%s`（并保证参数顺序、数量一致）。

### 3. 取行结果为字典

- **当前**：`conn.row_factory = sqlite3.Row`，然后 `row['col']` 或 `dict(row)`。
- **MySQL**：PyMySQL 默认返回 tuple，可用 `cursor = conn.cursor(pymysql.cursors.DictCursor)` 得到字典行，这样与当前 `dict(row)` 用法兼容。

### 4. 自增主键

- **当前**：`INTEGER PRIMARY KEY AUTOINCREMENT`。
- **MySQL**：`INT PRIMARY KEY AUTO_INCREMENT`。  
  建表 DDL 需单独写一份 MySQL 版本（见下文「MySQL 建表说明」）。

### 5. 表与列是否存在（初始化/迁移）

- **当前**：  
  - 表：`SELECT name FROM sqlite_master WHERE type='table' AND name='...'`  
  - 列：`PRAGMA table_info(table_name)`
- **MySQL**：  
  - 表：查 `INFORMATION_SCHEMA.TABLES` 或 `SHOW TABLES LIKE '...'`  
  - 列：`SHOW COLUMNS FROM table_name` 或 `INFORMATION_SCHEMA.COLUMNS`  
  建议在初始化/迁移逻辑里按 `DB_TYPE` 分支，或封装成 `table_exists(table_name)`、`column_exists(table, column)` 再在 `database.py` 里调用。

### 6. INSERT OR IGNORE

- **当前**：`INSERT OR IGNORE INTO user_projects (...) VALUES (?, ?, ?)`。
- **MySQL**：`INSERT IGNORE INTO user_projects (...) VALUES (%s, %s, %s)`。  
  仅此语法差异，占位符一并改为 `%s` 即可。

### 7. 唯一冲突异常

- **当前**：`except sqlite3.IntegrityError`。
- **MySQL**：使用驱动提供的异常，例如 `pymysql.IntegrityError` 或 `mysql.connector.errors.IntegrityError`。  
  建议在封装层统一捕获并暴露为同一异常名（如 `DBIntegrityError`），`database.py` 只捕该异常。

### 8. 索引

- **当前**：`CREATE INDEX IF NOT EXISTS idx_xxx ON table (...)`
- **MySQL**：  
  - 8.0+ 部分版本支持 `CREATE INDEX ... IF NOT EXISTS`（语法与 SQLite 不完全一致）。  
  - 更稳妥做法：先 `SHOW INDEX` 或查 `INFORMATION_SCHEMA.STATISTICS` 判断是否存在，再决定是否执行 `CREATE INDEX`，避免重复创建报错。

### 9. 时间默认值

- **当前**：`DEFAULT CURRENT_TIMESTAMP`。
- **MySQL**：同样支持；若使用 `DATETIME`，可用 `DEFAULT CURRENT_TIMESTAMP` 或 `ON UPDATE CURRENT_TIMESTAMP`。保持与现有业务一致即可。

### 10. 其它

- `cursor.lastrowid`：SQLite 和 MySQL 均支持，无需改。
- `COALESCE`、`LIMIT`/`OFFSET`、`ORDER BY`：两边语法一致，只改占位符即可。
- 所有 `cursor.execute(..., (a, b))` 的元组参数形式不变，仅占位符从 `?` 改为 `%s`。

---

## 四、MySQL 建表说明（与当前 SQLite 表结构对应）

需要为 MySQL 准备一套建表 DDL，把现有 SQLite 的：

- `INTEGER PRIMARY KEY AUTOINCREMENT` → `INT AUTO_INCREMENT PRIMARY KEY`（或 `BIGINT` 若需更大范围）
- `TEXT` → `VARCHAR(255)` 或 `TEXT`/`LONGTEXT`（按字段实际长度选）
- `TIMESTAMP` → `DATETIME` 或 `TIMESTAMP`（注意 MySQL 的 TIMESTAMP 范围与时区）

并保持表名、列名、唯一约束、外键（若使用）与现有逻辑一致。  
项目中表较多时，建议在 `docs/` 或 `scripts/` 下单独维护一份 `schema_mysql.sql`，在空库上执行一次完成建表；`init_database()` 中可改为：若为 MySQL 且表已存在则只做“加列、加索引”的增量更新，避免重复建表。

---

## 五、数据迁移（可选）

若希望保留现有 SQLite 数据：

1. **导出 SQLite 数据**  
   用 `sqlite3` 命令行或脚本按表导出为 CSV/JSON，或生成 INSERT 语句。
2. **导入 MySQL**  
   按表顺序导入（先主表后从表，避免外键报错）；若用 INSERT 语句，需把 SQLite 的 `?` 占位或已替换成的值改为 MySQL 兼容格式（如日期、布尔等）。
3. **自增主键**  
   若表之间有外键或业务依赖主键 ID，导出/导入时注意保持 ID 一致，或在 MySQL 建表时暂时关闭外键检查，导入后再开启。

若可以接受“重新开始”，则只需在 MySQL 中执行上述建表 DDL，无需迁移数据。

---

## 六、推荐实施顺序

1. 增加 `DB_TYPE` 与 MySQL 相关环境变量，在代码中读取。
2. 新增数据库抽象层（如 `db_adapter.py`）：  
   - `get_conn()`：根据 `DB_TYPE` 返回 SQLite 或 MySQL 连接。  
   - 执行前将 SQL 中 `?` 替换为 `%s`（仅当使用 MySQL 时）。  
   - 使用 DictCursor 或等价方式，使返回行与当前 `dict(row)` 兼容。  
   - 统一抛出/捕获唯一约束异常。
3. 修改 `database.py`：  
   - 所有 `sqlite3.connect(DB_PATH)` 改为 `get_conn()`。  
   - 所有 `conn.row_factory = sqlite3.Row` 改为由封装层保证返回字典行（或保留在 SQLite 分支中）。  
   - 表/列存在性检查改为调用抽象层的 `table_exists` / `column_exists`（或分支实现）。  
   - `init_database()` 中建表部分：SQLite 分支保留现有逻辑，MySQL 分支执行 `schema_mysql.sql` 或等价 DDL + 增量加列/加索引。  
   - `INSERT OR IGNORE` 改为 `INSERT IGNORE`（仅 MySQL 分支）。  
   - 唯一约束异常改为捕获抽象层提供的异常。
4. 编写并执行 MySQL 建表脚本，在测试库验证。
5. 若有迁移需求，按第五节做一次导出/导入并在测试环境验证。
6. 在开发/测试环境用 `DB_TYPE=mysql` 跑完整业务流程（登录、生成记录、项目、视频任务等），确认无报错后再部署生产。

---

## 七、回滚

- 保留原 `database.py` 和 `generation_records.db` 备份。
- 切换回 SQLite：将 `DB_TYPE` 设为非 `mysql`（或删除 MySQL 相关配置），恢复使用 `DB_PATH` 和 SQLite 驱动即可。

按上述步骤操作即可将当前可管理的 SQLite 数据库切换为 MySQL。

---

## 八、本仓库已提供的辅助文件（可选）

- **`db_adapter.py`**（项目根目录）  
  - 根据环境变量 `DB_TYPE=mysql` 选择 MySQL，否则使用 SQLite。  
  - 提供：`get_conn()`、`execute(cursor, sql, params)`（内部处理 `?` → `%s`）、`IntegrityError`、`table_exists`、`column_exists`。  
  - 使用方式：在 `database.py` 中改为 `from db_adapter import get_conn, execute, IntegrityError`，所有 `sqlite3.connect(DB_PATH)` 改为 `get_conn()`，所有 `cursor.execute(sql, params)` 改为 `execute(cursor, sql, params)`，`sqlite3.IntegrityError` 改为 `IntegrityError`。

- **`scripts/schema_mysql.sql`**  
  - 与当前 SQLite 表结构等价的 MySQL 建表脚本，在空库上执行即可创建全部表与索引。

若你希望改为“仅用 MySQL、不再保留 SQLite”，可在完成上述替换后删除 SQLite 相关分支，只保留 MySQL 实现。
