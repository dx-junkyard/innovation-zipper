CREATE TABLE IF NOT EXISTS user_message_analyses (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id VARCHAR(36) NOT NULL,
    user_message_id BIGINT UNSIGNED NOT NULL,
    analysis JSON NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_user_message_analyses_user (user_id, created_at),
    CONSTRAINT fk_user_message_analyses_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_user_message_analyses_message FOREIGN KEY (user_message_id) REFERENCES user_messages(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
