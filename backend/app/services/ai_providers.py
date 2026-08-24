from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class ProviderReply:
    content: str
    provider: str
    model: str



async def ollama_chat(*, base_url: str, model: str, messages: list[dict[str, str]], timeout: float = 600.0, think: bool | None = None, num_ctx: int = 8192, num_predict: int = 512, temperature: float = 0.2) -> ProviderReply:
    if not model.strip():
        raise RuntimeError("Не выбрана модель Ollama")
    endpoint = base_url.rstrip("/") + "/api/chat"
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "keep_alive": "10m",
        # Most Ollama installs default to 4096. ContentDesk keeps prompts small,
        # while 8192 gives the coordinator enough room for a project summary.
        "options": {"num_ctx": num_ctx, "num_predict": num_predict, "temperature": temperature},
    }
    # Thinking is chosen by the AI role. Coordinator/editor use a fast path;
    # SEO/fact-checking may enable reasoning for DeepSeek-R1.
    if think is not None:
        payload["think"] = think
    elif model.lower().startswith(("deepseek-r1", "qwen3")):
        payload["think"] = False
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
            response = await client.post(endpoint, json=payload)
            if response.is_error:
                detail = response.text[:1200].strip()
                raise RuntimeError(f"Ollama /api/chat: HTTP {response.status_code}{': ' + detail if detail else ''}")
            data = response.json()
    except httpx.TimeoutException as exc:
        raise RuntimeError(f"Ollama не успела ответить за {int(timeout)} сек. Возможно, модель ещё загружается или не хватает ресурсов.") from exc
    except httpx.ConnectError as exc:
        raise RuntimeError(f"Не удалось подключиться к Ollama по адресу {base_url}") from exc
    message = data.get("message") or {}
    content = str(message.get("content") or "").strip()
    # Совместимость с reasoning-моделями/старыми версиями Ollama, где ответ
    # иногда возвращается только в поле thinking.
    if not content:
        content = str(message.get("thinking") or data.get("response") or "").strip()
    if not content:
        raise RuntimeError("Ollama ответила, но не вернула текст. Проверь версию Ollama и выбранную модель.")
    return ProviderReply(content=content, provider="ollama", model=model)


async def ollama_status(base_url: str, model: str = "", probe_chat: bool = True) -> dict[str, Any]:
    endpoint = base_url.rstrip("/") + "/api/tags"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(endpoint)
            response.raise_for_status()
            data = response.json()
        models = [str(x.get("name", "")) for x in data.get("models", [])]
        matched_name = next((x for x in models if x == model or (model and x.startswith(model + ":"))), "")
        result: dict[str, Any] = {
            "online": True, "models": models,
            "model_available": bool(matched_name) if model else None,
            "matched_model": matched_name or None, "chat_available": None, "chat_error": "",
        }
        if probe_chat and model and matched_name:
            try:
                reply = await ollama_chat(
                    base_url=base_url, model=matched_name,
                    messages=[{"role": "user", "content": "Ответь одним словом: работает"}], timeout=300.0,
                )
                result["chat_available"] = bool(reply.content)
            except Exception as exc:
                result["chat_available"] = False
                result["chat_error"] = str(exc)
        return result
    except Exception as exc:
        return {"online": False, "models": [], "model_available": False, "chat_available": False, "chat_error": "", "error": str(exc)}
