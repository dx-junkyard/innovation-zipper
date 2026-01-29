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
            cursor.execute(query, (f"%{file_id}.pdf",))
            return cursor.fetchone()
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error in get_file_info_by_uuid: {err}")
            return None
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def get_file_by_id(self, file_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieves file info by Primary Key ID.
        """
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor(dictionary=True)
            query = "SELECT id, user_id, file_path, is_public, title FROM user_files WHERE id = %s"
            cursor.execute(query, (file_id,))
            return cursor.fetchone()
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error in get_file_by_id: {err}")
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

    def add_file_keywords(self, file_id: int, keywords: List[str], conn=None, cursor=None) -> bool:
        """Adds keywords to a file."""
        if not keywords:
            return True

        local_conn = False
        if not conn:
            try:
                conn = mysql.connector.connect(**self.config)
                cursor = conn.cursor()
                local_conn = True
            except mysql.connector.Error as err:
                print(f"[✗] MySQL Error in add_file_keywords connection: {err}")
                return False

        try:
            query = "INSERT IGNORE INTO file_keywords (file_id, keyword) VALUES (%s, %s)"
            data = [(file_id, kw) for kw in keywords]
            cursor.executemany(query, data)
            if local_conn:
                conn.commit()
            return True
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error in add_file_keywords: {err}")
            return False
        finally:
            if local_conn:
                if cursor: cursor.close()
                if conn: conn.close()

    def delete_file_keywords(self, file_id: int, conn=None, cursor=None) -> bool:
        """Deletes all keywords for a file."""
        local_conn = False
        if not conn:
            try:
                conn = mysql.connector.connect(**self.config)
                cursor = conn.cursor()
                local_conn = True
            except mysql.connector.Error as err:
                print(f"[✗] MySQL Error in delete_file_keywords connection: {err}")
                return False

        try:
            query = "DELETE FROM file_keywords WHERE file_id = %s"
            cursor.execute(query, (file_id,))
            if local_conn:
                conn.commit()
            return True
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error in delete_file_keywords: {err}")
            return False
        finally:
            if local_conn:
                if cursor: cursor.close()
                if conn: conn.close()

    def update_file_category(self, file_id: int, categories: List[str], is_verified: bool = True, keywords: List[str] = None) -> bool:
        """
        Updates categories and keywords for a file by deleting existing ones and inserting new ones.
        Also marks the file as verified.
        Executes within a single transaction.
        """
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            # Start transaction
            conn.start_transaction()
            cursor = conn.cursor()

            # 1. Update verification status
            query_update = "UPDATE user_files SET is_verified = %s WHERE id = %s"
            cursor.execute(query_update, (is_verified, file_id))

            # 2. Update categories (Delete & Insert)
            if not self.delete_file_categories(file_id, conn=conn, cursor=cursor):
                conn.rollback()
                return False

            if not self.add_file_categories(file_id, categories, conn=conn, cursor=cursor):
                conn.rollback()
                return False

            # 3. Update keywords (Delete & Insert) if provided
            if keywords is not None:
                if not self.delete_file_keywords(file_id, conn=conn, cursor=cursor):
                    conn.rollback()
                    return False
                if not self.add_file_keywords(file_id, keywords, conn=conn, cursor=cursor):
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

            # 1. Files (with aggregated categories and keywords)
            # Using LEFT JOIN to ensure files without categories/keywords are still returned.
            # We need subqueries or separate aggregations to avoid cross-product duplication issues with multiple GROUP_CONCATs
            # But simple GROUP_CONCAT with DISTINCT usually works for simple 1:N relations.

            query_files = """
                SELECT f.id, f.title, f.is_verified, f.created_at, 'file' as type, f.file_name as source,
                       GROUP_CONCAT(DISTINCT fc.category_name) as category,
                       GROUP_CONCAT(DISTINCT fk.keyword) as keywords
                FROM user_files f
                LEFT JOIN file_categories fc ON f.id = fc.file_id
                LEFT JOIN file_keywords fk ON f.id = fk.file_id
                WHERE f.user_id = %s
                GROUP BY f.id
            """
            cursor.execute(query_files, (user_id,))
            files = cursor.fetchall()

            # Post-process files: convert 'category' and 'keywords' strings to list
            for f in files:
                cat_str = f.get("category")
                if cat_str:
                    f["category"] = cat_str.split(",")
                else:
                    f["category"] = []

                kw_str = f.get("keywords")
                if kw_str:
                    f["keywords"] = kw_str.split(",")
                else:
                    f["keywords"] = []

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

    # =========================================================================
    # Team Brain: Hypothesis Management (FR-103, FR-104)
    # =========================================================================

    def create_hypothesis(
        self,
        user_id: str,
        content: str,
        original_experience: str = None,
        tags: List[str] = None,
        parent_hypothesis_id: str = None
    ) -> Optional[str]:
        """
        Create a new hypothesis (1階: Private Layer).
        """
        conn = None
        cursor = None
        import uuid
        import hashlib
        hypothesis_id = str(uuid.uuid4())
        user_hash = hashlib.sha256(user_id.encode()).hexdigest()[:16]
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor()
            query = """
                INSERT INTO hypotheses (
                    id, origin_user_id, origin_user_id_hash, content,
                    original_experience, tags, parent_hypothesis_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (
                hypothesis_id,
                user_id,
                user_hash,
                content,
                original_experience,
                json.dumps(tags or [], ensure_ascii=False),
                parent_hypothesis_id
            ))
            conn.commit()
            print(f"[✓] Created hypothesis {hypothesis_id} for user {user_id}")
            return hypothesis_id
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error in create_hypothesis: {err}")
            return None
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def get_hypothesis(self, hypothesis_id: str) -> Optional[Dict[str, Any]]:
        """Get a single hypothesis by ID."""
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT h.*,
                       (SELECT COUNT(*) FROM hypothesis_verifications hv WHERE hv.hypothesis_id = h.id) as verification_count,
                       (SELECT COUNT(*) FROM hypothesis_verifications hv WHERE hv.hypothesis_id = h.id AND hv.verification_result = 'SUCCESS') as success_count
                FROM hypotheses h
                WHERE h.id = %s
            """
            cursor.execute(query, (hypothesis_id,))
            row = cursor.fetchone()
            if row:
                row = self._format_hypothesis_row(row)
            return row
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error in get_hypothesis: {err}")
            return None
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def get_user_hypotheses(
        self,
        user_id: str,
        status: str = None,
        verification_state: str = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get hypotheses for a user (1階: Private Layer).
        """
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT h.*,
                       (SELECT COUNT(*) FROM hypothesis_verifications hv WHERE hv.hypothesis_id = h.id) as verification_count
                FROM hypotheses h
                WHERE h.origin_user_id = %s
            """
            params = [user_id]
            if status:
                query += " AND h.status = %s"
                params.append(status)
            if verification_state:
                query += " AND h.verification_state = %s"
                params.append(verification_state)
            query += " ORDER BY h.updated_at DESC LIMIT %s"
            params.append(limit)
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [self._format_hypothesis_row(row) for row in rows]
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error in get_user_hypotheses: {err}")
            return []
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def update_hypothesis(
        self,
        hypothesis_id: str,
        user_id: str,
        content: str = None,
        status: str = None,
        verification_state: str = None,
        tags: List[str] = None
    ) -> bool:
        """Update hypothesis (ownership check included)."""
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor()

            # Build dynamic update
            updates = []
            params = []
            if content is not None:
                updates.append("content = %s")
                params.append(content)
            if status is not None:
                updates.append("status = %s")
                params.append(status)
                if status == 'SHARED':
                    updates.append("shared_at = NOW()")
            if verification_state is not None:
                updates.append("verification_state = %s")
                params.append(verification_state)
            if tags is not None:
                updates.append("tags = %s")
                params.append(json.dumps(tags, ensure_ascii=False))

            if not updates:
                return True

            query = f"UPDATE hypotheses SET {', '.join(updates)} WHERE id = %s AND origin_user_id = %s"
            params.extend([hypothesis_id, user_id])
            cursor.execute(query, tuple(params))
            conn.commit()
            return cursor.rowcount > 0
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error in update_hypothesis: {err}")
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def update_hypothesis_verification_state(
        self,
        hypothesis_id: str,
        user_id: str,
        verification_state: str
    ) -> bool:
        """Update hypothesis verification state (FR-104)."""
        return self.update_hypothesis(
            hypothesis_id, user_id,
            verification_state=verification_state
        )

    def _format_hypothesis_row(self, row: Dict) -> Dict:
        """Format hypothesis row for API response."""
        if row.get('tags') and isinstance(row['tags'], str):
            row['tags'] = json.loads(row['tags'])
        if row.get('quality_score') and isinstance(row['quality_score'], str):
            row['quality_score'] = json.loads(row['quality_score'])
        if row.get('created_at'):
            row['created_at'] = row['created_at'].isoformat()
        if row.get('updated_at'):
            row['updated_at'] = row['updated_at'].isoformat()
        if row.get('shared_at'):
            row['shared_at'] = row['shared_at'].isoformat()
        return row

    # =========================================================================
    # Team Brain: Verification Management (FR-301)
    # =========================================================================

    def add_verification(
        self,
        hypothesis_id: str,
        verifier_user_id: str,
        verification_result: str,
        conditions: str = None,
        notes: str = None,
        evidence: Dict = None,
        verifier_team_id: str = None,
        is_differential: bool = False,
        parent_verification_id: int = None
    ) -> Optional[int]:
        """Add a verification result to a hypothesis."""
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor()
            query = """
                INSERT INTO hypothesis_verifications (
                    hypothesis_id, verifier_user_id, verifier_team_id,
                    verification_result, conditions, notes, evidence,
                    is_differential, parent_verification_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (
                hypothesis_id,
                verifier_user_id,
                verifier_team_id,
                verification_result,
                conditions,
                notes,
                json.dumps(evidence, ensure_ascii=False) if evidence else None,
                is_differential,
                parent_verification_id
            ))
            conn.commit()
            return cursor.lastrowid
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error in add_verification: {err}")
            return None
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def get_hypothesis_verifications(
        self,
        hypothesis_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get all verifications for a hypothesis."""
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT hv.*, t.name as team_name
                FROM hypothesis_verifications hv
                LEFT JOIN teams t ON hv.verifier_team_id = t.id
                WHERE hv.hypothesis_id = %s
                ORDER BY hv.created_at DESC
                LIMIT %s
            """
            cursor.execute(query, (hypothesis_id, limit))
            rows = cursor.fetchall()
            for row in rows:
                if row.get('evidence') and isinstance(row['evidence'], str):
                    row['evidence'] = json.loads(row['evidence'])
                if row.get('created_at'):
                    row['created_at'] = row['created_at'].isoformat()
            return rows
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error in get_hypothesis_verifications: {err}")
            return []
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    # =========================================================================
    # Team Brain: Quality Scoring (FR-201)
    # =========================================================================

    def save_quality_score(
        self,
        hypothesis_id: str,
        novelty_score: float,
        specificity_score: float,
        impact_score: float,
        overall_score: float,
        is_high_potential: bool,
        scoring_rationale: str = None
    ) -> Optional[int]:
        """Save quality score for a hypothesis."""
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor()

            # Insert score record
            query = """
                INSERT INTO hypothesis_quality_scores (
                    hypothesis_id, novelty_score, specificity_score,
                    impact_score, overall_score, is_high_potential,
                    scoring_rationale
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (
                hypothesis_id,
                novelty_score,
                specificity_score,
                impact_score,
                overall_score,
                is_high_potential,
                scoring_rationale
            ))
            score_id = cursor.lastrowid

            # Update hypothesis with latest score
            update_query = """
                UPDATE hypotheses
                SET quality_score = %s
                WHERE id = %s
            """
            score_json = json.dumps({
                "novelty": novelty_score,
                "specificity": specificity_score,
                "impact": impact_score,
                "overall": overall_score,
                "is_high_potential": is_high_potential
            })
            cursor.execute(update_query, (score_json, hypothesis_id))

            conn.commit()
            return score_id
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error in save_quality_score: {err}")
            return None
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def get_high_potential_hypotheses(
        self,
        user_id: str = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get hypotheses marked as high potential."""
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT h.*, hqs.overall_score, hqs.scoring_rationale
                FROM hypotheses h
                JOIN hypothesis_quality_scores hqs ON h.id = hqs.hypothesis_id
                WHERE hqs.is_high_potential = TRUE
            """
            params = []
            if user_id:
                query += " AND h.origin_user_id = %s"
                params.append(user_id)
            query += " ORDER BY hqs.overall_score DESC LIMIT %s"
            params.append(limit)
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [self._format_hypothesis_row(row) for row in rows]
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error in get_high_potential_hypotheses: {err}")
            return []
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    # =========================================================================
    # Team Brain: Sharing Suggestions (FR-202)
    # =========================================================================

    def create_sharing_suggestion(
        self,
        hypothesis_id: str,
        user_id: str,
        suggestion_reason: str,
        draft_content: str
    ) -> Optional[int]:
        """Create a sharing suggestion for a hypothesis."""
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor()
            query = """
                INSERT INTO sharing_suggestions (
                    hypothesis_id, user_id, suggestion_reason, draft_content
                )
                VALUES (%s, %s, %s, %s)
            """
            cursor.execute(query, (
                hypothesis_id, user_id, suggestion_reason, draft_content
            ))
            conn.commit()
            return cursor.lastrowid
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error in create_sharing_suggestion: {err}")
            return None
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def get_pending_suggestions(
        self,
        user_id: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get pending sharing suggestions for a user."""
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT ss.*, h.content as hypothesis_content
                FROM sharing_suggestions ss
                JOIN hypotheses h ON ss.hypothesis_id = h.id
                WHERE ss.user_id = %s AND ss.status = 'PENDING'
                ORDER BY ss.created_at DESC
                LIMIT %s
            """
            cursor.execute(query, (user_id, limit))
            rows = cursor.fetchall()
            for row in rows:
                if row.get('created_at'):
                    row['created_at'] = row['created_at'].isoformat()
            return rows
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error in get_pending_suggestions: {err}")
            return []
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def respond_to_suggestion(
        self,
        suggestion_id: int,
        user_id: str,
        status: str,
        edited_content: str = None
    ) -> bool:
        """Respond to a sharing suggestion."""
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor()
            query = """
                UPDATE sharing_suggestions
                SET status = %s, edited_content = %s, responded_at = NOW()
                WHERE id = %s AND user_id = %s
            """
            cursor.execute(query, (status, edited_content, suggestion_id, user_id))
            conn.commit()
            return cursor.rowcount > 0
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error in respond_to_suggestion: {err}")
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    # =========================================================================
    # Team Brain: Public Hypothesis Bank (FR-301)
    # =========================================================================

    def get_shared_hypotheses(
        self,
        team_id: str = None,
        verification_state: str = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get shared hypotheses (3階: Public Layer).
        Returns hypotheses with their verification status summary.
        """
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT h.*,
                       h.origin_user_id_hash as anonymous_author,
                       (SELECT COUNT(*) FROM hypothesis_verifications hv WHERE hv.hypothesis_id = h.id) as total_verifications,
                       (SELECT COUNT(*) FROM hypothesis_verifications hv WHERE hv.hypothesis_id = h.id AND hv.verification_result = 'SUCCESS') as success_count,
                       (SELECT COUNT(*) FROM hypothesis_verifications hv WHERE hv.hypothesis_id = h.id AND hv.verification_result = 'FAILURE') as failure_count
                FROM hypotheses h
                WHERE h.status = 'SHARED'
            """
            params = []
            if team_id:
                query += " AND h.team_id = %s"
                params.append(team_id)
            if verification_state:
                query += " AND h.verification_state = %s"
                params.append(verification_state)
            query += " ORDER BY h.shared_at DESC LIMIT %s"
            params.append(limit)
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()

            # Remove sensitive data and format
            result = []
            for row in rows:
                row = self._format_hypothesis_row(row)
                # Remove origin_user_id from public view
                if 'origin_user_id' in row:
                    del row['origin_user_id']
                result.append(row)
            return result
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error in get_shared_hypotheses: {err}")
            return []
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def share_hypothesis(
        self,
        hypothesis_id: str,
        user_id: str,
        team_id: str = None
    ) -> bool:
        """Share a hypothesis to the public layer."""
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor()
            query = """
                UPDATE hypotheses
                SET status = 'SHARED', team_id = %s, shared_at = NOW()
                WHERE id = %s AND origin_user_id = %s AND status IN ('DRAFT', 'PROPOSED')
            """
            cursor.execute(query, (team_id, hypothesis_id, user_id))
            conn.commit()
            return cursor.rowcount > 0
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error in share_hypothesis: {err}")
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    # =========================================================================
    # Team Brain: Team Management
    # =========================================================================

    def create_team(
        self,
        name: str,
        created_by: str,
        description: str = None
    ) -> Optional[str]:
        """Create a new team."""
        conn = None
        cursor = None
        import uuid
        team_id = str(uuid.uuid4())
        try:
            conn = mysql.connector.connect(**self.config)
            conn.start_transaction()
            cursor = conn.cursor()

            # Create team
            query = """
                INSERT INTO teams (id, name, description, created_by)
                VALUES (%s, %s, %s, %s)
            """
            cursor.execute(query, (team_id, name, description, created_by))

            # Add creator as owner
            member_query = """
                INSERT INTO team_members (team_id, user_id, role)
                VALUES (%s, %s, 'owner')
            """
            cursor.execute(member_query, (team_id, created_by))

            conn.commit()
            return team_id
        except mysql.connector.Error as err:
            if conn: conn.rollback()
            print(f"[✗] MySQL Error in create_team: {err}")
            return None
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def get_user_teams(self, user_id: str) -> List[Dict[str, Any]]:
        """Get teams a user belongs to."""
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT t.*, tm.role,
                       (SELECT COUNT(*) FROM team_members WHERE team_id = t.id) as member_count
                FROM teams t
                JOIN team_members tm ON t.id = tm.team_id
                WHERE tm.user_id = %s
                ORDER BY t.name
            """
            cursor.execute(query, (user_id,))
            rows = cursor.fetchall()
            for row in rows:
                if row.get('created_at'):
                    row['created_at'] = row['created_at'].isoformat()
                if row.get('updated_at'):
                    row['updated_at'] = row['updated_at'].isoformat()
            return rows
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error in get_user_teams: {err}")
            return []
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def add_team_member(
        self,
        team_id: str,
        user_id: str,
        role: str = 'viewer'
    ) -> bool:
        """Add a member to a team."""
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor()
            query = """
                INSERT INTO team_members (team_id, user_id, role)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE role = VALUES(role)
            """
            cursor.execute(query, (team_id, user_id, role))
            conn.commit()
            return True
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error in add_team_member: {err}")
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    # =========================================================================
    # Team Brain: Status-Aware RAG Support (FR-401)
    # =========================================================================

    def search_hypotheses_for_rag(
        self,
        keywords: List[str],
        exclude_user_id: str = None,
        include_verification_summary: bool = True,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search shared hypotheses for RAG retrieval.
        Returns hypotheses with verification status metadata.
        """
        conn = None
        cursor = None
        try:
            conn = mysql.connector.connect(**self.config)
            cursor = conn.cursor(dictionary=True)

            # Build LIKE conditions for keywords
            keyword_conditions = " OR ".join(["h.content LIKE %s"] * len(keywords))
            keyword_params = [f"%{kw}%" for kw in keywords]

            query = f"""
                SELECT h.id, h.content, h.verification_state, h.tags,
                       h.origin_user_id_hash as author_hash,
                       (SELECT COUNT(*) FROM hypothesis_verifications hv WHERE hv.hypothesis_id = h.id) as total_verifications,
                       (SELECT COUNT(*) FROM hypothesis_verifications hv WHERE hv.hypothesis_id = h.id AND hv.verification_result = 'SUCCESS') as success_count,
                       (SELECT COUNT(*) FROM hypothesis_verifications hv WHERE hv.hypothesis_id = h.id AND hv.verification_result = 'FAILURE') as failure_count,
                       (SELECT GROUP_CONCAT(DISTINCT CONCAT(t.name, ':', hv2.verification_result) SEPARATOR '; ')
                        FROM hypothesis_verifications hv2
                        LEFT JOIN teams t ON hv2.verifier_team_id = t.id
                        WHERE hv2.hypothesis_id = h.id) as verification_summary
                FROM hypotheses h
                WHERE h.status = 'SHARED'
                  AND ({keyword_conditions})
            """
            params = keyword_params.copy()

            if exclude_user_id:
                query += " AND h.origin_user_id != %s"
                params.append(exclude_user_id)

            query += " ORDER BY h.verification_state = 'VALIDATED' DESC, h.shared_at DESC LIMIT %s"
            params.append(limit)

            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [self._format_hypothesis_row(row) for row in rows]
        except mysql.connector.Error as err:
            print(f"[✗] MySQL Error in search_hypotheses_for_rag: {err}")
            return []
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
