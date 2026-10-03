"""Foundry / Azure AI model client with routing across GPT, Claude, Kimi, Grok."""
import json as _json
import os
from typing import Any

import httpx

from app.config import settings
from app.models import ModelChoice


class FoundryClient:
    def __init__(self) -> None:
        self.project_endpoint = settings.azure_ai_project_endpoint.rstrip("/")
        self.api_key = settings.azure_ai_api_key or os.environ.get("AZURE_AI_API_KEY")
        self.models = {
            ModelChoice.GPT: settings.model_gpt,
            ModelChoice.CLAUDE: settings.model_claude,
            ModelChoice.KIMI: settings.model_kimi,
            ModelChoice.GROK: settings.model_grok,
        }

    def _endpoint(self, model: ModelChoice) -> str:
        # All models are accessed through the Azure OpenAI endpoint using the v1 route.
        # The deployment name is passed in the request body as `model`.
        base = settings.azure_openai_endpoint or self.project_endpoint
        return f"{base.rstrip('/')}/openai/v1/chat/completions"

    async def chat(
        self,
        model: ModelChoice,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        stream: bool = False,
    ) -> str:
        headers = {
            "Content-Type": "application/json",
            "api-key": self.api_key or "",
        }
        payload: dict[str, Any] = {
            "messages": messages,
            "model": self.models[model],
            "stream": stream,
        }
        # GPT (o-series / reasoning models) does not support temperature or max_tokens.
        if model == ModelChoice.GPT:
            payload["max_completion_tokens"] = max_tokens
        else:
            payload["temperature"] = temperature
            payload["max_tokens"] = max_tokens

        async with httpx.AsyncClient(timeout=httpx.Timeout(600)) as client:
            resp = await client.post(self._endpoint(model), headers=headers, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Model {model.value} error {resp.status_code}: {resp.text}"
                )
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def translate_chunk(
        self,
        model: ModelChoice,
        text: str,
        target_language: str,
        glossary: dict[str, str],
        previous_context: str = "",
        mode: str = "standard",
    ) -> str:
        system_prompt = self._build_system_prompt(target_language, glossary, mode)
        user_prompt = self._build_user_prompt(text, previous_context)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        # Use lower temperature for consistency.
        temperature = 0.2 if mode != "literary" else 0.35
        try:
            return await self.chat(model, messages, temperature=temperature)
        except RuntimeError as exc:
            err_text = str(exc).lower()
            # Fallback to GPT if selected model is unavailable/rate-limited.
            if model != ModelChoice.GPT and (
                "not supported" in err_text or "ratelimit" in err_text or "rate limit" in err_text
            ):
                return await self.chat(ModelChoice.GPT, messages, temperature=temperature)
            raise

    def _build_system_prompt(self, target_language: str, glossary: dict[str, str], mode: str) -> str:
        tone = {
            "standard": "natural and fluent",
            "literary": "literary, preserving style, rhythm, and voice",
            "technical": "precise and consistent, preserving terminology",
            "fast": "natural and fluent",
        }.get(mode, "natural and fluent")

        glossary_lines = "\n".join(
            [f"- {source}: {target}" for source, target in glossary.items()]
        )

        return (
            f"You are a professional translator translating from English to {target_language}.\n"
            f"Tone: {tone}.\n"
            "Rules:\n"
            "- Translate every sentence fully. Do not summarize, omit, or add explanations.\n"
            "- Preserve paragraph breaks, emphasis, and dialogue formatting.\n"
            "- Use the glossary below consistently. Do not translate glossary terms differently.\n"
            "- Keep names, places, and proper nouns consistent with the glossary.\n"
            "- Output only the translated text, no metadata, no preamble.\n"
            f"Glossary:\n{glossary_lines or '(none provided)' }"
        )

    def _build_user_prompt(self, text: str, previous_context: str) -> str:
        context_section = ""
        if previous_context:
            context_section = (
                "The following is the previous translated context for consistency:\n"
                f"{previous_context}\n\n"
            )
        return f"{context_section}Translate the following text:\n\n{text}"

    async def extract_glossary(
        self,
        sample_text: str,
        target_language: str,
        model: ModelChoice = ModelChoice.GPT,
    ) -> dict[str, str]:
        system_prompt = (
            "You are a literary translation assistant. Given a sample of an English text, "
            f"extract a glossary of proper nouns, recurring terms, and specialized vocabulary for translation into {target_language}. "
            "Return ONLY a JSON object mapping English terms to their target-language equivalents. "
            "Do not include explanations, markdown, or comments."
        )
        user_prompt = (
            "Extract a translation glossary from this sample:\n\n"
            f"{sample_text[:8000]}\n\n"
            "Return JSON: {\"source_term\": \"target_term\"}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        response = await self.chat(model, messages, max_tokens=2048)

        try:
            glossary = _json.loads(response)
            return {str(k): str(v) for k, v in glossary.items()}
        except _json.JSONDecodeError:
            # Fallback: try to extract first JSON-like block.
            start = response.find("{")
            end = response.rfind("}")
            if start != -1 and end != -1:
                return _json.loads(response[start : end + 1])
            return {}
