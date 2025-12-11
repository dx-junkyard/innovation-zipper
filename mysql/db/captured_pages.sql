CREATE TABLE IF NOT EXISTS captured_pages (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id VARCHAR(36) NOT NULL,
    url TEXT,
    title TEXT,
    content MEDIUMTEXT,
    screenshot_url TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_captured_pages_user (user_id, created_at),
    CONSTRAINT fk_captured_pages_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
