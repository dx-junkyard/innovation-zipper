# config.py
# ここに設定を記載します

import os
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()


# =============================================================================
# Provider Definitions
# =============================================================================
PROVIDER_LOCAL = "local"
PROVIDER_OPENAI = "openai"


# =============================================================================
# Model Configuration Data Classes
# =============================================================================
@dataclass
class ModelConfig:
    """Single model configuration with provider and model name."""
    provider: str
    model: str

    def to_dict(self) -> Dict[str, str]:
        return {"provider": self.provider, "model": self.model}


@dataclass
class EmbeddingConfig:
    """Embedding model configuration with dimension information."""
    provider: str
    model: str
    dimension: int

    def to_dict(self) -> Dict[str, Any]:
        return {"provider": self.provider, "model": self.model, "dimension": self.dimension}

    def get_collection_suffix(self) -> str:
        """Generate collection name suffix from model name and dimension."""
        # Sanitize model name for collection name (replace special chars)
        safe_model = self.model.replace("/", "_").replace("-", "_").replace(".", "_")
        return f"{safe_model}_{self.dimension}"


# =============================================================================
# Local LLM Model Definitions (Ollama)
# =============================================================================
LOCAL_MODEL_FAST = "llama3.2"           # 速度・コスト重視（ゼロコスト）
LOCAL_MODEL_SMART = "llama3.2"          # 品質重視（ローカル最高性能）
LOCAL_EMBEDDING_MODEL = "mxbai-embed-large"  # Ollama embedding model
LOCAL_EMBEDDING_DIMENSION = 1024        # mxbai-embed-large dimension


# =============================================================================
# Cloud LLM Model Definitions (OpenAI)
# =============================================================================
CLOUD_MODEL_FAST = "gpt-4o-mini"         # 速度・コスト重視
CLOUD_MODEL_SMART = "gpt-4o"             # 品質・推論能力重視
CLOUD_EMBEDDING_MODEL = "text-embedding-3-small"  # OpenAI embedding model
CLOUD_EMBEDDING_DIMENSION = 1536         # text-embedding-3-small dimension


class Settings(BaseSettings):
    # --- Local LLM Configuration ---
    LOCAL_MODEL_FAST: str = LOCAL_MODEL_FAST
    LOCAL_MODEL_SMART: str = LOCAL_MODEL_SMART
    LOCAL_EMBEDDING_MODEL: str = LOCAL_EMBEDDING_MODEL
    LOCAL_EMBEDDING_DIMENSION: int = LOCAL_EMBEDDING_DIMENSION
    AI_URL: str = "http://host.docker.internal:11434"

    # --- Cloud LLM Configuration (OpenAI) ---
    CLOUD_MODEL_FAST: str = CLOUD_MODEL_FAST
    CLOUD_MODEL_SMART: str = CLOUD_MODEL_SMART
    CLOUD_EMBEDDING_MODEL: str = CLOUD_EMBEDDING_MODEL
    CLOUD_EMBEDDING_DIMENSION: int = CLOUD_EMBEDDING_DIMENSION

    # --- Legacy Settings (for backward compatibility) ---
    LLM_MODEL: str = "gpt-4o-mini"  # Deprecated: Use task-specific configs
    EMBEDDING_MODEL: str = "text-embedding-3-small"  # Deprecated
    EMBEDDING_DIMENSION: int = 1536  # Deprecated

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

# =============================================================================
# Export Globals for Backward Compatibility
# =============================================================================
# Legacy model definitions (use TASK_* configs for new code)
MODEL_FAST = settings.CLOUD_MODEL_FAST
MODEL_SMART = settings.CLOUD_MODEL_SMART


# =============================================================================
# Task-Specific Configurations (Hybrid Model Support)
# =============================================================================
# Each task can specify its preferred provider and model.
# Default configurations prioritize Cloud (OpenAI) for quality-critical tasks
# and can be switched to Local for cost optimization.

# --- Helper functions to create task configs ---
def _local_fast() -> ModelConfig:
    return ModelConfig(provider=PROVIDER_LOCAL, model=settings.LOCAL_MODEL_FAST)

def _local_smart() -> ModelConfig:
    return ModelConfig(provider=PROVIDER_LOCAL, model=settings.LOCAL_MODEL_SMART)

def _cloud_fast() -> ModelConfig:
    return ModelConfig(provider=PROVIDER_OPENAI, model=settings.CLOUD_MODEL_FAST)

def _cloud_smart() -> ModelConfig:
    return ModelConfig(provider=PROVIDER_OPENAI, model=settings.CLOUD_MODEL_SMART)

