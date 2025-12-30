import os
import logging
import json
import numpy as np
from typing import List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from bertopic import BERTopic
from bertopic.vectorizers import ClassTfidfTransformer
from bertopic.representation import MaximalMarginalRelevance
from sklearn.feature_extraction.text import CountVectorizer
from umap import UMAP
from hdbscan import HDBSCAN
import MeCab
import ipadic
import spacy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="BERTopic API Service")

MODEL_PATH = "/app/models/my_bertopic_model"
SEED_DATA_PATH = "seed_data.json"
ZERO_SHOT_TOPICS = [
    "政治_行政_法律_政策",
    "経済_金融_ビジネス_産業",
    "国際_社会問題_平和_人権",
    "労働_働き方_キャリア",
    "自然_環境_宇宙_気候",
    "科学_数学_物理_生命",
    "IT_テクノロジー_AI_情報",
    "工学_製造_建築_インフラ",
    "医療_健康_身体_ヘルスケア",
    "心理_メンタル_精神_哲学",
    "歴史_文化_言語_人類学",
    "芸術_アート_デザイン_表現",
    "エンタメ_サブカル_娯楽",
    "生活_家事_住まい_育児",
    "料理_グルメ_食文化",
    "趣味_旅行_レジャー_活動",
    "教育_学習_自己啓発",
    "人間関係_家族_恋愛_対話"
]

class JapaneseTokenizer:
    def __init__(self):
        self._init_tagger()

    def _init_tagger(self):
        self.tagger = MeCab.Tagger(ipadic.MECAB_ARGS)

    def __call__(self, text):
        if not hasattr(self, "tagger") or self.tagger is None:
            self._init_tagger()

        node = self.tagger.parseToNode(text)
        words = []
        while node:
            if node.surface:
                words.append(node.surface)
            node = node.next
        return words

    def __getstate__(self):
        state = self.__dict__.copy()
        if "tagger" in state:
            del state["tagger"]
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._init_tagger()

class TopicModelManager:
    def __init__(self):
        self.model = None
        self.tokenizer = JapaneseTokenizer()
        try:
            nlp = spacy.load("ja_core_news_sm")
            self.stop_words = list(nlp.Defaults.stop_words)
        except:
            self.stop_words = []

    def _build_pipeline(self):
        return {
            "embedding_model": "paraphrase-multilingual-MiniLM-L12-v2",
            "umap_model": UMAP(n_components=5, n_neighbors=15, metric='cosine', min_dist=0.0, random_state=42),
            "hdbscan_model": HDBSCAN(min_samples=10, metric='euclidean', cluster_selection_method='eom', prediction_data=True, min_cluster_size=10),
            "vectorizer_model": CountVectorizer(tokenizer=self.tokenizer, ngram_range=(1, 2), max_df=0.95, stop_words=self.stop_words),
            "ctfidf_model": ClassTfidfTransformer(reduce_frequent_words=True),
            "representation_model": MaximalMarginalRelevance(diversity=0.7),
            "zeroshot_topic_list": ZERO_SHOT_TOPICS,
            "zeroshot_min_similarity": 0.6,
            "language": "japanese",
            "calculate_probabilities": True
        }

    def initialize(self):
        if os.path.exists(MODEL_PATH):
            try:
                self.model = BERTopic.load(MODEL_PATH)
                logger.info("Loaded existing model.")
                return
            except Exception as e:
                logger.error(f"Load failed: {e}")

        if not os.path.exists(SEED_DATA_PATH):
            logger.info("Seed data not found. Generating default seed data...")
            from seed_generator import generate_seed_data
            try:
                generate_seed_data(output_path=SEED_DATA_PATH)
            except Exception as e:
                logger.error(f"Failed to generate seed data: {e}")
                return

        logger.info("Initializing with seed data...")
        if os.path.exists(SEED_DATA_PATH):
            with open(SEED_DATA_PATH, "r", encoding="utf-8") as f:
                docs = json.load(f)
            self.model = BERTopic(**self._build_pipeline())
            self.model.fit_transform(docs)
            os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
            self.model.save(MODEL_PATH)
            logger.info(f"Model trained on {len(docs)} seeds and saved.")

manager = TopicModelManager()

@app.on_event("startup")
def on_startup():
    manager.initialize()

class PredictRequest(BaseModel):
    text: str
class TrainRequest(BaseModel):
    texts: List[str]
    use_seed_data: bool = True

@app.post("/predict")
def predict(payload: PredictRequest):
    if not manager.model:
        return {"topic_id": -2, "label": "Not Initialized", "probability": 0.0}
    topics, probs = manager.model.transform([payload.text])
    topic_id = int(topics[0])
    info = manager.model.get_topic_info(topic_id)
    label = "Unknown"
    if not info.empty:
        if "CustomName" in info.columns and info["CustomName"].values[0]:
            label = info["CustomName"].values[0]
        elif "Name" in info.columns:
            label = "_".join(info["Name"].values[0].split("_")[1:3])

    prob_value = 0.0
    if probs is not None:
        # probs[0] is array -> get max, scalar -> use as is
        if isinstance(probs[0], (np.ndarray, list)):
             prob_value = float(np.max(probs[0]))
        else:
             prob_value = float(probs[0])

    return {"topic_id": topic_id, "label": label, "probability": prob_value}

@app.post("/train")
def train(payload: TrainRequest):
    docs = payload.texts
    if payload.use_seed_data and os.path.exists(SEED_DATA_PATH):
        with open(SEED_DATA_PATH, "r") as f: docs.extend(json.load(f))
    if len(docs) < 50: raise HTTPException(400, "Not enough data")
    manager.model = BERTopic(**manager._build_pipeline())
    manager.model.fit_transform(docs)
    manager.model.save(MODEL_PATH)
    return {"status": "success"}
