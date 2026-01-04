CREATE TABLE IF NOT EXISTS file_categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    file_id INT NOT NULL,
    category_name VARCHAR(100) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_file_categories_file FOREIGN KEY (file_id) REFERENCES user_files(id) ON DELETE CASCADE,
    UNIQUE KEY idx_file_category_unique (file_id, category_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
