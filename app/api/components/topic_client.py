import requests
import os
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class TopicClient:
    def __init__(self):
        self.api_url = os.getenv("TOPIC_API_URL", "http://topic-api:8000")

    def predict_category(self, text: str) -> Optional[str]:
        """
        Returns the category label (e.g., 'Health_Medical') or None.
        """
        try:
            resp = requests.post(
                f"{self.api_url}/predict",
                json={"text": text},
                timeout=5.0
            )
            if resp.status_code == 200:
                data = resp.json()
                label = data.get("label")
                # Exclude outliers/unknowns if necessary
                if label and label not in ["Unknown", "Outlier", "Not Initialized"]:
                    return label
            return None
        except Exception as e:
            logger.warning(f"Topic API call failed: {e}")
            return None

    def train_model(self, texts: list):
        # Implementation for background training...
        pass
