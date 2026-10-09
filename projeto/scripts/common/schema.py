"""
Modelos de dados compartilhados entre as etapas do pipeline. Todos os arquivos .jsonl
trocados entre scripts seguem (aproximadamente) estes esquemas — úteis tanto como
documentação quanto para validação leve ao carregar/salvar.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional


def read_jsonl(path: Path) -> Iterator[dict]:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_jsonl(path: Path, rows: Iterable[dict], mode: str = "w") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, mode, encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


@dataclass
class CodeSample:
    """Uma amostra do benchmark: um trecho/arquivo de código com (ou sem) vulnerabilidade
    conhecida, usado como unidade de análise por todas as abordagens (A/B/C)."""

    sample_id: str                      # id único e estável (ex.: "rpb-0007" ou "jsts-0031")
    source_benchmark: str                # "repopairbench" | "cvefixes_jsts"
    language: str                        # "python" | "javascript" | "typescript"
    repo: str                            # owner/repo de origem
    commit_vulnerable: str               # sha do commit vulnerável
    commit_fixed: Optional[str] = None   # sha do commit corrigido (None se não aplicável)
    file_path: str = ""                  # caminho do arquivo dentro do repo
    code: str = ""                       # conteúdo do arquivo/trecho no estado vulnerável
    is_vulnerable: bool = True           # True = contém a vulnerabilidade (gabarito positivo)
    cwe_id: Optional[str] = None         # ex.: "CWE-89"
    cve_id: Optional[str] = None         # ex.: "CVE-2023-12345" (quando existir)
    vulnerable_lines: list[int] = field(default_factory=list)  # linhas marcadas como vulneráveis
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DetectionResult:
    """Resultado de uma abordagem (A, B ou C) para UMA amostra, de UM "detector" (ferramenta
    SAST, LLM, ou mecanismo de triagem)."""

    sample_id: str
    approach: str          # "A_sast" | "B_llm" | "C_triage"
    detector: str          # "semgrep" | "codeql" | "claude" | "gemini" | "jev" | "jury"
    predicted_vulnerable: bool
    predicted_cwe: Optional[str] = None
    confidence: Optional[float] = None     # 0-1, quando o detector fornecer
    raw_output: str = ""                   # saída crua (texto do LLM, JSON do SAST) p/ auditoria
    latency_seconds: Optional[float] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    estimated_cost_usd: Optional[float] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SastFinding:
    """Um achado bruto de uma ferramenta SAST, antes da triagem (Abordagem C)."""

    sample_id: str
    tool: str               # "semgrep" | "codeql"
    rule_id: str
    cwe_id: Optional[str]
    line_start: int
    line_end: int
    message: str
    severity: str = ""
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)
