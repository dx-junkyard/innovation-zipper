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
        try:
            resp = requests.post(
                f"{self.api_url}/predict",
                json={"text": text},
                timeout=5.0
            )
            if resp.status_code == 200:
                return resp.json()
            return {"categories": []}
        except Exception as e:
            logger.warning(f"Topic API call failed: {e}")
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
