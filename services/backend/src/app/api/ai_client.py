import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Generator, AsyncGenerator, Union

import requests
from openai import OpenAI, AsyncOpenAI

from config import (
    AI_URL,
    LLM_MODEL,
    PROVIDER_LOCAL,
    PROVIDER_OPENAI,
    ModelConfig,
    EmbeddingConfig,
    get_active_embedding_config,
    settings,
)

# ログ設定（必要に応じてレベルを DEBUG に変更可能）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger(__name__)


class AIClient:
    """
    Hybrid LLM Router - Local LLMとCloud APIを動的に使い分けるクライアント。

    このクラスは「どちらか一方」ではなく「ルーター」として機能し、
    タスク設定に基づいて最適なプロバイダーにリクエストをルーティングします。
    """

    def __init__(self, model: str = LLM_MODEL, base_url: str = AI_URL) -> None:
        self.default_model = model
        self.local_base_url = base_url
        self.local_api_url = f"{base_url}/api/generate"
        self.local_embedding_url = f"{base_url}/api/embed"

        # Initialize both providers
        self._init_openai_client()
        self._init_local_availability()

        # Log initialization status
        self._log_initialization_status()

    def _init_openai_client(self) -> None:
        """Initialize OpenAI client if API key is available."""
        self.openai_client: Optional[OpenAI] = None
        self.async_openai_client: Optional[AsyncOpenAI] = None
        self.openai_available = False

        openai_api_key = os.environ.get("OPENAI_API_KEY")
        if openai_api_key:
            masked_key = openai_api_key[:4] + "*" * 4 + openai_api_key[-4:] if len(openai_api_key) > 8 else "****"
            logger.info(f"OPENAI_API_KEY found: {masked_key}")
            self.openai_client = OpenAI(api_key=openai_api_key)
            self.async_openai_client = AsyncOpenAI(api_key=openai_api_key)
            self.openai_available = True
        else:
            logger.warning("OPENAI_API_KEY not found - OpenAI provider disabled")

    def _init_local_availability(self) -> None:
        """Check if local LLM (Ollama) is available."""
        self.local_available = False
        try:
            # Quick health check to Ollama
            response = requests.get(f"{self.local_base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                self.local_available = True
                logger.info(f"Local LLM (Ollama) available at {self.local_base_url}")
            else:
                logger.warning(f"Local LLM returned status {response.status_code}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Local LLM (Ollama) not available: {e}")

    def _log_initialization_status(self) -> None:
        """Log the initialization status of both providers."""
        logger.info("=" * 50)
        logger.info("AIClient Hybrid Router Initialized")
        logger.info(f"  OpenAI: {'✓ Available' if self.openai_available else '✗ Unavailable'}")
        logger.info(f"  Local LLM: {'✓ Available' if self.local_available else '✗ Unavailable'}")
        logger.info(f"  Default Model: {self.default_model}")
        logger.info("=" * 50)

    def _resolve_provider(
        self,
        task_config: Optional[Union[ModelConfig, EmbeddingConfig]] = None,
        provider: Optional[str] = None
    ) -> str:
        """
        Resolve which provider to use based on task config or explicit provider.

        Priority:
        1. Explicit provider argument
        2. Task config provider
        3. OpenAI if available, else Local
        """
        if provider:
            return provider

        if task_config:
            return task_config.provider

        # Fallback: prefer OpenAI if available
        if self.openai_available:
            return PROVIDER_OPENAI
        elif self.local_available:
            return PROVIDER_LOCAL
        else:
            raise RuntimeError("No LLM provider available")

    def _resolve_model(
        self,
        task_config: Optional[Union[ModelConfig, EmbeddingConfig]] = None,
        model: Optional[str] = None,
        provider: str = PROVIDER_OPENAI
    ) -> str:
        """Resolve which model to use."""
        if model:
            return model

        if task_config:
            return task_config.model

        # Fallback based on provider
        if provider == PROVIDER_OPENAI:
            return settings.CLOUD_MODEL_FAST
        else:
            return settings.LOCAL_MODEL_FAST

    @staticmethod
    def _extract_json(payload: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from LLM response text."""
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
        現在は gpt-5 系と o1 系を対象とする。
        """
        return model.startswith("gpt-5") or model.startswith("o1")

    # =========================================================================
    # Text Generation Methods
    # =========================================================================

    def generate_response(
        self,
        prompt: str,
        model: Optional[str] = None,
        force_json: bool = False,
        task_config: Optional[ModelConfig] = None,
        provider: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        LLMを使用して応答を生成する汎用メソッド。

        Args:
            prompt: プロンプト
            model: 使用するモデル（指定がなければtask_configまたはデフォルト）
            force_json: JSON形式を強制するかどうか
            task_config: タスク設定（ModelConfig）
            provider: プロバイダー指定（"local" or "openai"）

        Returns:
            生成されたJSONレスポンス
        """
        resolved_provider = self._resolve_provider(task_config, provider)
        target_model = self._resolve_model(task_config, model, resolved_provider)

        logger.info(f"[Router] Provider: {resolved_provider}, Model: {target_model}")
        logger.debug(f"Prompt sent to LLM: {prompt[:200]}...")

        if resolved_provider == PROVIDER_OPENAI:
            return self._generate_openai(prompt, target_model, force_json)
        else:
            return self._generate_local(prompt, target_model)

    def _generate_openai(
        self,
        prompt: str,
        model: str,
        force_json: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Generate response using OpenAI API."""
        if not self.openai_client:
            logger.error("OpenAI client not available")
            return None

        try:
            if self._is_reasoning_model(model):
                # GPT-5 / o1 specific handling
                response = self.openai_client.responses.create(
                    model=model,
                    reasoning={"effort": "medium"},
                    input=[{"role": "user", "content": prompt}]
                )
                raw_text = self._extract_reasoning_response(response)
            else:
                kwargs = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": prompt}
                    ]
                }
                if force_json:
                    kwargs["response_format"] = {"type": "json_object"}

                response = self.openai_client.chat.completions.create(**kwargs)
                raw_text = response.choices[0].message.content.strip()

            logger.debug(f"OpenAI response: {raw_text[:200]}...")
            return self._extract_json(raw_text)

        except Exception as exc:
            logger.error(f"[✗] OpenAI API request failed: {exc}")
            return None

    def _extract_reasoning_response(self, response: Any) -> str:
        """Extract text from reasoning model response."""
        raw_text = ""
        try:
            if hasattr(response, "output") and isinstance(response.output, list):
                for item in response.output:
                    if hasattr(item, "type") and item.type == "message":
                        if hasattr(item, "content"):
                            for content_item in item.content:
                                if hasattr(content_item, "type") and content_item.type == "output_text":
                                    raw_text = content_item.text
                                    break
                    if raw_text:
                        break

            if not raw_text:
                logger.warning("Could not find output_text in response.output list")
                raw_text = str(response)

        except Exception as e:
            logger.error(f"Error parsing reasoning model response: {e}")
            raw_text = str(response)

        return raw_text

    def _generate_local(self, prompt: str, model: str) -> Optional[Dict[str, Any]]:
        """Generate response using local LLM (Ollama)."""
        if not self.local_available:
            logger.error("Local LLM not available")
            return None

        try:
            response = requests.post(
                self.local_api_url,
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=120,
            )
            response.raise_for_status()
            raw_text = response.json().get("response", "").strip()
            logger.debug(f"Local LLM response: {raw_text[:200]}...")
            return self._extract_json(raw_text)

        except Exception as exc:
            logger.error(f"[✗] Local LLM request failed: {exc}")
            return None

    def generate_json(
        self,
        prompt: str,
        model: Optional[str] = None,
        task_config: Optional[ModelConfig] = None,
        provider: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        JSON形式の応答を生成する。
        """
        return self.generate_response(
            prompt,
            model=model,
            force_json=True,
            task_config=task_config,
            provider=provider
        )

    # =========================================================================
    # Streaming Methods
    # =========================================================================

    async def generate_stream(
        self,
        prompt: str,
        model: Optional[str] = None,
        task_config: Optional[ModelConfig] = None,
        provider: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        LLMを使用してストリーミング応答を生成する。
        """
        resolved_provider = self._resolve_provider(task_config, provider)
        target_model = self._resolve_model(task_config, model, resolved_provider)

        logger.info(f"[Stream Router] Provider: {resolved_provider}, Model: {target_model}")

        if resolved_provider == PROVIDER_OPENAI:
            async for chunk in self._stream_openai(prompt, target_model):
                yield chunk
        else:
            async for chunk in self._stream_local(prompt, target_model):
                yield chunk

    async def _stream_openai(self, prompt: str, model: str) -> AsyncGenerator[str, None]:
        """Stream response from OpenAI."""
        if not self.async_openai_client:
            logger.error("OpenAI async client not available")
            yield ""
            return

        try:
            stream = await self.async_openai_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ],
                stream=True
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as exc:
            logger.error(f"[✗] OpenAI stream request failed: {exc}")
            yield ""

    async def _stream_local(self, prompt: str, model: str) -> AsyncGenerator[str, None]:
        """Stream response from local LLM (full response as single chunk)."""
        if not self.local_available:
            logger.error("Local LLM not available for streaming")
            yield ""
            return

        try:
            response = requests.post(
                self.local_api_url,
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=120,
            )
            response.raise_for_status()
            text = response.json().get("response", "")
            yield text
        except Exception as e:
            logger.error(f"Local LLM stream fallback failed: {e}")
            yield ""

    # =========================================================================
    # Embedding Methods
    # =========================================================================

    def get_embedding(
        self,
        text: str,
        embedding_config: Optional[EmbeddingConfig] = None,
        provider: Optional[str] = None
    ) -> List[float]:
        """
        テキストの埋め込みベクトルを生成する。

        Args:
            text: 入力テキスト
            embedding_config: Embedding設定（EmbeddingConfig）
            provider: プロバイダー指定（"local" or "openai"）

        Returns:
            埋め込みベクトル
        """
        # Use default embedding config if not specified
        if embedding_config is None:
            embedding_config = get_active_embedding_config()

        resolved_provider = self._resolve_provider(embedding_config, provider)
        model = embedding_config.model if embedding_config else settings.CLOUD_EMBEDDING_MODEL

        logger.debug(f"[Embedding Router] Provider: {resolved_provider}, Model: {model}")

        text = text.replace("\n", " ")

        if resolved_provider == PROVIDER_OPENAI:
            return self._get_embedding_openai(text, model)
        else:
            return self._get_embedding_local(text, model)

    def _get_embedding_openai(self, text: str, model: str) -> List[float]:
        """Get embedding from OpenAI API."""
        if not self.openai_client:
            logger.error("OpenAI client not available for embeddings")
            return []

        try:
            response = self.openai_client.embeddings.create(input=[text], model=model)
            return response.data[0].embedding
        except Exception as exc:
            logger.error(f"[✗] OpenAI Embedding request failed: {exc}")
            return []

    def _get_embedding_local(self, text: str, model: str) -> List[float]:
        """
        Get embedding from local LLM (Ollama).

        Ollama API for embeddings:
        POST /api/embed
        {
            "model": "mxbai-embed-large",
            "input": "text to embed"
        }
        """
        if not self.local_available:
            logger.error("Local LLM not available for embeddings")
            return []

        try:
            response = requests.post(
                self.local_embedding_url,
                json={"model": model, "input": text},
                timeout=60,
            )
            response.raise_for_status()
            result = response.json()

            # Ollama returns {"embeddings": [[...]]} for single input
            embeddings = result.get("embeddings", [])
            if embeddings and len(embeddings) > 0:
                return embeddings[0]

            # Fallback: try "embedding" key (older Ollama versions)
            embedding = result.get("embedding", [])
            if embedding:
                return embedding

            logger.warning(f"Unexpected embedding response format: {result.keys()}")
            return []

        except Exception as exc:
            logger.error(f"[✗] Local LLM Embedding request failed: {exc}")
            return []

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def is_provider_available(self, provider: str) -> bool:
        """Check if a specific provider is available."""
        if provider == PROVIDER_OPENAI:
            return self.openai_available
        elif provider == PROVIDER_LOCAL:
            return self.local_available
        return False

    def get_available_providers(self) -> List[str]:
        """Get list of available providers."""
        providers = []
        if self.openai_available:
            providers.append(PROVIDER_OPENAI)
        if self.local_available:
            providers.append(PROVIDER_LOCAL)
        return providers
