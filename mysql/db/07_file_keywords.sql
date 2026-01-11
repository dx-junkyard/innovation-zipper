CREATE TABLE IF NOT EXISTS file_keywords (
    id INT AUTO_INCREMENT PRIMARY KEY,
    file_id INT NOT NULL,
    keyword VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES user_files(id) ON DELETE CASCADE,
    UNIQUE KEY unique_file_keyword (file_id, keyword)
);
