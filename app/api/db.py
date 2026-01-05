import json
from typing import Any, Dict, List, Optional

import mysql.connector
from mysql.connector import errorcode

from config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT

class DBClient:
    def __init__(self):
        self.config = {
            'host': DB_HOST,
            'user': DB_USER,
            'password': DB_PASSWORD,
            'database': DB_NAME,
            'port': DB_PORT,
            'charset': 'utf8mb4'
        }

    def create_user(self, line_user_id=None):
        conn = None
        cursor = None
        import uuid
        user_id = str(uuid.uuid4())
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (id, line_user_id) VALUES (%s,%s)",
                (user_id, line_user_id),
            )
            conn.commit()
        except mysql.connector.Error as err:
            if err.errno == errorcode.ER_DUP_ENTRY:
                cursor.execute(
                    "SELECT id FROM users WHERE line_user_id=%s",
                    (line_user_id,),
                )
                row = cursor.fetchone()
                user_id = row[0] if row else user_id
            else:
                print(f"[✗] MySQL Error: {err}")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
        return user_id

    def get_file_info_by_uuid(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves file info by UUID (extracted from file_path).
        """
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor(dictionary=True)
            # Search by file path pattern since UUID is not a column
            query = "SELECT id, user_id, file_path, is_public, title FROM user_files WHERE file_path LIKE %s LIMIT 1"
            cursor.execute(query, (f"%/{file_id}.pdf",))
            return cursor.fetchone()
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error in get_file_info_by_uuid: {err}")
            return None
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def check_file_exists(self, user_id: str, file_hash: str) -> bool:
        """
        Check if the file already exists for the user or is public.
        """
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor()
            query = """
                SELECT id FROM user_files
                WHERE (user_id = %s AND file_hash = %s)
                   OR (is_public = 1 AND file_hash = %s)
                LIMIT 1
            """
            cursor.execute(query, (user_id, file_hash, file_hash))
            return cursor.fetchone() is not None
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error in check_file_exists: {err}")
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def insert_user_file(self, user_id: str, file_name: str, file_path: str, title: str, file_hash: str, is_public: bool) -> Optional[int]:
        """
        Inserts a record for an uploaded user file and returns the ID.
        """
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor()
            query = "INSERT INTO user_files (user_id, file_name, file_path, title, file_hash, is_public) VALUES (%s, %s, %s, %s, %s, %s)"
            cursor.execute(query, (user_id, file_name, file_path, title, file_hash, int(is_public)))
            conn.commit()
            return cursor.lastrowid
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error: {err}")
            return None
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def insert_message(self, user_id, role, message):
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor()

            query = """
                INSERT INTO user_messages (user_id, role, message)
                VALUES (%s, %s, %s)
            """
            values = (user_id, role, message)
            cursor.execute(query, values)
            conn.commit()

            print(f"[✓] Inserted user_messages for user_id={user_id} role={role}")
            return cursor.lastrowid

        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error: {err}")
            return None
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def get_user_messages(self, user_id, limit=10):
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT user_id, role, message
                FROM user_messages
                WHERE user_id = %s
                ORDER BY id DESC
                LIMIT %s
            """
            cursor.execute(query, (user_id, limit))
            messages = cursor.fetchall()
            return messages
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error: {err}")
            return []
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def get_innovation_history(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        イノベーションモード（構造分解など）が行われた分析ログを取得する。
        """
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor(dictionary=True)
            # MySQL 5.7/8.0のJSON関数を使用してフィルタリング
            query = """
                SELECT id, created_at, analysis
                FROM user_message_analyses
                WHERE user_id = %s
                  AND JSON_EXTRACT(analysis, '$.structural_analysis') IS NOT NULL
                ORDER BY id DESC
                LIMIT %s
            """
            cursor.execute(query, (user_id, limit))
            rows = cursor.fetchall()

            results = []
            for row in rows:
                analysis_data = json.loads(row["analysis"]) if isinstance(row["analysis"], str) else row["analysis"]
                results.append({
                    "id": row["id"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "data": analysis_data
                })
            return results
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error: {err}")
            return []
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def get_recent_conversation(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT id, user_id, role, message, created_at
                FROM (
                    SELECT id, user_id, role, message, created_at
                    FROM user_messages
                    WHERE user_id = %s
                    ORDER BY id DESC
                    LIMIT %s
                ) AS recent
                ORDER BY id ASC
            """
            cursor.execute(query, (user_id, limit))
            rows = cursor.fetchall()
            for row in rows:
                if row.get("created_at"):
                    row["created_at"] = row["created_at"].isoformat()
            return rows
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error: {err}")
            return []
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def get_user_state(self, user_id: str) -> Optional[Dict[str, Any]]:
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor()
            query = """
                SELECT interest_profile, active_hypotheses
                FROM user_states
                WHERE user_id = %s
            """
            cursor.execute(query, (user_id,))
            row = cursor.fetchone()
            if not row:
                return None
            interest_profile = json.loads(row[0]) if row[0] else None
            active_hypotheses = json.loads(row[1]) if row[1] else None
            return {
                "interest_profile": interest_profile,
                "active_hypotheses": active_hypotheses,
            }
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error: {err}")
            return None
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def upsert_user_state(self, user_id: str, interest_profile: Dict[str, Any], active_hypotheses: Dict[str, Any]) -> None:
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor()
            query = """
                INSERT INTO user_states (user_id, interest_profile, active_hypotheses)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    interest_profile = VALUES(interest_profile),
                    active_hypotheses = VALUES(active_hypotheses)
            """
            cursor.execute(
                query,
                (
                    user_id,
                    json.dumps(interest_profile, ensure_ascii=False),
                    json.dumps(active_hypotheses, ensure_ascii=False),
                ),
            )
            conn.commit()
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error: {err}")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def save_captured_page(self, user_id: str, url: str, title: str, content: str, screenshot_url: Optional[str] = None) -> int:
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor()
            query = """
                INSERT INTO captured_pages (user_id, url, title, content, screenshot_url)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(query, (user_id, url, title, content, screenshot_url))
            conn.commit()
            return cursor.lastrowid
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error: {err}")
            return None
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def get_latest_captured_page(self, user_id: str) -> Optional[Dict[str, Any]]:
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT * FROM captured_pages
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT 1
            """
            cursor.execute(query, (user_id,))
            row = cursor.fetchone()
            return row
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error: {err}")
            return None
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def record_analysis(self, user_id: str, user_message_id: int, analysis: Dict[str, Any]) -> None:
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor()
            query = """
                INSERT INTO user_message_analyses (user_id, user_message_id, analysis)
                VALUES (%s, %s, %s)
            """
            cursor.execute(
                query,
                (
                    user_id,
                    user_message_id,
                    json.dumps(analysis, ensure_ascii=False),
                ),
            )
            conn.commit()
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error: {err}")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def create_service_catalog_table(self):
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor()
            query = """
                CREATE TABLE IF NOT EXISTS service_catalog (
                    id VARCHAR(255) PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    target TEXT,
                    target_labels JSON,
                    conditions TEXT,
                    service_content TEXT,
                    service_labels JSON,
                    url JSON,
                    updated_at VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            cursor.execute(query)
            conn.commit()
            print("[✓] Table service_catalog created or already exists.")
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error: {err}")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def insert_service_catalog_entry(self, entry: Dict[str, Any]):
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor()
            query = """
                INSERT INTO service_catalog (
                    id, title, target, target_labels, conditions,
                    service_content, service_labels, url, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    title = VALUES(title),
                    target = VALUES(target),
                    target_labels = VALUES(target_labels),
                    conditions = VALUES(conditions),
                    service_content = VALUES(service_content),
                    service_labels = VALUES(service_labels),
                    url = VALUES(url),
                    updated_at = VALUES(updated_at)
            """
            # Generate a deterministic ID if not present
            import hashlib
            if "id" not in entry:
                unique_str = entry.get("タイトル", "") + entry.get("URL", {}).get("items", "")
                entry_id = hashlib.md5(unique_str.encode()).hexdigest()
            else:
                entry_id = entry["id"]

            values = (
                entry_id,
                entry.get("タイトル"),
                entry.get("対象者"),
                json.dumps(entry.get("対象者ラベル", []), ensure_ascii=False),
                entry.get("条件・申し込み方法"),
                entry.get("サービス内容"),
                json.dumps(entry.get("サービスラベル", []), ensure_ascii=False),
                json.dumps(entry.get("URL", {}), ensure_ascii=False),
                entry.get("更新日") or entry.get("公開日")
            )
            cursor.execute(query, values)
            conn.commit()
            return entry_id
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error: {err}")
            return None
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def get_service_by_id(self, service_id: str) -> Optional[Dict[str, Any]]:
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor(dictionary=True)
            query = "SELECT * FROM service_catalog WHERE id = %s"
            cursor.execute(query, (service_id,))
            row = cursor.fetchone()
            if row:
                if row.get("target_labels"):
                    row["target_labels"] = json.loads(row["target_labels"])
                if row.get("service_labels"):
                    row["service_labels"] = json.loads(row["service_labels"])
                if row.get("url"):
                    row["url"] = json.loads(row["url"])
            return row
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error: {err}")
            return None
        finally:
            if conn:
                conn.close()

    def truncate_service_catalog(self):
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor()
            query = "TRUNCATE TABLE service_catalog"
            cursor.execute(query)
            conn.commit()
            print("[✓] Table service_catalog truncated.")
            return True
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error: {err}")
            return False
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def add_file_categories(self, file_id: int, categories: List[str], conn=None, cursor=None) -> bool:
        """Adds categories to a file."""
        if not categories:
            return True

        # If no connection provided, create new (safe fallback, but transactional use is preferred)
        local_conn = False
        if not conn:
            try:
                conn = mysql.connector.connect(**self.config)
                cursor = conn.cursor()
                local_conn = True
            except mysql.connector.Error as err:
                print(f"[✗] MySQL Error in add_file_categories connection: {err}")
                return False

        try:
            query = "INSERT IGNORE INTO file_categories (file_id, category_name) VALUES (%s, %s)"
            data = [(file_id, cat) for cat in categories]
            cursor.executemany(query, data)
            if local_conn:
                conn.commit()
            return True
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error in add_file_categories: {err}")
            return False
        finally:
            if local_conn:
                if cursor: cursor.close()
                if conn: conn.close()

    def delete_file_categories(self, file_id: int, conn=None, cursor=None) -> bool:
        """Deletes all categories for a file."""
        local_conn = False
        if not conn:
            try:
                conn = mysql.connector.connect(**self.config)
                cursor = conn.cursor()
                local_conn = True
            except mysql.connector.Error as err:
                print(f"[✗] MySQL Error in delete_file_categories connection: {err}")
                return False

        try:
            query = "DELETE FROM file_categories WHERE file_id = %s"
            cursor.execute(query, (file_id,))
            if local_conn:
                conn.commit()
            return True
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error in delete_file_categories: {err}")
            return False
        finally:
            if local_conn:
                if cursor: cursor.close()
                if conn: conn.close()

    def update_file_category(self, file_id: int, categories: List[str], is_verified: bool = True) -> bool:
        """
        Updates categories for a file by deleting existing ones and inserting new ones.
        Also marks the file as verified.
        Executes within a single transaction.
        """
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            # Start transaction (autocommit is False by default in mysql-connector if using transactions,
            # but explicit start_transaction ensures it)
            conn.start_transaction()
            cursor = conn.cursor()

            # 1. Update verification status
            query_update = "UPDATE user_files SET is_verified = %s WHERE id = %s"
            cursor.execute(query_update, (is_verified, file_id))

            # 2. Update categories (Delete & Insert)
            # Pass conn/cursor to reuse the transaction
            if not self.delete_file_categories(file_id, conn=conn, cursor=cursor):
                conn.rollback()
                return False

            if not self.add_file_categories(file_id, categories, conn=conn, cursor=cursor):
                conn.rollback()
                return False

            conn.commit()
            return True
        except mysql.connector.Error as err:
            if conn:
                conn.rollback()
            print(f"[✗] MySQL Error in update_file_category: {err}")
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def update_capture_category(self, capture_id: int, category: str, is_verified: bool = True) -> bool:
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor()
            query = "UPDATE captured_pages SET category = %s, is_verified = %s WHERE id = %s"
            cursor.execute(query, (category, is_verified, capture_id))
            conn.commit()
            return True
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error in update_capture_category: {err}")
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def get_all_user_contents(self, user_id: str) -> List[Dict[str, Any]]:
        conn = None
        cursor = None
        contents = []
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor(dictionary=True)

            # 1. Files (with aggregated categories)
            # GROUP_CONCAT returns a comma-separated string of categories.
            # Using LEFT JOIN to ensure files without categories are still returned.
            query_files = """
                SELECT f.id, f.title, f.is_verified, f.created_at, 'file' as type, f.file_name as source,
                       GROUP_CONCAT(fc.category_name) as category
                FROM user_files f
                LEFT JOIN file_categories fc ON f.id = fc.file_id
                WHERE f.user_id = %s
                GROUP BY f.id
            """
            cursor.execute(query_files, (user_id,))
            files = cursor.fetchall()

            # Post-process files: convert 'category' string to list
            for f in files:
                cat_str = f.get("category")
                if cat_str:
                    f["category"] = cat_str.split(",")
                else:
                    f["category"] = []

            contents.extend(files)

            # 2. Captured Pages
            # Keeping as single category but wrapping in list for consistency if needed by UI
            # or UI handles both list and string.
            # To unify, we'll convert to list.
            query_captures = """
                SELECT id, title, category, is_verified, created_at, 'capture' as type, url as source
                FROM captured_pages
                WHERE user_id = %s
            """
            cursor.execute(query_captures, (user_id,))
            captures = cursor.fetchall()

            for c in captures:
                cat = c.get("category")
                if cat:
                    c["category"] = [cat]
                else:
                    c["category"] = []

            contents.extend(captures)

            # Sort by created_at DESC
            contents.sort(key=lambda x: x['created_at'], reverse=True)

            # Format datetime
            for item in contents:
                if item.get('created_at'):
                    item['created_at'] = item['created_at'].isoformat()

            return contents
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error in get_all_user_contents: {err}")
            return []
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
