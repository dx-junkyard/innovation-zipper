# config.py
# ここに設定を記載します

import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()

class Settings(BaseSettings):
    # --- Base Model Definitions ---
    # 基本となるモデル定義（環境変数で上書き可能）
    MODEL_FAST: str = "gpt-5-mini" # 速度・コスト重視
    MODEL_SMART: str = "gpt-5.2"   # 品質・推論能力重視

    # --- LLM & Embedding ---
    LLM_MODEL: str = "gpt-5-mini"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536
    AI_URL: str = "http://host.docker.internal:11434"

    # --- DB Configuration ---
    DB_HOST: str = "db"
    DB_USER: str = "me"
    DB_PASSWORD: str = "me"
    DB_NAME: str = "mydb"
    DB_PORT: int = 3306

    # --- S3 / MinIO Configuration ---
    S3_ENDPOINT_URL: str = "http://minio:9000" # Docker network alias
    S3_PUBLIC_ENDPOINT_URL: str = "http://localhost:9000" # ブラウザから見た外部URL (New)
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadminpassword"
    S3_BUCKET_NAME: str = "user-files"
    S3_REGION_NAME: str = "us-east-1" # MinIO default
    S3_USE_SSL: bool = False

settings = Settings()

# --- Export Globals for Backward Compatibility ---
MODEL_FAST = settings.MODEL_FAST
MODEL_SMART = settings.MODEL_SMART

# --- Task Specific Model Assignments ---
# 利用タイミングごとのモデル割り当て

# 1. Webコンテンツフィルタリング (速度重視)
MODEL_CAPTURE_FILTERING = MODEL_FAST

# 2. Hot Cache / サジェスト生成 (速度重視)
MODEL_HOT_CACHE = MODEL_FAST

# 3. 意図判定・ルーティング (速度重視)
MODEL_INTENT_ROUTING = MODEL_FAST

# 4. 興味の探索・チャット (速度重視 - テンポ優先)
MODEL_INTEREST_EXPLORATION = MODEL_FAST

# 5. 状況分析・事実抽出 (品質重視 - 文脈理解必須)
MODEL_SITUATION_ANALYSIS = MODEL_SMART

# 6. 仮説生成 (品質重視 - 洞察力必須)
MODEL_HYPOTHESIS_GENERATION = MODEL_SMART

# 7. 構造分析・グラフ化 (品質重視 - 論理整合性必須)
MODEL_STRUCTURAL_ANALYSIS = MODEL_SMART

# 8. イノベーション・結合 (品質重視 - 創造性必須)
MODEL_INNOVATION_SYNTHESIS = MODEL_SMART

# 9. ギャップ分析 (品質重視 - 批判的思考必須)
MODEL_GAP_ANALYSIS = MODEL_SMART

# 10. レポート生成 (品質重視 - 文章力必須)
MODEL_REPORT_GENERATION = MODEL_SMART

# 11. 応答計画 (品質重視)
MODEL_RESPONSE_PLANNING = MODEL_SMART

LLM_MODEL = settings.LLM_MODEL
EMBEDDING_MODEL = settings.EMBEDDING_MODEL
EMBEDDING_DIMENSION = settings.EMBEDDING_DIMENSION
AI_URL = settings.AI_URL

DB_HOST = settings.DB_HOST
DB_USER = settings.DB_USER
DB_PASSWORD = settings.DB_PASSWORD
DB_NAME = settings.DB_NAME
DB_PORT = settings.DB_PORT
