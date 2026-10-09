"""
Configuração central do pipeline: carrega variáveis de ambiente (.env), define caminhos
padrão e constantes usadas por todos os scripts (CWEs de interesse, linguagens no escopo,
etc.).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Raiz do projeto = pasta "projeto/" (duas pastas acima de scripts/common/config.py)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RESULTS_DIR = PROJECT_ROOT / "results"
LOGS_DIR = PROJECT_ROOT / "logs"

for _d in (DATA_DIR, RESULTS_DIR, LOGS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

load_dotenv(PROJECT_ROOT / ".env")


def _env_int(name: str, default: int) -> int:
    val = os.getenv(name)
    return int(val) if val else default


def _env_float(name: str, default: float) -> float:
    val = os.getenv(name)
    return float(val) if val else default


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    claude_model: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-5")

    google_api_key: str = os.getenv("GOOGLE_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")

    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    jev_model: str = os.getenv("JEV_MODEL", "typesafe/jev-latest")

    request_timeout_seconds: int = _env_int("REQUEST_TIMEOUT_SECONDS", 60)
    max_retries: int = _env_int("MAX_RETRIES", 3)
    retry_backoff_seconds: int = _env_int("RETRY_BACKOFF_SECONDS", 5)
    llm_temperature: float = _env_float("LLM_TEMPERATURE", 0.0)
    random_seed: int = _env_int("RANDOM_SEED", 42)


SETTINGS = Settings()

# Escopo de linguagens do estudo (ver "Artigo - Testes de Software.md" > Metodologia)
LANGUAGES_IN_SCOPE = ["python", "javascript", "typescript"]

# CWEs priorizados na amostragem estratificada (ajustar com o time conforme o que o
# RepoPairBench/CVEfixes realmente cobrirem — esta lista é um ponto de partida, não final)
PRIORITY_CWES = [
    "CWE-79",   # XSS
    "CWE-89",   # SQL Injection
    "CWE-22",   # Path Traversal
    "CWE-78",   # OS Command Injection
    "CWE-94",   # Code Injection
    "CWE-502",  # Insecure Deserialization
    "CWE-798",  # Hard-coded Credentials
    "CWE-611",  # XXE
    "CWE-918",  # SSRF
    "CWE-862",  # Missing Authorization
]
