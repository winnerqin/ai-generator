-- Add recharge_orders table for user-center balance recharge.
-- Usage: mysql -u user -p ai_generator < scripts/migrate_recharge_orders_mysql.sql

CREATE TABLE IF NOT EXISTS recharge_orders (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_no VARCHAR(64) NOT NULL,
    user_id INT NOT NULL,
    username VARCHAR(255),
    amount_cent BIGINT NOT NULL,
    currency_code VARCHAR(8) NOT NULL DEFAULT 'CNY',
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    payment_channel VARCHAR(32) NOT NULL DEFAULT 'wechat_native',
    payment_scene VARCHAR(32) NOT NULL DEFAULT 'user_center',
    subject VARCHAR(255),
    description VARCHAR(512),
    payment_center_order_no VARCHAR(128),
    channel_trade_no VARCHAR(128),
    qr_code_url LONGTEXT,
    qr_code_img_url LONGTEXT,
    expire_at DATETIME NULL,
    paid_at DATETIME NULL,
    closed_at DATETIME NULL,
    fail_reason VARCHAR(512),
    request_payload_json LONGTEXT,
    callback_payload_json LONGTEXT,
    metadata_json LONGTEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_recharge_orders_order_no (order_no),
    INDEX idx_recharge_orders_user_created (user_id, created_at DESC),
    INDEX idx_recharge_orders_status_created (status, created_at DESC),
    INDEX idx_recharge_orders_payment_center (payment_center_order_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
