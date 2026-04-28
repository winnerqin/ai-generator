"""
数据库模型 - 存储图片生成记录和用户信息
"""
import sqlite3
import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = 'generation_records.db'


def ensure_media_library_tables():
    """Ensure media library tables exist for older databases."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        '''
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
    '''
    )
    cursor.execute(
        '''
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
    '''
    )
    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS audio_library (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            project_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            filename TEXT NOT NULL,
            url TEXT NOT NULL,
            meta TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    '''
    )
    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS deleted_video_library_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            project_id INTEGER,
            task_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    '''
    )

    for table_name in ('image_library', 'video_library', 'audio_library'):
        cursor.execute(f"PRAGMA table_info({table_name})")
        cols = [col[1] for col in cursor.fetchall()]
        if 'project_id' not in cols:
            cursor.execute(f'ALTER TABLE {table_name} ADD COLUMN project_id INTEGER')

    cursor.execute(
        'CREATE INDEX IF NOT EXISTS idx_image_user_project_created ON image_library(user_id, project_id, created_at DESC)'
    )
    cursor.execute(
        'CREATE INDEX IF NOT EXISTS idx_video_user_project_created ON video_library(user_id, project_id, created_at DESC)'
    )
    cursor.execute(
        'CREATE INDEX IF NOT EXISTS idx_audio_user_project_created ON audio_library(user_id, project_id, created_at DESC)'
    )
    cursor.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS idx_deleted_video_task_unique ON deleted_video_library_tasks(user_id, project_id, task_id)'
    )

    conn.commit()
    conn.close()

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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audio_library (
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
        CREATE TABLE IF NOT EXISTS deleted_video_library_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            project_id INTEGER,
            task_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS omni_video_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            task_id TEXT UNIQUE NOT NULL,
            project_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'queued',
            model TEXT,
            mode TEXT,
            prompt TEXT,
            input_payload_json TEXT,
            raw_response_json TEXT,
            result_json TEXT,
            fail_reason TEXT,
            video_url TEXT,
            cover_url TEXT,
            first_frame_url TEXT,
            last_frame_url TEXT,
            reference_urls_json TEXT,
            duration INTEGER,
            frame_count INTEGER,
            resolution TEXT,
            aspect_ratio TEXT,
            filename TEXT,
            seed INTEGER,
            token_usage INTEGER,
            usage_json TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    '''
    )
    
    # 创建索引以提高查询性能
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_tasks_user_id ON video_tasks(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_tasks_task_id ON video_tasks(task_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_tasks_status ON video_tasks(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_tasks_created_at ON video_tasks(created_at)')
    cursor.execute(
        'CREATE INDEX IF NOT EXISTS idx_omni_video_tasks_user_id ON omni_video_tasks(user_id)'
    )
    cursor.execute(
        'CREATE INDEX IF NOT EXISTS idx_omni_video_tasks_task_id ON omni_video_tasks(task_id)'
    )
    cursor.execute(
        'CREATE INDEX IF NOT EXISTS idx_omni_video_tasks_status ON omni_video_tasks(status)'
    )
    cursor.execute(
        'CREATE INDEX IF NOT EXISTS idx_omni_video_tasks_created_at ON omni_video_tasks(created_at)'
    )

    # 添加复合索引以优化日期范围查询和用户统计查询
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_gen_user_date ON generation_records(user_id, DATE(created_at))')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_gen_date ON generation_records(DATE(created_at))')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_tasks_user_date ON video_tasks(user_id, DATE(created_at))')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_tasks_date ON video_tasks(DATE(created_at))')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_omni_user_date ON omni_video_tasks(user_id, DATE(created_at))')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_omni_date ON omni_video_tasks(DATE(created_at))')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_enhance_user_date ON video_enhance_tasks(user_id, DATE(created_at))')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_enhance_date ON video_enhance_tasks(DATE(created_at))')
    
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
        'audio_library',
        'video_tasks',
        'omni_video_tasks',
    ]:
        ensure_column(table_name, 'project_id', 'INTEGER')
    ensure_column('omni_video_tasks', 'frame_count', 'INTEGER')
    ensure_column('omni_video_tasks', 'token_usage', 'INTEGER')
    ensure_column('omni_video_tasks', 'usage_json', 'TEXT')
    ensure_column('omni_video_tasks', 'filename', 'TEXT')

    # 图片生成记录添加token_usage字段
    ensure_column('generation_records', 'token_usage', 'INTEGER')
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_records_user_project_created ON generation_records(user_id, project_id, created_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_person_user_project_created ON person_library(user_id, project_id, created_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_scene_user_project_created ON scene_library(user_id, project_id, created_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_image_user_project_created ON image_library(user_id, project_id, created_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_user_project_created ON video_library(user_id, project_id, created_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_audio_user_project_created ON audio_library(user_id, project_id, created_at DESC)')
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_deleted_video_task_unique ON deleted_video_library_tasks(user_id, project_id, task_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_tasks_user_project_created ON video_tasks(user_id, project_id, created_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_omni_video_tasks_user_project_created ON omni_video_tasks(user_id, project_id, created_at DESC)')
    
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
            'audio_library',
            'video_tasks',
            'omni_video_tasks',
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
            - token_usage (optional) - 图片生成消耗的token
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
         num_images, seed, steps, sample_images, image_path, filename, batch_id, status, token_usage)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        data.get('status', 'success'),
        data.get('token_usage')  # 新增token_usage字段
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
    ensure_media_library_tables()
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
    ensure_media_library_tables()
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
    ensure_media_library_tables()
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
    ensure_media_library_tables()
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


def rename_video_asset(asset_id, filename, user_id=None, project_id=None):
    """Rename a video asset in the video library."""
    ensure_media_library_tables()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    query = 'UPDATE video_library SET filename = ? WHERE id = ?'
    params = [filename, asset_id]
    if user_id is not None:
        query += ' AND user_id = ?'
        params.append(user_id)
    if project_id is not None:
        query += ' AND project_id = ?'
        params.append(project_id)
    cursor.execute(query, tuple(params))
    updated = cursor.rowcount
    conn.commit()
    conn.close()
    return updated


def update_video_asset_url(asset_id, new_url):
    """更新视频库记录的URL"""
    ensure_media_library_tables()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('UPDATE video_library SET url = ? WHERE id = ?', (new_url, asset_id))
    conn.commit()
    conn.close()


def update_video_asset_url_by_task_id(user_id, task_id, new_url, project_id=None):
    """根据task_id更新视频库记录的URL"""
    ensure_media_library_tables()
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
                cursor.execute('UPDATE video_library SET url = ? WHERE id = ?', (new_url, asset['id']))
                conn.commit()
                conn.close()
                return True
        except Exception:
            pass
    conn.close()
    return False


def update_video_asset_meta(asset_id, meta_update):
    """更新视频库记录的meta字段（合并更新）"""
    ensure_media_library_tables()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT meta FROM video_library WHERE id = ?', (asset_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False
    try:
        existing_meta = json.loads(row['meta'] or '{}')
        if not isinstance(existing_meta, dict):
            existing_meta = {}
        # 合并新的meta数据
        existing_meta.update(meta_update)
        cursor.execute('UPDATE video_library SET meta = ? WHERE id = ?', (json.dumps(existing_meta), asset_id))
        conn.commit()
        conn.close()
        return True
    except Exception:
        conn.close()
        return False


def save_audio_asset(user_id, filename, url, meta=None, project_id=None):
    """淇濆瓨闊抽鍒伴煶棰戝簱"""
    ensure_media_library_tables()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        '''
        INSERT INTO audio_library (user_id, project_id, created_at, filename, url, meta)
        VALUES (?, ?, ?, ?, ?, ?)
    ''',
        (
            user_id,
            project_id,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            filename,
            url,
            json.dumps(meta or {}),
        ),
    )
    asset_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return asset_id


def get_audio_assets(user_id, project_id=None, limit=500):
    """鑾峰彇闊抽搴撹祫婧?"""
    ensure_media_library_tables()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute(
            'SELECT * FROM audio_library WHERE user_id = ? ORDER BY created_at DESC LIMIT ?',
            (user_id, limit),
        )
    else:
        cursor.execute(
            'SELECT * FROM audio_library WHERE user_id = ? AND project_id = ? ORDER BY created_at DESC LIMIT ?',
            (user_id, project_id, limit),
        )
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
    ensure_media_library_tables()
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


def mark_video_task_deleted_from_library(user_id, task_id, project_id=None):
    """Remember that a generated video task was manually removed from the library."""
    ensure_media_library_tables()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        '''
        INSERT OR IGNORE INTO deleted_video_library_tasks (user_id, project_id, task_id, created_at)
        VALUES (?, ?, ?, ?)
        ''',
        (user_id, project_id, task_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
    )
    conn.commit()
    conn.close()


def is_video_task_deleted_from_library(user_id, task_id, project_id=None):
    """Check whether a generated video task was manually removed from the library."""
    ensure_media_library_tables()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if project_id is None:
        cursor.execute(
            '''
            SELECT 1
            FROM deleted_video_library_tasks
            WHERE user_id = ? AND task_id = ? AND project_id IS NULL
            LIMIT 1
            ''',
            (user_id, task_id),
        )
    else:
        cursor.execute(
            '''
            SELECT 1
            FROM deleted_video_library_tasks
            WHERE user_id = ? AND task_id = ? AND project_id = ?
            LIMIT 1
            ''',
            (user_id, task_id, project_id),
        )
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def _ensure_omni_video_task_schema(cursor):
    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS omni_video_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            task_id TEXT UNIQUE NOT NULL,
            project_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'queued',
            model TEXT,
            mode TEXT,
            prompt TEXT,
            input_payload_json TEXT,
            raw_response_json TEXT,
            result_json TEXT,
            fail_reason TEXT,
            video_url TEXT,
            cover_url TEXT,
            first_frame_url TEXT,
            last_frame_url TEXT,
            reference_urls_json TEXT,
            duration INTEGER,
            frame_count INTEGER,
            resolution TEXT,
            aspect_ratio TEXT,
            filename TEXT,
            seed INTEGER,
            token_usage INTEGER,
            usage_json TEXT
        )
    '''
    )
    cursor.execute("PRAGMA table_info(omni_video_tasks)")
    columns = [col[1] for col in cursor.fetchall()]
    if "frame_count" not in columns:
        cursor.execute("ALTER TABLE omni_video_tasks ADD COLUMN frame_count INTEGER")
    if "token_usage" not in columns:
        cursor.execute("ALTER TABLE omni_video_tasks ADD COLUMN token_usage INTEGER")
    if "usage_json" not in columns:
        cursor.execute("ALTER TABLE omni_video_tasks ADD COLUMN usage_json TEXT")
    if "filename" not in columns:
        cursor.execute("ALTER TABLE omni_video_tasks ADD COLUMN filename TEXT")


def _decode_omni_video_task(row):
    task = dict(row)
    for field in ("input_payload_json", "raw_response_json", "result_json", "reference_urls_json", "usage_json"):
        raw = task.get(field)
        if not raw:
            task[field] = [] if field == "reference_urls_json" else {}
            continue
        try:
            task[field] = json.loads(raw)
        except Exception:
            task[field] = [] if field == "reference_urls_json" else {}
    return task


def save_omni_video_task(data):
    """Insert or update an omni video task."""

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    _ensure_omni_video_task_schema(cursor)

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('SELECT id FROM omni_video_tasks WHERE task_id = ?', (data.get('task_id'),))
    existing = cursor.fetchone()

    params = (
        data.get('user_id'),
        data.get('task_id'),
        data.get('project_id'),
        now,
        now,
        data.get('status', 'queued'),
        data.get('model'),
        data.get('mode'),
        data.get('prompt'),
        json.dumps(data.get('input_payload_json', {})),
        json.dumps(data.get('raw_response_json', {})),
        json.dumps(data.get('result_json', {})),
        data.get('fail_reason'),
        data.get('video_url'),
        data.get('cover_url'),
        data.get('first_frame_url'),
        data.get('last_frame_url'),
        json.dumps(data.get('reference_urls_json', [])),
        data.get('duration'),
        data.get('frame_count'),
        data.get('resolution'),
        data.get('aspect_ratio'),
        data.get('filename'),
        data.get('seed'),
        data.get('token_usage'),
        json.dumps(data.get('usage_json', {})),
    )

    if existing:
        cursor.execute(
            '''
            UPDATE omni_video_tasks
            SET user_id = ?, project_id = ?, updated_at = ?, status = ?, model = ?, mode = ?,
                prompt = ?, input_payload_json = ?, raw_response_json = ?, result_json = ?,
                fail_reason = ?, video_url = ?, cover_url = ?, first_frame_url = ?,
                last_frame_url = ?, reference_urls_json = ?, duration = ?, frame_count = ?,
                resolution = ?, aspect_ratio = ?, filename = ?, seed = ?, token_usage = ?, usage_json = ?
            WHERE task_id = ?
        ''',
            (
                data.get('user_id'),
                data.get('project_id'),
                now,
                data.get('status', 'queued'),
                data.get('model'),
                data.get('mode'),
                data.get('prompt'),
                json.dumps(data.get('input_payload_json', {})),
                json.dumps(data.get('raw_response_json', {})),
                json.dumps(data.get('result_json', {})),
                data.get('fail_reason'),
                data.get('video_url'),
                data.get('cover_url'),
                data.get('first_frame_url'),
                data.get('last_frame_url'),
                json.dumps(data.get('reference_urls_json', [])),
                data.get('duration'),
                data.get('frame_count'),
                data.get('resolution'),
                data.get('aspect_ratio'),
                data.get('filename'),
                data.get('seed'),
                data.get('token_usage'),
                json.dumps(data.get('usage_json', {})),
                data.get('task_id'),
            ),
        )
        record_id = existing[0]
    else:
        cursor.execute(
            '''
            INSERT INTO omni_video_tasks (
                user_id, task_id, project_id, created_at, updated_at, status, model, mode,
                prompt, input_payload_json, raw_response_json, result_json, fail_reason,
                video_url, cover_url, first_frame_url, last_frame_url, reference_urls_json,
                duration, frame_count, resolution, aspect_ratio, filename, seed, token_usage, usage_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
            params,
        )
        record_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return record_id


def get_omni_video_task(task_id, user_id=None, project_id=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    _ensure_omni_video_task_schema(cursor)

    query = 'SELECT * FROM omni_video_tasks WHERE task_id = ?'
    params = [task_id]
    if user_id is not None:
        query += ' AND user_id = ?'
        params.append(user_id)
    if project_id is not None:
        query += ' AND project_id = ?'
        params.append(project_id)

    cursor.execute(query, params)
    row = cursor.fetchone()
    conn.close()
    return _decode_omni_video_task(row) if row else None


def get_omni_video_tasks(user_id, project_id=None, status=None, search=None, start_date=None, end_date=None, limit=20, offset=0):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    _ensure_omni_video_task_schema(cursor)

    query = 'SELECT * FROM omni_video_tasks WHERE user_id = ?'
    params = [user_id]
    if project_id is not None:
        query += ' AND project_id = ?'
        params.append(project_id)
    if status:
        query += ' AND status = ?'
        params.append(status)
    if search:
        query += ' AND (task_id LIKE ? OR prompt LIKE ? OR filename LIKE ?)'
        like = f'%{search}%'
        params.extend([like, like, like])
    if start_date:
        query += ' AND DATE(created_at) >= DATE(?)'
        params.append(start_date)
    if end_date:
        query += ' AND DATE(created_at) <= DATE(?)'
        params.append(end_date)

    query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
    params.extend([limit, offset])
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [_decode_omni_video_task(row) for row in rows]


def count_omni_video_tasks(user_id, project_id=None, status=None, search=None, start_date=None, end_date=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    _ensure_omni_video_task_schema(cursor)

    query = 'SELECT COUNT(*) FROM omni_video_tasks WHERE user_id = ?'
    params = [user_id]
    if project_id is not None:
        query += ' AND project_id = ?'
        params.append(project_id)
    if status:
        query += ' AND status = ?'
        params.append(status)
    if search:
        query += ' AND (task_id LIKE ? OR prompt LIKE ? OR filename LIKE ?)'
        like = f'%{search}%'
        params.extend([like, like, like])
    if start_date:
        query += ' AND DATE(created_at) >= DATE(?)'
        params.append(start_date)
    if end_date:
        query += ' AND DATE(created_at) <= DATE(?)'
        params.append(end_date)

    cursor.execute(query, params)
    total = cursor.fetchone()[0]
    conn.close()
    return total


def delete_omni_video_task(task_id, user_id=None, project_id=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    _ensure_omni_video_task_schema(cursor)

    query = 'DELETE FROM omni_video_tasks WHERE task_id = ?'
    params = [task_id]
    if user_id is not None:
        query += ' AND user_id = ?'
        params.append(user_id)
    if project_id is not None:
        query += ' AND project_id = ?'
        params.append(project_id)

    cursor.execute(query, params)
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted


# ==================== 视频画质增强任务函数 ====================

def _ensure_video_enhance_tasks_schema(cursor):
    """确保视频画质增强任务表存在。"""
    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS video_enhance_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            task_id TEXT UNIQUE NOT NULL,
            project_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'queued',
            source_video_url TEXT NOT NULL,
            source_video_id TEXT,
            source_filename TEXT,
            input_payload_json TEXT,
            tool_version TEXT NOT NULL DEFAULT 'standard',
            resolution TEXT NOT NULL DEFAULT '1080p',
            raw_response_json TEXT,
            result_json TEXT,
            video_url TEXT,
            output_filename TEXT,
            cover_url TEXT,
            fail_reason TEXT,
            token_usage INTEGER,
            usage_json TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    '''
    )
    cursor.execute(
        'CREATE INDEX IF NOT EXISTS idx_video_enhance_tasks_user_id ON video_enhance_tasks(user_id)'
    )
    cursor.execute(
        'CREATE INDEX IF NOT EXISTS idx_video_enhance_tasks_task_id ON video_enhance_tasks(task_id)'
    )
    cursor.execute(
        'CREATE INDEX IF NOT EXISTS idx_video_enhance_tasks_status ON video_enhance_tasks(status)'
    )
    cursor.execute(
        'CREATE INDEX IF NOT EXISTS idx_video_enhance_tasks_created_at ON video_enhance_tasks(created_at)'
    )
    cursor.execute(
        'CREATE INDEX IF NOT EXISTS idx_video_enhance_tasks_user_project_created ON video_enhance_tasks(user_id, project_id, created_at DESC)'
    )

    # Migration: add tool_version column if needed, ensure resolution exists
    cursor.execute("PRAGMA table_info(video_enhance_tasks)")
    columns = [row[1] for row in cursor.fetchall()]

    # Clean up any leftover migration tables from previous failed migrations
    cursor.execute('DROP TABLE IF EXISTS video_enhance_tasks_new')

    # If table has resolution but not tool_version, add tool_version
    if 'resolution' in columns and 'tool_version' not in columns:
        cursor.execute(
            '''
            CREATE TABLE video_enhance_tasks_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                task_id TEXT UNIQUE NOT NULL,
                project_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'queued',
                source_video_url TEXT NOT NULL,
                source_video_id TEXT,
                source_filename TEXT,
                input_payload_json TEXT,
                tool_version TEXT NOT NULL DEFAULT 'standard',
                resolution TEXT NOT NULL DEFAULT '1080p',
                raw_response_json TEXT,
                result_json TEXT,
                video_url TEXT,
                output_filename TEXT,
                cover_url TEXT,
                fail_reason TEXT,
                token_usage INTEGER,
                usage_json TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            '''
        )
        cursor.execute(
            '''
            INSERT INTO video_enhance_tasks_new (
                id, user_id, task_id, project_id, created_at, updated_at, status,
                source_video_url, source_video_id, source_filename, input_payload_json,
                tool_version, resolution, raw_response_json, result_json, video_url, output_filename,
                cover_url, fail_reason, token_usage, usage_json
            )
            SELECT id, user_id, task_id, project_id, created_at, updated_at, status,
                source_video_url, source_video_id, source_filename, input_payload_json,
                'standard', resolution, raw_response_json, result_json, video_url, output_filename,
                cover_url, fail_reason, token_usage, usage_json
            FROM video_enhance_tasks
            '''
        )
        cursor.execute('DROP TABLE video_enhance_tasks')
        cursor.execute('ALTER TABLE video_enhance_tasks_new RENAME TO video_enhance_tasks')
        # Recreate indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_enhance_tasks_user_id ON video_enhance_tasks(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_enhance_tasks_task_id ON video_enhance_tasks(task_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_enhance_tasks_status ON video_enhance_tasks(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_enhance_tasks_created_at ON video_enhance_tasks(created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_enhance_tasks_user_project_created ON video_enhance_tasks(user_id, project_id, created_at DESC)')

    # If table has tool_version but not resolution, add resolution column
    elif 'tool_version' in columns and 'resolution' not in columns:
        cursor.execute(
            '''
            CREATE TABLE video_enhance_tasks_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                task_id TEXT UNIQUE NOT NULL,
                project_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'queued',
                source_video_url TEXT NOT NULL,
                source_video_id TEXT,
                source_filename TEXT,
                input_payload_json TEXT,
                tool_version TEXT NOT NULL DEFAULT 'standard',
                resolution TEXT NOT NULL DEFAULT '1080p',
                raw_response_json TEXT,
                result_json TEXT,
                video_url TEXT,
                output_filename TEXT,
                cover_url TEXT,
                fail_reason TEXT,
                token_usage INTEGER,
                usage_json TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            '''
        )
        cursor.execute(
            '''
            INSERT INTO video_enhance_tasks_new (
                id, user_id, task_id, project_id, created_at, updated_at, status,
                source_video_url, source_video_id, source_filename, input_payload_json,
                tool_version, resolution, raw_response_json, result_json, video_url, output_filename,
                cover_url, fail_reason, token_usage, usage_json
            )
            SELECT id, user_id, task_id, project_id, created_at, updated_at, status,
                source_video_url, source_video_id, source_filename, input_payload_json,
                tool_version, '1080p', raw_response_json, result_json, video_url, output_filename,
                cover_url, fail_reason, token_usage, usage_json
            FROM video_enhance_tasks
            '''
        )
        cursor.execute('DROP TABLE video_enhance_tasks')
        cursor.execute('ALTER TABLE video_enhance_tasks_new RENAME TO video_enhance_tasks')
        # Recreate indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_enhance_tasks_user_id ON video_enhance_tasks(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_enhance_tasks_task_id ON video_enhance_tasks(task_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_enhance_tasks_status ON video_enhance_tasks(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_enhance_tasks_created_at ON video_enhance_tasks(created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_enhance_tasks_user_project_created ON video_enhance_tasks(user_id, project_id, created_at DESC)')


def _decode_video_enhance_task(row):
    """解码视频画质增强任务的JSON字段。"""
    task = dict(row)
    for field in ("input_payload_json", "raw_response_json", "result_json", "usage_json"):
        raw = task.get(field)
        if not raw:
            task[field] = {}
            continue
        try:
            task[field] = json.loads(raw)
        except Exception:
            task[field] = {}
    return task


def save_video_enhance_task(data):
    """插入或更新视频画质增强任务。"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    _ensure_video_enhance_tasks_schema(cursor)

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('SELECT id FROM video_enhance_tasks WHERE task_id = ?', (data.get('task_id'),))
    existing = cursor.fetchone()

    if existing:
        cursor.execute(
            '''
            UPDATE video_enhance_tasks
            SET user_id = ?, project_id = ?, updated_at = ?, status = ?,
                source_video_url = ?, source_video_id = ?, source_filename = ?,
                input_payload_json = ?, tool_version = ?, resolution = ?, raw_response_json = ?,
                result_json = ?, video_url = ?, output_filename = ?, cover_url = ?,
                fail_reason = ?, token_usage = ?, usage_json = ?
            WHERE task_id = ?
            ''',
            (
                data.get('user_id'),
                data.get('project_id'),
                now,
                data.get('status', 'queued'),
                data.get('source_video_url'),
                data.get('source_video_id'),
                data.get('source_filename'),
                json.dumps(data.get('input_payload_json', {})),
                data.get('tool_version'),
                data.get('resolution'),
                json.dumps(data.get('raw_response_json', {})),
                json.dumps(data.get('result_json', {})),
                data.get('video_url'),
                data.get('output_filename'),
                data.get('cover_url'),
                data.get('fail_reason'),
                data.get('token_usage'),
                json.dumps(data.get('usage_json', {})),
                data.get('task_id'),
            ),
        )
        record_id = existing[0]
    else:
        cursor.execute(
            '''
            INSERT INTO video_enhance_tasks (
                user_id, task_id, project_id, created_at, updated_at, status,
                source_video_url, source_video_id, source_filename, input_payload_json,
                tool_version, resolution, raw_response_json, result_json, video_url, output_filename,
                cover_url, fail_reason, token_usage, usage_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                data.get('user_id'),
                data.get('task_id'),
                data.get('project_id'),
                now,
                now,
                data.get('status', 'queued'),
                data.get('source_video_url'),
                data.get('source_video_id'),
                data.get('source_filename'),
                json.dumps(data.get('input_payload_json', {})),
                data.get('tool_version'),
                data.get('resolution'),
                json.dumps(data.get('raw_response_json', {})),
                json.dumps(data.get('result_json', {})),
                data.get('video_url'),
                data.get('output_filename'),
                data.get('cover_url'),
                data.get('fail_reason'),
                data.get('token_usage'),
                json.dumps(data.get('usage_json', {})),
            ),
        )
        record_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return record_id


def get_video_enhance_task(task_id, user_id=None, project_id=None):
    """获取单个视频画质增强任务。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    _ensure_video_enhance_tasks_schema(cursor)

    query = 'SELECT * FROM video_enhance_tasks WHERE task_id = ?'
    params = [task_id]
    if user_id is not None:
        query += ' AND user_id = ?'
        params.append(user_id)
    if project_id is not None:
        query += ' AND project_id = ?'
        params.append(project_id)

    cursor.execute(query, params)
    row = cursor.fetchone()
    conn.close()
    return _decode_video_enhance_task(row) if row else None


def get_video_enhance_tasks(user_id, project_id=None, status=None, search=None, start_date=None, end_date=None, limit=20, offset=0):
    """分页查询视频画质增强任务列表。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    _ensure_video_enhance_tasks_schema(cursor)

    query = 'SELECT * FROM video_enhance_tasks WHERE user_id = ?'
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
    if search:
        query += ' AND (task_id LIKE ? OR source_filename LIKE ? OR output_filename LIKE ?)'
        search_pattern = f'%{search}%'
        params.extend([search_pattern, search_pattern, search_pattern])

    query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [_decode_video_enhance_task(row) for row in rows]


def count_video_enhance_tasks(user_id, project_id=None, status=None, search=None, start_date=None, end_date=None):
    """计数视频画质增强任务。"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    _ensure_video_enhance_tasks_schema(cursor)

    query = 'SELECT COUNT(*) FROM video_enhance_tasks WHERE user_id = ?'
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
    if search:
        query += ' AND (task_id LIKE ? OR source_filename LIKE ? OR output_filename LIKE ?)'
        search_pattern = f'%{search}%'
        params.extend([search_pattern, search_pattern, search_pattern])

    cursor.execute(query, params)
    total = cursor.fetchone()[0]
    conn.close()
    return total


def delete_video_enhance_task(task_id, user_id=None, project_id=None):
    """删除视频画质增强任务。"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    _ensure_video_enhance_tasks_schema(cursor)

    query = 'DELETE FROM video_enhance_tasks WHERE task_id = ?'
    params = [task_id]
    if user_id is not None:
        query += ' AND user_id = ?'
        params.append(user_id)
    if project_id is not None:
        query += ' AND project_id = ?'
        params.append(project_id)

    cursor.execute(query, params)
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted


def delete_image_asset(asset_id, user_id=None, project_id=None):
    """删除图片库资源。传入 user_id、project_id 时仅当资源属于该用户且属于该项目时删除（项目隔离）。"""
    ensure_media_library_tables()
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
    ensure_media_library_tables()
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


def delete_audio_asset(asset_id, user_id=None, project_id=None):
    """鍒犻櫎闊抽搴撹祫婧愩€?"""
    ensure_media_library_tables()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if user_id is not None and project_id is not None:
        cursor.execute(
            'DELETE FROM audio_library WHERE id = ? AND user_id = ? AND (project_id = ? OR (project_id IS NULL AND ? IS NULL))',
            (asset_id, user_id, project_id, project_id),
        )
    elif user_id is not None:
        cursor.execute('DELETE FROM audio_library WHERE id = ? AND user_id = ?', (asset_id, user_id))
    else:
        cursor.execute('DELETE FROM audio_library WHERE id = ?', (asset_id,))
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


def delete_project(project_id):
    """Delete a project and its membership relations."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM user_projects WHERE project_id = ?', (project_id,))
    cursor.execute('DELETE FROM projects WHERE id = ?', (project_id,))
    conn.commit()
    deleted = cursor.rowcount
    conn.close()
    return deleted > 0


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


# ========== 报表统计函数 ==========

def get_report_overview(start_date=None, end_date=None):
    """
    获取报表概览统计（图片、视频、增强三种任务）

    返回: {
        'total_users': int,
        'image': {'total': int, 'today': int, 'last7days': int, 'period': int},
        'video': {'total': int, 'today': int, 'last7days': int, 'period': int, 'total_duration': int, 'today_duration': int, 'last7days_duration': int, 'period_duration': int},
        'enhance': {'total': int, 'today': int, 'last7days': int, 'period': int}
    }
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    today = datetime.now().strftime('%Y-%m-%d')
    # 近7天：从前一天开始往前推6天（不含今天）
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    last7days_start = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

    # 总用户数
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]

    # 图片统计
    image_stats = {
        'total': 0, 'today': 0, 'last7days': 0, 'period': 0
    }
    cursor.execute('SELECT COUNT(*) FROM generation_records')
    image_stats['total'] = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM generation_records WHERE DATE(created_at) = ?', (today,))
    image_stats['today'] = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM generation_records WHERE DATE(created_at) BETWEEN ? AND ?', (last7days_start, yesterday))
    image_stats['last7days'] = cursor.fetchone()[0]

    if start_date and end_date:
        cursor.execute('SELECT COUNT(*) FROM generation_records WHERE DATE(created_at) BETWEEN ? AND ?', (start_date, end_date))
        image_stats['period'] = cursor.fetchone()[0]

    # 视频统计（合并 video_tasks 和 omni_video_tasks）
    video_stats = {
        'total': 0, 'today': 0, 'last7days': 0, 'period': 0,
        'total_duration': 0, 'today_duration': 0, 'last7days_duration': 0, 'period_duration': 0
    }

    # 总数和总时长
    cursor.execute('''
        SELECT COUNT(*), COALESCE(SUM(duration), 0) FROM (
            SELECT duration FROM video_tasks
            UNION ALL
            SELECT duration FROM omni_video_tasks
        )
    ''')
    row = cursor.fetchone()
    video_stats['total'] = row[0] or 0
    video_stats['total_duration'] = row[1] or 0

    # 今日
    cursor.execute('''
        SELECT COUNT(*), COALESCE(SUM(duration), 0) FROM (
            SELECT duration, created_at FROM video_tasks
            UNION ALL
            SELECT duration, created_at FROM omni_video_tasks
        ) WHERE DATE(created_at) = ?
    ''', (today,))
    row = cursor.fetchone()
    video_stats['today'] = row[0] or 0
    video_stats['today_duration'] = row[1] or 0

    # 近7天
    cursor.execute('''
        SELECT COUNT(*), COALESCE(SUM(duration), 0) FROM (
            SELECT duration, created_at FROM video_tasks
            UNION ALL
            SELECT duration, created_at FROM omni_video_tasks
        ) WHERE DATE(created_at) BETWEEN ? AND ?
    ''', (last7days_start, yesterday))
    row = cursor.fetchone()
    video_stats['last7days'] = row[0] or 0
    video_stats['last7days_duration'] = row[1] or 0

    # 指定时间段
    if start_date and end_date:
        cursor.execute('''
            SELECT COUNT(*), COALESCE(SUM(duration), 0) FROM (
                SELECT duration, created_at FROM video_tasks
                UNION ALL
                SELECT duration, created_at FROM omni_video_tasks
            ) WHERE DATE(created_at) BETWEEN ? AND ?
        ''', (start_date, end_date))
        row = cursor.fetchone()
        video_stats['period'] = row[0] or 0
        video_stats['period_duration'] = row[1] or 0

    # 增强统计
    enhance_stats = {
        'total': 0, 'today': 0, 'last7days': 0, 'period': 0
    }
    cursor.execute('SELECT COUNT(*) FROM video_enhance_tasks')
    enhance_stats['total'] = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM video_enhance_tasks WHERE DATE(created_at) = ?', (today,))
    enhance_stats['today'] = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM video_enhance_tasks WHERE DATE(created_at) BETWEEN ? AND ?', (last7days_start, yesterday))
    enhance_stats['last7days'] = cursor.fetchone()[0]

    if start_date and end_date:
        cursor.execute('SELECT COUNT(*) FROM video_enhance_tasks WHERE DATE(created_at) BETWEEN ? AND ?', (start_date, end_date))
        enhance_stats['period'] = cursor.fetchone()[0]

    conn.close()

    return {
        'total_users': total_users,
        'image': image_stats,
        'video': video_stats,
        'enhance': enhance_stats
    }


def get_user_report(start_date=None, end_date=None, username_filter=None):
    """
    获取用户维度统计（使用单次聚合查询，消除N+1问题）

    Args:
        start_date: 开始日期
        end_date: 结束日期
        username_filter: 用户名筛选（可选）

    返回: List[{
        'user_id': int, 'username': str,
        'image_count': int, 'video_count': int, 'video_duration': int,
        'enhance_count': int, 'total_count': int, 'last_active': str,
        'video_tokens': int, 'enhance_tokens': int, 'total_tokens': int
    }]
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 构建日期条件
    date_condition = ""
    date_params = []
    if start_date and end_date:
        date_condition = "AND DATE(created_at) BETWEEN ? AND ?"
        date_params = [start_date, end_date]

    # 用户名筛选条件
    username_condition = ""
    username_params = []
    if username_filter:
        username_condition = "AND u.username LIKE ?"
        username_params = [f"%{username_filter}%"]

    # 单次聚合查询，合并所有表的统计
    # 使用LEFT JOIN确保所有用户都被包含，即使没有记录
    # Token只统计全能视频(omni_video_tasks)
    # 视频统计合并 video_tasks 和 omni_video_tasks
    query = f'''
        SELECT
            u.id as user_id,
            u.username,
            COALESCE(g.image_count, 0) as image_count,
            COALESCE(v.video_count, 0) as video_count,
            COALESCE(v.video_duration, 0) as video_duration,
            COALESCE(e.enhance_count, 0) as enhance_count,
            COALESCE(ov.video_tokens, 0) as video_tokens,
            MAX(COALESCE(g.last_active, ''), COALESCE(v.last_active, ''), COALESCE(e.last_active, ''), COALESCE(ov.last_active, '')) as last_active
        FROM users u
        LEFT JOIN (
            SELECT user_id, COUNT(*) as image_count, MAX(created_at) as last_active
            FROM generation_records
            WHERE 1=1 {date_condition}
            GROUP BY user_id
        ) g ON u.id = g.user_id
        LEFT JOIN (
            SELECT user_id, COUNT(*) as video_count, SUM(COALESCE(duration, 0)) as video_duration, MAX(created_at) as last_active
            FROM (
                SELECT user_id, duration, created_at FROM video_tasks WHERE 1=1 {date_condition}
                UNION ALL
                SELECT user_id, COALESCE(duration, 0) as duration, created_at FROM omni_video_tasks WHERE 1=1 {date_condition}
            )
            GROUP BY user_id
        ) v ON u.id = v.user_id
        LEFT JOIN (
            SELECT user_id, COUNT(*) as enhance_count, MAX(created_at) as last_active
            FROM video_enhance_tasks
            WHERE 1=1 {date_condition}
            GROUP BY user_id
        ) e ON u.id = e.user_id
        LEFT JOIN (
            SELECT user_id, SUM(COALESCE(token_usage, 0)) as video_tokens, MAX(created_at) as last_active
            FROM omni_video_tasks
            WHERE 1=1 {date_condition}
            GROUP BY user_id
        ) ov ON u.id = ov.user_id
        WHERE 1=1 {username_condition}
        ORDER BY u.id
    '''

    params = date_params + date_params + date_params + date_params + date_params + date_params + username_params
    cursor.execute(query, params)
    rows = cursor.fetchall()

    stats = []
    for row in rows:
        total_count = (row['image_count'] or 0) + (row['video_count'] or 0) + (row['enhance_count'] or 0)
        video_tokens = row['video_tokens'] or 0
        last_active = row['last_active'] if row['last_active'] else None
        stats.append({
            'user_id': row['user_id'],
            'username': row['username'],
            'image_count': row['image_count'] or 0,
            'video_count': row['video_count'] or 0,
            'video_duration': row['video_duration'] or 0,
            'enhance_count': row['enhance_count'] or 0,
            'total_count': total_count,
            'last_active': last_active,
            'video_tokens': video_tokens,
            'total_tokens': video_tokens
        })

    conn.close()
    return stats


def get_daily_report(start_date=None, end_date=None, days=30):
    """
    获取每日趋势统计（使用子查询优化，消除循环查询）

    返回: List[{
        'date': str, 'image_count': int, 'video_count': int,
        'video_duration': int, 'enhance_count': int, 'user_count': int,
        'video_tokens': int
    }]
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 确定日期范围
    if not start_date or not end_date:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days-1)).strftime('%Y-%m-%d')

    # 单次查询获取所有日期的统计数据（使用UNION合并所有活动）
    # Token只统计全能视频(omni_video_tasks)
    cursor.execute('''
        WITH all_activities AS (
            -- 图片生成（不计token）
            SELECT DATE(created_at) as date, user_id, 'image' as type, 0 as duration, 0 as video_tokens
            FROM generation_records
            WHERE DATE(created_at) BETWEEN ? AND ?
            UNION ALL
            -- 视频任务（不计token）
            SELECT DATE(created_at) as date, user_id, 'video' as type, COALESCE(duration, 0) as duration, 0 as video_tokens
            FROM video_tasks
            WHERE DATE(created_at) BETWEEN ? AND ?
            UNION ALL
            -- 全能视频任务（统计token）
            SELECT DATE(created_at) as date, user_id, 'omni_video' as type, COALESCE(duration, 0) as duration, COALESCE(token_usage, 0) as video_tokens
            FROM omni_video_tasks
            WHERE DATE(created_at) BETWEEN ? AND ?
            UNION ALL
            -- 视频增强（不计token）
            SELECT DATE(created_at) as date, user_id, 'enhance' as type, 0 as duration, 0 as video_tokens
            FROM video_enhance_tasks
            WHERE DATE(created_at) BETWEEN ? AND ?
        ),
        daily_stats AS (
            SELECT
                date,
                SUM(CASE WHEN type = 'image' THEN 1 ELSE 0 END) as image_count,
                SUM(CASE WHEN type IN ('video', 'omni_video') THEN 1 ELSE 0 END) as video_count,
                SUM(CASE WHEN type IN ('video', 'omni_video') THEN duration ELSE 0 END) as video_duration,
                SUM(CASE WHEN type = 'enhance' THEN 1 ELSE 0 END) as enhance_count,
                COUNT(DISTINCT user_id) as user_count,
                SUM(video_tokens) as video_tokens
            FROM all_activities
            GROUP BY date
        )
        SELECT * FROM daily_stats ORDER BY date DESC
    ''', (start_date, end_date, start_date, end_date, start_date, end_date, start_date, end_date))

    rows = cursor.fetchall()

    # 如果需要补全日期（无数据的日期也要显示）
    # 获取日期范围内的所有日期
    cursor.execute('''
        WITH dates(date) AS (
            SELECT DATE(?) as date
            UNION ALL
            SELECT DATE(date, '+1 day')
            FROM dates
            WHERE date < DATE(?)
        )
        SELECT date FROM dates ORDER BY date DESC
    ''', (start_date, end_date))
    all_dates = [row[0] for row in cursor.fetchall()]

    # 合并数据，补全无数据的日期
    stats_dict = {row['date']: dict(row) for row in rows}
    stats = []
    for date in all_dates:
        if date in stats_dict:
            stats.append(stats_dict[date])
        else:
            stats.append({
                'date': date,
                'image_count': 0,
                'video_count': 0,
                'video_duration': 0,
                'enhance_count': 0,
                'user_count': 0,
                'video_tokens': 0
            })

    conn.close()
    return stats


def get_task_status_report(start_date=None, end_date=None):
    """
    获取任务状态统计（成功率、失败率分析）

    返回: {
        'image': {'success': int, 'failed': int, 'total': int, 'success_rate': float},
        'video': {'success': int, 'failed': int, 'pending': int, 'total': int, 'success_rate': float},
        'omni_video': {'success': int, 'failed': int, 'queued': int, 'total': int, 'success_rate': float},
        'enhance': {'success': int, 'failed': int, 'queued': int, 'total': int, 'success_rate': float}
    }
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    date_condition = ""
    date_params = []
    if start_date and end_date:
        date_condition = "AND DATE(created_at) BETWEEN ? AND ?"
        date_params = [start_date, end_date]

    result = {}

    # 图片生成状态统计
    query = f'''
        SELECT status, COUNT(*) as count
        FROM generation_records
        WHERE 1=1 {date_condition}
        GROUP BY status
    '''
    cursor.execute(query, date_params)
    rows = cursor.fetchall()
    image_stats = {'success': 0, 'failed': 0, 'total': 0}
    for row in rows:
        status = row[0] or 'success'
        count = row[1]
        if status == 'success':
            image_stats['success'] = count
        else:
            image_stats['failed'] += count
        image_stats['total'] += count
    image_stats['success_rate'] = round(image_stats['success'] / max(image_stats['total'], 1) * 100, 2)
    result['image'] = image_stats

    # 视频任务状态统计
    query = f'''
        SELECT status, COUNT(*) as count
        FROM video_tasks
        WHERE 1=1 {date_condition}
        GROUP BY status
    '''
    cursor.execute(query, date_params)
    rows = cursor.fetchall()
    video_stats = {'success': 0, 'failed': 0, 'pending': 0, 'total': 0}
    for row in rows:
        status = row[0] or 'pending'
        count = row[1]
        if status in ('success', 'completed', 'done'):
            video_stats['success'] += count
        elif status in ('failed', 'error'):
            video_stats['failed'] += count
        else:
            video_stats['pending'] += count
        video_stats['total'] += count
    video_stats['success_rate'] = round(video_stats['success'] / max(video_stats['total'], 1) * 100, 2)
    result['video'] = video_stats

    # 全能视频任务状态统计
    query = f'''
        SELECT status, COUNT(*) as count
        FROM omni_video_tasks
        WHERE 1=1 {date_condition}
        GROUP BY status
    '''
    cursor.execute(query, date_params)
    rows = cursor.fetchall()
    omni_stats = {'success': 0, 'failed': 0, 'queued': 0, 'total': 0}
    for row in rows:
        status = row[0] or 'queued'
        count = row[1]
        # 成功状态包括: success, succeeded, completed, done, finished
        if status in ('success', 'succeeded', 'completed', 'done', 'finished'):
            omni_stats['success'] += count
        elif status in ('failed', 'error', 'cancelled', 'canceled', 'expired'):
            omni_stats['failed'] += count
        else:
            # queued, running, pending 等都归为排队/处理中
            omni_stats['queued'] += count
        omni_stats['total'] += count
    omni_stats['success_rate'] = round(omni_stats['success'] / max(omni_stats['total'], 1) * 100, 2)
    result['omni_video'] = omni_stats

    # 视频增强任务状态统计
    query = f'''
        SELECT status, COUNT(*) as count
        FROM video_enhance_tasks
        WHERE 1=1 {date_condition}
        GROUP BY status
    '''
    cursor.execute(query, date_params)
    rows = cursor.fetchall()
    enhance_stats = {'success': 0, 'failed': 0, 'queued': 0, 'total': 0}
    for row in rows:
        status = row[0] or 'queued'
        count = row[1]
        # 成功状态包括: success, succeeded, completed, done, finished
        if status in ('success', 'succeeded', 'completed', 'done', 'finished'):
            enhance_stats['success'] += count
        elif status in ('failed', 'error', 'cancelled', 'canceled', 'expired'):
            enhance_stats['failed'] += count
        else:
            # queued, running, pending 等都归为排队/处理中
            enhance_stats['queued'] += count
        enhance_stats['total'] += count
    enhance_stats['success_rate'] = round(enhance_stats['success'] / max(enhance_stats['total'], 1) * 100, 2)
    result['enhance'] = enhance_stats

    conn.close()
    return result


def get_token_usage_report(start_date=None, end_date=None):
    """
    获取Token消耗统计（只统计全能视频生成token）

    返回: {
        'total_tokens': int,  # 总消耗（所有时间）
        'today_tokens': int,  # 今日消耗
        'last7days_tokens': int,  # 近7日消耗
        'period_tokens': int,  # 所选时间范围消耗
        'video_generation_tokens': int,  # 全能视频生成(omni_video_tasks)
        'daily_tokens': List[{date: str, video_tokens: int}],
        'user_tokens': List[{user_id: int, username: str, video_tokens: int}]
    }
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    today = datetime.now().strftime('%Y-%m-%d')
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    last7days_start = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

    # 确定日期范围
    if not start_date or not end_date:
        end_date = yesterday
        start_date = last7days_start

    # 总消耗（所有时间）
    cursor.execute('SELECT COALESCE(SUM(token_usage), 0) FROM omni_video_tasks')
    total_tokens_all = cursor.fetchone()[0] or 0

    # 今日消耗
    cursor.execute('SELECT COALESCE(SUM(token_usage), 0) FROM omni_video_tasks WHERE DATE(created_at) = ?', (today,))
    today_tokens = cursor.fetchone()[0] or 0

    # 近7日消耗（不含今天）
    cursor.execute('SELECT COALESCE(SUM(token_usage), 0) FROM omni_video_tasks WHERE DATE(created_at) BETWEEN ? AND ?', (last7days_start, yesterday))
    last7days_tokens = cursor.fetchone()[0] or 0

    # 所选时间范围消耗（omni_video_tasks）
    cursor.execute('''
        SELECT COALESCE(SUM(token_usage), 0) as tokens
        FROM omni_video_tasks
        WHERE DATE(created_at) BETWEEN ? AND ?
    ''', (start_date, end_date))
    period_tokens = cursor.fetchone()[0] or 0

    video_generation_tokens = period_tokens

    # 每日Token消耗（只统计全能视频）
    cursor.execute('''
        SELECT DATE(created_at) as date, SUM(COALESCE(token_usage, 0)) as video_tokens
        FROM omni_video_tasks
        WHERE DATE(created_at) BETWEEN ? AND ?
        GROUP BY DATE(created_at)
    ''', (start_date, end_date))
    daily_tokens = [{'date': row[0], 'video_tokens': row[1]} for row in cursor.fetchall()]

    # 用户Token消耗（只统计全能视频）
    cursor.execute('''
        SELECT user_id, SUM(COALESCE(token_usage, 0)) as video_tokens
        FROM omni_video_tasks
        WHERE DATE(created_at) BETWEEN ? AND ?
        GROUP BY user_id
    ''', (start_date, end_date))
    video_user = {row[0]: row[1] for row in cursor.fetchall()}

    # 获取所有用户
    cursor.execute('SELECT id, username FROM users')
    users = cursor.fetchall()

    user_tokens = []
    for user in users:
        user_id = user[0]
        username = user[1]
        vt = video_user.get(user_id, 0)
        user_tokens.append({
            'user_id': user_id,
            'username': username,
            'video_tokens': vt
        })

    # 按消耗排序
    user_tokens.sort(key=lambda x: x['video_tokens'], reverse=True)

    conn.close()
    return {
        'total_tokens': total_tokens_all,
        'today_tokens': today_tokens,
        'last7days_tokens': last7days_tokens,
        'period_tokens': period_tokens,
        'video_generation_tokens': video_generation_tokens,
        'daily_tokens': daily_tokens,
        'user_tokens': user_tokens
    }


# ==================== 操作日志函数 ====================

def _ensure_operation_logs_schema():
    """确保操作日志表存在。"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS operation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            project_id INTEGER,
            request_path TEXT NOT NULL,
            request_method TEXT NOT NULL,
            request_params TEXT,
            response_status INTEGER,
            response_summary TEXT,
            ip_address TEXT,
            duration_ms INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        '''
    )
    cursor.execute(
        'CREATE INDEX IF NOT EXISTS idx_operation_logs_user_created '
        'ON operation_logs(user_id, created_at DESC)'
    )
    cursor.execute(
        'CREATE INDEX IF NOT EXISTS idx_operation_logs_path_created '
        'ON operation_logs(request_path, created_at DESC)'
    )
    cursor.execute(
        'CREATE INDEX IF NOT EXISTS idx_operation_logs_project_created '
        'ON operation_logs(project_id, created_at DESC)'
    )

    conn.commit()
    conn.close()


