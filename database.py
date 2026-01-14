"""
数据库模型 - 存储图片生成记录和用户信息
"""
import sqlite3
import json
import hashlib
from datetime import datetime
from pathlib import Path

DB_PATH = 'generation_records.db'

def init_database():
    """初始化数据库"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 创建用户表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
    ''')
    
    # 检查generation_records表是否存在
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='generation_records'")
    table_exists = cursor.fetchone() is not None
    
    if table_exists:
        # 检查user_id列是否存在
        cursor.execute("PRAGMA table_info(generation_records)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'user_id' not in columns:
            print("检测到旧数据库，需要迁移...")
            # 创建新表
            cursor.execute('''
                CREATE TABLE generation_records_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    prompt TEXT NOT NULL,
                    negative_prompt TEXT,
                    aspect_ratio TEXT,
                    resolution TEXT,
                    width INTEGER,
                    height INTEGER,
                    num_images INTEGER,
                    seed INTEGER,
                    steps INTEGER,
                    sample_images TEXT,
                    image_path TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    batch_id TEXT,
                    status TEXT DEFAULT 'success',
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')
            
            # 复制数据（所有旧记录分配给用户ID=1）
            cursor.execute('''
                INSERT INTO generation_records_new 
                (id, user_id, created_at, prompt, negative_prompt, aspect_ratio, resolution, 
                 width, height, num_images, seed, steps, sample_images, image_path, filename, batch_id, status)
                SELECT id, 1, created_at, prompt, negative_prompt, aspect_ratio, resolution,
                       width, height, num_images, seed, steps, sample_images, image_path, filename, batch_id, status
                FROM generation_records
            ''')
            
            # 删除旧表，重命名新表
            cursor.execute('DROP TABLE generation_records')
            cursor.execute('ALTER TABLE generation_records_new RENAME TO generation_records')
            print("数据库迁移完成")
    else:
        # 创建新表
        cursor.execute('''
            CREATE TABLE generation_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                prompt TEXT NOT NULL,
                negative_prompt TEXT,
                aspect_ratio TEXT,
                resolution TEXT,
                width INTEGER,
                height INTEGER,
                num_images INTEGER,
                seed INTEGER,
                steps INTEGER,
                sample_images TEXT,
                image_path TEXT NOT NULL,
                filename TEXT NOT NULL,
                batch_id TEXT,
                status TEXT DEFAULT 'success',
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
    
    # 创建索引
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_username ON users(username)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_created ON generation_records(user_id, created_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_batch_id ON generation_records(batch_id)')
    
    # 创建人物库和场景库表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS person_library (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            filename TEXT NOT NULL,
            url TEXT NOT NULL,
            meta TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scene_library (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            filename TEXT NOT NULL,
            url TEXT NOT NULL,
            meta TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # 创建图片库和视频库表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS image_library (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            filename TEXT NOT NULL,
            url TEXT NOT NULL,
            meta TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS video_library (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            filename TEXT NOT NULL,
            url TEXT NOT NULL,
            meta TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # 创建视频任务表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS video_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            task_id TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'pending',
            prompt TEXT,
            generate_type TEXT,
            resolution TEXT,
            ratio TEXT,
            duration INTEGER,
            seed INTEGER,
            camera_fixed INTEGER DEFAULT 0,
            watermark INTEGER DEFAULT 0,
            generate_audio INTEGER DEFAULT 0,
            return_last_frame INTEGER DEFAULT 0,
            first_frame_url TEXT,
            last_frame_url TEXT,
            reference_image_urls TEXT,
            video_url TEXT,
            last_frame_image_url TEXT,
            token INTEGER,
            usage TEXT,
            content TEXT,
            error_message TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # 创建索引以提高查询性能
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_tasks_user_id ON video_tasks(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_tasks_task_id ON video_tasks(task_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_tasks_status ON video_tasks(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_tasks_created_at ON video_tasks(created_at)')
    
    conn.commit()
    conn.close()
    print(f"数据库初始化完成: {DB_PATH}")

def save_generation_record(data):
    """
    保存生成记录
    
    Args:
        data: dict with keys:
            - user_id (required)
            - prompt, negative_prompt, aspect_ratio, resolution
            - width, height, num_images, seed, steps
            - sample_images (list), image_path, filename
            - batch_id (optional)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    sample_images_json = json.dumps(data.get('sample_images', []))
    # 使用本地时间
    local_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # 防止重复保存相同的 image_path（避免前端/网络重试导致重复记录）
    existing = None
    try:
        cursor.execute('SELECT id FROM generation_records WHERE user_id = ? AND image_path = ? LIMIT 1', (
            data.get('user_id'), data.get('image_path')
        ))
        row = cursor.fetchone()
        if row:
            existing = row[0]
    except Exception:
        existing = None

    if existing:
        # 已存在相同记录，返回已有 ID 并不重复插入
        conn.close()
        return existing

    cursor.execute('''
        INSERT INTO generation_records 
        (user_id, created_at, prompt, negative_prompt, aspect_ratio, resolution, width, height, 
         num_images, seed, steps, sample_images, image_path, filename, batch_id, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('user_id'),
        local_time,
        data.get('prompt'),
        data.get('negative_prompt', ''),
        data.get('aspect_ratio'),
        data.get('resolution'),
        data.get('width'),
        data.get('height'),
        data.get('num_images', 1),
        data.get('seed', 0),
        data.get('steps', 28),
        sample_images_json,
        data.get('image_path'),
        data.get('filename'),
        data.get('batch_id'),
        data.get('status', 'success')
    ))
    
    record_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return record_id


def save_person_asset(user_id, filename, url, meta=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO person_library (user_id, created_at, filename, url, meta)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), filename, url, json.dumps(meta or {})))
    asset_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return asset_id


def save_scene_asset(user_id, filename, url, meta=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO scene_library (user_id, created_at, filename, url, meta)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), filename, url, json.dumps(meta or {})))
    asset_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return asset_id


def get_person_assets(user_id, limit=500):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM person_library WHERE user_id = ? ORDER BY created_at DESC LIMIT ?', (user_id, limit))
    rows = cursor.fetchall()
    assets = [dict(r) for r in rows]
    for a in assets:
        try:
            a['meta'] = json.loads(a.get('meta') or '{}')
        except Exception:
            a['meta'] = {}
    conn.close()
    return assets


def get_scene_assets(user_id, limit=500):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM scene_library WHERE user_id = ? ORDER BY created_at DESC LIMIT ?', (user_id, limit))
    rows = cursor.fetchall()
    assets = [dict(r) for r in rows]
    for a in assets:
        try:
            a['meta'] = json.loads(a.get('meta') or '{}')
        except Exception:
            a['meta'] = {}
    conn.close()
    return assets


def delete_person_asset(asset_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM person_library WHERE id = ?', (asset_id,))
    conn.commit()
    conn.close()


def delete_scene_asset(asset_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM scene_library WHERE id = ?', (asset_id,))
    conn.commit()
    conn.close()

def save_image_asset(user_id, filename, url, meta=None):
    """保存图片到图片库"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO image_library (user_id, created_at, filename, url, meta)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), filename, url, json.dumps(meta or {})))
    asset_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return asset_id

def save_video_asset(user_id, filename, url, meta=None):
    """保存视频到视频库"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO video_library (user_id, created_at, filename, url, meta)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), filename, url, json.dumps(meta or {})))
    asset_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return asset_id

def get_image_assets(user_id, limit=500):
    """获取图片库资源"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM image_library WHERE user_id = ? ORDER BY created_at DESC LIMIT ?', (user_id, limit))
    rows = cursor.fetchall()
    assets = [dict(r) for r in rows]
    for a in assets:
        try:
            a['meta'] = json.loads(a.get('meta') or '{}')
        except Exception:
            a['meta'] = {}
    conn.close()
    return assets

def get_video_assets(user_id, limit=500):
    """获取视频库资源"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM video_library WHERE user_id = ? ORDER BY created_at DESC LIMIT ?', (user_id, limit))
    rows = cursor.fetchall()
    assets = [dict(r) for r in rows]
    for a in assets:
        try:
            a['meta'] = json.loads(a.get('meta') or '{}')
        except Exception:
            a['meta'] = {}
    conn.close()
    return assets

def get_video_by_task_id(user_id, task_id):
    """根据任务ID获取视频库中的视频"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM video_library WHERE user_id = ?', (user_id,))
    rows = cursor.fetchall()
    for row in rows:
        asset = dict(row)
        try:
            meta = json.loads(asset.get('meta') or '{}')
            if meta.get('task_id') == task_id:
                asset['meta'] = meta
                conn.close()
                return asset
        except Exception:
            pass
    conn.close()
    return None

def save_video_task(data):
    """保存视频任务记录"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    local_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # 检查任务是否已存在
    cursor.execute('SELECT id FROM video_tasks WHERE task_id = ?', (data.get('task_id'),))
    existing = cursor.fetchone()
    
    if existing:
        # 更新现有记录
        cursor.execute('''
            UPDATE video_tasks SET
                updated_at = ?,
                status = ?,
                video_url = ?,
                last_frame_image_url = ?,
                token = ?,
                usage = ?,
                content = ?,
                error_message = ?
            WHERE task_id = ?
        ''', (
            local_time,
            data.get('status', 'pending'),
            data.get('video_url'),
            data.get('last_frame_image_url'),
            data.get('token'),
            json.dumps(data.get('usage', {})) if data.get('usage') else None,
            json.dumps(data.get('content', {})) if data.get('content') else None,
            data.get('error_message'),
            data.get('task_id')
        ))
        task_id = existing[0]
    else:
        # 插入新记录
        cursor.execute('''
            INSERT INTO video_tasks 
            (user_id, task_id, created_at, updated_at, status, prompt, generate_type, resolution, ratio,
             duration, seed, camera_fixed, watermark, generate_audio, return_last_frame,
             first_frame_url, last_frame_url, reference_image_urls, video_url, last_frame_image_url,
             token, usage, content, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('user_id'),
            data.get('task_id'),
            local_time,
            local_time,
            data.get('status', 'pending'),
            data.get('prompt'),
            data.get('generate_type'),
            data.get('resolution'),
            data.get('ratio'),
            data.get('duration'),
            data.get('seed'),
            1 if data.get('camera_fixed') else 0,
            1 if data.get('watermark') else 0,
            1 if data.get('generate_audio') else 0,
            1 if data.get('return_last_frame') else 0,
            data.get('first_frame_url'),
            data.get('last_frame_url'),
            json.dumps(data.get('reference_image_urls', [])) if data.get('reference_image_urls') else None,
            data.get('video_url'),
            data.get('last_frame_image_url'),
            data.get('token'),
            json.dumps(data.get('usage', {})) if data.get('usage') else None,
            json.dumps(data.get('content', {})) if data.get('content') else None,
            data.get('error_message')
        ))
        task_id = cursor.lastrowid
    
    conn.commit()
    conn.close()
    return task_id

