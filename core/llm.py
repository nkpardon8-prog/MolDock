import os

from openai import OpenAI

_client = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        key = os.getenv("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY not set")
        _client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=key,
            default_headers={
                "HTTP-Referer": "https://molecopilot.netlify.app",
                "X-Title": "MolCopilot",
            },
        )
    return _client


def complete(prompt: str, model: str, max_tokens: int = 2000) -> str:
    """Single-shot chat completion via OpenRouter (OpenAI-compatible)."""
    resp = get_client().chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.3,
    )
    return resp.choices[0].message.content or ""
