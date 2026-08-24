-- Add indexes used by the shared Wan/Seedance task queue.
-- Usage: mysql -u user -p ai_generator < scripts/migrate_wan_video_mysql.sql

SET @schema_name = DATABASE();

SET @sql = IF(
    (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = @schema_name AND table_name = 'omni_video_tasks' AND index_name = 'idx_omni_video_tasks_source_status_created') = 0,
    'ALTER TABLE omni_video_tasks ADD INDEX idx_omni_video_tasks_source_status_created (source, status, created_at DESC)',
    'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF(
    (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = @schema_name AND table_name = 'omni_video_tasks' AND index_name = 'idx_omni_video_tasks_user_project_source_created') = 0,
    'ALTER TABLE omni_video_tasks ADD INDEX idx_omni_video_tasks_user_project_source_created (user_id, project_id, source, created_at DESC)',
    'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
