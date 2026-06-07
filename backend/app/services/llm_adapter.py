"""
LLM Adapter — لایهٔ abstraction یکپارچه برای ارائه‌دهندگان مختلف مدل زبانی.

این ماژول یک رابط واحد برای کار با OpenAI، Perplexity Sonar و Google Gemini
فراهم می‌کند. هر provider پشت یک interface مشترک (BaseLLMProvider) قرار می‌گیرد
تا بقیهٔ سیستم (osint_agent، risk_engine، encyclopedia summarizer) مستقل از
provider واقعی کار کند و با env var قابل plug-in باشد.

قابلیت‌ها:
- chat / completion یکپارچه (sync + async)
- جستجوی آنلاین (Perplexity Sonar / online search models)
- embeddings (برای semantic search دانشنامه)
- structured output (JSON mode) برای risk classification
- retry با backoff نمایی
- شمارش توکن و گزارش usage
- انتخاب خودکار provider بر اساس قابلیت موردنیاز (search/embed/chat)
"""

from __future__ import annotations

import abc
import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, AsyncIterator, Callable, Iterable, Literal, Optional, TypeVar, cast

# External libraries
import httpx
import openai
import google.generativeai as genai
from google.generativeai.types import GenerationConfig
from openai import APIStatusError

logger = logging.getLogger("detective.llm_adapter")

# ---------------------------------------------------------------------------
# Optional config import (سازگار با backend/app/core/config.py)
# ---------------------------------------------------------------------------
try:  # pragma: no cover - config ممکن است در زمان تست موجود نباشد
    from app.core.config import settings as _app_settings  # type: ignore
except Exception:  # pragma: no cover
    _app_settings = None


def _cfg(name: str, default: Optional[str] = None) -> Optional[str]:
    """خواندن مقدار config از settings یا fallback به متغیر محیطی."""
    if _app_settings is not None and hasattr(_app_settings, name):
        val = getattr(_app_settings, name)
        if val is not None:
            return str(val)
    return os.getenv(name, default)


# ---------------------------------------------------------------------------
# Enums و Data classes
# ---------------------------------------------------------------------------
class LLMProviderName(str, Enum):
    OPENAI = "openai"
    PERPLEXITY = "perplexity"
    GEMINI = "gemini"


class ChatRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ChatMessage:
    role: ChatRole
    content: str
    tool_calls: Optional[list[dict]] = None
    tool_call_id: Optional[str] = None


@dataclass
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0


# ---------------------------------------------------------------------------
# Retry Logic
# ---------------------------------------------------------------------------

R = TypeVar("R")


def retry_with_exponential_backoff(
    max_retries: int = 5,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    status_codes: Optional[Iterable[int]] = None,
) -> Callable[[Callable[..., R]], Callable[..., R]]:
    """
    Decorator for retrying a function with exponential backoff on specific HTTP status codes or exceptions.
    """
    if status_codes is None:
        status_codes = {429, 500, 502, 503, 504}

    def decorator(func: Callable[..., R]) -> Callable[..., R]:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> R:
            delay = initial_delay
            for i in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except (openai.APITimeoutError, openai.APIConnectionError) as e:
                    logger.warning(
                        f"LLM API connection/timeout error on attempt {i+1}/{max_retries}: {e}"
                    )
                except openai.APIStatusError as e:
                    if e.status_code in status_codes:
                        logger.warning(
                            f"LLM API status error {e.status_code} on attempt {i+1}/{max_retries}: {e}"
                        )
                    else:
                        raise  # Re-raise for non-retryable status codes
                except httpx.HTTPStatusError as e:  # For Perplexity direct calls or other HTTP issues
                    if e.response.status_code in status_codes:
                        logger.warning(
                            f"HTTP status error {e.response.status_code} on attempt {i+1}/{max_retries}: {e}"
                        )
                    else:
                        raise
                except Exception as e:
                    # Catch other unexpected errors that might warrant a retry
                    logger.warning(
                        f"Unexpected error on attempt {i+1}/{max_retries}: {e}", exc_info=True
                    )

                if i < max_retries - 1:
                    logger.info(f"Retrying in {delay:.2f} seconds...")
                    await asyncio.sleep(delay)
                    delay *= backoff_factor
            logger.error(f"Max retries ({max_retries}) exceeded for {func.__name__}.")
            raise

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> R:
            delay = initial_delay
            for i in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (openai.APITimeoutError, openai.APIConnectionError) as e:
                    logger.warning(
                        f"LLM API connection/timeout error on attempt {i+1}/{max_retries}: {e}"
                    )
                except openai.APIStatusError as e:
                    if e.status_code in status_codes:
                        logger.warning(
                            f"LLM API status error {e.status_code} on attempt {i+1}/{max_retries}: {e}"
                        )
                    else:
                        raise
                except httpx.HTTPStatusError as e:
                    if e.response.status_code in status_codes:
                        logger.warning(
                            f"HTTP status error {e.response.status_code} on attempt {i+1}/{max_retries}: {e}"
                        )
                    else:
                        raise
                except Exception as e:
                    logger.warning(
                        f"Unexpected error on attempt {i+1}/{max_retries}: {e}", exc_info=True
                    )

                if i < max_retries - 1:
                    logger.info(f"Retrying in {delay:.2f} seconds...")
                    time.sleep(delay)
                    delay *= backoff_factor
            logger.error(f"Max retries ({max_retries}) exceeded for {func.__name__}.")
            raise

        # Check if the function is async
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        else:
            return sync_wrapper  # type: ignore

    return decorator


