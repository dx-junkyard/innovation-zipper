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
#    "単純分類タスク"。入力されたテキストが「興味/関心」か「事務連絡」かを判定するだけであり、高度な推論は不要です。大量に実行される可能性があるため、コスト効率と速度を最優先します。
MODEL_CAPTURE_FILTERING = MODEL_FAST

# 2. Hot Cache / サジェスト生成 (速度重視)
#    速度とレスポンス重視です。ユーザーの興味に基づき「次に聞きそうなこと」を3つ挙げるタスクですが、創造性よりもUIの表示速度（ユーザーを待たせないこと）が重要です。
MODEL_HOT_CACHE = MODEL_FAST

# 3. 意図判定・ルーティング (速度重視)
#    "論理的振り分け"。ユーザーの発言から「分析モード」か「探索モード」かを決めるロジックは明確であり、プロンプトで指示を守らせればminiモデルで十分に機能します。
MODEL_INTENT_ROUTING = MODEL_FAST

# 4. 興味の探索・チャット (速度重視 - テンポ優先)
#    "対話のテンポが重要"。ユーザーへのヒアリング段階では、深すぎる分析よりも、会話のキャッチボールをスムーズに行うことが優先されます。
MODEL_INTEREST_EXPLORATION = MODEL_FAST

# 5. 状況分析・事実抽出 (品質重視 - 文脈理解必須)
#    "文脈理解の要"。ここでユーザーの曖昧な入力から正確な「事実」と「意図」を汲み取れないと、後続の分析すべてがズレてしまいます。ニュアンスを理解する能力が必要です。
MODEL_SITUATION_ANALYSIS = MODEL_SMART

# 6. 仮説生成 (品質重視 - 洞察力必須)
#    "洞察力が必要"。単なる要約ではなく、行間を読んで「ありそうな可能性」を提示するため、学習データ量が多く推論能力が高いモデルが必須です。
MODEL_HYPOTHESIS_GENERATION = MODEL_SMART

# 7. 構造分析・グラフ化 (品質重視 - 論理整合性必須)
#    "論理的複雑性が最大"。物事を要素分解し、関係性を定義する（グラフ理論的アプローチ）には、高い論理的整合性が求められます。miniでは関係性の抽出が浅くなるリスクがあります。
MODEL_STRUCTURAL_ANALYSIS = MODEL_SMART

# 8. イノベーション・結合 (品質重視 - 創造性必須)
#    "創造性 (Creativity)" 。異質な概念を組み合わせて新しいアイデアを出すタスクは、パラメータ数が多いモデルの方が「意外性のある、かつ納得感のある」回答を出せます。
MODEL_INNOVATION_SYNTHESIS = MODEL_SMART

# 9. ギャップ分析 (品質重視 - 批判的思考必須)
#    "批判的思考"。「何が足りないか」を見つけるには、全体を俯瞰して論理の飛躍を指摘する能力が必要で、高度なモデルが適しています。
MODEL_GAP_ANALYSIS = MODEL_SMART

# 10. レポート生成 (品質重視 - 文章力必須)
#     "成果物の品質"。要約自体はminiでも可能ですが、最終的にユーザーの手元に残るドキュメントとしての「文章の滑らかさ」や「説得力」を担保するため、上位モデルを推奨します。
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
