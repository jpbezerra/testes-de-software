#!/usr/bin/env python
"""
Junta o gabarito (CodeSample.is_vulnerable/cwe_id) com os resultados de todas as
abordagens (A, B, C) em uma única tabela larga, uma linha por (sample_id, detector),
pronta para o cálculo de métricas (script 07) e para exportação/inspeção manual (ex.:
planilha de classificação manual de casos discordantes).

Saída: results/consolidated.csv e results/consolidated.jsonl
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common.config import DATA_DIR, RESULTS_DIR  # noqa: E402
from common.schema import read_jsonl  # noqa: E402

DETECTION_FILES = [
    "detection_A_sast.jsonl",
    "detection_B_llm.jsonl",
    "detection_C_triage.jsonl",
]


def load_ground_truth() -> pd.DataFrame:
    rows = []
    for sub in ("repopairbench", "jsts_sample"):
        path = DATA_DIR / sub / "samples.jsonl"
        if path.exists():
            rows.extend(read_jsonl(path))
    if not rows:
        raise FileNotFoundError(
            "Nenhum CodeSample encontrado em data/*/samples.jsonl. Rode scripts/01_fetch_dataset.py."
        )
    df = pd.DataFrame(rows)
    return df[["sample_id", "language", "source_benchmark", "is_vulnerable", "cwe_id", "repo"]]


def load_detections() -> pd.DataFrame:
    rows = []
    for fname in DETECTION_FILES:
        path = RESULTS_DIR / fname
        if path.exists():
            rows.extend(read_jsonl(path))
        else:
            print(f"[aviso] {path} não existe ainda — rode o script correspondente antes.")
    if not rows:
        raise FileNotFoundError("Nenhum resultado de detecção encontrado em results/*.jsonl.")
    return pd.DataFrame(rows)


def main():
    gt = load_ground_truth()
    det = load_detections()

    merged = det.merge(gt, on="sample_id", how="left", suffixes=("_pred", "_true"))
    merged["correct"] = merged["predicted_vulnerable"] == merged["is_vulnerable"]

    missing_gt = merged["is_vulnerable"].isna().sum()
    if missing_gt:
        print(
            f"[aviso] {missing_gt} linhas de detecção não encontraram gabarito correspondente "
            "(sample_id ausente em data/*/samples.jsonl) — verifique se os IDs estão consistentes "
            "entre as etapas."
        )

    out_csv = RESULTS_DIR / "consolidated.csv"
    out_jsonl = RESULTS_DIR / "consolidated.jsonl"
    merged.to_csv(out_csv, index=False)
    merged.to_json(out_jsonl, orient="records", lines=True, force_ascii=False)

    print(f"[ok] {len(merged)} linhas consolidadas -> {out_csv} e {out_jsonl}")
    print("\nResumo por (approach, detector):")
    print(
        merged.groupby(["approach", "detector"])
        .agg(n=("sample_id", "count"), acuracia=("correct", "mean"))
        .round(3)
    )


if __name__ == "__main__":
    main()
