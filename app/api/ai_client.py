import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import requests
from openai import OpenAI

from config import AI_URL, LLM_MODEL, EMBEDDING_MODEL

# ログ設定（必要に応じてレベルを DEBUG に変更可能）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger(__name__)


class AIClient:
    """LLM を利用してユーザー情報の整理と次の質問を生成するクラス。"""

    def __init__(self, model: str = LLM_MODEL, base_url: str = AI_URL) -> None:
        self.model = model
        self.api_url = f"{base_url}/api/generate"

        self.openai_client = None
        openai_api_key = os.environ.get("OPENAI_API_KEY")

        # Debug logging for API key status
        if openai_api_key:
            masked_key = openai_api_key[:4] + "*" * 4 + openai_api_key[-4:] if len(openai_api_key) > 8 else "****"
            logger.info(f"OPENAI_API_KEY found: {masked_key}")
        else:
            logger.warning("OPENAI_API_KEY not found in environment variables.")

        # Debug logging for model
        logger.info(f"AIClient model: '{self.model}' (type: {type(self.model)})")
        logger.info(f"Env LLM_MODEL: '{os.environ.get('LLM_MODEL')}'")

        if openai_api_key:
            self.openai_client = OpenAI(api_key=openai_api_key)
            logger.info("AIClient initialized with OpenAI API")
        else:
            logger.info(
                "AIClient initialized with local LLM model: %s endpoint: %s",
                model,
                self.api_url
            )

    @staticmethod
    def _extract_json(payload: str) -> Optional[Dict[str, Any]]:
        text = payload.strip()
        if not text:
            return None

        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text, count=1).strip()
            if text.endswith("```"):
                text = text[:-3].strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    return None
        return None


    @staticmethod
    def _is_reasoning_model(model: str) -> bool:
        """
        モデルが推論モデル（Reasoning Model）かどうかを判定する。
        現在は gpt-5 系のみを対象とする。
        """
        return model.startswith("gpt-5") or model.startswith("o1")

    def generate_response(self, prompt: str) -> Optional[Dict[str, Any]]:
        """
        LLMを使用して応答を生成する汎用メソッド。

        Args:
            prompt (str): プロンプト

        Returns:
            Optional[Dict[str, Any]]: 生成されたJSONレスポンス
        """
        logger.info("Prompt sent to LLM: %s", prompt)

        if self.openai_client:
            try:
                if self._is_reasoning_model(self.model):
                    # GPT-5 specific connection
                    response = self.openai_client.responses.create(
                        model=self.model,
                        reasoning={"effort": "medium"},
                        input=[
                            {"role": "user", "content": prompt}
                        ]
                    )
                    # Helper to find output text in list of response items
                    raw_text = ""
                    # The response object has an 'output' attribute which is a list of items
                    try:
                        if hasattr(response, "output") and isinstance(response.output, list):
                            for item in response.output:
                                if hasattr(item, "type") and item.type == "message":
                                    # This is likely ResponseOutputMessage
                                    if hasattr(item, "content"):
                                        for content_item in item.content:
                                            if hasattr(content_item, "type") and content_item.type == "output_text":
                                                raw_text = content_item.text
                                                break
                                if raw_text:
                                    break
                        
                        if not raw_text:
                            logger.warning("Could not find output_text in response.output list, dumping raw response.")
                            raw_text = str(response)

                    except Exception as e:
                        logger.error(f"Error parsing GPT-5 response: {e}")
                        raw_text = str(response)
                else:
                    response = self.openai_client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": "You are a helpful assistant."},
                            {"role": "user", "content": prompt}
                        ],
                        response_format={"type": "json_object"}
                    )
                    raw_text = response.choices[0].message.content.strip()
                logger.info("OpenAI response raw text: %s", raw_text)
            except Exception as exc:
                logger.error("[✗] OpenAI API request failed: %s", exc)
                return None
        else:
            try:
                response = requests.post(
                    self.api_url,
                    json={"model": self.model, "prompt": prompt, "stream": False},
                    timeout=120,
                )
                response.raise_for_status()
                raw_text = response.json().get("response", "").strip()
                logger.info("Local LLM response raw text: %s", raw_text)
            except Exception as exc:
                logger.error("[✗] LLM へのリクエストに失敗しました: %s", exc)
                return None

        parsed = self._extract_json(raw_text)
        if parsed is None:
            logger.error("LLM からの応答を JSON として解析できませんでした。")
        return parsed

    def get_embedding(self, text: str) -> List[float]:
        """
        テキストの埋め込みベクトルを生成する。

        Args:
            text (str): 入力テキスト

        Returns:
            List[float]: 埋め込みベクトル
        """
        text = text.replace("\n", " ")
        if self.openai_client:
            try:
                return self.openai_client.embeddings.create(input=[text], model=EMBEDDING_MODEL).data[0].embedding
            except Exception as exc:
                logger.error("[✗] OpenAI Embedding request failed: %s", exc)
                return []
        else:
            # Local LLM embedding support (optional, for now return empty or implement if needed)
            # For this task, we assume OpenAI is used for embeddings as per previous context.
            logger.warning("Local LLM embedding not fully implemented, returning empty list.")
            return []
