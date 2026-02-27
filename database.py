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

    def ensure_column(table, column, definition):
        cursor.execute(f"PRAGMA table_info({table})")
        cols = [col[1] for col in cursor.fetchall()]
        if column not in cols:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    
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
                    project_id INTEGER,
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
                (id, user_id, project_id, created_at, prompt, negative_prompt, aspect_ratio, resolution, 
                 width, height, num_images, seed, steps, sample_images, image_path, filename, batch_id, status)
                SELECT id, 1, NULL, created_at, prompt, negative_prompt, aspect_ratio, resolution,
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
                project_id INTEGER,
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
    
    # 创建项目与授权表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            owner_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_projects (
            user_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, project_id)
        )
    ''')

    # 剧本提示词模板
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS script_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            project_id INTEGER,
            name TEXT NOT NULL,
            prompt TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, project_id, name)
        )
    ''')

    # 剧本保存记录
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS script_saves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            project_id INTEGER,
            title TEXT NOT NULL,
            novel_text TEXT,
            prompt TEXT,
            min_seconds INTEGER,
            max_seconds INTEGER,
            script_text TEXT,
            episodes_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 剧本分集记录
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS script_episode_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            script_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            project_id INTEGER,
            episode_index INTEGER,
            title TEXT,
            duration_seconds INTEGER,
            summary TEXT,
            content_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 分镜保存记录
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS storyboard_saves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            project_id INTEGER,
            title TEXT NOT NULL,
            script_text TEXT,
            prompt TEXT,
            storyboard_json TEXT,
            storyboard_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 分镜分集记录（按剧本分集保存）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS storyboard_episode_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            script_episode_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            project_id INTEGER,
            prompt TEXT,
            storyboard_json TEXT,
            storyboard_text TEXT,
            images_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 迁移分镜保存记录字段
    ensure_column('storyboard_saves', 'series_id', 'INTEGER')
    ensure_column('storyboard_saves', 'version', 'INTEGER DEFAULT 1')
    cursor.execute('UPDATE storyboard_saves SET version = 1 WHERE version IS NULL')
    cursor.execute('UPDATE storyboard_saves SET series_id = id WHERE series_id IS NULL')

    # 生成任务记录（用于进度与恢复）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS generation_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            project_id INTEGER,
            task_type TEXT NOT NULL,
            status TEXT NOT NULL,
            progress INTEGER DEFAULT 0,
            payload_json TEXT,
            result_json TEXT,
            error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 创建人物库和场景库表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS person_library (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            project_id INTEGER,
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
            project_id INTEGER,
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
            project_id INTEGER,
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
            project_id INTEGER,
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
            project_id INTEGER,
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
    
    # ===== 项目字段迁移与默认项目 =====
    def ensure_column(table_name, column_name, column_def):
        cursor.execute(f"PRAGMA table_info({table_name})")
        cols = [col[1] for col in cursor.fetchall()]
        if column_name not in cols:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")
    
    for table_name in [
        'generation_records',
        'person_library',
        'scene_library',
        'image_library',
        'video_library',
        'video_tasks'
    ]:
        ensure_column(table_name, 'project_id', 'INTEGER')
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_records_user_project_created ON generation_records(user_id, project_id, created_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_person_user_project_created ON person_library(user_id, project_id, created_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_scene_user_project_created ON scene_library(user_id, project_id, created_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_image_user_project_created ON image_library(user_id, project_id, created_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_user_project_created ON video_library(user_id, project_id, created_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_tasks_user_project_created ON video_tasks(user_id, project_id, created_at DESC)')
    
    # 为现有用户创建默认项目并回填 project_id
    cursor.execute('SELECT id FROM users')
    user_ids = [row[0] for row in cursor.fetchall()]
    for user_id in user_ids:
        cursor.execute('SELECT project_id FROM user_projects WHERE user_id = ? LIMIT 1', (user_id,))
        row = cursor.fetchone()
        project_id = row[0] if row else None
        if not project_id:
            cursor.execute('SELECT id FROM projects WHERE owner_id = ? ORDER BY id LIMIT 1', (user_id,))
            row = cursor.fetchone()
            project_id = row[0] if row else None
        if not project_id:
            cursor.execute('''
                INSERT INTO projects (name, owner_id, created_at)
                VALUES (?, ?, ?)
            ''', ('默认项目', user_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            project_id = cursor.lastrowid
        cursor.execute('''
            INSERT OR IGNORE INTO user_projects (user_id, project_id, created_at)
            VALUES (?, ?, ?)
        ''', (user_id, project_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        for table_name in [
            'generation_records',
            'person_library',
            'scene_library',
            'image_library',
            'video_library',
            'video_tasks'
        ]:
            cursor.execute(
                f"UPDATE {table_name} SET project_id = ? WHERE user_id = ? AND (project_id IS NULL OR project_id = 0)",
                (project_id, user_id)
            )
    
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
        (user_id, project_id, created_at, prompt, negative_prompt, aspect_ratio, resolution, width, height, 
         num_images, seed, steps, sample_images, image_path, filename, batch_id, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('user_id'),
        data.get('project_id'),
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


def save_person_asset(user_id, filename, url, meta=None, project_id=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO person_library (user_id, project_id, created_at, filename, url, meta)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, project_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), filename, url, json.dumps(meta or {})))
    asset_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return asset_id


def save_scene_asset(user_id, filename, url, meta=None, project_id=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO scene_library (user_id, project_id, created_at, filename, url, meta)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, project_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), filename, url, json.dumps(meta or {})))
    asset_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return asset_id


def get_person_assets(user_id, project_id=None, limit=500):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute('SELECT * FROM person_library WHERE user_id = ? ORDER BY created_at DESC LIMIT ?', (user_id, limit))
    else:
        cursor.execute('SELECT * FROM person_library WHERE user_id = ? AND project_id = ? ORDER BY created_at DESC LIMIT ?', (user_id, project_id, limit))
    rows = cursor.fetchall()
    assets = [dict(r) for r in rows]
    for a in assets:
        try:
            a['meta'] = json.loads(a.get('meta') or '{}')
        except Exception:
            a['meta'] = {}
    conn.close()
    return assets


def get_scene_assets(user_id, project_id=None, limit=500):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute('SELECT * FROM scene_library WHERE user_id = ? ORDER BY created_at DESC LIMIT ?', (user_id, limit))
    else:
        cursor.execute('SELECT * FROM scene_library WHERE user_id = ? AND project_id = ? ORDER BY created_at DESC LIMIT ?', (user_id, project_id, limit))
    rows = cursor.fetchall()
    assets = [dict(r) for r in rows]
    for a in assets:
        try:
            a['meta'] = json.loads(a.get('meta') or '{}')
        except Exception:
            a['meta'] = {}
    conn.close()
    return assets


def delete_person_asset(asset_id, user_id=None, project_id=None):
    """删除人物库资源。传入 user_id、project_id 时仅当资源属于该用户且属于该项目时删除（项目隔离）。"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if user_id is not None and project_id is not None:
        cursor.execute(
            'DELETE FROM person_library WHERE id = ? AND user_id = ? AND (project_id = ? OR (project_id IS NULL AND ? IS NULL))',
            (asset_id, user_id, project_id, project_id)
        )
    elif user_id is not None:
        cursor.execute('DELETE FROM person_library WHERE id = ? AND user_id = ?', (asset_id, user_id))
    else:
        cursor.execute('DELETE FROM person_library WHERE id = ?', (asset_id,))
    conn.commit()
    conn.close()


def delete_scene_asset(asset_id, user_id=None, project_id=None):
    """删除场景库资源。传入 user_id、project_id 时仅当资源属于该用户且属于该项目时删除（项目隔离）。"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if user_id is not None and project_id is not None:
        cursor.execute(
            'DELETE FROM scene_library WHERE id = ? AND user_id = ? AND (project_id = ? OR (project_id IS NULL AND ? IS NULL))',
            (asset_id, user_id, project_id, project_id)
        )
    elif user_id is not None:
        cursor.execute('DELETE FROM scene_library WHERE id = ? AND user_id = ?', (asset_id, user_id))
    else:
        cursor.execute('DELETE FROM scene_library WHERE id = ?', (asset_id,))
    conn.commit()
    conn.close()

def save_image_asset(user_id, filename, url, meta=None, project_id=None):
    """保存图片到图片库"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO image_library (user_id, project_id, created_at, filename, url, meta)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, project_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), filename, url, json.dumps(meta or {})))
    asset_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return asset_id

def save_video_asset(user_id, filename, url, meta=None, project_id=None):
    """保存视频到视频库"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO video_library (user_id, project_id, created_at, filename, url, meta)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, project_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), filename, url, json.dumps(meta or {})))
    asset_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return asset_id

def get_image_assets(user_id, project_id=None, limit=500):
    """获取图片库资源"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute('SELECT * FROM image_library WHERE user_id = ? ORDER BY created_at DESC LIMIT ?', (user_id, limit))
    else:
        cursor.execute('SELECT * FROM image_library WHERE user_id = ? AND project_id = ? ORDER BY created_at DESC LIMIT ?', (user_id, project_id, limit))
    rows = cursor.fetchall()
    assets = [dict(r) for r in rows]
    for a in assets:
        try:
            a['meta'] = json.loads(a.get('meta') or '{}')
        except Exception:
            a['meta'] = {}
    conn.close()
    return assets

def get_video_assets(user_id, project_id=None, limit=500):
    """获取视频库资源"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute('SELECT * FROM video_library WHERE user_id = ? ORDER BY created_at DESC LIMIT ?', (user_id, limit))
    else:
        cursor.execute('SELECT * FROM video_library WHERE user_id = ? AND project_id = ? ORDER BY created_at DESC LIMIT ?', (user_id, project_id, limit))
    rows = cursor.fetchall()
    assets = [dict(r) for r in rows]
    for a in assets:
        try:
            a['meta'] = json.loads(a.get('meta') or '{}')
        except Exception:
            a['meta'] = {}
    conn.close()
    return assets

def get_video_by_task_id(user_id, task_id, project_id=None):
    """根据任务ID获取视频库中的视频"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute('SELECT * FROM video_library WHERE user_id = ?', (user_id,))
    else:
        cursor.execute('SELECT * FROM video_library WHERE user_id = ? AND project_id = ?', (user_id, project_id))
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
                project_id = COALESCE(?, project_id),
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
            data.get('project_id'),
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
            (user_id, task_id, project_id, created_at, updated_at, status, prompt, generate_type, resolution, ratio,
             duration, seed, camera_fixed, watermark, generate_audio, return_last_frame,
             first_frame_url, last_frame_url, reference_image_urls, video_url, last_frame_image_url,
             token, usage, content, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('user_id'),
            data.get('task_id'),
            data.get('project_id'),
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


def update_video_task_media(task_id, video_url=None, last_frame_image_url=None, first_frame_url=None, last_frame_url=None):
    """仅更新视频任务的媒体链接字段"""
    if not task_id:
        return
    updates = []
    params = []
    if video_url is not None:
        updates.append("video_url = ?")
        params.append(video_url)
    if last_frame_image_url is not None:
        updates.append("last_frame_image_url = ?")
        params.append(last_frame_image_url)
    if first_frame_url is not None:
        updates.append("first_frame_url = ?")
        params.append(first_frame_url)
    if last_frame_url is not None:
        updates.append("last_frame_url = ?")
        params.append(last_frame_url)
    if not updates:
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    updates.append("updated_at = ?")
    params.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    params.append(task_id)
    cursor.execute(
        f"UPDATE video_tasks SET {', '.join(updates)} WHERE task_id = ?",
        params
    )
    conn.commit()
    conn.close()

def get_video_tasks(user_id, project_id=None, status=None, start_date=None, end_date=None, limit=100, offset=0):
    """获取视频任务列表"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = 'SELECT * FROM video_tasks WHERE user_id = ?'
    params = [user_id]
    
    if project_id is not None:
        query += ' AND project_id = ?'
        params.append(project_id)
    
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

def delete_image_asset(asset_id, user_id=None, project_id=None):
    """删除图片库资源。传入 user_id、project_id 时仅当资源属于该用户且属于该项目时删除（项目隔离）。"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if user_id is not None and project_id is not None:
        cursor.execute(
            'DELETE FROM image_library WHERE id = ? AND user_id = ? AND (project_id = ? OR (project_id IS NULL AND ? IS NULL))',
            (asset_id, user_id, project_id, project_id)
        )
    elif user_id is not None:
        cursor.execute('DELETE FROM image_library WHERE id = ? AND user_id = ?', (asset_id, user_id))
    else:
        cursor.execute('DELETE FROM image_library WHERE id = ?', (asset_id,))
    conn.commit()
    conn.close()

def delete_video_asset(asset_id, user_id=None, project_id=None):
    """删除视频库资源。传入 user_id、project_id 时仅当资源属于该用户且属于该项目时删除（项目隔离）。"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if user_id is not None and project_id is not None:
        cursor.execute(
            'DELETE FROM video_library WHERE id = ? AND user_id = ? AND (project_id = ? OR (project_id IS NULL AND ? IS NULL))',
            (asset_id, user_id, project_id, project_id)
        )
    elif user_id is not None:
        cursor.execute('DELETE FROM video_library WHERE id = ? AND user_id = ?', (asset_id, user_id))
    else:
        cursor.execute('DELETE FROM video_library WHERE id = ?', (asset_id,))
    conn.commit()
    conn.close()

def get_all_records(user_id, project_id=None, limit=100, offset=0):
    """获取指定用户的所有记录"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute('''
            SELECT * FROM generation_records 
            WHERE user_id = ?
            ORDER BY created_at DESC 
            LIMIT ? OFFSET ?
        ''', (user_id, limit, offset))
    else:
        cursor.execute('''
            SELECT * FROM generation_records 
            WHERE user_id = ? AND project_id = ?
            ORDER BY created_at DESC 
            LIMIT ? OFFSET ?
        ''', (user_id, project_id, limit, offset))
    
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

def get_records_by_batch(batch_id, project_id=None):
    """获取指定批次的记录"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute('''
            SELECT * FROM generation_records 
            WHERE batch_id = ?
            ORDER BY created_at DESC
        ''', (batch_id,))
    else:
        cursor.execute('''
            SELECT * FROM generation_records 
            WHERE batch_id = ? AND project_id = ?
            ORDER BY created_at DESC
        ''', (batch_id, project_id))
    
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

def delete_record(record_id, user_id=None, project_id=None):
    """删除生成记录。传入 user_id、project_id 时仅当记录属于该用户且属于该项目时删除（项目隔离）。"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if user_id is not None and project_id is not None:
        cursor.execute(
            'DELETE FROM generation_records WHERE id = ? AND user_id = ? AND (project_id = ? OR (project_id IS NULL AND ? IS NULL))',
            (record_id, user_id, project_id, project_id)
        )
    elif user_id is not None:
        cursor.execute('DELETE FROM generation_records WHERE id = ? AND user_id = ?', (record_id, user_id))
    else:
        cursor.execute('DELETE FROM generation_records WHERE id = ?', (record_id,))
    conn.commit()
    conn.close()

def get_total_count(user_id, project_id=None):
    """获取指定用户的总记录数"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute('SELECT COUNT(*) FROM generation_records WHERE user_id = ?', (user_id,))
    else:
        cursor.execute('SELECT COUNT(*) FROM generation_records WHERE user_id = ? AND project_id = ?', (user_id, project_id))
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


def delete_user(user_id):
    """删除用户"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM user_projects WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()


def update_user_password(user_id, new_password):
    """更新用户密码"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    password_hash = hash_password(new_password)
    cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?', (password_hash, user_id))
    conn.commit()
    conn.close()


def create_project(name, owner_id=None):
    """创建项目"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO projects (name, owner_id, created_at)
        VALUES (?, ?, ?)
    ''', (name, owner_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    project_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return project_id


def get_all_projects():
    """获取所有项目"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM projects ORDER BY id DESC')
    rows = cursor.fetchall()
    projects = [dict(r) for r in rows]
    conn.close()
    return projects


def get_user_projects(user_id):
    """获取用户可用项目"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.* FROM projects p
        JOIN user_projects up ON up.project_id = p.id
        WHERE up.user_id = ?
        ORDER BY p.id DESC
    ''', (user_id,))
    rows = cursor.fetchall()
    projects = [dict(r) for r in rows]
    conn.close()
    return projects


def assign_user_to_project(user_id, project_id):
    """授权用户到项目"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO user_projects (user_id, project_id, created_at)
        VALUES (?, ?, ?)
    ''', (user_id, project_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()


def revoke_user_from_project(user_id, project_id):
    """取消用户项目授权"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM user_projects WHERE user_id = ? AND project_id = ?', (user_id, project_id))
    conn.commit()
    conn.close()


def get_project_by_id(project_id):
    """获取项目"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM projects WHERE id = ?', (project_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_project_users(project_id):
    """获取项目内用户"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.id, u.username, u.created_at, u.last_login
        FROM users u
        JOIN user_projects up ON up.user_id = u.id
        WHERE up.project_id = ?
        ORDER BY u.id
    ''', (project_id,))
    rows = cursor.fetchall()
    users = [dict(r) for r in rows]
    conn.close()
    return users


def get_script_templates(user_id, project_id=None):
    """获取剧本提示词模板"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute('SELECT * FROM script_templates WHERE user_id = ? ORDER BY id DESC', (user_id,))
    else:
        cursor.execute('SELECT * FROM script_templates WHERE user_id = ? AND project_id = ? ORDER BY id DESC', (user_id, project_id))
    rows = cursor.fetchall()
    templates = [dict(r) for r in rows]
    conn.close()
    return templates


def create_script_template(user_id, project_id, name, prompt):
    """创建剧本提示词模板"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO script_templates (user_id, project_id, name, prompt, created_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, project_id, name, prompt, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    template_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return template_id


def delete_script_template(user_id, template_id, project_id=None):
    """删除剧本提示词模板。传入 project_id 时仅删除该项目下的模板（项目隔离）。"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if project_id is not None:
        cursor.execute(
            'DELETE FROM script_templates WHERE id = ? AND user_id = ? AND (project_id = ? OR (project_id IS NULL AND ? IS NULL))',
            (template_id, user_id, project_id, project_id)
        )
    else:
        cursor.execute('DELETE FROM script_templates WHERE id = ? AND user_id = ?', (template_id, user_id))
    conn.commit()
    conn.close()


def create_generation_task(user_id, project_id, task_type, payload):
    """创建生成任务"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO generation_tasks (
            user_id, project_id, task_type, status, progress, payload_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        user_id,
        project_id,
        task_type,
        'running',
        0,
        json.dumps(payload or {}, ensure_ascii=False),
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ))
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return task_id


def update_generation_task(task_id, status=None, progress=None, result=None, error=None):
    """更新生成任务"""
    fields = []
    values = []
    if status is not None:
        fields.append('status = ?')
        values.append(status)
    if progress is not None:
        fields.append('progress = ?')
        values.append(progress)
    if result is not None:
        fields.append('result_json = ?')
        values.append(json.dumps(result, ensure_ascii=False))
    if error is not None:
        fields.append('error = ?')
        values.append(error)
    if not fields:
        return
    fields.append('updated_at = ?')
    values.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    values.append(task_id)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(f'''
        UPDATE generation_tasks
        SET {", ".join(fields)}
        WHERE id = ?
    ''', tuple(values))
    conn.commit()
    conn.close()


def get_generation_task(user_id, project_id, task_id):
    """获取生成任务"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute('SELECT * FROM generation_tasks WHERE id = ? AND user_id = ?', (task_id, user_id))
    else:
        cursor.execute('SELECT * FROM generation_tasks WHERE id = ? AND user_id = ? AND project_id = ?', (task_id, user_id, project_id))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def save_script_record(user_id, project_id, title, novel_text, prompt, min_seconds, max_seconds, script_text, episodes, record_id=None):
    """保存剧本记录"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    episodes_json = json.dumps(episodes or [], ensure_ascii=False)
    if record_id:
        cursor.execute('''
            UPDATE script_saves
            SET title = ?, novel_text = ?, prompt = ?, min_seconds = ?, max_seconds = ?, script_text = ?, episodes_json = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
        ''', (
            title, novel_text, prompt, min_seconds, max_seconds, script_text, episodes_json, now, record_id, user_id
        ))
        conn.commit()
        conn.close()
        return record_id
    cursor.execute('''
        INSERT INTO script_saves (
            user_id, project_id, title, novel_text, prompt, min_seconds, max_seconds, script_text, episodes_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        user_id, project_id, title, novel_text, prompt, min_seconds, max_seconds, script_text, episodes_json, now, now
    ))
    record_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return record_id


def list_script_records(user_id, project_id=None):
    """获取剧本保存列表"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute('SELECT id, title, created_at, updated_at FROM script_saves WHERE user_id = ? ORDER BY updated_at DESC', (user_id,))
    else:
        cursor.execute('''
            SELECT id, title, created_at, updated_at
            FROM script_saves
            WHERE user_id = ? AND project_id = ?
            ORDER BY updated_at DESC
        ''', (user_id, project_id))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_script_record(user_id, project_id, record_id):
    """获取剧本记录"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute('SELECT * FROM script_saves WHERE id = ? AND user_id = ?', (record_id, user_id))
    else:
        cursor.execute('SELECT * FROM script_saves WHERE id = ? AND user_id = ? AND project_id = ?', (record_id, user_id, project_id))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def save_script_episodes(script_id, user_id, project_id, episodes):
    """保存剧本分集记录"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for ep in episodes:
        cursor.execute('''
            INSERT INTO script_episode_records (
                script_id, user_id, project_id, episode_index, title, duration_seconds, summary, content_url, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            script_id,
            user_id,
            project_id,
            ep.get('episode_index'),
            ep.get('title'),
            ep.get('duration_seconds'),
            ep.get('summary'),
            ep.get('content_url'),
            now,
            now
        ))
    conn.commit()
    conn.close()


def list_script_episodes(script_id, user_id, project_id=None):
    """获取剧本分集列表"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute('''
            SELECT id, script_id, episode_index, title, duration_seconds, summary, content_url, created_at, updated_at
            FROM script_episode_records
            WHERE script_id = ? AND user_id = ?
            ORDER BY episode_index ASC, id ASC
        ''', (script_id, user_id))
    else:
        cursor.execute('''
            SELECT id, script_id, episode_index, title, duration_seconds, summary, content_url, created_at, updated_at
            FROM script_episode_records
            WHERE script_id = ? AND user_id = ? AND project_id = ?
            ORDER BY episode_index ASC, id ASC
        ''', (script_id, user_id, project_id))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_script_episode(episode_id, user_id, project_id=None):
    """获取单集记录"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute('SELECT * FROM script_episode_records WHERE id = ? AND user_id = ?', (episode_id, user_id))
    else:
        cursor.execute('''
            SELECT * FROM script_episode_records
            WHERE id = ? AND user_id = ? AND project_id = ?
        ''', (episode_id, user_id, project_id))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_max_script_episode_index(script_id, user_id, project_id=None):
    """获取剧本当前最大集数"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute('SELECT MAX(episode_index) FROM script_episode_records WHERE script_id = ? AND user_id = ?', (script_id, user_id))
    else:
        cursor.execute('''
            SELECT MAX(episode_index) FROM script_episode_records
            WHERE script_id = ? AND user_id = ? AND project_id = ?
        ''', (script_id, user_id, project_id))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row and row[0] is not None else 0


def list_all_script_episodes(user_id, project_id=None):
    """获取所有剧本分集列表"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute('''
            SELECT id, script_id, episode_index, title, duration_seconds, summary, content_url, created_at, updated_at
            FROM script_episode_records
            WHERE user_id = ?
            ORDER BY id ASC
        ''', (user_id,))
    else:
        cursor.execute('''
            SELECT id, script_id, episode_index, title, duration_seconds, summary, content_url, created_at, updated_at
            FROM script_episode_records
            WHERE user_id = ? AND project_id = ?
            ORDER BY id ASC
        ''', (user_id, project_id))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_script_episode(episode_id, user_id, content_url=None, summary=None, title=None, episode_index=None, duration_seconds=None):
    """更新剧本分集内容"""
    fields = []
    values = []
    if content_url is not None:
        fields.append('content_url = ?')
        values.append(content_url)
    if summary is not None:
        fields.append('summary = ?')
        values.append(summary)
    if title is not None:
        fields.append('title = ?')
        values.append(title)
    if episode_index is not None:
        fields.append('episode_index = ?')
        values.append(episode_index)
    if duration_seconds is not None:
        fields.append('duration_seconds = ?')
        values.append(duration_seconds)
    if not fields:
        return
    fields.append('updated_at = ?')
    values.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    values.append(episode_id)
    values.append(user_id)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(f'''
        UPDATE script_episode_records
        SET {", ".join(fields)}
        WHERE id = ? AND user_id = ?
    ''', tuple(values))
    conn.commit()
    conn.close()


def delete_script_episode(episode_id, user_id):
    """删除剧本分集"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM script_episode_records WHERE id = ? AND user_id = ?', (episode_id, user_id))
    conn.commit()
    conn.close()


def save_storyboard_record(user_id, project_id, title, script_text, prompt, storyboard_json, storyboard_text, record_id=None, series_id=None, create_version=False):
    """保存分镜记录"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    storyboard_json_text = json.dumps(storyboard_json or {}, ensure_ascii=False)
    if record_id and not create_version:
        cursor.execute('''
            UPDATE storyboard_saves
            SET title = ?, script_text = ?, prompt = ?, storyboard_json = ?, storyboard_text = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
        ''', (
            title, script_text, prompt, storyboard_json_text, storyboard_text, now, record_id, user_id
        ))
        conn.commit()
        conn.close()
        return record_id
    version = 1
    if series_id:
        cursor.execute('SELECT MAX(version) FROM storyboard_saves WHERE series_id = ? AND user_id = ?', (series_id, user_id))
        row = cursor.fetchone()
        max_ver = row[0] if row else None
        version = (max_ver or 0) + 1
    cursor.execute('''
        INSERT INTO storyboard_saves (
            user_id, project_id, title, script_text, prompt, storyboard_json, storyboard_text, created_at, updated_at, series_id, version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        user_id, project_id, title, script_text, prompt, storyboard_json_text, storyboard_text, now, now, series_id, version
    ))
    record_id = cursor.lastrowid
    if not series_id:
        cursor.execute('UPDATE storyboard_saves SET series_id = ? WHERE id = ?', (record_id, record_id))
    conn.commit()
    conn.close()
    return record_id


def list_storyboard_records(user_id, project_id=None):
    """获取分镜保存列表"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute('SELECT id, title, created_at, updated_at, series_id, version FROM storyboard_saves WHERE user_id = ? ORDER BY updated_at DESC', (user_id,))
    else:
        cursor.execute('''
            SELECT id, title, created_at, updated_at, series_id, version
            FROM storyboard_saves
            WHERE user_id = ? AND project_id = ?
            ORDER BY updated_at DESC
        ''', (user_id, project_id))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_storyboard_series(user_id, project_id=None):
    """获取分镜系列列表（每个系列最新版本）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute('''
            SELECT s.*
            FROM storyboard_saves s
            JOIN (
                SELECT series_id, MAX(version) AS max_version
                FROM storyboard_saves
                WHERE user_id = ?
                GROUP BY series_id
            ) latest ON latest.series_id = s.series_id AND latest.max_version = s.version
            WHERE s.user_id = ?
            ORDER BY s.updated_at DESC
        ''', (user_id, user_id))
    else:
        cursor.execute('''
            SELECT s.*
            FROM storyboard_saves s
            JOIN (
                SELECT series_id, MAX(version) AS max_version
                FROM storyboard_saves
                WHERE user_id = ? AND project_id = ?
                GROUP BY series_id
            ) latest ON latest.series_id = s.series_id AND latest.max_version = s.version
            WHERE s.user_id = ? AND s.project_id = ?
            ORDER BY s.updated_at DESC
        ''', (user_id, project_id, user_id, project_id))
    rows = cursor.fetchall()
    series = [dict(r) for r in rows]
    for item in series:
        cursor.execute('SELECT COUNT(*) FROM storyboard_saves WHERE series_id = ? AND user_id = ?', (item.get('series_id'), user_id))
        item['version_count'] = cursor.fetchone()[0]
    conn.close()
    return series


def list_storyboard_versions(user_id, project_id, series_id):
    """获取分镜系列的版本列表"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute('''
            SELECT id, title, created_at, updated_at, series_id, version
            FROM storyboard_saves
            WHERE user_id = ? AND series_id = ?
            ORDER BY version DESC
        ''', (user_id, series_id))
    else:
        cursor.execute('''
            SELECT id, title, created_at, updated_at, series_id, version
            FROM storyboard_saves
            WHERE user_id = ? AND project_id = ? AND series_id = ?
            ORDER BY version DESC
        ''', (user_id, project_id, series_id))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_storyboard_episode(user_id, project_id, script_episode_id, prompt, storyboard_json, storyboard_text, images_json):
    """保存分镜分集记录（按剧本分集）"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id FROM storyboard_episode_records
        WHERE script_episode_id = ? AND user_id = ?
    ''', (script_episode_id, user_id))
    row = cursor.fetchone()
    storyboard_json_text = json.dumps(storyboard_json or {}, ensure_ascii=False)
    images_json_text = json.dumps(images_json or {}, ensure_ascii=False)
    if row:
        record_id = row[0]
        cursor.execute('''
            UPDATE storyboard_episode_records
            SET prompt = ?, storyboard_json = ?, storyboard_text = ?, images_json = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
        ''', (
            prompt, storyboard_json_text, storyboard_text, images_json_text, now, record_id, user_id
        ))
    else:
        cursor.execute('''
            INSERT INTO storyboard_episode_records (
                script_episode_id, user_id, project_id, prompt, storyboard_json, storyboard_text, images_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            script_episode_id, user_id, project_id, prompt, storyboard_json_text, storyboard_text, images_json_text, now, now
        ))
        record_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return record_id


def get_storyboard_episode(user_id, project_id, script_episode_id):
    """获取分镜分集记录"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute('''
            SELECT * FROM storyboard_episode_records
            WHERE script_episode_id = ? AND user_id = ?
            ORDER BY updated_at DESC LIMIT 1
        ''', (script_episode_id, user_id))
    else:
        cursor.execute('''
            SELECT * FROM storyboard_episode_records
            WHERE script_episode_id = ? AND user_id = ? AND project_id = ?
            ORDER BY updated_at DESC LIMIT 1
        ''', (script_episode_id, user_id, project_id))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    record = dict(row)
    for key in ('storyboard_json', 'images_json'):
        if record.get(key):
            try:
                record[key] = json.loads(record[key])
            except Exception:
                record[key] = {}
        else:
            record[key] = {}
    return record


def get_storyboard_record(user_id, project_id, record_id):
    """获取分镜记录"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute('SELECT * FROM storyboard_saves WHERE id = ? AND user_id = ?', (record_id, user_id))
    else:
        cursor.execute('SELECT * FROM storyboard_saves WHERE id = ? AND user_id = ? AND project_id = ?', (record_id, user_id, project_id))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

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
