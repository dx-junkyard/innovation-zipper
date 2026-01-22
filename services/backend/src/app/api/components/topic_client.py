import requests
import os
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

class TopicClient:
    def __init__(self):
        self.api_url = os.getenv("TOPIC_API_URL", "http://topic-api:8000")

    def analyze_content(self, text: str) -> Dict[str, Any]:
        """
        Analyzes the text and returns a list of categories with keywords.
        Returns format: {"categories": [{"name": "...", "confidence": 0.9, "keywords": [...]}, ...]}
        """
        # [LOG] 入力テキストの記録 (長すぎる場合は切り詰める)
        logger.info(f"[TopicClient] Analyzing Text ({len(text)} chars): {text[:100].replace(chr(10), ' ')}...")

        try:
            resp = requests.post(
                f"{self.api_url}/predict",
                json={"text": text},
                timeout=5.0
            )
            if resp.status_code == 200:
                result = resp.json()
                categories = result.get("categories", [])

                # [LOG] 判定結果の記録
                if categories:
                    top_cat = categories[0]
                    logger.info(f"[TopicClient] Result: {top_cat['name']} (conf={top_cat.get('confidence')})")
                else:
                    logger.info("[TopicClient] Result: No categories detected")

                return result

            logger.warning(f"[TopicClient] API returned status {resp.status_code}")
            return {"categories": []}
        except Exception as e:
            logger.warning(f"[TopicClient] API call failed: {e}")
            return {"categories": []}

    def predict_category(self, text: str) -> Optional[str]:
        """
        Returns the top category label (e.g., 'Health_Medical') or None.
        Kept for backward compatibility.
        """
        result = self.analyze_content(text)
        categories = result.get("categories", [])
        if categories:
            top_category = categories[0]
            label = top_category.get("name")
            if label and label not in ["Unknown", "Outlier", "Not Initialized"]:
                return label
        return None

    def train_model(self, texts: list):
        # Implementation for background training...
        pass

    def learn_text(self, text: str, category: str) -> bool:
        """
        Sends feedback to the topic service to learn a new text-category pair.
        """
        try:
            resp = requests.post(
                f"{self.api_url}/feedback",
                json={"text": text, "category": category},
                timeout=5.0
            )
            if resp.status_code == 200:
                logger.info(f"[TopicClient] Successfully learned: '{category}'")
                return True
            else:
                logger.warning(f"[TopicClient] Feedback failed: {resp.status_code} - {resp.text}")
                return False
        except Exception as e:
            logger.warning(f"[TopicClient] Feedback call failed: {e}")
            return False
