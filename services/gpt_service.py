from __future__ import annotations

import json
from typing import Any


class GPTService:
    def __init__(self, api_key: str, model: str) -> None:
        try:
            from openai import AsyncOpenAI, AuthenticationError, PermissionDeniedError  # type: ignore
        except ImportError as exc:  # pragma: no cover - environment guard
            raise RuntimeError("Package 'openai' is required. Install dependencies from requirements.txt") from exc
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._fatal_errors = (AuthenticationError, PermissionDeniedError)

    async def complete_json(
        self,
        *,
        name: str,
        instructions: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int = 3000,
        temperature: float = 0.4,
    ) -> dict[str, Any]:
        """Ответ модели строго по JSON-схеме: strict-режим не дает пропустить поле или сломать JSON."""
        last_error: Exception | None = None
        for _ in range(3):
            try:
                response = await self._client.responses.create(
                    model=self._model,
                    instructions=instructions,
                    input=prompt,
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                    text={"format": {"type": "json_schema", "name": name, "schema": schema, "strict": True}},
                )
                data = json.loads(response.output_text)
                if not isinstance(data, dict):
                    raise ValueError("LLM output is not an object")
                return data
            except self._fatal_errors:
                # Неверный ключ или нет доступа к модели — повтор не поможет.
                raise
            except Exception as exc:  # pragma: no cover - network/runtime guard
                last_error = exc
        raise RuntimeError(f"Failed to get valid response from model: {last_error}")

    async def analyze_photos(self, photo_urls: list[str], context_note: str = "") -> str:
        if not photo_urls:
            return ""
        prompt = (
            "Проанализируй фото человека для подбора подарка. "
            "Опиши только наблюдаемые и нейтральные сигналы: примерный стиль, аксессуары, "
            "возможные интересы по контексту, общую эстетику. "
            "Не делай чувствительных выводов и не упоминай запрещенные категории. "
            "Верни короткое резюме на русском языке, 4-6 пунктов."
        )
        if context_note.strip():
            prompt = f"{prompt}\nКонтекст: {context_note.strip()}"
        content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
        for url in photo_urls[:6]:
            content.append({"type": "input_image", "image_url": url})
        response = await self._client.responses.create(
            model=self._model,
            input=[{"role": "user", "content": content}],
            temperature=0.2,
            max_output_tokens=500,
        )
        return response.output_text.strip()
