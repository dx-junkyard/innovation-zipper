import os
import json
import logging
import numpy as np
from typing import List, Dict, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from langchain_openai import OpenAIEmbeddings
from sklearn.metrics.pairwise import cosine_similarity

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 定数
CATEGORIES_FILE = "categories.json"
USER_EXAMPLES_FILE = "user_examples.json"
EMBEDDING_MODEL = "text-embedding-3-small"
SIMILARITY_THRESHOLD = 0.35  # しきい値

class KnowledgeBase:
    def __init__(self):
        self.vectors = None
        self.metadata = []
        # APIキーは環境変数 OPENAI_API_KEY から自動読込
        self.embedder = OpenAIEmbeddings(model=EMBEDDING_MODEL)

    def load_and_index(self):
        """categories.jsonを読み込みベクトルインデックスを構築する"""
        if not os.path.exists(CATEGORIES_FILE):
            logger.error(f"{CATEGORIES_FILE} not found!")
            return

        with open(CATEGORIES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        texts_to_embed = []
        self.metadata = []

        logger.info("Building vector index from categories...")

        for main_cat, main_val in data.items():
            # 大カテゴリ自体の定義も登録
            desc = main_val.get("description", "")
            if desc:
                text = f"{main_cat}: {desc}"
                texts_to_embed.append(text)
                self.metadata.append({
                    "category": main_cat,
                    "subcategory": None,
                    "type": "description",
                    "text": text
                })

            for sub in main_val.get("subcategories", []):
                sub_name = sub["category"]
                sub_desc = sub["description"]
                examples = sub.get("examples", [])

                # 1. サブカテゴリの説明文
                desc_text = f"{sub_name}: {sub_desc}"
                texts_to_embed.append(desc_text)
                self.metadata.append({
                    "category": main_cat,
                    "subcategory": sub_name,
                    "type": "description",
                    "text": desc_text
                })

                # 2. 例文 (Examples)
                for ex in examples:
                    texts_to_embed.append(ex)
                    self.metadata.append({
                        "category": main_cat,
                        "subcategory": sub_name,
                        "type": "example",
                        "text": ex
                    })

        # 3. ユーザーフィードバック (User Examples)
        if os.path.exists(USER_EXAMPLES_FILE):
            try:
                with open(USER_EXAMPLES_FILE, "r", encoding="utf-8") as f:
                    user_examples = json.load(f)
                    for item in user_examples:
                        text = item.get("text", "")
                        cat = item.get("category", "")
                        if text and cat:
                            texts_to_embed.append(text)
                            self.metadata.append({
                                "category": None, # Parent unknown for user examples unless stored
                                "subcategory": cat, # Treat as the target category
                                "type": "user_feedback",
                                "text": text
                            })
            except Exception as e:
                logger.error(f"Failed to load user examples: {e}")

        if not texts_to_embed:
            logger.warning("No texts found to embed.")
            return

        # 一括ベクトル化
        try:
            embeddings = self.embedder.embed_documents(texts_to_embed)
            self.vectors = np.array(embeddings)
            logger.info(f"Indexed {len(self.vectors)} items successfully.")
        except Exception as e:
            logger.error(f"Failed to create embeddings: {e}")

    def add_example(self, text: str, category: str):
        """ユーザーフィードバックを追加し、インデックスを更新する"""
        # 1. ファイルに追記
        examples = []
        if os.path.exists(USER_EXAMPLES_FILE):
            try:
                with open(USER_EXAMPLES_FILE, "r", encoding="utf-8") as f:
                    examples = json.load(f)
            except:
                pass

        examples.append({"text": text, "category": category})

        with open(USER_EXAMPLES_FILE, "w", encoding="utf-8") as f:
            json.dump(examples, f, ensure_ascii=False, indent=2)

        # 2. メモリ上のインデックスに追加
        try:
            vector = self.embedder.embed_query(text)
            new_vec = np.array(vector).reshape(1, -1)

            if self.vectors is None:
                self.vectors = new_vec
            else:
                self.vectors = np.vstack([self.vectors, new_vec])

            self.metadata.append({
                "category": None,
                "subcategory": category,
                "type": "user_feedback",
                "text": text
            })
            logger.info(f"Learned new example for category '{category}'")
            return True
        except Exception as e:
            logger.error(f"Failed to add example: {e}")
            return False

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if self.vectors is None or len(self.vectors) == 0:
            return []

        try:
            # クエリのベクトル化
            query_vec = np.array(self.embedder.embed_query(query)).reshape(1, -1)

            # コサイン類似度計算
            scores = cosine_similarity(query_vec, self.vectors)[0]

            # 上位候補の取得
            top_indices = np.argsort(scores)[::-1][:top_k]

            results = []
            seen_categories = set()

            for idx in top_indices:
                score = float(scores[idx])
                if score < SIMILARITY_THRESHOLD:
                    continue

                meta = self.metadata[idx]
                # 決定されたカテゴリ名 (サブカテゴリがあればそれ、なければ大カテゴリ)
                cat_name = meta["subcategory"] if meta["subcategory"] else meta["category"]

                # 重複排除（同じカテゴリで説明文と例文が両方ヒットした場合など）
                if cat_name in seen_categories:
                    continue

                seen_categories.add(cat_name)

                results.append({
                    "name": cat_name,
                    "confidence": round(score, 3),
                    "keywords": [], # 互換性のため空リスト
                    "parent_category": meta["category"],
                    "match_type": meta["type"],
                    "matched_text": meta["text"][:50] + "..." # デバッグ用
                })

            return results

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

# グローバルインスタンス
kb = KnowledgeBase()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 起動時の処理
    kb.load_and_index()
    yield
    # 終了時の処理 (必要なら)

app = FastAPI(title="Semantic Topic Classifier", lifespan=lifespan)

class PredictRequest(BaseModel):
    text: str

@app.post("/predict")
def predict(payload: PredictRequest):
    if not payload.text.strip():
        return {"categories": []}

    results = kb.search(payload.text)

    # ログ出力（デバッグ用）
    if results:
        top = results[0]
        logger.info(f"Input: {payload.text[:30]}... -> {top['name']} ({top['confidence']}) via {top['match_type']}")
    else:
        logger.info(f"Input: {payload.text[:30]}... -> No Match")

    return {"categories": results}

# 後方互換性・学習用エンドポイント（ダミー）
@app.post("/train")
def train():
    return {"status": "ignored", "message": "Training is not needed for semantic search."}

class FeedbackRequest(BaseModel):
    text: str
    category: str

@app.post("/feedback")
def feedback(payload: FeedbackRequest):
    if not payload.text.strip() or not payload.category.strip():
        raise HTTPException(status_code=400, detail="Text and category are required.")

    success = kb.add_example(payload.text, payload.category)
    if success:
        return {"status": "success", "message": f"Learned category '{payload.category}'."}
    else:
        raise HTTPException(status_code=500, detail="Failed to learn example.")
