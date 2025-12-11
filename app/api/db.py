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

    def insert_message(self, user_id, role, message):
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
