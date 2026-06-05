import json
from typing import Any

from openai import OpenAI

from app.core.config import Settings


class LlmClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.mock = settings.use_mock_llm or not settings.openai_api_key
        self.client: OpenAI | None = None
        if not self.mock and settings.openai_api_key:
            self.client = OpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
            )

    def status(self) -> dict[str, Any]:
        return {
            "mode": "mock" if self.mock else "real",
            "use_mock_llm": self.settings.use_mock_llm,
            "api_key_configured": bool(self.settings.openai_api_key),
            "base_url_configured": bool(self.settings.openai_base_url),
            "model": self.settings.openai_model,
        }

    def test_connection(self) -> dict[str, Any]:
        status = self.status()
        if self.mock:
            message = (
                "Mock mode is enabled."
                if self.settings.use_mock_llm
                else "OPENAI_API_KEY is missing, so the backend falls back to mock mode."
            )
            return {**status, "success": self.settings.use_mock_llm, "message": message}
        try:
            payload = self.generate_json(
                "Return JSON only. The JSON object must be exactly compatible with this request.",
                {"task": "connection_test", "expected": {"ok": True}},
            )
        except Exception as exc:  # pragma: no cover - network/provider dependent
            return {**status, "success": False, "message": str(exc)}
        return {
            **status,
            "success": True,
            "message": f"Connected to {self.settings.openai_model}. Response keys: {', '.join(payload.keys()) or 'none'}.",
        }

    def generate_json(self, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        if self.mock:
            raise RuntimeError("Mock LLM does not generate remote JSON.")
        if self.client is None:
            raise RuntimeError("LLM client is not configured.")
        response = self.client.chat.completions.create(
            model=self.settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("LLM returned empty content.")
        return json.loads(content)
