-- MySQL 建表脚本（与当前 SQLite 表结构对应）
-- 使用前请创建数据库: CREATE DATABASE ai_generator CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- 执行: mysql -u user -p ai_generator < schema_mysql.sql

SET NAMES utf8mb4;

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_login DATETIME NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 生成记录表
CREATE TABLE IF NOT EXISTS generation_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    project_id INT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    prompt TEXT NOT NULL,
    negative_prompt TEXT,
    aspect_ratio VARCHAR(64),
    resolution VARCHAR(64),
    width INT,
    height INT,
    num_images INT,
    seed INT,
    steps INT,
    sample_images TEXT,
    image_path TEXT NOT NULL,
    filename VARCHAR(512) NOT NULL,
    batch_id VARCHAR(255),
    status VARCHAR(64) DEFAULT 'success',
    INDEX idx_user_created (user_id, created_at DESC),
    INDEX idx_batch_id (batch_id),
    INDEX idx_records_user_project_created (user_id, project_id, created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 项目表
CREATE TABLE IF NOT EXISTS projects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    owner_id INT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 用户-项目关联
CREATE TABLE IF NOT EXISTS user_projects (
    user_id INT NOT NULL,
    project_id INT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_project (user_id, project_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 剧本提示词模板
CREATE TABLE IF NOT EXISTS script_templates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    project_id INT NULL,
    name VARCHAR(255) NOT NULL,
    prompt TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_project_name (user_id, project_id, name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 剧本保存记录
CREATE TABLE IF NOT EXISTS script_saves (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    project_id INT NULL,
    title VARCHAR(512) NOT NULL,
    novel_text LONGTEXT,
    prompt TEXT,
    min_seconds INT,
    max_seconds INT,
    script_text LONGTEXT,
    episodes_json LONGTEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 剧本分集记录
CREATE TABLE IF NOT EXISTS script_episode_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    script_id INT NOT NULL,
    user_id INT NOT NULL,
    project_id INT NULL,
    episode_index INT,
    title VARCHAR(512),
    duration_seconds INT,
    summary TEXT,
    content_url TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 分镜保存记录
CREATE TABLE IF NOT EXISTS storyboard_saves (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    project_id INT NULL,
    title VARCHAR(512) NOT NULL,
    script_text LONGTEXT,
    prompt TEXT,
    storyboard_json LONGTEXT,
    storyboard_text LONGTEXT,
    series_id INT NULL,
    version INT DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 分镜分集记录
CREATE TABLE IF NOT EXISTS storyboard_episode_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    script_episode_id INT NOT NULL,
    user_id INT NOT NULL,
    project_id INT NULL,
    prompt TEXT,
    storyboard_json LONGTEXT,
    storyboard_text LONGTEXT,
    images_json LONGTEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 生成任务记录
CREATE TABLE IF NOT EXISTS generation_tasks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    project_id INT NULL,
    task_type VARCHAR(64) NOT NULL,
    status VARCHAR(64) NOT NULL,
    progress INT DEFAULT 0,
    payload_json LONGTEXT,
    result_json LONGTEXT,
    error TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 人物库 / 场景库
CREATE TABLE IF NOT EXISTS person_library (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    project_id INT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    filename VARCHAR(512) NOT NULL,
    url TEXT NOT NULL,
    meta TEXT,
    INDEX idx_person_user_project_created (user_id, project_id, created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS scene_library (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    project_id INT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    filename VARCHAR(512) NOT NULL,
    url TEXT NOT NULL,
    meta TEXT,
    INDEX idx_scene_user_project_created (user_id, project_id, created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 图片库 / 视频库
CREATE TABLE IF NOT EXISTS image_library (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    project_id INT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    filename VARCHAR(512) NOT NULL,
    url TEXT NOT NULL,
    meta TEXT,
    INDEX idx_image_user_project_created (user_id, project_id, created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS video_library (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    project_id INT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    filename VARCHAR(512) NOT NULL,
    url TEXT NOT NULL,
    meta TEXT,
    INDEX idx_video_user_project_created (user_id, project_id, created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 视频任务表
CREATE TABLE IF NOT EXISTS video_tasks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    task_id VARCHAR(255) NOT NULL,
    project_id INT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    status VARCHAR(64) DEFAULT 'pending',
    prompt TEXT,
    generate_type VARCHAR(64),
    resolution VARCHAR(64),
    ratio VARCHAR(64),
    duration INT,
    seed INT,
    camera_fixed TINYINT DEFAULT 0,
    watermark TINYINT DEFAULT 0,
    generate_audio TINYINT DEFAULT 0,
    return_last_frame TINYINT DEFAULT 0,
    first_frame_url TEXT,
    last_frame_url TEXT,
    reference_image_urls TEXT,
    video_url TEXT,
    last_frame_image_url TEXT,
    token INT,
    usage TEXT,
    content LONGTEXT,
    error_message TEXT,
    UNIQUE KEY uk_task_id (task_id),
    INDEX idx_video_tasks_user_project_created (user_id, project_id, created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
