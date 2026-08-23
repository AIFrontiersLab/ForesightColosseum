from __future__ import annotations

import json
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config.settings import get_settings
from app.utils.logging import get_logger

log = get_logger("llm")
T = TypeVar("T", bound=BaseModel)


def extract_json(text: str) -> Any:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("empty LLM response")
    if raw.startswith("```"):
        lines = raw.splitlines()
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        raw = "\n".join(lines).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start : end + 1])
        start = raw.find("[")
        end = raw.rfind("]")
        if start >= 0 and end > start:
            return json.loads(raw[start : end + 1])
        raise


class TournamentLLM:
    def __init__(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
    ) -> None:
        settings = get_settings()
        self.provider = provider or settings.prediction_llm_provider
        self.model = model or settings.prediction_llm_model
        self.base_url = settings.prediction_llm_base_url.rstrip("/")
        self.temperature = temperature if temperature is not None else settings.prediction_llm_temperature
        self.timeout = settings.prediction_llm_timeout_seconds
        self.api_key = settings.openai_api_key
        self.max_retries = settings.prediction_llm_max_retries

    def available(self) -> bool:
        if self.provider == "ollama":
            try:
                native = self.base_url.removesuffix("/v1")
                with httpx.Client(timeout=5) as client:
                    response = client.get(f"{native}/api/tags")
                    response.raise_for_status()
                return True
            except Exception:
                return False
        return bool(self.api_key)

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
    def complete(self, system: str, user: str, *, json_mode: bool = True) -> str:
        log.stage(f"calling {self.provider} model={self.model} (timeout={self.timeout}s)")
        if self.provider == "openai":
            text = self._openai_complete(system, user, json_mode=json_mode)
        else:
            text = self._ollama_complete(system, user, json_mode=json_mode)
        log.stage(f"{self.provider} response received ({len(text)} chars)")
        return text

    def complete_json(self, system: str, user: str) -> Any:
        return extract_json(self.complete(system, user, json_mode=True))

    def complete_model(self, system: str, user: str, model: type[T]) -> T:
        return model.model_validate(self.complete_json(system, user))

    def _ollama_complete(self, system: str, user: str, *, json_mode: bool) -> str:
        native = self.base_url.removesuffix("/v1")
        payload: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "options": {"temperature": self.temperature},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            payload["format"] = "json"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(f"{native}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        return (data.get("message") or {}).get("content") or ""

    def _openai_complete(self, system: str, user: str, *, json_mode: bool) -> str:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY required for openai provider")
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        url = (
            self.base_url
            if self.base_url.endswith("/chat/completions")
            else f"{self.base_url}/chat/completions"
        )
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        return data["choices"][0]["message"]["content"]


def load_prompt(name: str) -> str:
    settings = get_settings()
    path = settings.prompts_dir / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"prompt not found: {path}")
    return path.read_text(encoding="utf-8")
