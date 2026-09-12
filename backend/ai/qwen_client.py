"""Small Qwen-compatible client abstraction.

No request is made unless a caller has supplied ``QWEN_API_KEY`` and disabled
the explicit ``MOCK_QWEN`` integration mode.  This keeps tests deterministic
and prevents a missing credential from becoming an accidental network call.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx


@dataclass(frozen=True)
class QwenSettings:
    api_key: Optional[str]
    base_url: str
    model: str
    mock: bool

    @classmethod
    def from_env(cls) -> "QwenSettings":
        raw_mock = os.getenv("MOCK_QWEN", "").strip().lower()
        return cls(
            api_key=os.getenv("QWEN_API_KEY") or None,
            base_url=os.getenv(
                "QWEN_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ).rstrip("/"),
            model=os.getenv("QWEN_MODEL", "qwen-plus"),
            mock=raw_mock in {"1", "true", "yes", "on"},
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key) and not self.mock


class QwenClient:
    """Qwen chat-completions client with an explicit mock mode."""

    def __init__(
        self,
        settings: Optional[QwenSettings] = None,
        *,
        timeout: float = 20.0,
    ) -> None:
        self.settings = settings or QwenSettings.from_env()
        self.timeout = timeout

    @property
    def is_mock(self) -> bool:
        return self.settings.mock

    @property
    def api_key(self) -> Optional[str]:
        return self.settings.api_key

    @property
    def base_url(self) -> str:
        return self.settings.base_url

    @property
    def model(self) -> str:
        return self.settings.model

    @property
    def is_configured(self) -> bool:
        return self.settings.configured

    def complete(
        self,
        messages: List[Dict[str, str]],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Return a model response, or an explicitly labelled mock response."""

        if self.settings.mock:
            return "[MOCK_QWEN] Deterministic integration mode; no external model was called."
        if not self.settings.api_key:
            raise RuntimeError(
                "QWEN_API_KEY is not configured; set MOCK_QWEN=true for deterministic tests"
            )

        payload: Dict[str, Any] = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": 0,
        }
        if tools:
            payload["tools"] = tools
        response = httpx.post(
            f"{self.settings.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
            },
            content=json.dumps(payload),
            timeout=self.timeout,
        )
        response.raise_for_status()
        body = response.json()
        try:
            return str(body["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Qwen response did not contain message content") from exc