def get_video_tasks(user_id, status=None, start_date=None, end_date=None, limit=100, offset=0):
    """获取视频任务列表"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = 'SELECT * FROM video_tasks WHERE user_id = ?'
    params = [user_id]
    
    if status:
        query += ' AND status = ?'
        params.append(status)
    
    if start_date:
        query += ' AND created_at >= ?'
        params.append(start_date)
    
    if end_date:
        query += ' AND created_at <= ?'
        params.append(end_date)
    
    query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    tasks = []
    for row in rows:
        task = dict(row)
        # 解析JSON字段
        try:
            if task.get('reference_image_urls'):
                task['reference_image_urls'] = json.loads(task['reference_image_urls'])
            if task.get('usage'):
                task['usage'] = json.loads(task['usage'])
            if task.get('content'):
                task['content'] = json.loads(task['content'])
        except Exception:
            pass
        tasks.append(task)
    
    conn.close()
    return tasks

def get_video_task_by_id(task_id):
    """根据任务ID获取视频任务"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM video_tasks WHERE task_id = ?', (task_id,))
    row = cursor.fetchone()
    if row:
        task = dict(row)
        # 解析JSON字段
        try:
            if task.get('reference_image_urls'):
                task['reference_image_urls'] = json.loads(task['reference_image_urls'])
            if task.get('usage'):
                task['usage'] = json.loads(task['usage'])
            if task.get('content'):
                task['content'] = json.loads(task['content'])
        except Exception:
            pass
        conn.close()
        return task
    conn.close()
    return None