def _local_embedding() -> EmbeddingConfig:
    return EmbeddingConfig(
        provider=PROVIDER_LOCAL,
        model=settings.LOCAL_EMBEDDING_MODEL,
        dimension=settings.LOCAL_EMBEDDING_DIMENSION
    )

def _cloud_embedding() -> EmbeddingConfig:
    return EmbeddingConfig(
        provider=PROVIDER_OPENAI,
        model=settings.CLOUD_EMBEDDING_MODEL,
        dimension=settings.CLOUD_EMBEDDING_DIMENSION
    )


# --- Task Configurations ---
# 利用タイミングごとのモデル割り当て（プロバイダーとモデルのセット）

# 1. Webコンテンツフィルタリング (速度重視)
#    "単純分類タスク"。入力されたテキストが「興味/関心」か「事務連絡」かを判定するだけであり、
#    高度な推論は不要です。大量に実行される可能性があるため、コスト効率と速度を最優先します。
TASK_CAPTURE_FILTERING: ModelConfig = _cloud_fast()

# 2. Hot Cache / サジェスト生成 (速度重視)
#    速度とレスポンス重視です。ユーザーの興味に基づき「次に聞きそうなこと」を3つ挙げるタスクですが、
#    創造性よりもUIの表示速度（ユーザーを待たせないこと）が重要です。
TASK_HOT_CACHE: ModelConfig = _cloud_fast()

# 3. 意図判定・ルーティング (速度重視)
#    "論理的振り分け"。ユーザーの発言から「分析モード」か「探索モード」かを決めるロジックは明確であり、
#    プロンプトで指示を守らせればminiモデルで十分に機能します。
TASK_INTENT_ROUTING: ModelConfig = _cloud_fast()

# 4. 興味の探索・チャット (速度重視 - テンポ優先)
#    "対話のテンポが重要"。ユーザーへのヒアリング段階では、深すぎる分析よりも、
#    会話のキャッチボールをスムーズに行うことが優先されます。
TASK_INTEREST_EXPLORATION: ModelConfig = _cloud_fast()

# 5. 状況分析・事実抽出 (品質重視 - 文脈理解必須)
#    "文脈理解の要"。ここでユーザーの曖昧な入力から正確な「事実」と「意図」を汲み取れないと、
#    後続の分析すべてがズレてしまいます。ニュアンスを理解する能力が必要です。
TASK_SITUATION_ANALYSIS: ModelConfig = _cloud_smart()

# 6. 仮説生成 (品質重視 - 洞察力必須)
#    "洞察力が必要"。単なる要約ではなく、行間を読んで「ありそうな可能性」を提示するため、
#    学習データ量が多く推論能力が高いモデルが必須です。
TASK_HYPOTHESIS_GENERATION: ModelConfig = _cloud_smart()

# 7. 構造分析・グラフ化 (品質重視 - 論理整合性必須)
#    "論理的複雑性が最大"。物事を要素分解し、関係性を定義する（グラフ理論的アプローチ）には、
#    高い論理的整合性が求められます。miniでは関係性の抽出が浅くなるリスクがあります。
TASK_STRUCTURAL_ANALYSIS: ModelConfig = _cloud_smart()

# 8. イノベーション・結合 (品質重視 - 創造性必須)
#    "創造性 (Creativity)" 。異質な概念を組み合わせて新しいアイデアを出すタスクは、
#    パラメータ数が多いモデルの方が「意外性のある、かつ納得感のある」回答を出せます。
TASK_INNOVATION_SYNTHESIS: ModelConfig = _cloud_smart()

# 9. ギャップ分析 (品質重視 - 批判的思考必須)
#    "批判的思考"。「何が足りないか」を見つけるには、全体を俯瞰して論理の飛躍を指摘する能力が必要で、
#    高度なモデルが適しています。
TASK_GAP_ANALYSIS: ModelConfig = _cloud_smart()

# 10. レポート生成 (品質重視 - 文章力必須)
#     "成果物の品質"。要約自体はminiでも可能ですが、最終的にユーザーの手元に残るドキュメントとしての
#     「文章の滑らかさ」や「説得力」を担保するため、上位モデルを推奨します。
TASK_REPORT_GENERATION: ModelConfig = _cloud_smart()

# 11. 応答計画 (品質重視)
TASK_RESPONSE_PLANNING: ModelConfig = _cloud_smart()


# --- Embedding Task Configurations ---
# Embedding生成のタスク別設定

# 12. Wiki Embedding (コスト重視 - 大量処理)
#     Wikipediaインポートなど大量のテキストをembedding化する処理。
#     コストゼロのLocal LLMを使用することで、大量処理でもコストを抑えられる。
TASK_WIKI_EMBEDDING: EmbeddingConfig = _local_embedding()

