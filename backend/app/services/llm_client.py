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