def delete_image_asset(asset_id):
    """删除图片库资源"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM image_library WHERE id = ?', (asset_id,))
    conn.commit()
    conn.close()

def delete_video_asset(asset_id):
    """删除视频库资源"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM video_library WHERE id = ?', (asset_id,))
    conn.commit()
    conn.close()

def get_all_records(user_id, limit=100, offset=0):
    """获取指定用户的所有记录"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM generation_records 
        WHERE user_id = ?
        ORDER BY created_at DESC 
        LIMIT ? OFFSET ?
    ''', (user_id, limit, offset))
    
    rows = cursor.fetchall()
    records = []
    
    for row in rows:
        record = dict(row)
        # 解析 JSON 字段
        if record['sample_images']:
            record['sample_images'] = json.loads(record['sample_images'])
        records.append(record)
    
    conn.close()
    return records

def get_records_by_batch(batch_id):
    """获取指定批次的记录"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM generation_records 
        WHERE batch_id = ?
        ORDER BY created_at DESC
    ''', (batch_id,))
    
    rows = cursor.fetchall()
    records = []
    
    for row in rows:
        record = dict(row)
        if record['sample_images']:
            record['sample_images'] = json.loads(record['sample_images'])
        records.append(record)
    
    conn.close()
    return records

def get_record_by_id(record_id):
    """获取单条记录"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM generation_records WHERE id = ?', (record_id,))
    row = cursor.fetchone()
    
    if row:
        record = dict(row)
        if record['sample_images']:
            record['sample_images'] = json.loads(record['sample_images'])
        conn.close()
        return record
    
    conn.close()
    return None

def delete_record(record_id):
    """删除记录"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM generation_records WHERE id = ?', (record_id,))
    conn.commit()
    conn.close()

def get_total_count(user_id):
    """获取指定用户的总记录数"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM generation_records WHERE user_id = ?', (user_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

# ==================== 用户管理函数 ====================

def hash_password(password):
    """生成密码哈希"""
    return hashlib.sha256(password.encode()).hexdigest()

def create_user(username, password):
    """创建新用户"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        password_hash = hash_password(password)
        cursor.execute('''
            INSERT INTO users (username, password_hash, created_at)
            VALUES (?, ?, ?)
        ''', (username, password_hash, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return user_id
    except sqlite3.IntegrityError:
        conn.close()
        return None  # 用户名已存在

def verify_user(username, password):
    """验证用户登录"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    password_hash = hash_password(password)
    cursor.execute('''
        SELECT * FROM users 
        WHERE username = ? AND password_hash = ?
    ''', (username, password_hash))
    
    row = cursor.fetchone()
    
    if row:
        user = dict(row)
        # 更新最后登录时间
        cursor.execute('''
            UPDATE users SET last_login = ? WHERE id = ?
        ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user['id']))
        conn.commit()
        conn.close()
        return user
    
    conn.close()
    return None

