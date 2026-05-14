"""LLM clients for presentation analysis.

Both DeepSeek and xAI Grok expose an OpenAI-compatible chat-completions API,
so they share the same retry/validation pipeline through
``OpenAICompatibleClient``. The response is strictly validated against
``LLMReport`` (see :mod:`app.checker.llm_schema`); on schema failure we send
one corrective follow-up before giving up.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any

from openai import OpenAI
from pydantic import ValidationError

from app.checker.llm_schema import LLMReport

logger = logging.getLogger(__name__)

_PROMPT_INJECTION = re.compile(
    r'(?i)(ignore|override|forget|disregard).{0,50}(instruction|prompt|rule|system)'
)
_MAX_USER_CHARS = 12000

_REPAIR_INSTRUCTION = (
    'Твой предыдущий ответ не прошёл валидацию JSON-схемы. '
    'Верни ТОЛЬКО валидный JSON со следующими полями (без markdown, без комментариев):\n'
    '{\n'
    '  "score": number 0..10,\n'
    '  "criteria": {"structure": 0..10, "platform_design": 0..10, '
    '"usp": 0..10, "competitor_analysis": 0..10, "vk_ads": 0..10},\n'
    '  "criteria_feedback": {"structure": string, "platform_design": string, '
    '"usp": string, "competitor_analysis": string, "vk_ads": string},\n'
    '  "feedback": string,\n'
    '  "strengths": [string, ...],\n'
    '  "weaknesses": [string, ...]\n'
    '}'
)

_EXPAND_INSTRUCTION = (
    'Твой ответ валиден, но слишком краткий. '
    'Перепиши тот же JSON, расширив комментарии:\n'
    '— каждое поле в criteria_feedback: минимум 3 предложения и ~150 символов, '
    'с конкретными наблюдениями и рекомендациями;\n'
    '— feedback: 3–5 предложений, минимум ~200 символов;\n'
    '— strengths и weaknesses: минимум по 2 конкретных пункта.\n'
    'Сохрани те же численные оценки. Верни ТОЛЬКО JSON, без markdown.'
)


def _sanitize_user_text(text: str) -> str:
    text = _PROMPT_INJECTION.sub('[REDACTED]', text)
    return text[:_MAX_USER_CHARS]


class LLMResponseError(RuntimeError):
    """Raised when the LLM repeatedly fails to return a valid response."""


class LLMConfigError(RuntimeError):
    """Raised when the selected provider is not configured (missing API key)."""


class OpenAICompatibleClient:
    """Common pipeline for any OpenAI-compatible chat-completions backend."""

    BASE_URL: str = ''
    DEFAULT_MODEL: str = ''
    PROVIDER_NAME: str = ''

    def __init__(
        self,
        api_key: str,
        model: str | None = None,
        max_retries: int = 3,
        timeout: int = 120,
    ) -> None:
        self._client = OpenAI(api_key=api_key, base_url=self.BASE_URL)
        self._model = model or self.DEFAULT_MODEL
        self._max_retries = max_retries
        self._timeout = timeout

    @property
    def model(self) -> str:
        return self._model

    def analyze_presentation(self, text: str, system_prompt: str = '') -> dict[str, Any]:
        user_text = _sanitize_user_text(text)
        messages: list[dict[str, str]] = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_text},
        ]

        report: LLMReport | None = None
        last_content: str = ''
        last_error: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                content = self._chat(messages)
                last_content = content
            except Exception as exc:
                last_error = exc
                logger.warning(
                    '%s API error (attempt %d): %s',
                    self.PROVIDER_NAME, attempt, exc,
                )
                self._backoff(attempt)
                continue

            try:
                payload = json.loads(content)
                report = LLMReport.model_validate(payload)
                break
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
                logger.warning(
                    '%s response did not match schema (attempt %d): %s\nRaw (first 500 chars): %s',
                    self.PROVIDER_NAME, attempt, exc, content[:500],
                )
                messages = [
                    *messages,
                    {'role': 'assistant', 'content': content},
                    {'role': 'user', 'content': _REPAIR_INSTRUCTION},
                ]
                self._backoff(attempt)

        if report is None:
            raise LLMResponseError(
                f'{self.PROVIDER_NAME}: failed after {self._max_retries} retries. '
                f'Last error: {last_error}'
            )

        if report.is_too_terse():
            logger.info(
                '%s response is terser than desired; asking for expansion.',
                self.PROVIDER_NAME,
            )
            expanded = self._try_expand(messages, last_content)
            if expanded is not None:
                report = expanded

        return report.to_normalized_dict()

    def _try_expand(
        self,
        messages: list[dict[str, str]],
        last_content: str,
    ) -> LLMReport | None:
        """Single best-effort follow-up call asking the model to elaborate."""
        follow_up = [
            *messages,
            {'role': 'assistant', 'content': last_content},
            {'role': 'user', 'content': _EXPAND_INSTRUCTION},
        ]
        try:
            content = self._chat(follow_up)
            payload = json.loads(content)
            return LLMReport.model_validate(payload)
        except Exception as exc:
            logger.warning(
                '%s expansion follow-up failed (using original answer): %s',
                self.PROVIDER_NAME, exc,
            )
            return None

    MAX_COMPLETION_TOKENS = 4096

    def _chat(self, messages: list[dict[str, str]]) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            timeout=self._timeout,
            response_format={'type': 'json_object'},
            max_tokens=self.MAX_COMPLETION_TOKENS,
        )
        return (response.choices[0].message.content or '').strip()

    @staticmethod
    def _backoff(attempt: int) -> None:
        time.sleep(min(2 ** attempt, 10))


class DeepSeekClient(OpenAICompatibleClient):
    BASE_URL = 'https://api.deepseek.com'
    DEFAULT_MODEL = 'deepseek-chat'
    PROVIDER_NAME = 'DeepSeek'


class GrokClient(OpenAICompatibleClient):
    BASE_URL = 'https://api.x.ai/v1'
    DEFAULT_MODEL = 'grok-4-1-fast-reasoning'
    PROVIDER_NAME = 'Grok'


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    label: str
    cls: type[OpenAICompatibleClient]
    api_key_env: str
    model_env: str


PROVIDERS: dict[str, ProviderSpec] = {
    'deepseek': ProviderSpec(
        key='deepseek',
        label='DeepSeek',
        cls=DeepSeekClient,
        api_key_env='DEEPSEEK_API_KEY',
        model_env='DEEPSEEK_MODEL',
    ),
    'grok': ProviderSpec(
        key='grok',
        label='Grok',
        cls=GrokClient,
        api_key_env='GROK_API_KEY',
        model_env='GROK_MODEL',
    ),
}

DEFAULT_PROVIDER = 'deepseek'


def get_provider_spec(provider: str | None) -> ProviderSpec:
    if not provider:
        return PROVIDERS[DEFAULT_PROVIDER]
    spec = PROVIDERS.get(provider.lower())
    if spec is None:
        raise LLMConfigError(f'Unknown LLM provider: {provider}')
    return spec


def is_provider_configured(provider: str, config: dict[str, Any] | None = None) -> bool:
    try:
        spec = get_provider_spec(provider)
    except LLMConfigError:
        return False
    config = config or {}
    return bool(config.get(spec.api_key_env) or os.environ.get(spec.api_key_env, ''))


def list_providers(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return UI-friendly metadata for every known provider."""
    config = config or {}
    items: list[dict[str, Any]] = []
    for spec in PROVIDERS.values():
        items.append({
            'key': spec.key,
            'label': spec.label,
            'configured': bool(
                config.get(spec.api_key_env) or os.environ.get(spec.api_key_env, '')
            ),
        })
    return items


def create_client(
    provider: str | None,
    config: dict[str, Any] | None = None,
) -> OpenAICompatibleClient:
    spec = get_provider_spec(provider)
    config = config or {}
    api_key = config.get(spec.api_key_env) or os.environ.get(spec.api_key_env, '')
    if not api_key:
        raise LLMConfigError(f'{spec.api_key_env} is not configured.')
    model = (
        config.get(spec.model_env)
        or os.environ.get(spec.model_env)
        or spec.cls.DEFAULT_MODEL
    )
    return spec.cls(api_key=api_key, model=model)


__all__ = [
    'OpenAICompatibleClient',
    'DeepSeekClient',
    'GrokClient',
    'ProviderSpec',
    'PROVIDERS',
    'DEFAULT_PROVIDER',
    'LLMResponseError',
    'LLMConfigError',
    'create_client',
    'get_provider_spec',
    'is_provider_configured',
    'list_providers',
]