# ---------------------------------------------------------------------------
# Base LLM Provider Interface
# ---------------------------------------------------------------------------


class BaseLLMProvider(abc.ABC):
    """
    Abstract base class for all LLM providers.
    Defines a common interface for chat completion, embeddings, and optional search.
    """

    provider_name: LLMProviderName

    @abc.abstractmethod
    @retry_with_exponential_backoff()
    def chat_completion(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        stream: bool = False,
        tools: Optional[list[Any]] = None,
        tool_choice: Optional[str | dict | Any] = None,
        **kwargs: Any,
    ) -> str | Iterable[str]:
        """
        Synchronously gets a chat completion from the LLM.
        Returns a string for non-streaming, an iterable of strings for streaming.
        `tools` should conform to the specific provider's tool definition (e.g., OpenAI's `ChatCompletionToolParam` or Gemini's `Tool`).
        `tool_choice` should conform to the specific provider's tool choice definition.
        """
        raise NotImplementedError

    @abc.abstractmethod
    @retry_with_exponential_backoff()
    async def achat_completion(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        stream: bool = False,
        tools: Optional[list[Any]] = None,
        tool_choice: Optional[str | dict | Any] = None,
        **kwargs: Any,
    ) -> str | AsyncIterator[str]:
        """
        Asynchronously gets a chat completion from the LLM.
        Returns a string for non-streaming, an async iterable of strings for streaming.
        `tools` should conform to the specific provider's tool definition (e.g., OpenAI's `ChatCompletionToolParam` or Gemini's `Tool`).
        `tool_choice` should conform to the specific provider's tool choice definition.
        """
        raise NotImplementedError

    @abc.abstractmethod
    @retry_with_exponential_backoff()
    def get_embedding(self, text: str | list[str], model: str) -> list[list[float]]:
        """
        Synchronously gets embeddings for the given text.
        Returns a list of embedding vectors.
        """
        raise NotImplementedError

    @abc.abstractmethod
    @retry_with_exponential_backoff()
    async def aget_embedding(
        self, text: str | list[str], model: str
    ) -> list[list[float]]:
        """
        Asynchronously gets embeddings for the given text.
        Returns a list of embedding vectors.
        """
        raise NotImplementedError

    def supports_online_search(self) -> bool:
        """Indicates if the provider supports online search."""
        return False

    def supports_embeddings(self) -> bool:
        """Indicates if the provider supports embedding generation."""
        return False

    def supports_json_mode(self) -> bool:
        """Indicates if the provider supports structured JSON output."""
        return False

    # TODO: Implement token counting and cost estimation for each provider
    def _calculate_usage(self, response: Any) -> LLMUsage:
        """
        Calculates token usage and estimated cost from LLM response.
        This is a placeholder and needs specific implementation for each provider.
        """
        # Example for OpenAI: response.usage.prompt_tokens, response.usage.completion_tokens
        # For other models, this varies.
        return LLMUsage()


# ---------------------------------------------------------------------------
# OpenAI Provider
# ---------------------------------------------------------------------------