def get_user_by_id(user_id):
    """根据ID获取用户信息"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    row = cursor.fetchone()
    
    if row:
        user = dict(row)
        conn.close()
        return user
    
    conn.close()
    return None

def get_all_users():
    """获取所有用户列表"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, username, created_at, last_login FROM users ORDER BY id')
    rows = cursor.fetchall()
    
    users = [dict(row) for row in rows]
    conn.close()
    return users

def get_stats_overview():
    """获取统计概览"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 总用户数
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    # 总图片数
    cursor.execute('SELECT COUNT(*) FROM generation_records')
    total_images = cursor.fetchone()[0]
    
    # 今日图片数
    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute('''
        SELECT COUNT(*) FROM generation_records 
        WHERE DATE(created_at) = ?
    ''', (today,))
    today_images = cursor.fetchone()[0]
    
    # 本周图片数
    cursor.execute('''
        SELECT COUNT(*) FROM generation_records 
        WHERE DATE(created_at) >= DATE('now', '-7 days')
    ''')
    week_images = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        'total_users': total_users,
        'total_images': total_images,
        'today_images': today_images,
        'week_images': week_images
    }

def get_user_stats(start_date=None, end_date=None):
    """获取每个用户的统计信息"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 获取所有用户
    users = get_all_users()
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    stats = []
    for user in users:
        user_id = user['id']
        
        # 总生成数
        if start_date and end_date:
            cursor.execute('''
                SELECT COUNT(*) FROM generation_records 
                WHERE user_id = ? AND DATE(created_at) BETWEEN ? AND ?
            ''', (user_id, start_date, end_date))
        else:
            cursor.execute('SELECT COUNT(*) FROM generation_records WHERE user_id = ?', (user_id,))
        total_count = cursor.fetchone()[0]
        
        # 今日生成数
        cursor.execute('''
            SELECT COUNT(*) FROM generation_records 
            WHERE user_id = ? AND DATE(created_at) = ?
        ''', (user_id, today))
        today_count = cursor.fetchone()[0]
        
        # 本周生成数
        cursor.execute('''
            SELECT COUNT(*) FROM generation_records 
            WHERE user_id = ? AND DATE(created_at) >= DATE('now', '-7 days')
        ''', (user_id,))
        week_count = cursor.fetchone()[0]
        
        # 最后生成时间
        cursor.execute('''
            SELECT created_at FROM generation_records 
            WHERE user_id = ? 
            ORDER BY created_at DESC LIMIT 1
        ''', (user_id,))
        last_row = cursor.fetchone()
        last_generated = last_row[0] if last_row else None
        
        stats.append({
            'user_id': user_id,
            'username': user['username'],
            'total_count': total_count,
            'today_count': today_count,
            'week_count': week_count,
            'last_generated': last_generated
        })
    
    conn.close()
    return stats

def get_daily_stats(days=7):
    """获取每日生成统计"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            DATE(created_at) as date,
            COUNT(*) as count,
            COUNT(DISTINCT user_id) as user_count
        FROM generation_records
        WHERE DATE(created_at) >= DATE('now', '-' || ? || ' days')
        GROUP BY DATE(created_at)
        ORDER BY date DESC
    ''', (days,))
    
    rows = cursor.fetchall()
    
    stats = [{
        'date': row[0],
        'count': row[1],
        'user_count': row[2]
    } for row in rows]
    
    conn.close()
    return stats

if __name__ == '__main__':
    # 测试数据库
    init_database()
    print("✅ 数据库表创建成功")
    
    # 创建测试用户
    test_user = create_user('admin', 'admin123')
    if test_user:
        print(f"✅ 创建测试用户: admin / admin123")
    else:
        print("⚠️ 测试用户已存在")