# 13. User Document Embedding (品質とコストのバランス)
#     ユーザーがアップロードしたドキュメントのembedding生成。
#     品質を重視しつつ、必要に応じてLocalに切り替え可能。
TASK_USER_DOCUMENT_EMBEDDING: EmbeddingConfig = _cloud_embedding()

# 14. RAG Search Embedding (品質重視)
#     RAG検索時のクエリembedding生成。検索品質に直結するため、
#     デフォルトはCloudを使用。
TASK_RAG_SEARCH_EMBEDDING: EmbeddingConfig = _cloud_embedding()


# =============================================================================
# Legacy Compatibility Exports
# =============================================================================
# 既存コードとの互換性のため、旧形式の変数も維持
# 新規コードではTASK_*を使用することを推奨

MODEL_CAPTURE_FILTERING = TASK_CAPTURE_FILTERING.model
MODEL_HOT_CACHE = TASK_HOT_CACHE.model
MODEL_INTENT_ROUTING = TASK_INTENT_ROUTING.model
MODEL_INTEREST_EXPLORATION = TASK_INTEREST_EXPLORATION.model
MODEL_SITUATION_ANALYSIS = TASK_SITUATION_ANALYSIS.model
MODEL_HYPOTHESIS_GENERATION = TASK_HYPOTHESIS_GENERATION.model
MODEL_STRUCTURAL_ANALYSIS = TASK_STRUCTURAL_ANALYSIS.model
MODEL_INNOVATION_SYNTHESIS = TASK_INNOVATION_SYNTHESIS.model
MODEL_GAP_ANALYSIS = TASK_GAP_ANALYSIS.model
MODEL_REPORT_GENERATION = TASK_REPORT_GENERATION.model
MODEL_RESPONSE_PLANNING = TASK_RESPONSE_PLANNING.model

# Legacy global exports
LLM_MODEL = settings.LLM_MODEL
EMBEDDING_MODEL = settings.EMBEDDING_MODEL
EMBEDDING_DIMENSION = settings.EMBEDDING_DIMENSION
AI_URL = settings.AI_URL

DB_HOST = settings.DB_HOST
DB_USER = settings.DB_USER
DB_PASSWORD = settings.DB_PASSWORD
DB_NAME = settings.DB_NAME
DB_PORT = settings.DB_PORT


# =============================================================================
# Helper Functions for Dynamic Configuration
# =============================================================================
def get_task_config(task_name: str) -> Optional[ModelConfig]:
    """Get task configuration by name."""
    task_configs = {
        "capture_filtering": TASK_CAPTURE_FILTERING,
        "hot_cache": TASK_HOT_CACHE,
        "intent_routing": TASK_INTENT_ROUTING,
        "interest_exploration": TASK_INTEREST_EXPLORATION,
        "situation_analysis": TASK_SITUATION_ANALYSIS,
        "hypothesis_generation": TASK_HYPOTHESIS_GENERATION,
        "structural_analysis": TASK_STRUCTURAL_ANALYSIS,
        "innovation_synthesis": TASK_INNOVATION_SYNTHESIS,
        "gap_analysis": TASK_GAP_ANALYSIS,
        "report_generation": TASK_REPORT_GENERATION,
        "response_planning": TASK_RESPONSE_PLANNING,
    }
    return task_configs.get(task_name)


def get_embedding_config(task_name: str) -> Optional[EmbeddingConfig]:
    """Get embedding configuration by task name."""
    embedding_configs = {
        "wiki_embedding": TASK_WIKI_EMBEDDING,
        "user_document_embedding": TASK_USER_DOCUMENT_EMBEDDING,
        "rag_search_embedding": TASK_RAG_SEARCH_EMBEDDING,
    }
    return embedding_configs.get(task_name)


def get_active_embedding_config() -> EmbeddingConfig:
    """
    Get the currently active embedding configuration.
    This is used to determine the default collection for most operations.
    For specific tasks like wiki import, use TASK_WIKI_EMBEDDING directly.
    """
    return TASK_RAG_SEARCH_EMBEDDING


def generate_collection_name(base_name: str, embedding_config: EmbeddingConfig) -> str:
    """
    Generate a dynamic collection name based on embedding model and dimension.

    Args:
        base_name: Base collection name (e.g., "knowledge_base")
        embedding_config: Embedding configuration

    Returns:
        Collection name with model and dimension suffix (e.g., "knowledge_base_mxbai_embed_large_1024")
    """
    return f"{base_name}_{embedding_config.get_collection_suffix()}"