class OpenAIProvider(BaseLLMProvider):
    provider_name: LLMProviderName = LLMProviderName.OPENAI
    _async_client: Optional[openai.AsyncOpenAI] = None
    _sync_client: Optional[openai.OpenAI] = None

    def __init__(self):
        api_key = _cfg("OPENAI_API_KEY")
        if not api_key:
            logger.error("OPENAI_API_KEY is not set.")
            raise ValueError("OpenAI API key is required.")
        self.api_key = api_key
        self.default_model = _cfg("OPENAI_DEFAULT_MODEL", "gpt-4o-mini")
        self.embedding_model = _cfg("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    @property
    def async_client(self) -> openai.AsyncOpenAI:
        if self._async_client is None:
            self._async_client = openai.AsyncOpenAI(api_key=self.api_key)
        return self._async_client

    @property
    def sync_client(self) -> openai.OpenAI:
        if self._sync_client is None:
            self._sync_client = openai.OpenAI(api_key=self.api_key)
        return self._sync_client

    def _format_messages(self, messages: list[ChatMessage]) -> list[dict]:
        formatted = []
        for msg in messages:
            if msg.role == ChatRole.TOOL:
                formatted.append(
                    {"role": "tool", "tool_call_id": msg.tool_call_id, "content": msg.content}
                )
            elif msg.tool_calls:
                 formatted.append(
                    {"role": msg.role.value, "content": msg.content, "tool_calls": msg.tool_calls}
                 )
            else:
                formatted.append({"role": msg.role.value, "content": msg.content})
        return formatted

    def _process_response(self, response: Any, stream: bool) -> str | Iterable[str]:
        if stream:
            def generator():
                for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content is not None:
                        yield chunk.choices[0].delta.content
            return generator()
        else:
            return response.choices[0].message.content or ""

    async def _aprocess_response(
        self, response: Any, stream: bool
    ) -> str | AsyncIterator[str]:
        if stream:
            async def generator():
                async for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content is not None:
                        yield chunk.choices[0].delta.content
            return generator()
        else:
            return response.choices[0].message.content or ""

    @retry_with_exponential_backoff()
    def chat_completion(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        stream: bool = False,
        tools: Optional[list[Any]] = None,
        tool_choice: Optional[str | dict | Any] = None,
        **kwargs: Any,
    ) -> str | Iterable[str]:
        logger.debug(f"OpenAI chat completion (sync) with model: {model}")
        formatted_messages = self._format_messages(messages)
        completion_args: dict = {
            "model": model,
            "messages": formatted_messages,
            "temperature": temperature,
            "stream": stream,
            **kwargs,
        }
        if max_tokens:
            completion_args["max_tokens"] = max_tokens
        if json_mode:
            completion_args["response_format"] = {"type": "json_object"}
        if tools:
            completion_args["tools"] = tools
        if tool_choice:
            completion_args["tool_choice"] = tool_choice

        response = self.sync_client.chat.completions.create(**completion_args)
        return self._process_response(response, stream)

    @retry_with_exponential_backoff()
    async def achat_completion(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        stream: bool = False,
        tools: Optional[list[Any]] = None,
        tool_choice: Optional[str | dict | Any] = None,
        **kwargs: Any,
    ) -> str | AsyncIterator[str]:
        logger.debug(f"OpenAI chat completion (async) with model: {model}")
        formatted_messages = self._format_messages(messages)
        completion_args: dict = {
            "model": model,
            "messages": formatted_messages,
            "temperature": temperature,
            "stream": stream,
            **kwargs,
        }
        if max_tokens:
            completion_args["max_tokens"] = max_tokens
        if json_mode:
            completion_args["response_format"] = {"type": "json_object"}
        if tools:
            completion_args["tools"] = tools
        if tool_choice:
            completion_args["tool_choice"] = tool_choice

        response = await self.async_client.chat.completions.create(**completion_args)
        return await self._aprocess_response(response, stream)

    @retry_with_exponential_backoff()
    def get_embedding(self, text: str | list[str], model: str) -> list[list[float]]:
        logger.debug(f"OpenAI get embedding (sync) with model: {model}")
        response = self.sync_client.embeddings.create(input=text, model=model)
        return [item.embedding for item in response.data]

    @retry_with_exponential_backoff()
    async def aget_embedding(
        self, text: str | list[str], model: str
    ) -> list[list[float]]:
        logger.debug(f"OpenAI get embedding (async) with model: {model}")
        response = await self.async_client.embeddings.create(input=text, model=model)
        return [item.embedding for item in response.data]

    def supports_embeddings(self) -> bool:
        return True

    def supports_json_mode(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Perplexity Provider
# ---------------------------------------------------------------------------


class PerplexityProvider(BaseLLMProvider):
    provider_name: LLMProviderName = LLMProviderName.PERPLEXITY
    _async_client: Optional[openai.AsyncOpenAI] = None
    _sync_client: Optional[openai.OpenAI] = None

    def __init__(self):
        api_key = _cfg("PERPLEXITY_API_KEY")
        if not api_key:
            logger.error("PERPLEXITY_API_KEY is not set.")
            raise ValueError("Perplexity API key is required.")
        self.api_key = api_key
        self.base_url = "https://api.perplexity.ai"
        self.default_model = _cfg("PERPLEXITY_DEFAULT_MODEL", "sonar-small-online")
        # Perplexity does not offer a separate embedding API like OpenAI or Gemini.
        # Online models perform search implicitly.

    @property
    def async_client(self) -> openai.AsyncOpenAI:
        if self._async_client is None:
            self._async_client = openai.AsyncOpenAI(api_key=self.api_key, base_url=f"{self.base_url}/chat/completions")
        return self._async_client

    @property
    def sync_client(self) -> openai.OpenAI:
        if self._sync_client is None:
            self._sync_client = openai.OpenAI(api_key=self.api_key, base_url=f"{self.base_url}/chat/completions")
        return self._sync_client

    def _format_messages(self, messages: list[ChatMessage]) -> list[dict]:
        # Perplexity's API is largely compatible with OpenAI's message format.
        formatted = []
        for msg in messages:
            if msg.role == ChatRole.TOOL:
                # Perplexity models might not directly support the 'tool' role in the same way.
                # It's generally better to integrate tool output into a user message for Perplexity.
                # However, for consistency with OpenAI, we'll pass it as 'tool' and
                # rely on Perplexity's compatibility.
                formatted.append({"role": "tool", "tool_call_id": msg.tool_call_id, "content": msg.content})
            elif msg.tool_calls:
                 formatted.append(
                    {"role": msg.role.value, "content": msg.content, "tool_calls": msg.tool_calls}
                 )
            else:
                formatted.append({"role": msg.role.value, "content": msg.content})
        return formatted


    def _process_response(self, response: Any, stream: bool) -> str | Iterable[str]:
        if stream:
            def generator():
                for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content is not None:
                        yield chunk.choices[0].delta.content
            return generator()
        else:
            return response.choices[0].message.content or ""

    async def _aprocess_response(
        self, response: Any, stream: bool
    ) -> str | AsyncIterator[str]:
        if stream:
            async def generator():
                async for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content is not None:
                        yield chunk.choices[0].delta.content
            return generator()
        else:
            return response.choices[0].message.content or ""

    @retry_with_exponential_backoff()
    def chat_completion(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        stream: bool = False,
        tools: Optional[list[Any]] = None,
        tool_choice: Optional[str | dict | Any] = None,
        **kwargs: Any,
    ) -> str | Iterable[str]:
        logger.debug(f"Perplexity chat completion (sync) with model: {model}")
        if json_mode:
            logger.warning("PerplexityProvider: JSON mode is not directly supported. Attempting to force JSON output via prompt.")
            messages.append(ChatMessage(role=ChatRole.SYSTEM, content="You are a helpful assistant. Respond only with a valid JSON object."))
        
        if tools:
            logger.warning("PerplexityProvider: Custom tools are not directly supported via OpenAI-compatible API in the same way as OpenAI. Relying on model's inherent online capabilities.")

        formatted_messages = self._format_messages(messages)
        completion_args: dict = {
            "model": model,
            "messages": formatted_messages,
            "temperature": temperature,
            "stream": stream,
            **kwargs,
        }
        if max_tokens:
            completion_args["max_tokens"] = max_tokens

        # Perplexity's OpenAI-compatible endpoint does not support `response_format` directly.
        # We handle json_mode by prompt engineering.
        # Perplexity does not support tool_choice either.
        if tool_choice:
            logger.warning("PerplexityProvider: `tool_choice` is not directly supported via OpenAI-compatible API.")

        response = self.sync_client.chat.completions.create(**completion_args)
        return self._process_response(response, stream)

    @retry_with_exponential_backoff()
    async def achat_completion(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        stream: bool = False,
        tools: Optional[list[Any]] = None,
        tool_choice: Optional[str | dict | Any] = None,
        **kwargs: Any,
    ) -> str | AsyncIterator[str]:
        logger.debug(f"Perplexity chat completion (async) with model: {model}")
        if json_mode:
            logger.warning("PerplexityProvider: JSON mode is not directly supported. Attempting to force JSON output via prompt.")
            messages.append(ChatMessage(role=ChatRole.SYSTEM, content="You are a helpful assistant. Respond only with a valid JSON object."))
        
        if tools:
            logger.warning("PerplexityProvider: Custom tools are not directly supported via OpenAI-compatible API in the same way as OpenAI. Relying on model's inherent online capabilities.")
        if tool_choice:
            logger.warning("PerplexityProvider: `tool_choice` is not directly supported via OpenAI-compatible API.")

        formatted_messages = self._format_messages(messages)
        completion_args: dict = {
            "model": model,
            "messages": formatted_messages,
            "temperature": temperature,
            "stream": stream,
            **kwargs,
        }
        if max_tokens:
            completion_args["max_tokens"] = max_tokens

        response = await self.async_client.chat.completions.create(**completion_args)
        return await self._aprocess_response(response, stream)

    @retry_with_exponential_backoff()
    def get_embedding(self, text: str | list[str], model: str) -> list[list[float]]:
        logger.warning("PerplexityProvider does not natively support embeddings. Consider using a different provider for embedding tasks.")
        raise NotImplementedError("PerplexityProvider does not natively support embeddings.")

    @retry_with_exponential_backoff()
    async def aget_embedding(
        self, text: str | list[str], model: str
    ) -> list[list[float]]:
        logger.warning("PerplexityProvider does not natively support embeddings. Consider using a different provider for embedding tasks.")
        raise NotImplementedError("PerplexityProvider does not natively support embeddings.")

    def supports_online_search(self) -> bool:
        # Perplexity's "online" models inherently perform search
        return True

    def supports_embeddings(self) -> bool:
        return False # No dedicated embedding API

    def supports_json_mode(self) -> bool:
        return False # Not directly, only via prompt engineering


# ---------------------------------------------------------------------------
# Gemini Provider
# ---------------------------------------------------------------------------


class GeminiProvider(BaseLLMProvider):
    provider_name: LLMProviderName = LLMProviderName.GEMINI
    _model_cache: dict[str, genai.GenerativeModel] = field(default_factory=dict)

    def __init__(self):
        api_key = _cfg("GEMINI_API_KEY")
        if not api_key:
            logger.error("GEMINI_API_KEY is not set.")
            raise ValueError("Gemini API key is required.")
        genai.configure(api_key=api_key)
        self.default_model = _cfg("GEMINI_DEFAULT_MODEL", "gemini-pro")
        self.embedding_model = _cfg("GEMINI_EMBEDDING_MODEL", "embedding-001")

    def _get_model(self, model_name: str) -> genai.GenerativeModel:
        if model_name not in self._model_cache:
            self._model_cache[model_name] = genai.GenerativeModel(model_name=model_name)
        return self._model_cache[model_name]

    def _format_messages(self, messages: list[ChatMessage]) -> list[dict]:
        formatted = []
        for msg in messages:
            # Gemini's message format is slightly different, especially for system role
            # System instructions are often passed as a separate parameter or initial message
            # For simplicity, we'll map system to user for now if not using system instruction param
            role_map = {
                ChatRole.SYSTEM: "user",  # Gemini often handles system instructions separately
                ChatRole.USER: "user",
                ChatRole.ASSISTANT: "model",
                ChatRole.TOOL: "user", # Tool output often comes from user side in Gemini
            }
            # Gemini's `parts` can be a list of strings or dicts for tool_code, function_call etc.
            # For simplicity, we'll assume content is string.
            if msg.tool_calls:
                # Gemini expects tool calls in the model's response, and tool outputs in user message.
                # If a ChatMessage has tool_calls, it's an assistant message calling a tool.
                formatted.append({"role": "model", "parts": [{"function_call": tc} for tc in msg.tool_calls]})
            elif msg.tool_call_id:
                # This is a tool response, which Gemini expects as part of a user message.
                formatted.append({"role": "user", "parts": [{"function_response": {"name": msg.tool_call_id, "content": msg.content}}]})
            else:
                formatted.append({"role": role_map[msg.role], "parts": [msg.content]})
        return formatted
    
    def _process_response(self, response: Any, stream: bool) -> str | Iterable[str]:
        if stream:
            def generator():
                for chunk in response:
                    # Gemini streaming provides chunks with text attribute for content
                    # or `parts` for tool calls
                    if hasattr(chunk, 'text') and chunk.text:
                        yield chunk.text
                    elif hasattr(chunk, 'parts') and chunk.parts:
                        # Handle potential tool calls in streaming response
                        for part in chunk.parts:
                            if hasattr(part, 'function_call'):
                                yield json.dumps({"tool_call": part.function_call.to_dict()})
            return generator()
        else:
            if hasattr(response, 'text') and response.text:
                return response.text
            elif hasattr(response, 'parts') and response.parts:
                # Handle potential tool calls in non-streaming response
                tool_calls = []
                for part in response.parts:
                    if hasattr(part, 'function_call'):
                        tool_calls.append(part.function_call.to_dict())
                if tool_calls:
                    return json.dumps({"tool_calls": tool_calls})
            return ""

    async def _aprocess_response(
        self, response: Any, stream: bool
    ) -> str | AsyncIterator[str]:
        if stream:
            async def generator():
                async for chunk in response:
                    if hasattr(chunk, 'text') and chunk.text:
                        yield chunk.text
                    elif hasattr(chunk, 'parts') and chunk.parts:
                        for part in chunk.parts:
                            if hasattr(part, 'function_call'):
                                yield json.dumps({"tool_call": part.function_call.to_dict()})
            return generator()
        else:
            if hasattr(response, 'text') and response.text:
                return response.text
            elif hasattr(response, 'parts') and response.parts:
                tool_calls = []
                for part in response.parts:
                    if hasattr(part, 'function_call'):
                        tool_calls.append(part.function_call.to_dict())
                if tool_calls:
                    return json.dumps({"tool_calls": tool_calls})
            return ""

    @retry_with_exponential_backoff()
    def chat_completion(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        stream: bool = False,
        tools: Optional[list[Any]] = None,
        tool_choice: Optional[str | dict | Any] = None,
        **kwargs: Any,
    ) -> str | Iterable[str]:
        logger.debug(f"Gemini chat completion (sync) with model: {model}")
        gemini_model = self._get_model(model)
        
        generation_config = GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            response_mime_type="application/json" if json_mode else "text/plain",
            **kwargs
        )
        
        gemini_tools = None
        gemini_tool_config = None
        if tools:
            # Assuming `tools` are passed in a format convertible to Gemini's Tool type.
            # Example: [{"function_declarations": [{"name": "...", "description": "...", "parameters": {...}}]}]
            gemini_tools = tools 
            if tool_choice == "auto":
                gemini_tool_config = {"function_calling_config": {"mode": "AUTO"}}
            elif tool_choice == "none":
                gemini_tool_config = {"function_calling_config": {"mode": "NONE"}}
            elif isinstance(tool_choice, dict) and tool_choice.get("function"):
                 gemini_tool_config = {"function_calling_config": {"mode": "ANY", "allowed_function_names": [tool_choice["function"]["name"]]}}

        response = gemini_model.generate_content(
            contents=self._format_messages(messages),
            generation_config=generation_config,
            stream=stream,
            tools=gemini_tools,
            tool_config=gemini_tool_config
        )
        return self._process_response(response, stream)

    @retry_with_exponential_backoff()
    async def achat_completion(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        stream: bool = False,
        tools: Optional[list[Any]] = None,
        tool_choice: Optional[str | dict | Any] = None,
        **kwargs: Any,
    ) -> str | AsyncIterator[str]:
        logger.debug(f"Gemini chat completion (async) with model: {model}")
        gemini_model = self._get_model(model)

        generation_config = GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            response_mime_type="application/json" if json_mode else "text/plain",
            **kwargs
        )

        gemini_tools = None
        gemini_tool_config = None
        if tools:
            gemini_tools = tools
            if tool_choice == "auto":
                gemini_tool_config = {"function_calling_config": {"mode": "AUTO"}}
            elif tool_choice == "none":
                gemini_tool_config = {"function_calling_config": {"mode": "NONE"}}
            elif isinstance(tool_choice, dict) and tool_choice.get("function"):
                 gemini_tool_config = {"function_calling_config": {"mode": "ANY", "allowed_function_names": [tool_choice["function"]["name"]]}}

        response = await gemini_model.generate_content_async(
            contents=self._format_messages(messages),
            generation_config=generation_config,
            stream=stream,
            tools=gemini_tools,
            tool_config=gemini_tool_config
        )
        return await self._aprocess_response(response, stream)

    @retry_with_exponential_backoff()
    def get_embedding(self, text: str | list[str], model: str) -> list[list[float]]:
        logger.debug(f"Gemini get embedding (sync) with model: {model}")
        texts = [text] if isinstance(text, str) else text
        
        response = genai.embed_content(model=model, content=texts)
        # The response structure is `EmbedContentResponse` which has `embedding` attribute
        return [e for e in response["embedding"]]


    @retry_with_exponential_backoff()
    async def aget_embedding(
        self, text: str | list[str], model: str
    ) -> list[list[float]]:
        logger.debug(f"Gemini get embedding (async) with model: {model}")
        texts = [text] if isinstance(text, str) else text
        
        response = await genai.embed_content_async(model=model, content=texts)
        return [e for e in response["embedding"]]

    def supports_embeddings(self) -> bool:
        return True

    def supports_json_mode(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# LLM Provider Factory
# ---------------------------------------------------------------------------


class LLMProviderFactory:
    """
    Factory to get the appropriate LLM provider based on configuration
    or required capabilities.
    """

    _providers: dict[LLMProviderName, BaseLLMProvider] = {}

    @classmethod
    def get_provider(
        cls,
        provider_name: Optional[LLMProviderName] = None,
        capability: Optional[Literal["chat", "embedding", "search"]] = None,
    ) -> BaseLLMProvider:
        """
        Retrieves an LLM provider instance.
        If provider_name is None, it tries to determine the best provider
        based on LLM_DEFAULT_PROVIDER or required capability.
        """
        if provider_name is None:
            default_provider_str = _cfg("LLM_DEFAULT_PROVIDER")
            if default_provider_str:
                try:
                    provider_name = LLMProviderName(default_provider_str.lower())
                except ValueError:
                    logger.warning(
                        f"Invalid LLM_DEFAULT_PROVIDER '{default_provider_str}'. Falling back to capability-based selection."
                    )
            
            if provider_name is None and capability:
                # Try to find a provider that supports the required capability
                if capability == "embedding":
                    # OpenAI and Gemini support embeddings
                    if _cfg("OPENAI_API_KEY"):
                        provider_name = LLMProviderName.OPENAI
                    elif _cfg("GEMINI_API_KEY"):
                        provider_name = LLMProviderName.GEMINI
                elif capability == "search":
                    # Perplexity supports online search inherently
                    if _cfg("PERPLEXITY_API_KEY"):
                        provider_name = LLMProviderName.PERPLEXITY
                # For 'chat', any configured provider is fine, prefer default
                if provider_name is None: # If still no provider, try any configured for chat
                    if _cfg("OPENAI_API_KEY"):
                        provider_name = LLMProviderName.OPENAI
                    elif _cfg("PERPLEXITY_API_KEY"):
                        provider_name = LLMProviderName.PERPLEXITY
                    elif _cfg("GEMINI_API_KEY"):
                        provider_name = LLMProviderName.GEMINI
            
            if provider_name is None:
                raise ValueError(
                    "No LLM provider specified and no default or capability-matching provider found. "
                    "Please set LLM_DEFAULT_PROVIDER or ensure API keys are configured for desired capabilities."
                )

        if provider_name not in cls._providers:
            if provider_name == LLMProviderName.OPENAI:
                cls._providers[provider_name] = OpenAIProvider()
            elif provider_name == LLMProviderName.PERPLEXITY:
                cls._providers[provider_name] = PerplexityProvider()
            elif provider_name == LLMProviderName.GEMINI:
                cls._providers[provider_name] = GeminiProvider()
            else:
                raise ValueError(f"Unknown LLM provider: {provider_name}")

        return cls._providers[provider_name]

    @classmethod
    def get_chat_provider(cls) -> BaseLLMProvider:
        return cls.get_provider(capability="chat")

    @classmethod
    def get_embedding_provider(cls) -> BaseLLMProvider:
        return cls.get_provider(capability="embedding")

    @classmethod
    def get_search_provider(cls) -> BaseLLMProvider:
        return cls.get_provider(capability="search")