def save_operation_log(data: dict) -> int | None:
    """
    保存操作日志。

    Args:
        data: 包含以下字段的字典：
            - user_id: 用户ID（可选）
            - username: 用户名（可选）
            - project_id: 项目ID（可选）
            - request_path: API路径
            - request_method: HTTP方法
            - request_params: 请求参数（dict，可选）
            - response_status: 响应状态码
            - response_summary: 响应摘要（可选）
            - ip_address: 客户端IP（可选）
            - duration_ms: 耗时毫秒（可选）

    Returns:
        日志记录ID，失败时返回None
    """
    try:
        _ensure_operation_logs_schema()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        params_json = json.dumps(data.get('request_params') or {}, ensure_ascii=False)

        cursor.execute(
            '''
            INSERT INTO operation_logs
            (user_id, username, project_id, request_path, request_method,
             request_params, response_status, response_summary, ip_address,
             duration_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                data.get('user_id'),
                data.get('username'),
                data.get('project_id'),
                data.get('request_path'),
                data.get('request_method'),
                params_json,
                data.get('response_status'),
                data.get('response_summary'),
                data.get('ip_address'),
                data.get('duration_ms'),
                now,
            ),
        )

        log_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return log_id

    except Exception as e:
        # 日志写入失败不应影响主流程，静默处理
        print(f"[operation_log] save failed: {e}")
        return None


def get_operation_logs(
    user_id: int | None = None,
    project_id: int | None = None,
    path_prefix: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """
    查询操作日志。

    Args:
        user_id: 按用户ID筛选（可选）
        project_id: 按项目ID筛选（可选）
        path_prefix: 按路径前缀筛选（可选）
        limit: 返回数量限制，最大500
        offset: 偏移量

    Returns:
        操作日志列表
    """
    _ensure_operation_logs_schema()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    limit = min(limit, 500)  # 限制最大返回量

    query = 'SELECT * FROM operation_logs WHERE 1=1'
    params = []

    if user_id is not None:
        query += ' AND user_id = ?'
        params.append(user_id)
    if project_id is not None:
        query += ' AND project_id = ?'
        params.append(project_id)
    if path_prefix:
        query += ' AND request_path LIKE ?'
        params.append(f'{path_prefix}%')

    query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    logs = [dict(row) for row in rows]

    # 解析JSON字段
    for log in logs:
        try:
            log['request_params'] = json.loads(log.get('request_params') or '{}')
        except Exception:
            log['request_params'] = {}

    conn.close()
    return logs


def count_operation_logs(
    user_id: int | None = None,
    project_id: int | None = None,
    path_prefix: str | None = None,
) -> int:
    """
    统计操作日志数量。

    Args:
        user_id: 按用户ID筛选（可选）
        project_id: 按项目ID筛选（可选）
        path_prefix: 按路径前缀筛选（可选）

    Returns:
        日志数量
    """
    _ensure_operation_logs_schema()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    query = 'SELECT COUNT(*) FROM operation_logs WHERE 1=1'
    params = []

    if user_id is not None:
        query += ' AND user_id = ?'
        params.append(user_id)
    if project_id is not None:
        query += ' AND project_id = ?'
        params.append(project_id)
    if path_prefix:
        query += ' AND request_path LIKE ?'
        params.append(f'{path_prefix}%')

    cursor.execute(query, params)
    count = cursor.fetchone()[0]

    conn.close()
    return count


def delete_old_operation_logs(days: int = 30) -> int:
    """
    删除指定天数之前的操作日志。

    Args:
        days: 保留天数，默认30天

    Returns:
        删除的记录数量
    """
    _ensure_operation_logs_schema()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')

    cursor.execute('DELETE FROM operation_logs WHERE created_at < ?', (cutoff_date,))
    deleted = cursor.rowcount

    conn.commit()
    conn.close()
    return deleted


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
