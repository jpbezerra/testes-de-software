#!/usr/bin/env python
"""
Abordagem C — triagem dos achados brutos do SAST (results/sast_findings.jsonl, gerado pelo
script 03) usando:

  C.1  Jev (TypeSafe AI)        — classificador rápido/barato, veredito único por achado.
  C.2  jury-as-a-judge          — painel Claude + Gemini, cada um dá um veredito
                                   independente sobre o MESMO achado; agregação por voto
                                   majoritário (e, como métrica auxiliar, média de
                                   confiança) decide o veredito final do jury.

Para cada achado do SAST, produz um DetectionResult por mecanismo de triagem
(detector="jev" | "jury"), já no "sample_id" original — ou seja, perguntando "depois da
triagem, este achado continua de pé (true_positive) ou foi descartado (false_positive)?".
Uma amostra com múltiplos achados do SAST é considerada "vulnerável segundo a triagem X"
se PELO MENOS UM achado sobreviver à triagem como true_positive.

Uso:
    python scripts/05_run_triage.py --sast-findings results/sast_findings.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common.config import DATA_DIR, RESULTS_DIR  # noqa: E402
from common.llm_clients import call_claude, call_gemini, call_jev  # noqa: E402
from common.prompts import JURY_SYSTEM_PROMPT, TRIAGE_JEV_SYSTEM_PROMPT, build_triage_user_prompt  # noqa: E402
from common.schema import DetectionResult, read_jsonl, write_jsonl  # noqa: E402

JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_verdict_json(text: str) -> dict:
    match = JSON_BLOCK_RE.search(text)
    if not match:
        raise ValueError(f"Resposta sem JSON reconhecível: {text[:200]!r}")
    return json.loads(match.group(0))


def load_code_by_sample_id() -> dict[str, dict]:
    """Carrega todas as amostras já processadas (RepoPairBench + JS/TS) para recuperar o
    trecho de código correspondente a cada achado do SAST, pelo sample_id."""
    by_id = {}
    for sub in ("repopairbench", "jsts_sample"):
        path = DATA_DIR / sub / "samples.jsonl"
        if path.exists():
            for s in read_jsonl(path):
                by_id[s["sample_id"]] = s
    return by_id


def snippet_for_finding(sample: dict, finding: dict, context_lines: int = 5) -> str:
    lines = sample["code"].splitlines()
    start = max(0, finding["line_start"] - 1 - context_lines)
    end = min(len(lines), finding["line_end"] + context_lines)
    numbered = [f"{i+1}: {lines[i]}" for i in range(start, end)]
    return "\n".join(numbered)


def triage_with_jev(sample: dict, finding: dict) -> DetectionResult:
    prompt = build_triage_user_prompt(
        tool=finding["tool"], rule_id=finding["rule_id"], cwe_id=finding.get("cwe_id") or "desconhecido",
        message=finding["message"], line_start=finding["line_start"], line_end=finding["line_end"],
        language=sample["language"], code_snippet=snippet_for_finding(sample, finding),
    )
    resp = call_jev(TRIAGE_JEV_SYSTEM_PROMPT, prompt)
    if resp.error or resp.text is None:
        return DetectionResult(
            sample_id=sample["sample_id"], approach="C_triage", detector="jev",
            predicted_vulnerable=False, error=resp.error, latency_seconds=resp.latency_seconds,
        )
    try:
        parsed = parse_verdict_json(resp.text)
        return DetectionResult(
            sample_id=sample["sample_id"], approach="C_triage", detector="jev",
            predicted_vulnerable=parsed.get("verdict") == "true_positive",
            predicted_cwe=finding.get("cwe_id"),
            confidence=parsed.get("confidence"),
            raw_output=resp.text, latency_seconds=resp.latency_seconds,
            input_tokens=resp.input_tokens, output_tokens=resp.output_tokens,
            estimated_cost_usd=resp.estimated_cost_usd,
        )
    except (ValueError, json.JSONDecodeError) as exc:
        return DetectionResult(
            sample_id=sample["sample_id"], approach="C_triage", detector="jev",
            predicted_vulnerable=False, raw_output=resp.text, error=f"parse_error: {exc}",
        )


def triage_with_jury(sample: dict, finding: dict) -> DetectionResult:
    prompt = build_triage_user_prompt(
        tool=finding["tool"], rule_id=finding["rule_id"], cwe_id=finding.get("cwe_id") or "desconhecido",
        message=finding["message"], line_start=finding["line_start"], line_end=finding["line_end"],
        language=sample["language"], code_snippet=snippet_for_finding(sample, finding),
    )
    votes = []
    confidences = []
    raw_outputs = {}
    for name, fn in (("claude", call_claude), ("gemini", call_gemini)):
        resp = fn(JURY_SYSTEM_PROMPT, prompt)
        raw_outputs[name] = resp.text or f"ERROR: {resp.error}"
        if resp.text:
            try:
                parsed = parse_verdict_json(resp.text)
                votes.append(parsed.get("verdict") == "true_positive")
                if parsed.get("confidence") is not None:
                    confidences.append(float(parsed["confidence"]))
            except (ValueError, json.JSONDecodeError):
                pass

    if not votes:
        return DetectionResult(
            sample_id=sample["sample_id"], approach="C_triage", detector="jury",
            predicted_vulnerable=False, error="nenhum voto válido do painel",
            raw_output=json.dumps(raw_outputs, ensure_ascii=False),
        )

    majority = sum(votes) > len(votes) / 2
    avg_confidence = sum(confidences) / len(confidences) if confidences else None
    return DetectionResult(
        sample_id=sample["sample_id"], approach="C_triage", detector="jury",
        predicted_vulnerable=majority, predicted_cwe=finding.get("cwe_id"),
        confidence=avg_confidence, raw_output=json.dumps(raw_outputs, ensure_ascii=False),
    )


def aggregate_per_sample(results: list[DetectionResult], detector_name: str) -> list[DetectionResult]:
    """Um achado sobrevivendo como true_positive já marca a amostra inteira como
    'vulnerável segundo esta triagem' (ver docstring do módulo)."""
    by_sample: dict[str, list[DetectionResult]] = defaultdict(list)
    for r in results:
        by_sample[r.sample_id].append(r)

    aggregated = []
    for sample_id, items in by_sample.items():
        any_tp = any(i.predicted_vulnerable for i in items)
        confidences = [i.confidence for i in items if i.confidence is not None]
        aggregated.append(
            DetectionResult(
                sample_id=sample_id, approach="C_triage", detector=detector_name,
                predicted_vulnerable=any_tp,
                confidence=max(confidences) if confidences and any_tp else (
                    min(confidences) if confidences else None
                ),
                raw_output=json.dumps([i.to_dict() for i in items], ensure_ascii=False),
            )
        )
    return aggregated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sast-findings", type=str, default=str(RESULTS_DIR / "sast_findings.jsonl"))
    parser.add_argument("--mechanisms", nargs="+", default=["jev", "jury"], choices=["jev", "jury"])
    args = parser.parse_args()

    findings = list(read_jsonl(Path(args.sast_findings)))
    if not findings:
        print(f"[aviso] Nenhum achado em {args.sast_findings}. Rode scripts/03_run_sast.py antes.")
        return

    code_by_sample = load_code_by_sample_id()

    per_finding_jev: list[DetectionResult] = []
    per_finding_jury: list[DetectionResult] = []

    for finding in tqdm(findings, desc="Triando achados do SAST"):
        sample = code_by_sample.get(finding["sample_id"])
        if sample is None:
            print(f"[aviso] sample_id {finding['sample_id']} não encontrado nos dados de origem; pulando achado.")
            continue
        if "jev" in args.mechanisms:
            per_finding_jev.append(triage_with_jev(sample, finding))
        if "jury" in args.mechanisms:
            per_finding_jury.append(triage_with_jury(sample, finding))

    all_detections: list[DetectionResult] = []
    if per_finding_jev:
        all_detections += aggregate_per_sample(per_finding_jev, "jev")
    if per_finding_jury:
        all_detections += aggregate_per_sample(per_finding_jury, "jury")

    write_jsonl(RESULTS_DIR / "detection_C_triage.jsonl", (d.to_dict() for d in all_detections))
    write_jsonl(RESULTS_DIR / "triage_raw_per_finding.jsonl", (
        d.to_dict() for d in (per_finding_jev + per_finding_jury)
    ))
    print(f"[ok] {len(all_detections)} resultados agregados -> results/detection_C_triage.jsonl")


if __name__ == "__main__":
    main()
