"""
Wrappers finos sobre os clientes de LLM usados no experimento:

- Claude (Anthropic API)         -> usado como detector (Abordagem B) e no jury (Abordagem C)
- Gemini (Google AI Studio API)  -> usado como detector (Abordagem B) e no jury (Abordagem C)
- Jev (TypeSafe AI, via OpenRouter, API OpenAI-compatível) -> usado na triagem (Abordagem C)

Cada wrapper devolve uma tupla (texto_da_resposta, metadados) onde metadados inclui
latência, tokens de entrada/saída (quando a API expõe) e um custo estimado (quando os
preços estiverem configurados). Nenhum wrapper lança exceção para erros de API — eles
devolvem (None, {"error": "..."}) para que o chamador decida como tratar (retry, pular
amostra, etc.) sem quebrar uma coleta longa.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import SETTINGS

# Preços por milhão de tokens (USD) — AJUSTE conforme os preços vigentes no momento da
# coleta; estes são apenas valores de referência para a estimativa de custo do experimento,
# não são usados para nenhuma decisão de negócio.
PRICE_PER_MILLION_TOKENS = {
    # modelo: (preço_input, preço_output)
    "claude-sonnet-5": (3.0, 15.0),            # ver https://docs.claude.com/ (verificar antes da coleta final)
    "gemini-2.5-pro": (1.25, 5.0),             # ver https://ai.google.dev/pricing (verificar antes da coleta final)
    "typesafe/jev-latest": (0.042, 0.042),     # confirmado em pesquisa anterior do projeto
}


@dataclass
class LLMResponse:
    text: Optional[str]
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    latency_seconds: Optional[float] = None
    estimated_cost_usd: Optional[float] = None
    error: Optional[str] = None


def _estimate_cost(model_key: str, input_tokens: Optional[int], output_tokens: Optional[int]) -> Optional[float]:
    if model_key not in PRICE_PER_MILLION_TOKENS or input_tokens is None or output_tokens is None:
        return None
    price_in, price_out = PRICE_PER_MILLION_TOKENS[model_key]
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000


# --------------------------------------------------------------------------------------
# Claude (Anthropic API)
# --------------------------------------------------------------------------------------

def _get_anthropic_client():
    import anthropic  # import local para não exigir a dependência se não for usada

    if not SETTINGS.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY não configurada em .env")
    return anthropic.Anthropic(api_key=SETTINGS.anthropic_api_key)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=30))
def _call_claude(client, model: str, system: str, user_prompt: str, max_tokens: int):
    return client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=SETTINGS.llm_temperature,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
    )


def call_claude(system_prompt: str, user_prompt: str, max_tokens: int = 2048) -> LLMResponse:
    start = time.time()
    try:
        client = _get_anthropic_client()
        resp = _call_claude(client, SETTINGS.claude_model, system_prompt, user_prompt, max_tokens)
        text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
        in_tok = getattr(resp.usage, "input_tokens", None)
        out_tok = getattr(resp.usage, "output_tokens", None)
        return LLMResponse(
            text=text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            latency_seconds=time.time() - start,
            estimated_cost_usd=_estimate_cost(SETTINGS.claude_model, in_tok, out_tok),
        )
    except Exception as exc:  # noqa: BLE001 - queremos capturar qualquer falha de API aqui
        return LLMResponse(text=None, latency_seconds=time.time() - start, error=str(exc))


# --------------------------------------------------------------------------------------
# Gemini (Google AI Studio API, via SDK google-genai)
# --------------------------------------------------------------------------------------

def _get_gemini_client():
    from google import genai  # import local

    if not SETTINGS.google_api_key:
        raise RuntimeError("GOOGLE_API_KEY não configurada em .env")
    return genai.Client(api_key=SETTINGS.google_api_key)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=30))
def _call_gemini(client, model: str, system: str, user_prompt: str):
    from google.genai import types  # import local

    return client.models.generate_content(
        model=model,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=SETTINGS.llm_temperature,
        ),
    )


def call_gemini(system_prompt: str, user_prompt: str) -> LLMResponse:
    start = time.time()
    try:
        client = _get_gemini_client()
        resp = _call_gemini(client, SETTINGS.gemini_model, system_prompt, user_prompt)
        text = resp.text
        usage = getattr(resp, "usage_metadata", None)
        in_tok = getattr(usage, "prompt_token_count", None) if usage else None
        out_tok = getattr(usage, "candidates_token_count", None) if usage else None
        return LLMResponse(
            text=text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            latency_seconds=time.time() - start,
            estimated_cost_usd=_estimate_cost(SETTINGS.gemini_model, in_tok, out_tok),
        )
    except Exception as exc:  # noqa: BLE001
        return LLMResponse(text=None, latency_seconds=time.time() - start, error=str(exc))


# --------------------------------------------------------------------------------------
# Jev (TypeSafe AI) via OpenRouter — API OpenAI-compatível (POST /chat/completions)
# --------------------------------------------------------------------------------------

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=30))
def _call_jev_raw(system_prompt: str, user_prompt: str):
    if not SETTINGS.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY não configurada em .env")
    headers = {
        "Authorization": f"Bearer {SETTINGS.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": SETTINGS.jev_model,
        "temperature": SETTINGS.llm_temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    resp = requests.post(
        OPENROUTER_URL, headers=headers, json=payload, timeout=SETTINGS.request_timeout_seconds
    )
    resp.raise_for_status()
    return resp.json()


def call_jev(system_prompt: str, user_prompt: str) -> LLMResponse:
    """Chama o Jev. NOTA: Jev é um modelo de decisão (não gerativo), então o prompt deve
    pedir explicitamente um veredito curto e estruturado (ver common/prompts.py,
    `TRIAGE_JEV_SYSTEM_PROMPT`) — a resposta esperada é um JSON pequeno com
    {"verdict": "true_positive"|"false_positive", "confidence": 0-1}, não um texto livre.
    """
    start = time.time()
    try:
        data = _call_jev_raw(system_prompt, user_prompt)
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        in_tok = usage.get("prompt_tokens")
        out_tok = usage.get("completion_tokens")
        return LLMResponse(
            text=text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            latency_seconds=time.time() - start,
            estimated_cost_usd=_estimate_cost(SETTINGS.jev_model, in_tok, out_tok),
        )
    except Exception as exc:  # noqa: BLE001
        return LLMResponse(text=None, latency_seconds=time.time() - start, error=str(exc))
