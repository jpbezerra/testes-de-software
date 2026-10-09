#!/usr/bin/env python
"""
Abordagem A — roda ferramentas SAST (Semgrep, e opcionalmente CodeQL) sobre cada
CodeSample do conjunto de entrada, produzindo:

1. results/sast_findings.jsonl  — achados brutos (schema common.schema.SastFinding),
   usados depois pela triagem (Abordagem C, script 05).
2. results/detection_A_sast.jsonl — um DetectionResult por (amostra, ferramenta),
   com predicted_vulnerable = True se a ferramenta gerou >=1 achado para a amostra
   (comparável diretamente com as Abordagens B/C no script 07).

Uso:
    python scripts/03_run_sast.py --input data/samples/pilot.jsonl
    python scripts/03_run_sast.py --input data/samples/pilot.jsonl --tools semgrep
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common.config import RESULTS_DIR  # noqa: E402
from common.schema import DetectionResult, SastFinding, read_jsonl, write_jsonl  # noqa: E402

EXT_BY_LANGUAGE = {"python": ".py", "javascript": ".js", "typescript": ".ts"}

# Config padrão de regras do Semgrep: usa os rulesets públicos de segurança por linguagem.
# Pode ser trocado por um registro próprio do time (ex.: "p/owasp-top-ten").
SEMGREP_CONFIGS = ["p/security-audit", "p/owasp-top-ten"]


def run_semgrep(code: str, language: str) -> list[dict]:
    """Roda o Semgrep em modo CLI sobre um arquivo temporário e devolve os achados crus
    (lista de dicts no formato do `--json` do Semgrep)."""
    suffix = EXT_BY_LANGUAGE.get(language, ".txt")
    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8") as tmp:
        tmp.write(code)
        tmp_path = tmp.name
    try:
        cmd = ["semgrep", "--json", "--quiet"]
        for cfg in SEMGREP_CONFIGS:
            cmd += ["--config", cfg]
        cmd.append(tmp_path)
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if not proc.stdout.strip():
            return []
        data = json.loads(proc.stdout)
        return data.get("results", [])
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def semgrep_result_to_finding(sample_id: str, raw: dict) -> SastFinding:
    extra = raw.get("extra", {})
    metadata = extra.get("metadata", {})
    cwe = metadata.get("cwe")
    cwe_id = cwe[0] if isinstance(cwe, list) and cwe else (cwe if isinstance(cwe, str) else None)
    return SastFinding(
        sample_id=sample_id,
        tool="semgrep",
        rule_id=raw.get("check_id", ""),
        cwe_id=cwe_id,
        line_start=raw.get("start", {}).get("line", 0),
        line_end=raw.get("end", {}).get("line", 0),
        message=extra.get("message", ""),
        severity=extra.get("severity", ""),
        raw=raw,
    )


def run_codeql(code: str, language: str) -> list[dict]:
    """Placeholder para o CodeQL. CodeQL exige um banco de dados compilado por projeto
    (não roda direto sobre um snippet isolado como o Semgrep), então a integração real
    depende de decidir, com o time, se cada CodeSample será analisado como projeto
    standalone (mais fiel, mais lento) ou se o CodeQL será pulado em favor de só Semgrep
    (mais simples, ainda defensável citando a limitação em "Ameaças à Validade").

    TODO equipe: se decidirem incluir CodeQL,
      1. instalar o CodeQL CLI (https://github.com/github/codeql-cli-binaries) e os
         query packs oficiais (`codeql pack download codeql/python-queries` etc.);
      2. para cada amostra, criar um "mini-projeto" de um arquivo só, rodar
         `codeql database create <db> --language=<lang> --source-root=<dir>`,
         depois `codeql database analyze <db> <query-pack> --format=sarif-latest -o out.sarif`;
      3. parsear o SARIF e converter para SastFinding, igual ao Semgrep acima.
    Por ora, devolve lista vazia (não quebra o pipeline; a ausência aparece nos logs).
    """
    return []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=str, required=True)
    parser.add_argument("--tools", nargs="+", default=["semgrep"], choices=["semgrep", "codeql"])
    args = parser.parse_args()

    if shutil.which("semgrep") is None and "semgrep" in args.tools:
        print("[erro] 'semgrep' não encontrado no PATH. Rode: pip install semgrep")
        return

    samples = list(read_jsonl(Path(args.input)))
    findings: list[SastFinding] = []
    detections: list[DetectionResult] = []

    for sample in samples:
        sample_findings: list[SastFinding] = []

        if "semgrep" in args.tools:
            raw_results = run_semgrep(sample["code"], sample["language"])
            sample_findings += [semgrep_result_to_finding(sample["sample_id"], r) for r in raw_results]

        if "codeql" in args.tools:
            sample_findings += run_codeql(sample["code"], sample["language"])  # placeholder (lista vazia)

        findings.extend(sample_findings)

        by_tool: dict[str, list[SastFinding]] = {}
        for f in sample_findings:
            by_tool.setdefault(f.tool, []).append(f)
        for tool in args.tools:
            tool_findings = by_tool.get(tool, [])
            detections.append(
                DetectionResult(
                    sample_id=sample["sample_id"],
                    approach="A_sast",
                    detector=tool,
                    predicted_vulnerable=len(tool_findings) > 0,
                    predicted_cwe=tool_findings[0].cwe_id if tool_findings else None,
                    raw_output=json.dumps([f.to_dict() for f in tool_findings], ensure_ascii=False),
                )
            )
        print(f"[{sample['sample_id']}] achados: {len(sample_findings)}")

    write_jsonl(RESULTS_DIR / "sast_findings.jsonl", (f.to_dict() for f in findings))
    write_jsonl(RESULTS_DIR / "detection_A_sast.jsonl", (d.to_dict() for d in detections))
    print(
        f"[ok] {len(findings)} achados brutos -> results/sast_findings.jsonl\n"
        f"[ok] {len(detections)} resultados de detecção -> results/detection_A_sast.jsonl"
    )


if __name__ == "__main__":
    main()
