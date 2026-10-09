#!/usr/bin/env python
"""
Abordagem A — roda ferramentas SAST (Semgrep, e opcionalmente CodeQL) sobre cada
CodeSample do conjunto de entrada, produzindo:

1. results/sast_findings.jsonl  — achados brutos (schema common.schema.SastFinding),
   usados depois pela triagem (Abordagem C, script 05).
2. results/detection_A_sast.jsonl — um DetectionResult por (amostra, ferramenta),
   com predicted_vulnerable = True se a ferramenta gerou >=1 achado para a amostra
   (comparável diretamente com as Abordagens B/C no script 07).

Requisitos: Semgrep (`pip install semgrep`, já no requirements.txt) e, para --tools codeql,
o CodeQL CLI instalado e no PATH (ver link no erro impresso se estiver ausente).

Uso:
    python scripts/03_run_sast.py --input data/samples/pilot.jsonl
    python scripts/03_run_sast.py --input data/samples/pilot.jsonl --tools semgrep
    python scripts/03_run_sast.py --input data/samples/pilot.jsonl --tools semgrep codeql
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


CODEQL_LANGUAGE_BY_OUR_LANGUAGE = {
    "python": "python",
    "javascript": "javascript",
    "typescript": "javascript",  # o pack "javascript" do CodeQL cobre TS também
}
CODEQL_QUERY_PACK_BY_LANGUAGE = {
    "python": "codeql/python-queries",
    "javascript": "codeql/javascript-queries",
}


def _codeql_sarif_to_findings(sample_id: str, sarif: dict) -> list[SastFinding]:
    """Converte um resultado SARIF (produzido por `codeql database analyze
    --format=sarif-latest`) em SastFinding. Formato SARIF: run.results[*] com
    ruleId, message.text, locations[*].physicalLocation.region.{startLine,endLine}."""
    findings = []
    for run in sarif.get("runs", []):
        # Mapa ruleId -> propriedades da regra (para extrair CWE/severidade quando presentes)
        rules_by_id = {}
        for tool_component in [run.get("tool", {}).get("driver", {})] + run.get("tool", {}).get("extensions", []):
            for rule in tool_component.get("rules", []):
                rules_by_id[rule.get("id")] = rule

        for result in run.get("results", []):
            rule_id = result.get("ruleId", "")
            rule_props = rules_by_id.get(rule_id, {}).get("properties", {})
            tags = rule_props.get("tags", [])
            cwe_id = next((t.upper().replace("EXTERNAL/CWE/CWE-", "CWE-") for t in tags if "cwe" in t.lower()), None)

            locations = result.get("locations", [])
            region = locations[0].get("physicalLocation", {}).get("region", {}) if locations else {}
            findings.append(
                SastFinding(
                    sample_id=sample_id,
                    tool="codeql",
                    rule_id=rule_id,
                    cwe_id=cwe_id,
                    line_start=region.get("startLine", 0),
                    line_end=region.get("endLine", region.get("startLine", 0)),
                    message=result.get("message", {}).get("text", ""),
                    severity=rule_props.get("problem.severity", ""),
                    raw=result,
                )
            )
    return findings


def run_codeql(sample_id: str, code: str, language: str, keep_tmp: bool = False) -> list[SastFinding]:
    """Roda o CodeQL CLI de ponta a ponta sobre UMA amostra: cria um projeto de arquivo
    único em um diretório temporário, compila um banco de dados CodeQL, analisa com o
    query pack padrão da linguagem e converte o SARIF resultante em SastFinding.

    Requisitos (ver active_attack/README.md — não, este é scripts/README; ver seção
    "Setup" do README principal): CodeQL CLI instalado e no PATH
    (https://github.com/github/codeql-action/releases ou
    https://docs.github.com/en/code-security/codeql-cli/getting-started-with-the-codeql-cli/setting-up-the-codeql-cli).
    Os query packs são baixados automaticamente na primeira execução via `--download`
    (comando confirmado na documentação oficial do GitHub).

    Nota de desempenho: criar um banco de dados CodeQL por amostra tem overhead alto
    (ordem de segundos por amostra, mesmo para um arquivo isolado) porque o CodeQL
    compila/extrai um modelo relacional do código a cada chamada. Para um piloto de
    20-30 amostras isso é tranquilo; para a coleta completa (200-300 amostras),
    considerar paralelizar (ver `--threads` do CodeQL) ou, alternativamente, agrupar
    amostras do mesmo repo/linguagem em um único banco de dados multi-arquivo.
    """
    codeql_lang = CODEQL_LANGUAGE_BY_OUR_LANGUAGE.get(language)
    query_pack = CODEQL_QUERY_PACK_BY_LANGUAGE.get(codeql_lang)
    if codeql_lang is None or query_pack is None:
        print(f"[aviso] CodeQL: linguagem '{language}' não mapeada, pulando amostra.")
        return []

    tmp_root = Path(tempfile.mkdtemp(prefix="codeql_sample_"))
    src_dir = tmp_root / "src"
    src_dir.mkdir()
    db_dir = tmp_root / "db"
    sarif_path = tmp_root / "results.sarif"

    suffix = EXT_BY_LANGUAGE.get(language, ".txt")
    source_file = src_dir / f"sample{suffix}"
    source_file.write_text(code, encoding="utf-8")

    try:
        subprocess.run(
            [
                "codeql", "database", "create", str(db_dir),
                f"--language={codeql_lang}",
                f"--source-root={src_dir}",
                "--overwrite",
            ],
            capture_output=True, text=True, timeout=300, check=True,
        )
        subprocess.run(
            [
                "codeql", "database", "analyze", str(db_dir), query_pack,
                "--format=sarif-latest", f"--output={sarif_path}",
                "--download",  # baixa o query pack automaticamente se não estiver em disco
            ],
            capture_output=True, text=True, timeout=300, check=True,
        )
        sarif = json.loads(sarif_path.read_text(encoding="utf-8"))
        return _codeql_sarif_to_findings(sample_id, sarif)
    except subprocess.CalledProcessError as exc:
        print(f"[erro] CodeQL falhou: {exc.stderr[:500] if exc.stderr else exc}")
        return []
    except subprocess.TimeoutExpired:
        print("[erro] CodeQL excedeu o tempo limite (300s) nesta amostra.")
        return []
    finally:
        if not keep_tmp:
            shutil.rmtree(tmp_root, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=str, required=True)
    parser.add_argument("--tools", nargs="+", default=["semgrep"], choices=["semgrep", "codeql"])
    args = parser.parse_args()

    if shutil.which("semgrep") is None and "semgrep" in args.tools:
        print("[erro] 'semgrep' não encontrado no PATH. Rode: pip install semgrep")
        return
    if shutil.which("codeql") is None and "codeql" in args.tools:
        print(
            "[erro] 'codeql' não encontrado no PATH. Instale o CodeQL CLI: "
            "https://docs.github.com/en/code-security/codeql-cli/getting-started-with-the-codeql-cli/setting-up-the-codeql-cli "
            "e garanta que o binário esteja no PATH antes de rodar com --tools codeql."
        )
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
            sample_findings += run_codeql(sample["sample_id"], sample["code"], sample["language"])

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
