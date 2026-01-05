CREATE TABLE IF NOT EXISTS user_files (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_path VARCHAR(255) NOT NULL,
    title VARCHAR(255) NOT NULL,
    file_hash VARCHAR(64) NOT NULL, -- SHA-256ハッシュ値
    is_public TINYINT(1) DEFAULT 0,  -- 0:非公開, 1:公開
    -- category VARCHAR(100) DEFAULT 'Uncategorized', -- Deprecated: Use file_categories table
    is_verified BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_user_files_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_hash (user_id, file_hash) -- ユーザーごとの重複チェックを高速化
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
