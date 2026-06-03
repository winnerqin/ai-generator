-- Add external batch API fields for omni video tasks.
-- Usage: mysql -u user -p ai_generator < scripts/migrate_omni_external_api_mysql.sql

SET @schema_name = DATABASE();

SET @sql = IF(
    (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'omni_video_tasks' AND column_name = 'batch_id') = 0,
    'ALTER TABLE omni_video_tasks ADD COLUMN batch_id VARCHAR(255)',
    'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF(
    (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'omni_video_tasks' AND column_name = 'client_request_id') = 0,
    'ALTER TABLE omni_video_tasks ADD COLUMN client_request_id VARCHAR(255)',
    'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF(
    (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'omni_video_tasks' AND column_name = 'source') = 0,
    'ALTER TABLE omni_video_tasks ADD COLUMN source VARCHAR(64)',
    'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF(
    (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'omni_video_tasks' AND column_name = 'callback_url') = 0,
    'ALTER TABLE omni_video_tasks ADD COLUMN callback_url TEXT',
    'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF(
    (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'omni_video_tasks' AND column_name = 'external_meta_json') = 0,
    'ALTER TABLE omni_video_tasks ADD COLUMN external_meta_json LONGTEXT',
    'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF(
    (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = @schema_name AND table_name = 'omni_video_tasks' AND index_name = 'idx_omni_video_tasks_batch_id') = 0,
    'ALTER TABLE omni_video_tasks ADD INDEX idx_omni_video_tasks_batch_id (batch_id)',
    'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF(
    (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = @schema_name AND table_name = 'omni_video_tasks' AND index_name = 'idx_omni_video_tasks_client_request') = 0,
    'ALTER TABLE omni_video_tasks ADD INDEX idx_omni_video_tasks_client_request (user_id, client_request_id)',
    'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

CREATE TABLE IF NOT EXISTS external_api_keys (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    project_id INT NULL,
    name VARCHAR(255),
    key_hash CHAR(64) NOT NULL UNIQUE,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_used_at DATETIME NULL,
    INDEX idx_external_api_keys_user_status (user_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
