#!/usr/bin/env python
"""
Teste de fumaça (smoke test): valida que o ambiente está configurado corretamente ANTES
de rodar qualquer coisa cara (downloads de GBs, coleta completa com custo de API).

Verifica, em ordem:
  1. Dependências Python instaladas (import das libs principais).
  2. Semgrep no PATH.
  3. CodeQL no PATH (aviso, não erro — é opcional).
  4. Uma chamada MÍNIMA (poucos tokens, custo de fração de centavo) para cada LLM
     configurado em .env: Claude, Gemini e Jev — para confirmar que as chaves de API
     funcionam antes de gastar dinheiro/tempo na coleta real.

Uso:
    python scripts/00_smoke_test.py
    python scripts/00_smoke_test.py --skip-llm      # só checa dependências/ferramentas
    python scripts/00_smoke_test.py --only claude    # testa só uma LLM específica
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common.config import SETTINGS  # noqa: E402

PING_SYSTEM = "Responda apenas com a palavra 'OK', nada mais."
PING_USER = "ping"


def check_dependencies() -> bool:
    ok = True
    deps = ["anthropic", "google.genai", "requests", "pandas", "numpy", "statsmodels", "tenacity", "tqdm", "dotenv"]
    for mod in deps:
        try:
            __import__(mod)
            print(f"  [ok] import {mod}")
        except ImportError as exc:
            print(f"  [FALHOU] import {mod}: {exc}")
            ok = False
    return ok


def check_cli_tools() -> None:
    semgrep_path = shutil.which("semgrep")
    print(f"  [{'ok' if semgrep_path else 'FALHOU'}] semgrep {'-> ' + semgrep_path if semgrep_path else '(não encontrado no PATH)'}")
    codeql_path = shutil.which("codeql")
    print(f"  [{'ok' if codeql_path else 'aviso'}] codeql {'-> ' + codeql_path if codeql_path else '(não encontrado — ok se não for usar --tools codeql)'}")


def check_claude() -> bool:
    if not SETTINGS.anthropic_api_key:
        print("  [FALHOU] ANTHROPIC_API_KEY vazia em .env")
        return False
    from common.llm_clients import call_claude
    resp = call_claude(PING_SYSTEM, PING_USER, max_tokens=10)
    if resp.error:
        print(f"  [FALHOU] Claude ({SETTINGS.claude_model}): {resp.error}")
        return False
    print(f"  [ok] Claude ({SETTINGS.claude_model}) respondeu: {resp.text!r} "
          f"(latência {resp.latency_seconds:.2f}s, custo ~${resp.estimated_cost_usd or 0:.6f})")
    return True


def check_gemini() -> bool:
    if not SETTINGS.google_api_key:
        print("  [FALHOU] GOOGLE_API_KEY vazia em .env")
        return False
    from common.llm_clients import call_gemini
    resp = call_gemini(PING_SYSTEM, PING_USER)
    if resp.error:
        print(f"  [FALHOU] Gemini ({SETTINGS.gemini_model}): {resp.error}")
        print(
            "           Se o erro mencionar modelo não encontrado (404/NOT_FOUND), o nome do "
            "modelo em GEMINI_MODEL (.env) pode estar desatualizado — confira os nomes atuais "
            "em https://ai.google.dev/gemini-api/docs/models e ajuste o .env."
        )
        return False
    print(f"  [ok] Gemini ({SETTINGS.gemini_model}) respondeu: {resp.text!r} "
          f"(latência {resp.latency_seconds:.2f}s, custo ~${resp.estimated_cost_usd or 0:.6f})")
    return True


def check_jev() -> bool:
    if not SETTINGS.openrouter_api_key:
        print("  [FALHOU] OPENROUTER_API_KEY vazia em .env")
        return False
    from common.llm_clients import call_jev
    resp = call_jev(PING_SYSTEM, PING_USER)
    if resp.error:
        print(f"  [FALHOU] Jev ({SETTINGS.jev_model}): {resp.error}")
        print(
            "           Se o erro mencionar modelo não encontrado, confirme o slug atual do Jev "
            "no OpenRouter (https://openrouter.ai/models?q=jev) e ajuste JEV_MODEL no .env."
        )
        return False
    print(f"  [ok] Jev ({SETTINGS.jev_model}) respondeu: {resp.text!r} "
          f"(latência {resp.latency_seconds:.2f}s, custo ~${resp.estimated_cost_usd or 0:.6f})")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-llm", action="store_true", help="pula os testes de API (só checa deps/ferramentas)")
    parser.add_argument("--only", choices=["claude", "gemini", "jev"], default=None)
    args = parser.parse_args()

    print("1. Dependências Python")
    deps_ok = check_dependencies()

    print("\n2. Ferramentas de linha de comando")
    check_cli_tools()

    all_llm_ok = True
    if not args.skip_llm:
        print("\n3. Chamadas mínimas às APIs de LLM (custo desprezível, poucos tokens)")
        checks = {"claude": check_claude, "gemini": check_gemini, "jev": check_jev}
        targets = [args.only] if args.only else list(checks.keys())
        for name in targets:
            all_llm_ok = checks[name]() and all_llm_ok

    print("\n" + "=" * 60)
    if deps_ok and all_llm_ok:
        print("[RESULTADO] Tudo certo — pode seguir para o teste com dados (ver data/samples/toy.jsonl).")
    else:
        print("[RESULTADO] Há falhas acima — resolva-as antes de rodar a coleta real.")


if __name__ == "__main__":
    main()
